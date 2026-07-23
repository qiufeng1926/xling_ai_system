"""Open Library 书目核验/发现工具（search.json，遵守 UA / 限流 / 缓存）。

官方约定：https://openlibrary.org/developers/api
- 标识 User-Agent（含联系邮箱）可约 3 rps
- 优先 search.json，禁止对 N 本书各打 Work API
- 尽量缓存；禁止当 bulk 后端
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable
from urllib.parse import quote_plus, urlencode

import httpx

from utils.logger import get_logger

logger = get_logger("tools.openlibrary")

SEARCH_URL = "https://openlibrary.org/search.json"
MAX_QUERIES = 12
MAX_DISCOVER = 12
DEFAULT_FIELDS = "key,title,author_name,first_publish_year,edition_count"
CACHE_TTL_SEC = 7 * 24 * 3600
CACHE_MAX = 512

# 可注入：async (url, headers) -> dict JSON
HttpGetJson = Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]

_http_get_json: HttpGetJson | None = None


def set_http_get_json(fn: HttpGetJson | None) -> None:
    """测试用：注入假 HTTP；传 None 恢复默认。"""
    global _http_get_json
    _http_get_json = fn


def clear_cache() -> None:
    _cache.clear()


def _user_agent() -> str:
    try:
        from config import config as cfg

        return str(
            getattr(cfg, "openlibrary_user_agent", None)
            or "XlinkAgent-OpenLibrary (xlink-agent@localhost)"
        )
    except Exception:
        return "XlinkAgent-OpenLibrary (xlink-agent@localhost)"


def _rps() -> float:
    try:
        from config import config as cfg

        return float(getattr(cfg, "openlibrary_rps", None) or 2.5)
    except Exception:
        return 2.5


def _cache_ttl() -> int:
    try:
        from config import config as cfg

        return int(getattr(cfg, "openlibrary_cache_ttl_sec", None) or CACHE_TTL_SEC)
    except Exception:
        return CACHE_TTL_SEC


class _RateLimiter:
    """简单 token bucket：全局共享，默认约 2.5 rps。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tokens = 3.0
        self._last = time.monotonic()

    async def acquire(self) -> None:
        rate = max(0.5, min(3.0, _rps()))
        capacity = rate
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(capacity, self._tokens + elapsed * rate)
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
                self._last = time.monotonic()
            else:
                self._tokens -= 1.0


_limiter = _RateLimiter()
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_http_lock = asyncio.Lock()


def _cache_get(key: str) -> Any | None:
    item = _cache.get(key)
    if not item:
        return None
    ts, val = item
    if time.time() - ts > _cache_ttl():
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return val


def _cache_set(key: str, val: Any) -> None:
    _cache[key] = (time.time(), val)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


def _norm_title(s: str) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"[\s《》\"'“”‘’\[\]（）()·・.,，。:：;；!?！？\-—_/\\]+", "", t)
    return t


def _titles_close(a: str, b: str) -> bool:
    na, nb = _norm_title(a), _norm_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 2 and len(nb) >= 2 and (na in nb or nb in na):
        return True
    # 字符重叠（短书名宽松）
    if len(na) >= 4 and len(nb) >= 4:
        sa, sb = set(na), set(nb)
        inter = len(sa & sb)
        union = len(sa | sb) or 1
        if inter / union >= 0.72:
            return True
    return False


def _doc_to_hit(doc: dict[str, Any]) -> dict[str, Any]:
    # search 常返回 "OL27448W" 或 "/works/OL27448W"
    raw_key = str(doc.get("key") or "").strip()
    if raw_key.startswith("/"):
        ol_key = raw_key
    elif raw_key.endswith("W") or "/works" in raw_key:
        ol_key = f"/works/{raw_key}"
    elif raw_key:
        ol_key = f"/books/{raw_key}"
    else:
        ol_key = ""
    authors = doc.get("author_name") or []
    if isinstance(authors, str):
        authors = [authors]
    authors = [str(a).strip() for a in authors if str(a).strip()][:5]
    year = doc.get("first_publish_year")
    try:
        year_i = int(year) if year is not None else None
    except Exception:
        year_i = None
    title = str(doc.get("title") or "").strip()
    try:
        ed_count = int(doc.get("edition_count") or 0) or None
    except Exception:
        ed_count = None
    return {
        "title": title,
        "authors": authors,
        "first_publish_year": year_i,
        "ol_work_key": ol_key,
        "ol_url": f"https://openlibrary.org{ol_key}" if ol_key else "",
        "edition_count": ed_count,
    }


