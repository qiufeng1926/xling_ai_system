"""面向终端用户的答复清洗与合成：绝不把 JSON / 内部步骤甩给用户。"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from agent.model_router import extract_json_block

if TYPE_CHECKING:
    from agent.context import TaskContext

_CODE_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)```", re.M)
_JSON_LINE_RE = re.compile(r"^\s*\{[\s\S]*\"action\"\s*:")
_INTERNAL_MARKERS = (
    "（内部步骤）",
    "(内部步骤)",
    '"action"',
    "'action'",
    "action_input",
    "file_write_",
    "Action:",
    "Observation:",
    "Thought:",
    "根据已收集到的信息",
    "HTTP 200:",
    "HTTP 30",
    "抽取正文要点:",
    "请输出核实后的",
    "请输出最终高质量",
    "线索，不是最终答案",
    "待核实草稿",
    "检索材料：",
    "Observation/工作记忆",
)

_META_LEAK_RE = re.compile(
    r"(请输出核实后的准确最终答案[。.]?|"
    r"请输出核实后的答案[。.]?|"
    r"请输出最终高质量中文答案[。.]?|"
    r"线索，不是最终答案本身[：:]?|"
    r"根据联网搜索，找到以下相关网页标题[^\n]*\n?|"
    r"用户目标：|"
    r"检索材料：|"
    r"待核实草稿：|"
    r"模型 Thought（仅供参考）[：:]?|"
    r"模型草稿（可参考[^\n]*）[：:]?)",
    re.M,
)

_NAV_NOISE = re.compile(
    r"^(首页|国内|国际|军事|财经|娱乐|体育|互联网|科技|游戏|女人|汽车|房产|"
    r"网页|新闻|贴吧|知道|音乐|图片|视频|地图|文库|帮助|新闻全文|新闻标题|"
    r"点击刷新|热点要闻|百度新闻).*$"
)


def _unwrap_protocol_json(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return text

    for m in _CODE_FENCE_RE.finditer(text):
        inner = m.group(1).strip()
        data = extract_json_block(inner)
        if isinstance(data, dict) and data.get("content"):
            return str(data["content"]).strip()
        if isinstance(data, dict) and data.get("action_input") and str(data.get("action") or "") in {
            "finish",
            "final",
            "answer",
            "done",
        }:
            ai = data["action_input"]
            return str(ai.get("content") if isinstance(ai, dict) else ai).strip()

    data = extract_json_block(text)
    if isinstance(data, dict):
        if data.get("action") in {"final", "finish", "answer", "done"} and data.get("content"):
            return str(data["content"]).strip()
        if data.get("action") in {"finish", "final"} and data.get("action_input") is not None:
            ai = data["action_input"]
            return str(ai.get("content") if isinstance(ai, dict) else ai).strip()
        if data.get("content") and "action" in data:
            return str(data["content"]).strip()

    # 半截 JSON：...最终回答： ```json {"action":...
    if "最终回答" in text or '"action"' in text:
        m = re.search(r'"content"\s*:\s*"((?:\\.|[^"\\])*)"', text)
        if m:
            try:
                return json.loads(f'"{m.group(1)}"')
            except Exception:
                return m.group(1).replace("\\n", "\n")

    return text


def looks_like_internal(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t.startswith("{") and ("action" in t or "tool" in t):
        return True
    if any(m in t for m in _INTERNAL_MARKERS):
        return True
    if "已执行 file_write" in t or "已执行 browser_" in t:
        return True
    return False


def sanitize_public_answer(text: str) -> str:
    """清洗模型/合成答复，只保留普通人能读的中文。"""
    raw = _unwrap_protocol_json(text)
    raw = _CODE_FENCE_RE.sub(lambda m: m.group(1).strip(), raw)
    raw = raw.strip()

    # 拦截把「核对提示词」整段吐给用户的情况
    if "请输出核实后的" in raw or "请输出最终高质量中文答案" in raw:
        # 若混有可用正文，尽量只留编号列表段；否则清空走重新合成
        m_list = re.search(r"((?:^|\n)\s*\d+[\.、．].+)", raw, re.S)
        if m_list and "用户目标：" not in m_list.group(1)[:80]:
            raw = m_list.group(1).strip()
        else:
            return ""

    raw = _META_LEAK_RE.sub("", raw)
    raw = re.sub(r"^最终回答\s*[：:]\s*", "", raw)
    raw = _unwrap_protocol_json(raw)

    if looks_like_internal(raw) and not _has_readable_news_list(raw):
        # 整段都是内部痕迹 → 再尝试抽 content，否则清空交给合成
        unwrapped = _unwrap_protocol_json(raw)
        if unwrapped != raw and not looks_like_internal(unwrapped):
            raw = unwrapped
        elif '"content"' in raw:
            m = re.search(r'"content"\s*:\s*"((?:\\.|[^"\\])*)"', raw)
            if m:
                try:
                    raw = json.loads(f'"{m.group(1)}"')
                except Exception:
                    raw = m.group(1)

    # 删掉仍含 JSON 行的段落
    lines = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            lines.append("")
            continue
        if s.startswith("{") and ("action" in s or "filename" in s):
            continue
        if "（内部步骤）" in s or "(内部步骤)" in s:
            continue
        if s.startswith("```"):
            continue
        lines.append(ln)
    out = "\n".join(lines).strip()
    # 压缩多余空行
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def _has_readable_news_list(text: str) -> bool:
    return bool(re.search(r"(热点|新闻|要闻)", text)) and (
        bool(re.search(r"^\s*\d+[\.、]", text, re.M)) or "·" in text
    )


def extract_headlines(blob: str, *, limit: int = 8) -> list[str]:
    """从网页/HTTP 抓取文本中抽取像新闻标题的句子。"""
    text = blob or ""
    # 定位「热点要闻」之后
    for marker in ("热点要闻", "热门", "头条", "要闻"):
        idx = text.find(marker)
        if idx >= 0:
            text = text[idx + len(marker) :]
            break

    # 预处理：管道两侧当作标题分隔；多空格也拆开
    text = text.replace("｜", "|")
    rough_parts: list[str] = []
    for block in re.split(r"[\n\|]+", text):
        block = block.strip()
        if not block:
            continue
        # 同块内用空白切开（百度新闻标题之间常为空格）
        if re.search(r"\s", block) and len(block) > 40:
            rough_parts.extend(p.strip() for p in re.split(r"\s+", block) if p.strip())
        else:
            rough_parts.append(block)

    candidates: list[str] = []
    for part in rough_parts:
        s = part.strip(" ·•-\t\"'")
        s = re.sub(r"\s+", "", s) if " " in s and len(s) < 40 else s.strip()
        # 保留标题内的少量空格（如「学习手记 | xxx」已被拆开）
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            continue
        if _NAV_NOISE.match(s):
            continue
        # 去空白后的长度
        compact = re.sub(r"\s+", "", s)
        if len(compact) < 8 or len(compact) > 48:
            continue
        if any(x in s for x in ("http", "www.", "{", "}", "file_write", "Action", "Observation")):
            continue
        if compact.count("首页") + compact.count("国内") >= 2:
            continue
        if s not in candidates:
            candidates.append(s)
        if len(candidates) >= limit:
            break
    return candidates


def format_news_answer(headlines: list[str]) -> str:
    if not headlines:
        return ""
    lines = ["最近热点新闻（整理自公开资讯）：", ""]
    for i, h in enumerate(headlines[:8], 1):
        lines.append(f"{i}. {h}")
    lines.append("")
    lines.append("以上为标题速览，具体内容以官网为准。")
    return "\n".join(lines)


def format_file_answer(artifacts: list[str]) -> str:
    if not artifacts:
        return ""
    names = "、".join(artifacts)
    return f"已经为你生成文件：{names}。\n请点击消息里的下载按钮获取。"


def public_facts(ctx: "TaskContext") -> list[str]:
    """仅保留适合给用户看、且与当前目标相关的事实。"""
    from agent.memory_policy import fact_relevant_to_goal, is_noise_fact

    out: list[str] = []
    goal = getattr(ctx, "goal", "") or ""
    for f in ctx.facts:
        t = (f or "").strip()
        if not t or looks_like_internal(t) or is_noise_fact(t):
            continue
        if t.startswith("此前结论:"):
            continue  # 跨轮结论不参与本轮合成
        if t.startswith("已打开页面:"):
            continue
        if t.startswith("HTTP ") or t.startswith("抽取正文要点:") or t.startswith("网页内容摘要:") or t.startswith("页面内容摘要:") or t.startswith("搜索结果:") or t.startswith("网页摘录:"):
            body = t.split(":", 1)[-1].strip() if ":" in t else t
            if fact_relevant_to_goal(body, goal):
                out.append(body[:300])
            else:
                for h in extract_headlines(t):
                    if fact_relevant_to_goal(h, goal):
                        out.append(h)
            continue
        if t.startswith("新闻标题:"):
            for x in t.split(":", 1)[-1].split("|"):
                h = x.strip()
                if h and fact_relevant_to_goal(h, goal):
                    out.append(h)
            continue
        if t.startswith("已生成文件"):
            continue
        if fact_relevant_to_goal(t, goal):
            out.append(t)
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def synthesize_public_answer(ctx: "TaskContext") -> str:
    """轮次用尽时：用本轮相关事实合成可读答复（通用，不按业务场景硬编码话术）。"""
    goal = ctx.goal or ""
    entities = extract_grounded_entities_from_facts(ctx.facts)
    if entities:
        return format_entity_list_answer(goal, entities)

    safe = public_facts(ctx)
    if ctx.artifacts and not safe:
        return format_file_answer(ctx.artifacts)

    body_facts = [
        s
        for s in safe
        if not s.startswith("搜索结果") and not s.startswith("页面拦截") and "HTTP 403" not in s
    ]
    if body_facts:
        bullets = "\n".join(f"· {s[:200]}" for s in body_facts[:8])
        return f"根据本轮查到的信息：\n{bullets}"

    if safe:
        bullets = "\n".join(f"· {s[:160]}" for s in safe[:8])
        return f"根据本轮查到的信息：\n{bullets}"

    if ctx.artifacts:
        return format_file_answer(ctx.artifacts)

    return (
        "这一轮工具结果还不够支撑可靠结论。"
        "请稍后再试，或把目标说得更具体一点；我会按新问题重新取数，不沿用上一题。"
    )


def clean_prior_assistant_for_memory(content: str) -> str | None:
    """历史助手消息摘要（仅用于会话层，不再写入 TaskContext.facts）。"""
    text = sanitize_public_answer(content or "")
    if not text or looks_like_internal(text):
        return None
    if text.startswith("这是我目前整理到的要点"):
        return None
    if len(text) > 280:
        text = text[:280] + "…"
    return text


_HOLLOW_PATTERNS = (
    r"^以上是.*希望对您有所帮助",
    r"^希望对您有所帮助",
    r"^已为您整理",
    r"^相关信息如下[。.!！]?$",
)


def is_hollow_answer(text: str) -> bool:
    """空壳答复：太短、套话、或几乎只剩搜索引擎链接。"""
    t = sanitize_public_answer(text or "").strip()
    if not t:
        return True
    if len(t) < 36:
        return True
    for pat in _HOLLOW_PATTERNS:
        if re.search(pat, t):
            return True
    # 去掉 URL 后几乎没正文
    without_urls = re.sub(r"https?://\S+", "", t)
    without_urls = re.sub(r"\s+", "", without_urls)
    url_count = len(re.findall(r"https?://", t))
    if url_count >= 1 and len(without_urls) < 24:
        return True
    # 全是搜狗/Bing 搜索中间页
    if url_count >= 1 and all(
        any(x in u for x in ("sogou.com/web", "bing.com/search", "duckduckgo.com/html", "google.com/search"))
        for u in re.findall(r"https?://[^\s]+", t)
    ):
        return True
    return False


def is_substantive_draft(text: str, goal: str = "") -> bool:
    """finish 草稿是否已可直接交付（不必再经「无材料」总结器否定）。"""
    t = sanitize_public_answer(text or "").strip()
    if not t or is_hollow_answer(t) or looks_like_internal(t):
        return False
    if answer_parrots_search_titles(t, []):  # 无 facts 时仍检测合集标题口吻
        if re.search(r"\d+\s*本.*(推荐|书单|合集)", t):
            return False
    items = extract_answer_items(t)
    if len(items) >= 2:
        return True
    if t.count("《") >= 2:
        return True
    if len(t) >= 80 and re.search(r"^\s*\d+[\.、．]", t, re.M):
        return True
    return len(t) >= 60


def _thought_has_substance(thought: str) -> bool:
    t = (thought or "").strip()
    if len(t) < 40:
        return False
    if re.search(r"^\s*\d+[\.、．]", t, re.M) or ("1." in t and "2." in t):
        return True
    if t.count("《") >= 2 or t.count("—") >= 2:
        return True
    return False


def _strip_search_engine_urls(text: str) -> str:
    def _repl(m: re.Match) -> str:
        u = m.group(0)
        if any(x in u for x in ("sogou.com/web", "bing.com/search", "duckduckgo.com", "google.com/search")):
            return ""
        return u

    out = re.sub(r"https?://\S+", _repl, text)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def format_search_facts_as_answer(facts: list[str], *, goal: str = "") -> str:
    """内部调试用：搜索页标题列表。禁止直接作为用户可见答案。"""
    return ""


def is_likely_source_title(name: str, search_titles: list[str] | None = None) -> bool:
    """判断是否为「来源页/合集页」标题，而非用户要的具体实体。"""
    name = (name or "").strip()
    if not name:
        return True
    n = _norm_item(name)
    for t in search_titles or []:
        tn = _norm_item(t)
        if not tn:
            continue
        if n == tn or (len(n) >= 8 and (n in tn or tn in n)):
            return True
    # 跨场景：盘点/清单/合集/「数字+单位+推荐」类标题
    if re.search(r"\d+\s*(本|条|个|款|篇|集|首|部)", name) and any(
        k in name for k in ("推荐", "清单", "合集", "盘点", "精选", "必看", "力荐", "书单", "榜")
    ):
        return True
    if any(k in name for k in ("合集", "清单", "盘点", "书单", "推荐榜")) and len(name) >= 8:
        return True
    return False


def extract_grounded_entities_from_facts(facts: list[str]) -> list[str]:
    """从搜索摘要/正文 Observation 中抽出具体实体（如《书名》），排除搜索页标题。"""
    titles = search_titles_from_facts(facts)
    blob = "\n".join(facts or [])
    # 摘要区（标题 — 摘要）里的内容更可能含实体
    snippet_parts: list[str] = []
    for line in blob.splitlines():
        if " — " in line:
            snippet_parts.append(line.split(" — ", 1)[1])
        else:
            snippet_parts.append(line)
    scan = "\n".join(snippet_parts)
    entities: list[str] = []

    def _add(name: str) -> None:
        name = (name or "").strip().strip("《》").strip()
        if not (2 <= len(name) <= 40):
            return
        if is_likely_source_title(name, titles):
            return
        if name in entities:
            return
        entities.append(name)

    for m in re.finditer(r"《([^》]{1,40})》", scan):
        _add(m.group(1))
    # 无书名号时：数字编号后的短专名（避免整段句子）
    for m in re.finditer(
        r"(?:^|[\s，、；;])(?:\d{1,2}[\.、．]|[-·•])\s*[《]?([\u4e00-\u9fffA-Za-z0-9·]{2,20})[》]?",
        scan,
    ):
        cand = m.group(1).strip()
        if any(k in cand for k in ("推荐", "链接", "作者", "如果", "希望", "本文")):
            continue
        _add(cand)

    return entities[:16]


def format_entity_list_answer(goal: str, entities: list[str]) -> str:
    """用已核实抽取出的实体生成简短列表草稿（不加书名号）。"""
    if not entities:
        return ""
    n = None
    m = re.search(r"(\d+)\s*(?:本|个|条|款|篇|首|部)", goal or "")
    if m:
        try:
            n = max(1, min(20, int(m.group(1))))
        except Exception:
            n = None
    take = entities[: n or min(8, len(entities))]
    head = "根据公开检索整理如下："
    lines = [head, ""] + [f"{i}. {e}" for i, e in enumerate(take, 1)]
    if n and len(take) < n:
        lines.append("")
        lines.append(f"（材料中明确可核验的条目共 {len(take)} 条。）")
    return "\n".join(lines)


def extract_search_hit_cards(facts: list[str]) -> list[dict[str, str]]:
    """从搜索 Observation 抽出 {title, snippet, url}，供富文本总结。"""
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    for f in facts or []:
        if not f.startswith("搜索结果"):
            continue
        raw = re.sub(r"搜索结果(?:\([^)]*\))?:\s*", "", f)
        pending_title = ""
        pending_snip = ""
        pending_url = ""

        def _flush() -> None:
            nonlocal pending_title, pending_snip, pending_url
            title = pending_title.strip()
            if not title:
                return
            key = _norm_item(title)
            if key in seen:
                pending_title = pending_snip = pending_url = ""
                return
            seen.add(key)
            cards.append(
                {
                    "title": title[:120],
                    "snippet": pending_snip.strip()[:400],
                    "url": pending_url.strip()[:300],
                }
            )
            pending_title = pending_snip = pending_url = ""

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("链接:") or line.startswith("链接："):
                pending_url = re.sub(r"^链接[:：]\s*", "", line)
                _flush()
                continue
            m = re.match(r"^\d+\.\s*(.+)$", line)
            if m:
                if pending_title:
                    _flush()
                body = m.group(1).strip()
                if " — " in body:
                    pending_title, pending_snip = body.split(" — ", 1)
                else:
                    pending_title, pending_snip = body, ""
                continue
            # 续行摘要
            if pending_title and not line.startswith("http"):
                pending_snip = (pending_snip + " " + line).strip()
        if pending_title:
            _flush()
    return cards[:15]


def build_citations(facts: list[str], *, max_n: int = 8) -> list[dict[str, str]]:
    """组装用户可见来源：搜索命中 + 已抓取正文 URL，去重。"""
    out: list[dict[str, str]] = []
    seen_url: set[str] = set()
    seen_title: set[str] = set()

    def _add(title: str, url: str, snippet: str = "") -> None:
        url = (url or "").strip()
        title = (title or "").strip() or (url[:60] if url else "")
        if not title and not url:
            return
        if url:
            if url in seen_url:
                return
            # 跳过搜索引擎中间页
            if any(
                x in url
                for x in (
                    "sogou.com/web",
                    "bing.com/search",
                    "duckduckgo.com",
                    "google.com/search",
                )
            ):
                return
            seen_url.add(url)
        key = _norm_item(title)
        if key and key in seen_title:
            return
        if key:
            seen_title.add(key)
        out.append(
            {
                "title": title[:120],
                "url": url[:300],
                "snippet": (snippet or "")[:200],
            }
        )

    for c in extract_search_hit_cards(facts):
        _add(c.get("title") or "", c.get("url") or "", c.get("snippet") or "")
        if len(out) >= max_n:
            return out

    for f in facts or []:
        if not (
            f.startswith("网页正文摘要")
            or f.startswith("网页内容摘要")
            or f.startswith("页面内容摘要")
            or f.startswith("网页摘录")
        ):
            continue
        m_url = re.search(r"https?://[^\s\]）)]+", f)
        url = m_url.group(0) if m_url else ""
        title_m = re.search(r"标题[:：]\s*([^\n]+)", f)
        title = (title_m.group(1).strip() if title_m else "") or "网页摘录"
        _add(title, url, f[:160])
        if len(out) >= max_n:
            break
    return out[:max_n]


def materials_blob_for_synthesis(facts: list[str], *, max_chars: int = 7000) -> str:
    """拼给总结模型的材料包：命中卡片 + 正文摘要。"""
    parts: list[str] = []
    cards = extract_search_hit_cards(facts)
    if cards:
        parts.append("## 搜索命中（标题/摘要/链接）")
        for i, c in enumerate(cards, 1):
            parts.append(
                f"{i}. 标题: {c['title']}\n"
                f"   摘要: {c.get('snippet') or '（无）'}\n"
                f"   链接: {c.get('url') or '（无）'}"
            )
    bodies = [
        f
        for f in (facts or [])
        if f.startswith("网页正文摘要")
        or f.startswith("网页内容摘要")
        or f.startswith("页面内容摘要")
        or "正文条目线索" in f[:20]
        or f.startswith("网页摘录")
    ]
    if bodies:
        parts.append("## 网页正文摘录")
        for b in bodies[-4:]:
            parts.append(b[:1200])
    blob = "\n".join(parts).strip()
    return blob[:max_chars]


async def synthesize_rich_answer(
    model: Any,
    *,
    goal: str,
    facts: list[str],
    draft: str = "",
    thought: str = "",
) -> str:
    """豆包风格交付：总起 + 编号条目（标题行 + 2～4 句要点），严格贴合目标与材料。"""
    materials = materials_blob_for_synthesis(facts)
    draft_clean = sanitize_public_answer(draft or "")

    # 无检索材料但 finish 草稿已够用 → 直接交付，禁止总结器改成「没有材料」
    if not materials and is_substantive_draft(draft_clean, goal):
        return draft_clean

    if not materials and not draft_clean:
        return ""

    n_hint = ""
    m = re.search(r"(\d+)\s*(?:本|个|条|款|篇|首|部)", goal or "")
    if m:
        n_hint = f"用户明确要求约 {m.group(1)} 条；尽量凑够，材料不够就如实少写并说明。\n"

    messages = [
        {
            "role": "system",
            "content": (
                "你是通用信息整理编辑，最终答案质量对齐主流办公智能体（结构清晰、可直接阅读）。\n"
                "根据「用户目标」与「检索材料」撰写最终答复，规则：\n"
                "1. 开头一句总起（点明主题；若目标含条数/范围，写清楚）。\n"
                "2. 用编号列表交付；每条第一行是简明标题（加粗可用 **标题**），"
                "下面紧跟 2～4 句具体说明（人物/数字/进展/时间），信息尽量来自材料。\n"
                "3. **禁止**给新闻/普通条目乱加书名号《》；仅当材料明确是书籍且原文带书名号时才用《》。\n"
                "4. **禁止**把搜索引擎结果页标题、栏目名、合集名当成答案条目交差；"
                "要从摘要/正文提炼用户真正要的内容。\n"
                "5. 严格遵守目标约束（例如只要「国际」新闻就不要用国内政闻凑数；"
                "若材料不对题，宁可不写或说明材料不足并建议换关键词）。\n"
                "6. 需要实时核验但材料没有的精确数字，不要编造。\n"
                "7. 若检索材料为空但「模型草稿」已有完整可用答案，请整理草稿交付，"
                "可标注「供参考」；**禁止**只说「没有材料无法推荐」。\n"
                "8. 只输出给用户的中文正文，禁止 JSON / 工具名 / 内部步骤。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户目标：{goal}\n"
                f"{n_hint}\n"
                f"检索材料：\n{materials or '（无）'}\n\n"
                f"模型草稿（可参考，错误处请改正）：\n{(draft or '（空）')[:1500]}\n\n"
                f"Thought（仅供参考）：\n{(thought or '（无）')[:400]}\n\n"
                "请输出最终高质量中文答案。"
            ),
        },
    ]
    try:
        text = await model.chat(messages, temperature=0.35)
    except Exception:
        return ""
    out = sanitize_public_answer(text or "")
    if not out or is_hollow_answer(out) or looks_like_internal(out):
        if is_substantive_draft(draft_clean, goal):
            return draft_clean
        return ""
    if answer_parrots_search_titles(out, facts):
        if is_substantive_draft(draft_clean, goal):
            return draft_clean
        return ""
    # 明显滥用书名号套新闻：再压一次简单清洗
    if out.count("《") >= 3 and not any(k in goal for k in ("书", "小说", "阅读", "著作")):
        out2 = re.sub(r"《([^》]+)》", r"\1", out)
        out = sanitize_public_answer(out2)
    return out


def _norm_item(s: str) -> str:
    t = re.sub(r"\s+", "", (s or "").lower())
    t = t.replace("《", "").replace("》", "").replace("“", "").replace("”", "")
    return t


def extract_answer_items(text: str) -> list[str]:
    """从答复中抽出列表项 / 《》标题（通用结构，不绑定业务）。"""
    items: list[str] = []
    for m in re.finditer(r"《([^》]{1,60})》", text or ""):
        items.append(m.group(1).strip())
    for line in (text or "").splitlines():
        m = re.match(r"^\s*(?:\d+[\.、．]|[-·•])\s*(.+)$", line.strip())
        if not m:
            continue
        raw = m.group(1).strip()
        raw = re.sub(r"https?://\S+", "", raw).strip(" —-\t")
        if " — " in raw:
            raw = raw.split(" — ", 1)[0].strip()
        # 去掉包裹书名号后的重复
        raw = raw.strip("《》")
        if 2 <= len(raw) <= 80 and raw not in items:
            items.append(raw)
    return items


def search_titles_from_facts(facts: list[str]) -> list[str]:
    titles: list[str] = []
    for f in facts or []:
        if not f.startswith("搜索结果"):
            continue
        raw = re.sub(r"搜索结果(?:\([^)]*\))?:\s*", "", f)
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("链接"):
                continue
            m = re.match(r"^\d+\.\s*(.+)$", line)
            if not m:
                continue
            title = m.group(1)
            if " — " in title:
                title = title.split(" — ", 1)[0].strip()
            title = re.sub(r"https?://\S+", "", title).strip(" —-\t")
            if 4 <= len(title) <= 120:
                titles.append(title)
    return titles


def answer_parrots_search_titles(answer: str, facts: list[str]) -> bool:
    """草稿是否把「搜索结果标题/合集标题」直接冒充成了用户要的答案实体。"""
    titles = search_titles_from_facts(facts)
    items = extract_answer_items(answer)
    if len(items) < 2:
        return False
    hits = 0
    for it in items:
        if is_likely_source_title(it, titles):
            hits += 1
            continue
        n = _norm_item(it)
        if len(n) < 4:
            continue
        tnorms = [_norm_item(t) for t in titles]
        if any(n in t or t in n or (len(n) >= 6 and n[:6] in t) for t in tnorms):
            hits += 1
    return hits >= max(1, (len(items) + 1) // 2)


async def verify_final_answer(
    model: Any,
    *,
    goal: str,
    facts: list[str],
    draft: str,
    thought: str = "",
) -> str:
    """核对入口：优先走富文本总结；失败再退回简版规则。"""
    rich = await synthesize_rich_answer(
        model, goal=goal, facts=facts, draft=draft, thought=thought
    )
    if rich:
        return rich

    entities = extract_grounded_entities_from_facts(facts)
    if entities and (not draft or answer_parrots_search_titles(draft, facts) or "线索，不是最终答案" in (draft or "")):
        draft = format_entity_list_answer(goal, entities)

    materials = materials_blob_for_synthesis(facts, max_chars=5000)
    messages = [
        {
            "role": "system",
            "content": (
                "你是通用 Agent 的答案核对员。\n"
                "对照目标与材料重写最终答复：编号列表；每条标题+2～4句要点；"
                "非书籍不要用《》；禁止用搜索页标题凑数；严格贴合目标范围。\n"
                "只输出中文最终答案。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户目标：{goal}\n\n材料：\n{materials or '（无）'}\n\n"
                f"草稿：\n{draft or '（空）'}\n\n请输出核实后的答案。"
            ),
        },
    ]
    try:
        text = await model.chat(messages, temperature=0.25)
    except Exception:
        return sanitize_public_answer(draft or "")
    out = sanitize_public_answer(text or "")
    if not out or is_hollow_answer(out) or looks_like_internal(out):
        return sanitize_public_answer(draft or "")
    if answer_parrots_search_titles(out, facts):
        return sanitize_public_answer(format_entity_list_answer(goal, entities)) if entities else ""
    if out.count("《") >= 3 and not any(k in goal for k in ("书", "小说", "阅读", "著作")):
        out = sanitize_public_answer(re.sub(r"《([^》]+)》", r"\1", out))
    return out


def has_substantive_content_facts(facts: list[str]) -> bool:
    """是否已有正文级 Observation（相对纯搜索标题列表）。"""
    markers = (
        "网页正文摘要",
        "网页内容摘要",
        "网页摘录",
        "页面内容摘要",
        "正文条目线索",
        "知识库命中",
        "新闻标题:",
    )
    for f in facts or []:
        if any(f.startswith(m) or m in f[:24] for m in markers):
            return True
        if f.startswith("搜索结果"):
            continue
        # 其它较长事实也视为已有实质内容
        if len(f) >= 100 and not f.startswith("页面拦截"):
            return True
    return False


def tools_shallow_without_body(ctx: "TaskContext") -> bool:
    """通用判定：本轮只有搜索标题、没有正文提炼（任意业务场景通用）。"""
    facts = getattr(ctx, "facts", None) or []
    if has_substantive_content_facts(facts):
        return False
    has_search = any(f.startswith("搜索结果") for f in facts)
    if not has_search:
        return False
    # 有可抓链接却未留下正文，或无可抓链接 → 仍属浅层
    return True


def search_only_needs_fetch(facts: list[str], *, fetched_already: bool) -> bool:
    """仅有搜索标题、尚未抓取内容页 → 应继续 web_fetch，而不是停下来让用户选编号。"""
    if fetched_already:
        return False
    if not any(f.startswith("搜索结果") for f in facts):
        return False
    return bool(first_content_urls_from_facts(facts, limit=1))


_FOLLOWUP_SELECT_RE = re.compile(
    r"^(?:请?(?:帮我)?(?:看|打开|详细)?(?:一下)?|选)?\s*"
    r"(?:第)?\s*(\d+)\s*[条项个号]?\s*"
    r"(?:吧|啊|哦)?\s*[。.!]?\s*$"
)


def expand_selection_followup(user_text: str, history: list[Any]) -> str | None:
    """用户只回「2 / 第2条」时，根据上轮助手编号列表展开为明确目标。"""
    raw = (user_text or "").strip()
    m = _FOLLOWUP_SELECT_RE.match(raw)
    if not m and not re.fullmatch(r"\d{1,2}", raw):
        return None
    idx = int(m.group(1) if m else raw)
    if idx < 1 or idx > 20:
        return None

    last_assistant = ""
    last_user_goal = ""
    prev_user = ""
    for item in history:
        role = getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else None)
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "") or ""
        if role == "user":
            prev_user = last_user_goal
            last_user_goal = content
        elif role == "assistant":
            last_assistant = content

    # 当前这条 user 已在 history 末尾时，上一问在 prev；否则 last_user_goal 仍是上一问
    prior_goal = prev_user if (last_user_goal.strip() == raw or _FOLLOWUP_SELECT_RE.match(last_user_goal.strip())) else last_user_goal
    if not last_assistant:
        return None

    title = ""
    for line in last_assistant.splitlines():
        lm = re.match(rf"^\s*{idx}[\.、．]\s*(.+)$", line.strip())
        if lm:
            title = re.sub(r"https?://\S+", "", lm.group(1)).strip(" —-\t")
            if " — " in title:
                title = title.split(" — ", 1)[0].strip()
            break
    if not title:
        return None

    base = prior_goal.strip() or "上一轮问题"
    return (
        f"继续完成任务「{base}」："
        f"不要再让用户选编号；请直接打开与「{title}」相关的网页（或先搜索该标题），"
        f"提炼出原目标所需的具体内容，一次给出完整中文答案。"
    )


def pick_fetch_url(facts: list[str], *, skip: set[str] | None = None) -> str | None:
    """取下一条可抓取内容 URL（跳过已失败/验证码页）。"""
    skip = skip or set()
    for u in first_content_urls_from_facts(facts, limit=8):
        if u in skip:
            continue
        if any(x in u for x in ("unhuman", "captcha", "challenge", "verify")):
            continue
        return u
    return None


def enrich_finish_answer(
    finish_text: str,
    *,
    thought: str = "",
    facts: list[str] | None = None,
    goal: str = "",
) -> str:
    """若 finish 空壳：优先用 thought 中的要点列表，其次用搜索事实重写。"""
    text = sanitize_public_answer(finish_text or "")
    facts = facts or []
    if not is_hollow_answer(text):
        cleaned = _strip_search_engine_urls(text)
        return cleaned or text

    if _thought_has_substance(thought):
        # 常见：模型把列表写在 thought，finish 只剩套话
        body = thought.strip()
        body = re.sub(r"^(根据搜索结果[，,]?|我找到了[：:]?)\s*", "", body)
        # 去掉前言废话，优先保留编号列表
        if re.search(r"^\d+[\.、]", body, re.M) is None:
            listed = re.search(r"((?:^\s*\d+[\.、．].+\n?)+)", body, re.M)
            if listed:
                body = listed.group(1).strip()
        if not body.startswith("根据") and not re.match(r"^\d+", body.lstrip()):
            body = "根据本轮搜集，要点如下：\n" + body
        return sanitize_public_answer(body)

    from_entities = format_entity_list_answer(goal, extract_grounded_entities_from_facts(facts))
    if from_entities:
        return from_entities

    return text


def first_content_urls_from_facts(facts: list[str], *, limit: int = 2) -> list[str]:
    """从搜索事实里抽出可 web_fetch 的内容站链接（跳过搜索引擎结果页）。"""
    urls: list[str] = []
    for f in facts:
        for m in re.finditer(r"https?://[^\s\]\)\"\'<>]+", f):
            u = m.group(0).rstrip(".,;，。")
            if any(
                x in u
                for x in (
                    "sogou.com/web",
                    "bing.com/search",
                    "bing.com/ck/",
                    "duckduckgo.com",
                    "google.com/search",
                )
            ):
                continue
            if u not in urls:
                urls.append(u)
            if len(urls) >= limit:
                return urls
    return urls


def summarize_http_or_extract_for_memory(tool: str, result: dict[str, Any]) -> str:
    """工具结果写入工作记忆：保留足够正文，供最终核实答案使用。"""
    text = str(result.get("text") or "")
    status = result.get("status")
    brief = re.sub(r"\s+", " ", text).strip()[:1500]
    # 额外保留若干短行，便于模型抽出「真正条目」（通用，不假定业务）
    line_items: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if not (6 <= len(s) <= 80):
            continue
        if re.match(r"^(首页|登录|注册|下载|分享|评论|相关|热门|导航)", s):
            continue
        if s not in line_items:
            line_items.append(s)
        if len(line_items) >= 16:
            break
    parts = [f"网页正文摘要: {brief}" if brief else "网页正文摘要: （空）"]
    if line_items:
        parts.append("正文条目线索: " + " | ".join(line_items[:12]))
    if status is not None:
        parts.append(f"(HTTP {status})")
    return " ".join(parts)
