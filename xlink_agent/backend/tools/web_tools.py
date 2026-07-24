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


# 搜索引擎中间页 / 跳转页：不可当内容站抓取
_SEARCH_SHELL_HOST_MARKERS = (
    "sogou.com/web",
    "sogou.com/link",
    "www.sogou.com/",
    "sogou.com/?",
    "bing.com/search",
    "bing.com/ck/",
    "duckduckgo.com",
    "google.com/search",
    "google.com/url?",
    "baidu.com/s?",
    "baidu.com/link?",
)


def is_content_fetch_url(url: str) -> bool:
    """是否适合 web_fetch 的内容站（排除搜索引擎结果页与加密跳转）。"""
    u = (url or "").strip()
    if not u.startswith("http"):
        return False
    low = u.lower()
    if any(x in low for x in _SEARCH_SHELL_HOST_MARKERS):
        return False
    # 搜狗任意站内页（跳转失败常落到首页备案页）
    if "sogou.com" in low:
        return False
    return True


def is_search_engine_shell_body(text: str) -> bool:
    """搜狗/备案页等：看起来很长，实则全是页脚垃圾。"""
    t = (text or "").strip()
    if not t:
        return False
    markers = (
        "京公网安备",
        "京ICP备",
        "京ICP证",
        "京网文",
        "网药械信息备字",
        "查询限制在100个汉字",
        "搜狗搜索引擎",
        "上网从搜狗开始",
        "网上有害信息举报专区",
        "药品医疗器械网络信息服务备案",
        "让每一次点击都充满意义",
    )
    hits = sum(1 for k in markers if k in t)
    if hits >= 3:
        return True
    if hits >= 2 and ("搜狗" in t or "Sogou.com" in t or "Sogou.com" in t):
        return True
    # 备案词 + 几乎无书名/叙述句
    if hits >= 2 and "《" not in t and len(re.findall(r"[。！？]", t)) < 2:
        return True
    return False


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
    # 搜狗跳转: /link?url= 或 link.sogou.com（多数为加密串，解不出真实 URL）
    if "sogou.com" in href or href.startswith("/link"):
        try:
            full = href
            if href.startswith("/"):
                full = "https://www.sogou.com" + href
            qs = parse_qs(urlparse(full).query)
            for key in ("url", "ou", "src", "u"):
                if qs.get(key):
                    cand = unquote(qs[key][0])
                    if cand.startswith("http") and is_content_fetch_url(cand):
                        return cand
        except Exception:
            pass
        # 解不出真实内容站 → 返回空，避免把 /link?url=加密串当可抓链接
        return ""
    if href.startswith("//"):
        href = "https:" + href
    return href


def _sanitize_search_hits(results: list[dict[str, str]]) -> list[dict[str, str]]:
    """去掉空标题；不可抓的搜索跳转 URL 清空（保留有摘要的命中供合成）。"""
    out: list[dict[str, str]] = []
    for r in results or []:
        title = str(r.get("title") or "").strip()
        if len(title) < 4:
            continue
        url = _clean_href(str(r.get("url") or ""))
        if url and not is_content_fetch_url(url):
            url = ""
        snippet = str(r.get("snippet") or "").strip()
        # 无链接且摘要极短的纯 SERP 标题，对交付帮助很小
        if not url and len(snippet) < 12 and "《" not in title and "《" not in snippet:
            # 仍保留带「书/推荐/历史」等线索的标题
            if not any(k in title for k in ("书", "推荐", "经典", "必读", "榜", "书单")):
                continue
        out.append({"title": title, "url": url, "snippet": snippet[:300]})
    return out