def _classify_docs(query: str, docs: list[dict[str, Any]]) -> dict[str, Any]:
    q = (query or "").strip()
    if not docs:
        return {
            "query": q,
            "status": "not_found",
            "note": "Open Library 未命中；中文书目可能覆盖不全，勿据此断言书不存在。",
            "hits": [],
        }
    hits = [_doc_to_hit(d) for d in docs[:5] if d]
    close = [h for h in hits if _titles_close(q, h.get("title") or "")]
    if len(close) == 1 or (close and _titles_close(q, close[0].get("title") or "")):
        best = close[0]
        # 若多个都接近，标 ambiguous
        if len(close) >= 3 or (
            len(close) >= 2 and not _titles_close(close[0].get("title") or "", close[1].get("title") or "")
        ):
            return {
                "query": q,
                "status": "ambiguous",
                "note": "多个接近结果，请选用或改查询。",
                "hits": close[:3],
            }
        return {"query": q, "status": "matched", "hit": best, "hits": [best]}
    if len(hits) == 1:
        return {"query": q, "status": "matched", "hit": hits[0], "hits": hits[:1]}
    if len(hits) >= 2:
        return {
            "query": q,
            "status": "ambiguous",
            "note": "未精确匹配书名，返回最相关候选。",
            "hits": hits[:3],
        }
    return {
        "query": q,
        "status": "not_found",
        "note": "Open Library 未命中；中文书目可能覆盖不全，勿据此断言书不存在。",
        "hits": [],
    }


async def _default_http_get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    await _limiter.acquire()
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _search_once(
    *,
    q: str = "",
    title: str = "",
    subject: str = "",
    limit: int = 5,
    http_calls: list[int] | None = None,
) -> dict[str, Any]:
    params: dict[str, str] = {"fields": DEFAULT_FIELDS, "limit": str(max(1, min(limit, 20)))}
    if q:
        params["q"] = q
    if title:
        params["title"] = title
    if subject:
        params["subject"] = subject
    cache_key = hashlib.sha1(
        ("&".join(f"{k}={params[k]}" for k in sorted(params))).encode("utf-8")
    ).hexdigest()
    cached = _cache_get(cache_key)
    if cached is not None:
        out = dict(cached)
        out["cached"] = True
        return out

    url = f"{SEARCH_URL}?{urlencode(params, quote_via=quote_plus)}"
    headers = {
        "User-Agent": _user_agent(),
        "Accept": "application/json",
    }
    getter = _http_get_json or _default_http_get_json
    async with _http_lock:
        data = await getter(url, headers)
        if http_calls is not None:
            http_calls[0] += 1
    docs = data.get("docs") if isinstance(data, dict) else None
    if not isinstance(docs, list):
        docs = []
    payload = {"docs": docs, "num_found": data.get("num_found") or data.get("numFound") or len(docs)}
    _cache_set(cache_key, payload)
    out = dict(payload)
    out["cached"] = False
    return out


def _format_hit_line(h: dict[str, Any]) -> str:
    title = h.get("title") or ""
    authors = "、".join(h.get("authors") or []) or "作者未知"
    year = h.get("first_publish_year")
    year_s = str(year) if year else "?"
    url = h.get("ol_url") or ""
    return f"《{title}》 — {authors} ({year_s}) {url}".strip()


def format_lookup_text(result: dict[str, Any]) -> str:
    """压成可写入 facts 的短文本。"""
    lines: list[str] = ["书目核验(Open Library):"]
    for item in result.get("items") or []:
        st = item.get("status")
        q = item.get("query") or ""
        if st == "matched":
            hit = item.get("hit") or (item.get("hits") or [None])[0] or {}
            lines.append(f"- [matched] {q} → {_format_hit_line(hit)}")
        elif st == "ambiguous":
            lines.append(f"- [ambiguous] {q}:")
            for h in (item.get("hits") or [])[:3]:
                lines.append(f"  · {_format_hit_line(h)}")
        else:
            note = item.get("note") or "未命中"
            lines.append(f"- [not_found] {q}（{note}）")
    discover = result.get("discover") or []
    if discover:
        topic = result.get("discover_query") or ""
        lines.append(f"书目发现(Open Library): {topic}")
        for i, h in enumerate(discover[:MAX_DISCOVER], 1):
            lines.append(f"{i}. {_format_hit_line(h)}")
    stats = result.get("stats") or {}
    if stats:
        lines.append(
            f"（http={stats.get('http_calls', 0)} cache_hits={stats.get('cache_hits', 0)} "
            f"matched={stats.get('matched', 0)} ambiguous={stats.get('ambiguous', 0)} "
            f"not_found={stats.get('not_found', 0)}）"
        )
    return "\n".join(lines)


