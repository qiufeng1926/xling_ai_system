"""高层联网工具：web_search / web_fetch（多源回退，避免依赖单一被反爬的引擎）。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup

from browser.net_guard import assert_public_url
from utils.logger import get_logger

logger = get_logger("tools.web")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _html_to_text(html: str, limit: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
    return text[:limit]


def _clean_href(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    # DuckDuckGo redirect: /l/?uddg=<url>
    if "uddg=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            if qs.get("uddg"):
                return unquote(qs["uddg"][0])
        except Exception:
            pass
    # 搜狗跳转: /link?url= 或 link.sogou.com
    if "sogou.com" in href or href.startswith("/link"):
        try:
            full = href
            if href.startswith("/"):
                full = "https://www.sogou.com" + href
            qs = parse_qs(urlparse(full).query)
            for key in ("url", "ou", "src", "u"):
                if qs.get(key):
                    cand = unquote(qs[key][0])
                    if cand.startswith("http"):
                        return cand
        except Exception:
            pass
    if href.startswith("//"):
        href = "https:" + href
    return href


async def web_fetch(url: str, *, max_chars: int = 18000) -> dict[str, Any]:
    """拉取公开网页可读正文。HTTP 错误 / 空壳拦截页视为失败。"""
    try:
        url = assert_public_url(url)
    except Exception as exc:
        return {"error": str(exc), "url": url, "ok": False}
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = await client.get(url)
        text = resp.text or ""
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" in ctype or "<html" in text[:500].lower():
            cleaned = _html_to_text(text, max_chars)
        else:
            cleaned = text[:max_chars]
        final_url = str(resp.url)
        if resp.status_code >= 400:
            return {
                "ok": False,
                "error": f"HTTP {resp.status_code}，无有效正文",
                "status": resp.status_code,
                "url": final_url,
                "text": cleaned[:300],
            }
        low = (cleaned or "")[:800].lower()
        blocked_markers = (
            "unhuman",
            "captcha",
            "安全验证",
            "人机验证",
            "让每一次点击都充满意义",  # 知乎空壳落地页
            "access denied",
            "403 forbidden",
        )
        if any(m in low or m in (cleaned or "")[:800] for m in blocked_markers):
            return {
                "ok": False,
                "error": "页面被拦截或无有效正文",
                "status": resp.status_code,
                "url": final_url,
                "text": cleaned[:300],
            }
        if len(re.sub(r"\s+", "", cleaned or "")) < 80:
            return {
                "ok": False,
                "error": "正文过短，无法使用",
                "status": resp.status_code,
                "url": final_url,
                "text": cleaned[:300],
            }
        return {
            "ok": True,
            "status": resp.status_code,
            "url": final_url,
            "text": cleaned,
        }
    except Exception as exc:
        logger.warning("web_fetch failed %s: %s", url, exc)
        return {"error": f"web_fetch 失败: {exc}", "url": url, "ok": False}


def _parse_duckduckgo(html: str, max_results: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for a in soup.select("a.result__a"):
        title = a.get_text(" ", strip=True)
        href = _clean_href(a.get("href") or "")
        snippet = ""
        parent = a.find_parent(class_="result") or a.find_parent("div")
        if parent:
            sn = parent.select_one(".result__snippet") or parent.select_one("a.result__snippet")
            if sn:
                snippet = sn.get_text(" ", strip=True)
        if title and href.startswith("http"):
            out.append({"title": title, "url": href, "snippet": snippet[:300]})
        if len(out) >= max_results:
            break
    return out


def _parse_sogou(html: str, max_results: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for block in soup.select(".vrwrap, .results .rb, .result"):
        a = block.select_one("h3 a") or block.select_one("a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = _clean_href(a.get("href") or "")
        if href.startswith("?"):
            href = "https://www.sogou.com/web" + href
        elif href.startswith("/"):
            href = "https://www.sogou.com" + href
        sn = block.select_one(".space-txt") or block.select_one(".str-text") or block.select_one("p")
        snippet = sn.get_text(" ", strip=True) if sn else ""
        if title and len(title) >= 4:
            out.append({"title": title, "url": href, "snippet": snippet[:300]})
        if len(out) >= max_results:
            break
    return out


def _parse_bing(html: str, max_results: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = _clean_href(a.get("href") or "")
        sn = li.select_one(".b_caption p") or li.select_one("p")
        snippet = sn.get_text(" ", strip=True) if sn else ""
        if title:
            out.append({"title": title, "url": href, "snippet": snippet[:300]})
        if len(out) >= max_results:
            break
    if not out:
        for a in soup.select("h2 a")[:max_results]:
            title = a.get_text(" ", strip=True)
            href = _clean_href(a.get("href") or "")
            if title:
                out.append({"title": title, "url": href, "snippet": ""})
    return out


async def _search_duckduckgo(client: httpx.AsyncClient, q: str, max_results: int) -> list[dict[str, str]]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
    # GET / POST 都试一遍（不同网络对反爬表现不一）
    for method in ("GET", "POST"):
        try:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(
                    url,
                    data={"q": q},
                    headers={**_HEADERS, "Referer": "https://html.duckduckgo.com/"},
                )
            hits = _parse_duckduckgo(resp.text or "", max_results)
            if hits:
                return hits
        except Exception as exc:
            logger.info("duckduckgo %s failed: %s", method, exc)
    return []


async def _search_sogou(client: httpx.AsyncClient, q: str, max_results: int) -> list[dict[str, str]]:
    url = f"https://www.sogou.com/web?query={quote_plus(q)}"
    resp = await client.get(url)
    return _parse_sogou(resp.text or "", max_results)


async def _search_bing(client: httpx.AsyncClient, q: str, max_results: int) -> list[dict[str, str]]:
    url = f"https://www.bing.com/search?q={quote_plus(q)}&setlang=zh-Hans"
    resp = await client.get(url)
    return _parse_bing(resp.text or "", max_results)


async def _search_via_browser(q: str, max_results: int) -> list[dict[str, str]]:
    """HTTP 解析全失败时，用已有 Playwright 打开 DuckDuckGo 再抽链接。"""
    try:
        from browser.pool import browser_pool
    except Exception as exc:
        logger.warning("browser search unavailable: %s", exc)
        return []
    # 用固定匿名用户位会冲突；这里用 0 临时任务 id —— browser_pool 按 user_id 隔离。
    # 调用方应传入真实 user_id；见 web_search(user_id=...).
    return []


async def web_search(
    query: str,
    *,
    max_results: int = 5,
    user_id: int | None = None,
) -> dict[str, Any]:
    """联网搜索：DuckDuckGo → 搜狗 → Bing →（可选）浏览器打开搜索页。"""
    q = (query or "").strip()
    if not q:
        return {"error": "query 不能为空", "ok": False}

    backends = (
        ("duckduckgo", _search_duckduckgo),
        ("sogou", _search_sogou),
        ("bing", _search_bing),
    )
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=_HEADERS) as client:
        for name, fn in backends:
            try:
                results = await fn(client, q, max_results)
                if results:
                    lines = [
                        f"{i}. {r['title']}"
                        + (f" — {r['snippet']}" if r.get("snippet") else "")
                        + (f"\n   链接: {r['url']}" if r.get("url") else "")
                        for i, r in enumerate(results, 1)
                    ]
                    text = "\n".join(lines)
                    logger.info("web_search ok via=%s query=%s hits=%s", name, q[:40], len(results))
                    return {
                        "ok": True,
                        "query": q,
                        "source": name,
                        "results": results,
                        "text": text,
                    }
                errors.append(f"{name}:0hits")
                logger.info("web_search empty via=%s query=%s", name, q[:40])
            except Exception as exc:
                errors.append(f"{name}:{exc}")
                logger.warning("web_search backend %s failed: %s", name, exc)

    # 最后手段：真浏览器打开搜索页再解析 HTML（绕开部分反爬）
    if user_id is not None:
        try:
            from browser.pool import browser_pool

            for search_url, parser in (
                (f"https://html.duckduckgo.com/html/?q={quote_plus(q)}", _parse_duckduckgo),
                (f"https://www.bing.com/search?q={quote_plus(q)}", _parse_bing),
            ):
                nav = await browser_pool.navigate(user_id, search_url)
                if nav.get("error"):
                    errors.append(f"browser-nav:{nav.get('error')}")
                    continue
                page = await browser_pool.page_html(user_id)
                html = str(page.get("html") or "")
                results = parser(html, max_results) if html else []
                if results:
                    lines = [
                        f"{i}. {r['title']}"
                        + (f" — {r['snippet']}" if r.get("snippet") else "")
                        + (f"\n   链接: {r['url']}" if r.get("url") else "")
                        for i, r in enumerate(results, 1)
                    ]
                    logger.info(
                        "web_search ok via=browser(%s) query=%s hits=%s",
                        search_url[:40],
                        q[:40],
                        len(results),
                    )
                    return {
                        "ok": True,
                        "query": q,
                        "source": "browser",
                        "results": results,
                        "text": "\n".join(lines),
                    }
                errors.append("browser:0hits")
        except Exception as exc:
            errors.append(f"browser:{exc}")
            logger.warning("web_search browser fallback failed: %s", exc)

    return {
        "ok": False,
        "error": "联网搜索未拿到结果（引擎可能被反爬或网络不可达）",
        "query": q,
        "detail": "; ".join(errors)[:500],
        "hint": "请确认服务器可访问外网；或改用 browser_navigate 打开具体资讯站后再 browser_extract",
    }


# 工具入参契约（提示词 + 运行时校验）
TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "web_search": {
        "desc": "联网搜索，返回标题+摘要+链接。不知道网址时优先用。",
        "input": {"query": "搜索词"},
        "example": {"query": "关键词"},
    },
    "web_fetch": {
        "desc": "抓取公开网页正文（不点按钮）。已知 URL 时用。",
        "input": {"url": "https://..."},
        "example": {"url": "https://example.com"},
    },
    "browser_navigate": {
        "desc": "打开网页，需要可视化浏览或点击交互时用。",
        "input": {"url": "https://..."},
        "example": {"url": "https://example.com"},
    },
    "browser_extract": {
        "desc": "抽取当前页文字。selector 可省略；禁止超长 CSS。",
        "input": {"selector": "可选，省略则取 body"},
        "example": {},
    },
    "browser_click": {
        "desc": "点击页面元素。",
        "input": {"selector": "CSS 选择器"},
        "example": {"selector": "button.search"},
    },
    "browser_type": {
        "desc": "在输入框输入文字。",
        "input": {"selector": "CSS", "text": "内容"},
        "example": {"selector": "input[name=q]", "text": "查询词"},
    },
    "http_request": {
        "desc": "底层 GET；一般优先 web_fetch。",
        "input": {"method": "GET", "url": "https://..."},
        "example": {"method": "GET", "url": "https://example.com"},
    },
    "kb_search": {
        "desc": "搜用户知识库。",
        "input": {"query": "..."},
        "example": {"query": "关键词"},
    },
    "file_write_html": {
        "desc": "生成 HTML 文件到工作区。",
        "input": {"filename": "x.html", "content": "HTML 正文"},
        "example": {"filename": "report.html", "content": "<html>...</html>"},
    },
    "file_write_docx": {
        "desc": "生成 Word。必须把完整正文放进 content，禁止空文件。",
        "input": {"filename": "x.docx", "title": "标题", "content": "完整正文（必填，可多段）"},
        "example": {
            "filename": "分析报告.docx",
            "title": "分析报告",
            "content": "一、概述\\n……\\n二、要点\\n1. ……",
        },
    },
    "file_write_markdown": {
        "desc": "生成 Markdown。content 必填且须为完整正文。",
        "input": {"filename": "x.md", "content": "完整 Markdown 正文"},
        "example": {"filename": "报告.md", "content": "# 标题\\n\\n正文……"},
    },
    "run_code": {
        "desc": "在服务端沙箱运行短 Python（算数/清洗/校验）。禁止网络与危险模块。",
        "input": {"code": "print(1+1)"},
        "example": {"code": "print(sum(range(1, 11)))"},
    },
    "memory_recall": {
        "desc": "召回本会话已压缩的历史摘要原文。用户追问旧轮细节时用；优先 summary_id，其次 query。",
        "input": {"summary_id": "可选，摘要ID或前8位", "query": "可选，关键词"},
        "example": {"summary_id": "a1b2c3d4"},
    },
}


def render_tool_contracts(tool_names: list[str]) -> str:
    lines = ["## 可用工具契约（每次只选一个）"]
    for name in tool_names:
        meta = TOOL_CONTRACTS.get(name)
        if not meta:
            lines.append(f"- {name}")
            continue
        lines.append(f"- {name}: {meta['desc']}")
        lines.append(f"  入参: {json.dumps(meta['input'], ensure_ascii=False)}")
        ex = {"thought": "...", "action": name, "action_input": meta.get("example") or {}}
        lines.append(f"  例: {json.dumps(ex, ensure_ascii=False)}")
    return "\n".join(lines)


def validate_and_normalize_args(tool: str, args: Any) -> tuple[dict[str, Any] | None, str | None]:
    """返回 (规范化 args, error)。"""
    if args is None:
        args = {}
    if isinstance(args, str):
        if tool == "browser_type":
            return {"selector": "input[name=q], input[type=search], #kw", "text": args}, None
        if tool == "web_search":
            return {"query": args}, None
        if tool in {"web_fetch", "browser_navigate", "http_request"}:
            return {"url": args, "method": "GET"}, None
        try:
            args = json.loads(args)
        except Exception:
            return None, f"{tool} 的 action_input 必须是对象，不能是纯字符串：{args[:80]}"

    if not isinstance(args, dict):
        return None, f"{tool} 的 action_input 必须是 JSON 对象"

    if tool == "web_search":
        q = str(args.get("query") or args.get("q") or "").strip()
        if not q:
            return None, "web_search 需要 query"
        return {"query": q}, None

    if tool == "web_fetch":
        url = str(args.get("url") or "").strip()
        if not url:
            return None, "web_fetch 需要 url"
        return {"url": url}, None

    if tool == "browser_navigate":
        url = str(args.get("url") or "").strip()
        if not url.startswith("http"):
            return None, "browser_navigate 需要完整 http(s) url"
        return {"url": url}, None

    if tool == "browser_extract":
        sel = args.get("selector")
        if sel is not None:
            sel = str(sel).strip()
            if len(sel) > 120 or sel.count(">") > 6 or sel.count("div") > 8:
                return {"selector": None}, None
            if not sel:
                sel = None
        return {"selector": sel}, None

    if tool == "browser_type":
        text = str(args.get("text") or args.get("value") or args.get("input") or "").strip()
        selector = str(args.get("selector") or "input[name=q], input[type=search], #kw").strip()
        if not text:
            return None, "browser_type 需要 text"
        return {"selector": selector, "text": text}, None

    if tool == "browser_click":
        selector = str(args.get("selector") or "").strip()
        if not selector or len(selector) > 120:
            return None, "browser_click 需要合理长度的 selector"
        return {"selector": selector}, None

    if tool == "http_request":
        url = str(args.get("url") or "").strip()
        method = str(args.get("method") or "GET").upper()
        if not url:
            return None, "http_request 需要 url"
        return {"url": url, "method": method}, None

    if tool == "kb_search":
        q = str(args.get("query") or "").strip()
        if not q:
            return None, "kb_search 需要 query"
        return {"query": q}, None

    if tool == "run_code":
        code = str(args.get("code") or args.get("source") or args.get("python") or "").strip()
        if not code:
            return None, "run_code 需要 code（短 Python 源码）"
        timeout = args.get("timeout")
        try:
            timeout_i = int(timeout) if timeout is not None else 8
        except Exception:
            timeout_i = 8
        return {"code": code, "timeout": max(1, min(timeout_i, 30))}, None

    if tool == "memory_recall":
        sid = str(args.get("summary_id") or args.get("id") or "").strip()
        q = str(args.get("query") or args.get("q") or args.get("keyword") or "").strip()
        if not sid and not q:
            return None, "memory_recall 需要 summary_id 或 query"
        out: dict[str, Any] = {}
        if sid:
            out["summary_id"] = sid
        if q:
            out["query"] = q
        return out, None

    if tool.startswith("file_write_"):
        return _normalize_file_write_args(tool, args)

    return args, None


def _normalize_file_write_args(tool: str, args: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """统一写文件入参：兼容 content/text/body 等字段，拒绝空正文。"""
    out = dict(args)
    content = _pick_write_content(out)
    if tool == "file_write_xlsx":
        rows = out.get("rows")
        if (not rows or rows == []) and content:
            out["rows"] = [[line] for line in content.splitlines() if line.strip()] or [[content]]
        if not out.get("rows"):
            return None, "file_write_xlsx 需要 rows 或 content，不能写空表"
        return out, None
    if tool == "file_write_pptx":
        slides = out.get("slides")
        if not slides and content:
            out["slides"] = [{"title": out.get("title") or "演示", "body": content}]
        if not out.get("slides") and not content:
            return None, "file_write_pptx 需要 slides 或 content，不能写空幻灯片"
        if content and not out.get("content"):
            out["content"] = content
        return out, None

    if len(content.strip()) < 8:
        return None, (
            f"{tool} 的 content 为空或过短。请把完整分析/总结正文放进 action_input.content "
            "（也可用 text/body/markdown），不要只给文件名。"
        )
    out["content"] = content
    if not out.get("filename"):
        suffix = {
            "file_write_markdown": ".md",
            "file_write_html": ".html",
            "file_write_docx": ".docx",
            "file_write_pdf": ".pdf",
        }.get(tool, ".txt")
        out["filename"] = f"document{suffix}"
    if tool == "file_write_docx" and not out.get("title"):
        # 用正文首行作标题兜底
        first = content.strip().splitlines()[0].strip("# ").strip()
        out["title"] = first[:40] if first else "文档"
    return out, None


def _pick_write_content(args: dict[str, Any]) -> str:
    for k in ("content", "text", "body", "markdown", "html", "article", "summary", "report"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            return "\n".join(str(x) for x in v if str(x).strip())
    paras = args.get("paragraphs") or args.get("sections")
    if isinstance(paras, list) and paras:
        parts: list[str] = []
        for p in paras:
            if isinstance(p, dict):
                title = str(p.get("title") or p.get("heading") or "").strip()
                body = str(p.get("body") or p.get("content") or p.get("text") or "").strip()
                if title:
                    parts.append(title)
                if body:
                    parts.append(body)
            else:
                s = str(p).strip()
                if s:
                    parts.append(s)
        if parts:
            return "\n".join(parts)
    return ""