async def web_fetch(url: str, *, max_chars: int = 18000) -> dict[str, Any]:
    """拉取公开网页可读正文。HTTP 错误 / 空壳拦截页视为失败。"""
    try:
        url = assert_public_url(url)
    except Exception as exc:
        return {"error": str(exc), "url": url, "ok": False}
    if not is_content_fetch_url(url):
        return {
            "ok": False,
            "error": "该链接为搜索引擎跳转/结果页，请换知乎/百科/豆瓣等内容站",
            "url": url,
            "status": 0,
            "text": "",
        }
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
        if not is_content_fetch_url(final_url):
            return {
                "ok": False,
                "error": "跳转后落到搜索引擎壳页，无有效正文",
                "status": resp.status_code,
                "url": final_url,
                "text": cleaned[:300],
            }
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
        if is_search_engine_shell_body(cleaned):
            return {
                "ok": False,
                "error": "页面无有效正文（搜索引擎壳页/备案页脚）",
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
        if title and (href.startswith("http") or len(snippet) >= 12):
            out.append({"title": title, "url": href if href.startswith("http") else "", "snippet": snippet[:300]})
        if len(out) >= max_results * 2:
            break
    return _sanitize_search_hits(out)[:max_results]


def _parse_sogou(html: str, max_results: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for block in soup.select(".vrwrap, .results .rb, .result"):
        a = block.select_one("h3 a") or block.select_one("a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        raw_href = (a.get("href") or "").strip()
        href = _clean_href(raw_href)
        # 禁止把 /link 加密跳转或 /web SERP 再拼回搜狗域名
        if not href and raw_href.startswith("/") and not raw_href.startswith("/link"):
            cand = "https://www.sogou.com" + raw_href
            href = cand if is_content_fetch_url(cand) else ""
        sn = block.select_one(".space-txt") or block.select_one(".str-text") or block.select_one("p")
        snippet = sn.get_text(" ", strip=True) if sn else ""
        if title and len(title) >= 4:
            out.append({"title": title, "url": href, "snippet": snippet[:300]})
        if len(out) >= max_results * 2:
            break
    return _sanitize_search_hits(out)[:max_results]


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
        if len(out) >= max_results * 2:
            break
    if not out:
        for a in soup.select("h2 a")[: max_results * 2]:
            title = a.get_text(" ", strip=True)
            href = _clean_href(a.get("href") or "")
            if title:
                out.append({"title": title, "url": href, "snippet": ""})
    return _sanitize_search_hits(out)[:max_results]


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
    """联网搜索：DuckDuckGo → Bing → 搜狗 →（可选）浏览器打开搜索页。"""
    q = (query or "").strip()
    if not q:
        return {"error": "query 不能为空", "ok": False}

    backends = (
        ("duckduckgo", _search_duckduckgo),
        ("bing", _search_bing),
        ("sogou", _search_sogou),
    )
    errors: list[str] = []
    weak_backup: list[dict[str, str]] | None = None
    weak_source = ""

    def _pack(source: str, results: list[dict[str, str]]) -> dict[str, Any]:
        lines = [
            f"{i}. {r['title']}"
            + (f" — {r['snippet']}" if r.get("snippet") else "")
            + (f"\n   链接: {r['url']}" if r.get("url") else "")
            for i, r in enumerate(results, 1)
        ]
        text = "\n".join(lines)
        logger.info("web_search ok via=%s query=%s hits=%s", source, q[:40], len(results))
        return {
            "ok": True,
            "query": q,
            "source": source,
            "results": results,
            "text": text,
        }

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=_HEADERS) as client:
        for name, fn in backends:
            try:
                results = _sanitize_search_hits(await fn(client, q, max_results))
                if not results:
                    errors.append(f"{name}:0hits")
                    logger.info("web_search empty via=%s query=%s", name, q[:40])
                    continue
                usable_urls = sum(1 for r in results if r.get("url"))
                if usable_urls == 0:
                    # 只有标题/摘要、无可抓链接 → 记弱备份，继续试其它引擎
                    if weak_backup is None:
                        weak_backup = results
                        weak_source = name
                    errors.append(f"{name}:no_fetchable_url")
                    logger.info("web_search %s hits lack fetchable urls, try next", name)
                    continue
                return _pack(name, results)
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
                results = _sanitize_search_hits(parser(html, max_results) if html else [])
                if results and any(r.get("url") for r in results):
                    return _pack("browser", results)
                if results and weak_backup is None:
                    weak_backup = results
                    weak_source = "browser"
                errors.append("browser:0hits")
        except Exception as exc:
            errors.append(f"browser:{exc}")
            logger.warning("web_search browser fallback failed: %s", exc)

    if weak_backup:
        return _pack(weak_source or "weak", weak_backup)

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
        "desc": "召回本会话已压缩的历史摘要。优先 summary_id；query 支持关键词，不足时自动向量模糊召回。",
        "input": {
            "summary_id": "可选，摘要ID或前8位",
            "query": "可选，关键词或自然语言追问",
            "mode": "可选 auto|keyword|vector，默认 auto",
        },
        "example": {"query": "上次那个销售周报结论", "mode": "auto"},
    },
    "call_influencer_match": {
        "desc": (
            "单向调用「商单筛库」专用智能体：传入商单 brief，由其在达人库内 ReAct 筛选并 grounded 总结。"
            "不可搜索网页；通用智能体不要自己编造达人。"
        ),
        "input": {"brief": "商单/brief 全文"},
        "example": {"brief": "抖音探店，粉丝5万以上，需要联系方式，至少推荐5位"},
    },
    "openlibrary_lookup": {
        "desc": (
            "Open Library 书目核验/发现：queries 批量核验书名；"
            "q/subject 发现补齐。未命中不代表书不存在。勿替代通用 web_search。"
        ),
        "input": {
            "queries": ["书名或 书名 作者"],
            "q": "可选主题发现",
            "subject": "可选英文主题",
            "limit": "可选≤12",
        },
        "example": {"queries": ["史记", "人类简史"], "q": "world history", "limit": 8},
    },
    "influencer_list_tags": {
        "desc": "【仅商单筛库专用运行时】列出达人库标签。",
        "input": {"query": "可选关键词"},
        "example": {"query": "美妆"},
    },
    "influencer_list_agencies": {
        "desc": "【仅商单筛库专用运行时】列出 MCN/机构。",
        "input": {"query": "可选机构名关键词", "limit": "可选"},
        "example": {"query": "美ONE"},
    },
    "influencer_search": {
        "desc": "【仅商单筛库专用运行时】按条件筛达人库。platform 只能是单个枚举值；tag_ids 必须来自 list_tags，禁止编造。",
        "input": {
            "platform": "可选，仅 douyin 或 xiaohongshu 其一；省略=不限。禁止写成 douyin|xiaohongshu",
            "keyword": "可选短主题词（会匹配昵称/资料/标签名）",
            "follower_min": "可选整数",
            "follower_max": "可选整数",
            "tag_ids": "可选，真实标签 id 数组（先 list_tags）",
            "page_size": 20,
        },
        "example": {"platform": "douyin", "follower_min": 50000, "keyword": "探店", "page_size": 30},
    },
    "influencer_get": {
        "desc": "【仅商单筛库专用运行时】按 ID 拉达人详情。",
        "input": {"influencer_id": 1},
        "example": {"influencer_id": 12},
    },
    "influencer_rank": {
        "desc": "【仅商单筛库专用运行时】对 candidates 打分排序。",
        "input": {"candidates": [], "preferred_tags": ["探店"], "limit": 10},
        "example": {"candidates": [], "preferred_tags": ["美妆"], "limit": 8},
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
        if tool == "openlibrary_lookup":
            from tools.openlibrary import normalize_openlibrary_args

            return normalize_openlibrary_args({"queries": [args], "q": args})
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
        mode = str(args.get("mode") or "auto").strip().lower() or "auto"
        if mode not in {"auto", "keyword", "vector"}:
            mode = "auto"
        if not sid and not q:
            return None, "memory_recall 需要 summary_id 或 query"
        out: dict[str, Any] = {"mode": mode}
        if sid:
            out["summary_id"] = sid
        if q:
            out["query"] = q
        return out, None

    if tool == "openlibrary_lookup":
        from tools.openlibrary import normalize_openlibrary_args

        return normalize_openlibrary_args(args)

    if tool == "call_influencer_match":
        brief = str(args.get("brief") or args.get("query") or args.get("message") or "").strip()
        if not brief:
            return None, "call_influencer_match 需要 brief"
        return {"brief": brief}, None

    if tool == "influencer_list_tags":
        return {"query": str(args.get("query") or args.get("keyword") or "").strip()}, None

    if tool == "influencer_list_agencies":
        out_a: dict[str, Any] = {
            "query": str(args.get("query") or args.get("keyword") or "").strip(),
        }
        if args.get("limit") is not None:
            try:
                out_a["limit"] = max(1, min(int(args.get("limit")), 100))
            except Exception:
                out_a["limit"] = 50
        return out_a, None

    if tool == "influencer_search":
        out_s: dict[str, Any] = {}
        # platform：拒绝契约抄写与多值，归一到单枚举或省略
        if args.get("platform") is not None and str(args.get("platform")).strip():
            from tools.influencer_tools import _normalize_platform

            plat, _warn = _normalize_platform(args.get("platform"))
            if plat:
                out_s["platform"] = plat
        for key in ("keyword", "q", "source", "profile_keyword"):
            if args.get(key) is not None and str(args.get(key)).strip():
                out_s[key] = str(args.get(key)).strip()
        for key in ("follower_min", "follower_max", "agency_id", "page", "page_size", "limit"):
            if args.get(key) is not None and str(args.get(key)).strip() != "":
                try:
                    out_s[key] = int(args.get(key))
                except Exception:
                    return None, f"influencer_search 的 {key} 必须是整数"
        tag_ids = args.get("tag_ids") or args.get("required_tag_ids")
        if isinstance(tag_ids, list):
            from tools.influencer_tools import _clean_tag_ids

            cleaned, _ = _clean_tag_ids(tag_ids)
            if cleaned:
                out_s["tag_ids"] = cleaned
        elif tag_ids is not None and str(tag_ids).strip().isdigit():
            from tools.influencer_tools import _clean_tag_ids

            cleaned, _ = _clean_tag_ids([tag_ids])
            if cleaned:
                out_s["tag_ids"] = cleaned
        return out_s, None

    if tool == "influencer_get":
        iid = args.get("influencer_id") or args.get("id")
        try:
            return {"influencer_id": int(iid)}, None
        except Exception:
            return None, "influencer_get 需要整数 influencer_id"

    if tool == "influencer_rank":
        cands = args.get("candidates") or args.get("items")
        if not isinstance(cands, list) or not cands:
            return None, "influencer_rank 需要非空 candidates 数组"
        out_r: dict[str, Any] = {"candidates": cands}
        for key in ("preferred_tags", "preferred_tag_names", "required_tags", "required_tag_names"):
            if isinstance(args.get(key), list):
                out_r[key] = [str(x).strip() for x in args[key] if str(x).strip()]
        if args.get("keyword"):
            out_r["keyword"] = str(args.get("keyword")).strip()
        out_r["must_have_contact"] = bool(args.get("must_have_contact"))
        try:
            out_r["limit"] = max(5, min(int(args.get("limit") or 10), 50))
        except Exception:
            out_r["limit"] = 10
        return out_r, None

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