async def openlibrary_lookup(
    *,
    queries: list[str] | None = None,
    q: str = "",
    subject: str = "",
    limit: int | None = None,
) -> dict[str, Any]:
    """批量核验 queries；可选 q/subject 发现补齐。"""
    qs: list[str] = []
    for raw in queries or []:
        s = str(raw or "").strip().strip("《》").strip()
        if s and s not in qs:
            qs.append(s)
        if len(qs) >= MAX_QUERIES:
            break

    discover_q = (q or "").strip()
    discover_subject = (subject or "").strip()
    disc_limit = max(1, min(limit or MAX_DISCOVER, MAX_DISCOVER))

    if not qs and not discover_q and not discover_subject:
        return {
            "ok": False,
            "error": "openlibrary_lookup 需要 queries[] 或 q/subject",
        }

    http_calls = [0]
    cache_hits = 0
    items: list[dict[str, Any]] = []

    for query in qs:
        try:
            raw = await _search_once(q=query, limit=5, http_calls=http_calls)
            if raw.get("cached"):
                cache_hits += 1
            classified = _classify_docs(query, list(raw.get("docs") or []))
            items.append(classified)
        except Exception as exc:
            logger.warning("openlibrary search failed q=%s err=%s", query[:80], exc)
            items.append(
                {
                    "query": query,
                    "status": "not_found",
                    "note": f"请求失败: {exc}",
                    "hits": [],
                    "error": str(exc),
                }
            )

    discover: list[dict[str, Any]] = []
    discover_label = ""
    if discover_q or discover_subject:
        discover_label = discover_subject or discover_q
        try:
            raw = await _search_once(
                q=discover_q if not discover_subject else "",
                subject=discover_subject,
                limit=disc_limit,
                http_calls=http_calls,
            )
            if raw.get("cached"):
                cache_hits += 1
            for d in list(raw.get("docs") or [])[:disc_limit]:
                discover.append(_doc_to_hit(d))
        except Exception as exc:
            logger.warning("openlibrary discover failed err=%s", exc)
            return {
                "ok": False,
                "error": f"发现检索失败: {exc}",
                "items": items,
            }

    matched = sum(1 for it in items if it.get("status") == "matched")
    ambiguous = sum(1 for it in items if it.get("status") == "ambiguous")
    not_found = sum(1 for it in items if it.get("status") == "not_found")
    stats = {
        "http_calls": http_calls[0],
        "cache_hits": cache_hits,
        "matched": matched,
        "ambiguous": ambiguous,
        "not_found": not_found,
        "discover_n": len(discover),
        "query_n": len(qs),
    }
    result: dict[str, Any] = {
        "ok": True,
        "items": items,
        "discover": discover,
        "discover_query": discover_label,
        "stats": stats,
    }
    result["text"] = format_lookup_text(result)
    return result


def normalize_openlibrary_args(args: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """校验/归一化入参。"""
    queries_raw = args.get("queries")
    if queries_raw is None and args.get("titles"):
        queries_raw = args.get("titles")
    if isinstance(queries_raw, str):
        # 逗号/换行分隔
        parts = re.split(r"[,，;\n]+", queries_raw)
        queries_raw = [p.strip() for p in parts if p.strip()]
    queries: list[str] = []
    if isinstance(queries_raw, list):
        for x in queries_raw:
            s = str(x or "").strip().strip("《》").strip()
            if s and s not in queries:
                queries.append(s)
            if len(queries) >= MAX_QUERIES:
                break
    q = str(args.get("q") or args.get("query") or "").strip()
    subject = str(args.get("subject") or "").strip()
    limit = args.get("limit")
    try:
        limit_i = int(limit) if limit is not None else None
    except Exception:
        limit_i = None
    if limit_i is not None:
        limit_i = max(1, min(limit_i, MAX_DISCOVER))
    if not queries and not q and not subject:
        return None, "openlibrary_lookup 需要 queries（书名列表）或 q/subject（发现）"
    out: dict[str, Any] = {}
    if queries:
        out["queries"] = queries
    if q:
        out["q"] = q
    if subject:
        out["subject"] = subject
    if limit_i is not None:
        out["limit"] = limit_i
    return out, None
