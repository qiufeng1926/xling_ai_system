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
    # 压缩多余空行；去掉「请回复编号」类只读任务尾巴
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = strip_pick_number_prompts(out)
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
    entities = extract_grounded_entities_from_facts(ctx.facts, goal=goal)
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


def is_substantive_draft(text: str, goal: str = "", facts: list[str] | None = None) -> bool:
    """finish 草稿是否已可直接交付（不必再经「无材料」总结器否定）。

    facts 用于检测是否复读搜索标题；thin_list / parrot 一律不算可交。
    """
    t = sanitize_public_answer(text or "").strip()
    if not t or is_hollow_answer(t) or looks_like_internal(t):
        return False
    facts = facts or []
    if facts and answer_parrots_search_titles(t, facts):
        return False
    if answer_parrots_search_titles(t, []) and re.search(r"\d+\s*本.*(推荐|书单|合集)", t):
        return False
    if is_thin_list_draft(t):
        return False
    items = extract_answer_items(t)
    if len(items) >= 2:
        return True
    if t.count("《") >= 2:
        return True
    if len(t) >= 80 and re.search(r"^\s*\d+[\.、．]", t, re.M):
        return True
    return len(t) >= 60


def is_thin_list_draft(text: str) -> bool:
    """条目只有标题、几乎无说明 → 需要扩写。"""
    t = sanitize_public_answer(text or "").strip()
    if not t:
        return True

    numbered = [ln for ln in t.splitlines() if re.match(r"^\s*\d+[\.、．]", ln.strip())]
    explain_lines = [
        ln.strip()
        for ln in t.splitlines()
        if ln.strip()
        and not re.match(r"^\s*\d+[\.、．]", ln)
        and not re.match(
            r"^(以下|为您|推荐|供参考|根据公开|根据本轮|根据检索|整理如下)", ln
        )
        and len(re.sub(r"[《》\*\#\s]", "", ln)) >= 18
    ]

    # 编号行全是短标签（来源名/站点名）→ 一律视为薄清单（优先于 depth_score）
    if len(numbered) >= 2 and len(explain_lines) < 2:
        short_n = sum(1 for ln in numbered if len(re.sub(r"^\s*\d+[\.、．]\s*", "", ln.strip())) <= 16)
        if short_n >= max(2, (len(numbered) + 1) // 2):
            return True
        if all(len(ln.strip()) < 40 for ln in numbered) and len(t) < 220:
            return True

    items = extract_answer_items(t)
    if len(items) >= 2 and len(explain_lines) < 2:
        cleaned = [re.sub(r"[《》\*\s]", "", i) for i in items]
        avg = sum(len(x) for x in cleaned) / max(len(cleaned), 1)
        if avg <= 18 and len(t) < 420:
            return True
        # 站点/频道名冒充答案
        site_hits = sum(1 for i in cleaned if _is_site_or_channel_label(i))
        if site_hits >= max(2, len(cleaned) // 2):
            return True

    # 已有多行说明段落，不算薄
    if len(explain_lines) >= 2 and len(t) >= 160:
        return False
    if answer_depth_score(t) >= 40 and len(explain_lines) >= 1:
        return False

    if t.count("《") >= 3 and len(t) < 280 and len(explain_lines) < 2:
        return True
    return False


_SITE_LABELS = (
    "维基百科",
    "百度百科",
    "知乎",
    "豆瓣",
    "搜狗",
    "必应",
    "谷歌",
    "wikipedia",
    "baike",
    "zhihu",
    "douban",
)


def _is_site_or_channel_label(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n or len(n) <= 2:
        return True  # zh / en 等语言码
    if n in {"zh", "en", "cn", "www", "http", "https"}:
        return True
    return any(s.lower() == n or s.lower() in n for s in _SITE_LABELS)


def answer_depth_score(text: str) -> int:
    """粗略衡量答复充实度（越高越好）。"""
    t = sanitize_public_answer(text or "").strip()
    if not t:
        return 0
    score = min(len(t), 1200) // 15
    score += t.count("\n") * 2
    score += len(extract_answer_items(t)) * 4
    # 标题后跟说明段落
    if re.search(r"(\*\*[^*]+\*\*|^\d+[\.、．].+)\n.+\n", t, re.M):
        score += 15
    if any(k in t for k in ("作者", "背景", "要点", "适合", "因为", "主要", "例如")):
        score += 8
    if any(k in t for k in ("没有材料", "无法推荐", "无法根据检索")):
        score -= 40
    return score


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


def is_count_list_goal(goal: str) -> bool:
    """用户明确要「N 条/个/本/…」或「推荐一份清单」类目标（跨场景通用）。"""
    g = goal or ""
    if re.search(r"\d+\s*(本|个|条|款|篇|首|部|家|种|项|份|套)", g):
        return True
    if any(k in g for k in ("推荐", "盘点", "清单", "列表", "列举", "给出")) and any(
        k in g for k in ("本", "个", "条", "款", "篇", "部", "种", "项", "一些", "几个")
    ):
        return True
    return False


def requested_list_count(goal: str) -> int | None:
    m = re.search(r"(\d+)\s*(本|个|条|款|篇|首|部|家|种|项|份|套)", goal or "")
    if not m:
        return None
    try:
        return max(1, min(50, int(m.group(1))))
    except Exception:
        return None


def requested_list_unit(goal: str) -> str:
    m = re.search(r"\d+\s*(本|个|条|款|篇|首|部|家|种|项|份|套)", goal or "")
    return m.group(1) if m else "条"


def prefers_title_marks(goal: str) -> bool:
    """目标像书籍/作品名清单时，优先信《》抽取。"""
    g = goal or ""
    return any(k in g for k in ("书", "书籍", "书单", "小说", "著作", "影片", "电影", "剧"))


# 兼容旧名：语义已升级为通用计数清单
def is_book_list_goal(goal: str) -> bool:
    return is_count_list_goal(goal)


def is_junk_entity_name(name: str) -> bool:
    """拦截清单套话、站点名、半截句子——禁止当成具体条目进终稿（通用）。"""
    name = (name or "").strip().strip("《》").strip()
    if not name:
        return True
    # 「以下10本/个」「10条高质量…」
    if re.match(r"^以下\d*", name):
        return True
    if re.match(r"^\d+\s*(本|个|条|款|篇|部|种|项)", name):
        return True
    if re.search(r"\d+\s*(本|个|条|款|篇|部|种|项)", name) and any(
        k in name for k in ("以下", "高质量", "硬核", "建议", "必读", "精选", "推荐", "盘点")
    ):
        return True
    if any(
        k in name
        for k in (
            "高质量的硬核",
            "本书围绕",
            "建议收藏",
            "重塑你的",
            "点击查看",
            "了解更多",
        )
    ):
        return True
    # 半截句子 / 非专名
    if name.startswith(("本书", "本文", "该文", "这里", "下面", "上述", "这个", "那个")):
        return True
    if any(k in name for k in ("围绕", "讲述了", "主要写", "介绍了", "点击")) and len(name) >= 8:
        return True
    if re.search(r"(推荐|书单|清单|盘点|合集|榜单)$", name) and len(name) <= 12:
        return True
    return False


_GOAL_STOP = {
    "给我",
    "帮我",
    "请",
    "一下",
    "一些",
    "几个",
    "相关",
    "推荐",
    "盘点",
    "清单",
    "列表",
    "列举",
    "详细",
    "介绍",
    "说说",
    "讲讲",
    "的",
    "和",
    "与",
    "及",
}

# 单独出现不足以证明「答对了题型」的宽泛主题词
_WEAK_CORE = {
    "历史",
    "中国",
    "文化",
    "科技",
    "经济",
    "生活",
    "新闻",
    "信息",
    "内容",
    "问题",
    "世界",
    "社会",
    "时代",
}


def goal_core_tokens(goal: str) -> list[str]:
    """去掉祈使/数量词后的主题核，用于正文相关性判断。"""
    g = goal or ""
    g = re.sub(r"\d+\s*(本|个|条|款|篇|首|部|家|种|项|份|套)", " ", g)
    for s in sorted(_GOAL_STOP, key=len, reverse=True):
        g = g.replace(s, " ")
    toks: list[str] = []
    for m in re.finditer(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9\-_]{2,20}", g):
        t = m.group(0)
        if t not in _GOAL_STOP and t not in toks:
            toks.append(t)
    return toks[:12]


def is_off_topic_body_for_goal(text: str, goal: str) -> bool:
    """抓取正文与当前目标主题/题型明显不符 → 不入库（通用）。"""
    g = (goal or "").strip()
    t = (text or "").strip()
    if not g or len(t) < 80:
        return False
    core = goal_core_tokens(g)
    if not core:
        return False
    strong_hit = sum(1 for c in core if c in t and c not in _WEAK_CORE)
    weak_hit = sum(1 for c in core if c in t and c in _WEAK_CORE)
    listish = (
        t.count("《")
        + len(re.findall(r"(?:^|[\n\s])\d{1,2}[\.、．]", t[:1200]))
        + sum(1 for k in ("推荐", "清单", "盘点", "排行", "TOP", "榜单", "入门", "书单") if k in t)
    )
    # 主题词几乎对不上
    if strong_hit == 0 and weak_hit == 0 and len(t) > 120:
        return True
    # 计数清单：只有宽泛主题词、又无列表结构 → 常见「同主题但答错题型」
    if is_count_list_goal(g):
        # 故事/通史站：即使夹杂《诗经》《春秋》，没有书单语义也算跑题
        storyish = sum(
            1
            for k in ("历史故事", "盘古", "各朝代", "上下五千年", "5000言", "远古时代", "治水")
            if k in t
        )
        list_cue = sum(1 for k in ("书单", "书籍推荐", "必读书", "好书", "豆瓣", "荐书") if k in t)
        if storyish >= 1 and list_cue == 0:
            return True
        if listish >= 2 and list_cue >= 1 and (strong_hit + weak_hit) >= 1:
            return False
        if strong_hit == 0 and list_cue == 0 and len(t) > 100:
            return True
    return False


def extract_grounded_entities_from_facts(facts: list[str], *, goal: str = "") -> list[str]:
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
    prefer_marks = prefers_title_marks(goal)

    def _add(name: str) -> None:
        name = (name or "").strip().strip("《》").strip()
        if not (2 <= len(name) <= 40):
            return
        if _is_site_or_channel_label(name):
            return
        if is_junk_entity_name(name):
            return
        if is_likely_source_title(name, titles):
            return
        # 纯站点后缀 / 百科噪声
        if re.search(r"(百科|专栏|首页|登录|目录|编辑|维基)", name):
            return
        if name in entities:
            return
        entities.append(name)

    for m in re.finditer(r"《([^》]{1,40})》", scan):
        _add(m.group(1))
    # 有书名号类目标且已抽到《》时，不再用编号短名（易吸入「以下N本」套话）
    allow_numbered = not prefer_marks or not entities
    if allow_numbered:
        for m in re.finditer(
            r"(?:^|[\s，、；;])(?:\d{1,2}[\.、．]|[-·•])\s*[《]?([\u4e00-\u9fffA-Za-z0-9·]{2,20})[》]?",
            scan,
        ):
            cand = m.group(1).strip()
            if any(k in cand for k in ("推荐", "链接", "作者", "如果", "希望", "本文", "以下", "高质量")):
                continue
            if is_junk_entity_name(cand):
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


def _fact_looks_like_list_source(fact: str) -> bool:
    """是否像「清单/书单/盘点」来源，而非故事站正文里偶尔出现的《书名》。"""
    f = fact or ""
    if f.startswith("搜索结果"):
        return any(k in f for k in ("推荐", "书单", "盘点", "好书", "必读", "豆瓣", "本 "))
    if any(k in f[:80] for k in ("书单", "书籍推荐", "必读书", "好书推荐", "豆瓣")):
        return True
    # 正文里有较多编号 + 书名号，才像清单页
    if f.count("《") >= 3 and len(re.findall(r"\d+[\.、．]", f[:800])) >= 3:
        return True
    return False


def materials_support_count_list(facts: list[str], goal: str) -> bool:
    """检索材料是否真能支撑「计数清单」交付（有足够具体条目，而非百科定义/新闻壳）。"""
    if not is_count_list_goal(goal):
        return bool(facts)
    # 只从「像清单」的事实里抽条目；故事站里的《诗经》《春秋》不能充当荐书材料
    list_facts = [f for f in (facts or []) if _fact_looks_like_list_source(f)]
    if not list_facts:
        return False
    ents = [
        e
        for e in extract_grounded_entities_from_facts(list_facts, goal=goal)
        if not is_off_type_list_item(e, goal) and not _is_and_template_title(e)
    ]
    if len(ents) >= 3:
        return True
    marks = []
    for m in re.finditer(r"《([^》]{2,40})》", "\n".join(list_facts)):
        name = m.group(1).strip()
        if (
            not is_off_type_list_item(name, goal)
            and not is_junk_entity_name(name)
            and not _is_and_template_title(name)
        ):
            marks.append(name)
    return len(set(marks)) >= 3


def is_off_type_list_item(name: str, goal: str = "") -> bool:
    """条目类型与目标明显不符（如荐书却交规划/日报/门户站）。"""
    n = (name or "").strip().strip("《》")
    if not n or is_junk_entity_name(n):
        return True
    if any(
        k in n
        for k in (
            "规划",
            "公报",
            "日报",
            "晚报",
            "纲要",
            "通知",
            "统计局",
            "百科",
            "门户",
            "官网",
            "杂志社",
            "新闻网",
            "经济网",
            "人民日报",
            "新华社",
        )
    ):
        return True
    # 荐书/作品清单：单字栏目名不算（两字书名如《史记》必须保留）
    if prefers_title_marks(goal) and len(n) < 2:
        return True
    return False


def materials_usable_for_goal(facts: list[str], goal: str) -> bool:
    """是否存在「可用来接地扩写」的材料；计数清单要求材料真有可列条目。"""
    facts = facts or []
    if not facts:
        return False
    if is_count_list_goal(goal):
        return materials_support_count_list(facts, goal)
    return bool(extract_search_hit_cards(facts)) or has_substantive_content_facts(facts)


def _is_and_template_title(name: str) -> bool:
    """「主题与后缀」短模板名（历史与记忆 / 笔记与同步）。"""
    n = (name or "").strip().strip("《》")
    return bool(re.match(r"^[\u4e00-\u9fffA-Za-z]{2,8}与[\u4e00-\u9fffA-Za-z]{1,10}$", n))


def format_title_marks_as_list(text: str, *, goal: str = "") -> str:
    """把『《A》、《B》、…』草稿整理成编号列表（保留实质条目，去重、去错类型）。"""
    titles = []
    seen: set[str] = set()
    for m in re.finditer(r"《([^》]{1,40})》", text or ""):
        name = m.group(1).strip()
        if is_off_type_list_item(name, goal) or is_junk_entity_name(name):
            continue
        # 去掉末尾明显模板注水（如「历史学家的技艺：历史与历史学」连造）
        if re.search(r"[：:].{0,12}(历史与|与历史学)", name) and "技艺" in name:
            continue
        if _is_and_template_title(name):
            continue
        key = _norm_item(name)
        if not key or key in seen:
            continue
        seen.add(key)
        titles.append(name)
    if len(titles) < 3:
        return (text or "").strip()
    n_want = requested_list_count(goal)
    take = titles[: n_want or len(titles)]
    head = "根据已整理条目推荐如下（未充分联网核验正文，条目来自本轮整理，供参考）："
    if n_want and len(take) < n_want:
        head = (
            f"根据已整理条目推荐如下（未凑满要求的 {n_want} {requested_list_unit(goal)}；"
            "未充分联网核验正文，供参考）："
        )
    lines = [head, ""] + [f"{i}. 《{t}》" for i, t in enumerate(take, 1)]
    if n_want and len(take) < n_want:
        lines.append("")
        lines.append("若需要更完整清单，请提供可打开的书单链接，或稍后再试。")
    return "\n".join(lines)


def rescue_count_list_answer(
    text: str, *, goal: str = "", facts: list[str] | None = None
) -> str:
    """计数清单交付抢救：优先保留文本中的具体条目，绝不因跑题 facts 丢掉已总结书名。

    这是前端交付与 finish 草稿不一致的关键修复点。
    """
    raw = sanitize_public_answer(text or "")
    if is_count_list_goal(goal) and raw.count("《") >= 3:
        formatted = format_title_marks_as_list(raw, goal=goal)
        if formatted.count("《") >= 3:
            return ensure_knowledge_disclaimer(formatted)
    # 编号列表里的非错类型、非模板条目
    items: list[str] = []
    seen: set[str] = set()
    for it in _list_item_titles(raw):
        if is_off_type_list_item(it, goal) or is_junk_entity_name(it) or _is_and_template_title(it):
            continue
        key = _norm_item(it)
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(it.strip("《》"))
    if len(items) >= 3:
        n_want = requested_list_count(goal)
        take = items[: n_want or len(items)]
        mark = prefers_title_marks(goal)
        head = "根据已整理条目推荐如下（未充分联网核验正文，供参考）："
        if n_want and len(take) < n_want:
            head = (
                f"根据已整理条目推荐如下（未凑满要求的 {n_want} {requested_list_unit(goal)}；"
                "未充分联网核验正文，供参考）："
            )
        lines = [head, ""]
        for i, e in enumerate(take, 1):
            lines.append(f"{i}. 《{e}》" if mark else f"{i}. {e}")
        return ensure_knowledge_disclaimer("\n".join(lines))
    return honest_grounded_list_answer(goal, facts)


def materials_blob_for_synthesis(
    facts: list[str], *, max_chars: int = 10000, goal: str = ""
) -> str:
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
        if (
            f.startswith("网页正文摘要")
            or f.startswith("网页内容摘要")
            or f.startswith("页面内容摘要")
            or "正文条目线索" in f[:20]
            or f.startswith("网页摘录")
        )
        and not is_nav_chrome_body(f)
        and not (goal and is_off_topic_body_for_goal(f, goal))
    ]
    if bodies:
        parts.append("## 网页正文摘录")
        for b in bodies[-6:]:
            parts.append(b[:1800])
    elif cards:
        # 正文是导航壳时，明确提示模型优先用搜索摘要扩写，勿复读站点名
        parts.append(
            "## 说明\n抓取页多为导航壳或与目标无关，请优先依据上方「搜索命中」摘要扩写成完整中文答复，"
            "禁止只输出维基百科/知乎/百度百科等来源名列表；"
            "禁止把「以下N本/个/条」等清单套话当成具体条目；材料不够就少写并说明。"
        )
    # 其它与目标相关的事实也带上
    extras = [
        f
        for f in (facts or [])
        if f not in bodies
        and not f.startswith("搜索结果")
        and len(f) >= 20
        and not is_nav_chrome_body(f)
        and not (goal and is_off_topic_body_for_goal(f, goal))
    ]
    if extras:
        parts.append("## 其它本轮有效信息")
        for e in extras[-8:]:
            parts.append(e[:600])
    blob = "\n".join(parts).strip()
    return blob[:max_chars]


_SYNTH_SYSTEM = (
    "你是通用信息整理编辑。优先「有依据、少幻觉」，其次才是篇幅。\n"
    "根据「用户目标」与「检索材料 / 模型草稿」撰写最终答复，规则：\n"
    "1. 开头 1～2 句总起（点明主题；若目标含条数/范围，写清楚）。\n"
    "2. 简单题：总起 + 编号要点；每条至少 2～3 句实质说明，禁止只有标题。\n"
    "3. 深度题：总起 + 分节「概览 → 结构或阶段 → 核心观点 → 小结/启示」，"
    "每节有实质段落；但分节内容必须能在材料中找到依据。\n"
    "4. 编号条目：标题行（书籍可用《书名》，新闻/普通条目禁止乱加《》）+ 随后说明；"
    "有数字/时间须与材料一致。\n"
    "5. **接地优先**：当检索材料能支撑当前题型时，事实须来自材料或草稿已写明内容；"
    "若材料明显跑题（如荐书却只有百科定义/新闻公报），而草稿已有具体条目，应整理草稿并标明未充分联网核实，"
    "**禁止**用跑题材料里的栏目名/规划名顶替草稿条目。\n"
    "6. **禁止**把搜索引擎结果页标题、栏目名、合集名当成答案条目交差。\n"
    "7. **禁止**让用户在只读任务里「回复编号 / 告诉我第几条 / 选一条再展开」；自行写完完整答案。\n"
    "8. 实时精确数字/股价/天气等核验不到：明确说无法核验，禁止编造。\n"
    "9. 检索材料为空或极弱时：若草稿已有实质内容，可整理草稿并在文首标明"
    "「以下未充分联网核实，仅供参考」；"
    "不要为了凑篇幅编造材料中没有的书名、数据、事件。\n"
    "10. 只输出给用户的中文正文，禁止 JSON / 工具名 / 内部步骤 / Thought/Observation。"
)

_KNOWLEDGE_DISCLAIMER = "以下内容未充分联网核实，仅供常识参考："

_PICK_NUMBER_RE = re.compile(
    r"(回复|告诉我|请选|选择|选一个|选一条|发我).{0,12}(编号|第?\s*\d+\s*[条项个]|哪一[条项])|"
    r"(如需|若要|想看).{0,20}(详细|展开).{0,16}(编号|回复|告诉我)|"
    r"请(回复|告诉我)编号",
    re.I,
)


def asks_user_to_pick_number(text: str) -> bool:
    """只读交付不应让用户再选编号。"""
    t = (text or "").strip()
    if not t:
        return False
    return bool(_PICK_NUMBER_RE.search(t))


def strip_pick_number_prompts(text: str) -> str:
    """去掉「请回复编号」类尾巴，保留正文。"""
    t = (text or "").strip()
    if not t:
        return t
    lines = []
    for ln in t.splitlines():
        if _PICK_NUMBER_RE.search(ln) and len(ln) < 80:
            continue
        if re.search(r"如需某一条的详细|告诉我编号|回复编号即可", ln):
            continue
        lines.append(ln)
    out = "\n".join(lines).strip()
    out = re.sub(r"\n*如需某一条的详细内容[^\n]*\n?", "\n", out).strip()
    return out


def ensure_knowledge_disclaimer(text: str) -> str:
    """常识/弱材料路径：文首必须有未核实声明。"""
    t = (text or "").strip()
    if not t:
        return t
    if any(
        k in t[:80]
        for k in (
            "未充分联网核实",
            "未联网核实",
            "仅供常识参考",
            "仅供参考",
            "未能核实",
            "无法核验",
        )
    ):
        return t
    return f"{_KNOWLEDGE_DISCLAIMER}\n\n{t}"


_GROUNDING_STOP = {
    "根据",
    "可以",
    "以及",
    "还有",
    "进行",
    "通过",
    "关于",
    "如果",
    "因为",
    "所以",
    "这个",
    "这些",
    "那些",
    "一个",
    "我们",
    "他们",
    "用户",
    "问题",
    "内容",
    "主要",
    "如下",
    "以下",
    "上面",
    "下面",
    "总起",
    "概述",
    "小结",
    "启示",
    "参考",
    "公开",
    "检索",
    "材料",
    "整理",
    "说明",
    "介绍",
}


def _content_tokens(text: str) -> set[str]:
    """抽取可用于接地比对的词块（中文二元组 / 短词段 / 英文词 / 数字）。"""
    t = text or ""
    out: set[str] = set()
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9\-_.]{1,24}|\d{2,4}", t):
        out.add(m.group(0).lower())
    for m in re.finditer(r"[\u4e00-\u9fff]{2,}", t):
        run = m.group(0)
        if run in _GROUNDING_STOP:
            continue
        if 2 <= len(run) <= 6:
            out.add(run)
        for i in range(len(run) - 1):
            bg = run[i : i + 2]
            if bg not in _GROUNDING_STOP:
                out.add(bg)
    return out


def answer_grounding_ratio(answer: str, materials: str) -> float:
    """答案词块落在材料中的比例；材料过短时返回 1.0（不做硬拦）。"""
    mat = (materials or "").strip()
    ans = (answer or "").strip()
    if not ans:
        return 0.0
    if len(mat) < 80:
        return 1.0
    a_toks = _content_tokens(ans)
    if len(a_toks) < 10:
        return 1.0
    m_toks = _content_tokens(mat)
    if len(m_toks) < 8:
        return 1.0
    hit = sum(1 for x in a_toks if x in m_toks or (len(x) >= 2 and x in mat))
    return hit / max(len(a_toks), 1)


def is_poorly_grounded(answer: str, facts: list[str] | None, *, goal: str = "") -> bool:
    """有实质正文材料时，答案与材料重合过低 → 疑似幻觉扩写。

    仅有搜索标题/摘要时不做硬拦（否则任何合理扩写都会被误杀）。
    """
    facts = facts or []
    if not has_substantive_content_facts(facts):
        return False
    materials = materials_blob_for_synthesis(facts, goal=goal)
    if len(materials) < 80:
        return False
    return answer_grounding_ratio(answer, materials) < 0.18


async def synthesize_rich_answer(
    model: Any,
    *,
    goal: str,
    facts: list[str],
    draft: str = "",
    thought: str = "",
    force_expand: bool = False,
) -> str:
    """豆包风格交付：总起 + 编号条目；有材料时强制接地，禁止臆造细节。"""
    draft_clean = sanitize_public_answer(draft or "")
    list_materials_ok = (
        materials_support_count_list(facts, goal) if is_count_list_goal(goal) else True
    )
    # 计数清单但材料跑题：清空材料包，避免用百科/新闻「接地」冲掉草稿
    if is_count_list_goal(goal) and not list_materials_ok:
        materials = ""
        if (
            draft_clean
            and not is_template_fabricated_list(draft_clean, goal=goal)
            and draft_clean.count("《") >= 3
            and not (force_expand and is_thin_list_draft(draft_clean))
        ):
            formatted = format_title_marks_as_list(draft_clean, goal=goal)
            body = formatted if formatted.count("《") >= 3 else draft_clean
            return ensure_knowledge_disclaimer(body)
    else:
        materials = materials_blob_for_synthesis(facts, goal=goal)

    if not materials and not draft_clean:
        return ""

    # 无材料且草稿已充实（非薄清单）且未强制扩写 → 可直接交（文首加声明）
    if (
        not materials
        and is_substantive_draft(draft_clean, goal)
        and not is_thin_list_draft(draft_clean)
        and not force_expand
    ):
        return ensure_knowledge_disclaimer(draft_clean)

    n_hint = ""
    m = re.search(r"(\d+)\s*(?:本|个|条|款|篇|首|部)", goal or "")
    if m:
        n_hint = (
            f"用户明确要求约 {m.group(1)} 条；尽量凑够并写充分，"
            "材料不够就如实少写并说明，禁止虚构条目凑数。\n"
        )

    expand_hint = ""
    if materials:
        expand_hint = (
            "特别要求（接地）：只依据「检索材料」与草稿已有内容组织答案；"
            "不要把 Thought 里的猜测写进终稿；材料没有的细节直接省略；"
            "可概括材料，但禁止补充材料未出现的具体事实/数据/人名。\n"
            "禁止把「以下N本/条」「N个高质量…」等清单套话当成具体条目。\n"
        )
        if is_thin_list_draft(draft_clean) or force_expand:
            expand_hint += (
                "草稿若只有标题清单：用材料中的摘要/正文为每条补写 2～4 句；"
                "材料不够写的条目宁可删掉，也不要凭空扩写。\n"
            )
    elif force_expand or is_thin_list_draft(draft_clean) or not materials:
        expand_hint = (
            "特别要求：当前几乎无检索正文。若草稿已有条目，整理成可读答复，"
            f"文首必须写「{_KNOWLEDGE_DISCLAIMER}」；"
            "禁止为凑篇幅编造草稿中没有的书名、数据或事件；"
            "宁可条目少、说明短，也不要臆造。\n"
        )
    from agent.research_policy import is_deep_research_goal

    if is_deep_research_goal(goal) and materials:
        expand_hint += (
            "这是深度问题：在材料支撑范围内按「概览 / 结构或阶段 / 核心观点 / 小结启示」展开；"
            "某一节材料不足就写「材料未覆盖」并跳过，禁止用臆测填满分节。\n"
        )
    elif is_deep_research_goal(goal) and not materials:
        expand_hint += (
            "这是深度问题但材料不足：给出有限概述即可，并标明未充分核实；禁止假装已完成多源综述。\n"
        )

    thought_block = ""
    if thought and not materials:
        thought_block = f"Thought（仅线索，禁止把未核实猜测写进答案）：\n{(thought or '（无）')[:300]}\n\n"
    elif thought and materials:
        thought_block = (
            "Thought（忽略其中与材料不符的猜测，不得据此扩写事实）：\n"
            f"{(thought or '（无）')[:200]}\n\n"
        )

    messages = [
        {"role": "system", "content": _SYNTH_SYSTEM},
        {
            "role": "user",
            "content": (
                f"用户目标：{goal}\n"
                f"{n_hint}"
                f"{expand_hint}\n"
                f"检索材料：\n{materials or '（无）'}\n\n"
                f"模型草稿（可参考；与材料冲突时以材料为准；薄清单请用材料扩写）：\n"
                f"{(draft or '（空）')[:2500]}\n\n"
                f"{thought_block}"
                "请输出最终中文答案（有材料则接地；无材料则短而诚实）。"
            ),
        },
    ]
    try:
        text = await model.chat(messages, temperature=0.2)
    except Exception:
        if is_substantive_draft(draft_clean, goal, facts=facts):
            return draft_clean if materials else ensure_knowledge_disclaimer(draft_clean)
        if draft_clean and (extract_answer_items(draft_clean) or draft_clean.count("《") >= 2):
            return draft_clean if materials else ensure_knowledge_disclaimer(draft_clean)
        return ""
    out = sanitize_public_answer(text or "")
    out = strip_pick_number_prompts(out)
    if not materials and out:
        out = ensure_knowledge_disclaimer(out)
    if (
        not out
        or is_hollow_answer(out)
        or looks_like_internal(out)
        or asks_user_to_pick_number(out)
        or any(x in out for x in ("没有材料无法", "无法根据检索材料", "目前没有提供具体"))
    ):
        if is_substantive_draft(draft_clean, goal, facts=facts):
            fb = strip_pick_number_prompts(draft_clean)
            return fb if materials else ensure_knowledge_disclaimer(fb)
        # 薄清单：模型误杀时仍回退草稿，避免交空壳
        if draft_clean and (
            extract_answer_items(draft_clean) or draft_clean.count("《") >= 2 or len(draft_clean) >= 24
        ):
            fb = strip_pick_number_prompts(draft_clean)
            return fb if materials else ensure_knowledge_disclaimer(fb)
        return ""
    if answer_parrots_search_titles(out, facts):
        if is_substantive_draft(draft_clean, goal, facts=facts):
            return strip_pick_number_prompts(draft_clean)
        if draft_clean and (extract_answer_items(draft_clean) or draft_clean.count("《") >= 2):
            return strip_pick_number_prompts(draft_clean)
        return ""
    # 有材料却几乎不接地 → 回退草稿或材料摘要，避免幻觉终稿
    if materials and is_poorly_grounded(out, facts, goal=goal):
        # 计数清单：草稿书名远多于材料实体时，禁止用 format_entity_list 冲成单条
        if is_count_list_goal(goal) and draft_clean.count("《") >= 5:
            formatted = format_title_marks_as_list(draft_clean, goal=goal)
            body = formatted if formatted.count("《") >= 3 else draft_clean
            if body.count("《") >= 5:
                return ensure_knowledge_disclaimer(strip_pick_number_prompts(body))
        if is_substantive_draft(draft_clean, goal, facts=facts) and not is_poorly_grounded(
            draft_clean, facts, goal=goal
        ):
            return strip_pick_number_prompts(draft_clean)
        # 用材料拼一段保守答复（仅当草稿也撑不起清单时）
        from agent.context import TaskContext

        conservative = synthesize_public_answer(
            TaskContext(goal=goal, facts=list(facts or []))
        )
        if (
            conservative
            and len(conservative) >= 40
            and not (
                is_count_list_goal(goal)
                and draft_clean.count("《") > (conservative or "").count("《")
            )
        ):
            return sanitize_public_answer(conservative)
        if is_substantive_draft(draft_clean, goal, facts=facts):
            return strip_pick_number_prompts(draft_clean)
        if draft_clean.count("《") >= 3:
            formatted = format_title_marks_as_list(draft_clean, goal=goal)
            body = formatted if formatted.count("《") >= 3 else draft_clean
            return ensure_knowledge_disclaimer(strip_pick_number_prompts(body))
    # 扩写后若反而更薄，回退草稿
    if draft_clean and answer_depth_score(out) + 8 < answer_depth_score(draft_clean):
        return strip_pick_number_prompts(draft_clean)
    # 计数清单：模型 grounding 后条目骤减 → 回退草稿
    if (
        is_count_list_goal(goal)
        and draft_clean.count("《") >= 5
        and (out or "").count("《") < 3
    ):
        formatted = format_title_marks_as_list(draft_clean, goal=goal)
        body = formatted if formatted.count("《") >= 3 else draft_clean
        return ensure_knowledge_disclaimer(strip_pick_number_prompts(body))
    # 明显滥用书名号套新闻：再压一次简单清洗
    if out.count("《") >= 3 and not any(k in goal for k in ("书", "小说", "阅读", "著作", "经济")):
        out2 = re.sub(r"《([^》]+)》", r"\1", out)
        out = sanitize_public_answer(out2)
    # 薄清单且有材料：视为失败，交给上层再扩或回退
    if materials and is_thin_list_draft(out) and is_substantive_draft(draft_clean, goal):
        if answer_depth_score(draft_clean) >= answer_depth_score(out):
            return strip_pick_number_prompts(draft_clean)
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

    entities = extract_grounded_entities_from_facts(facts, goal=goal)
    if entities and (not draft or answer_parrots_search_titles(draft, facts) or "线索，不是最终答案" in (draft or "")):
        draft = format_entity_list_answer(goal, entities)

    materials = materials_blob_for_synthesis(facts, max_chars=5000, goal=goal)
    messages = [
        {
            "role": "system",
            "content": (
                "你是通用 Agent 的答案核对员。\n"
                "对照目标与材料重写最终答复：只保留材料能支撑的事实；"
                "编号列表；每条标题+要点；非书籍不要用《》；禁止用搜索页标题凑数。\n"
                "材料没有的细节禁止补充；宁可短，也不要编造。\n"
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
        # 禁止回退成「来源名清单」；有实质草稿则保留草稿
        if is_substantive_draft(draft, goal, facts=facts):
            return sanitize_public_answer(draft or "")
        return ""
    if out.count("《") >= 3 and not any(k in goal for k in ("书", "小说", "阅读", "著作")):
        out = sanitize_public_answer(re.sub(r"《([^》]+)》", r"\1", out))
    return out


def is_nav_chrome_body(text: str) -> bool:
    """维基导航壳 / 搜狗备案页等：看起来很长，实则不可用。

    短文本不算 chrome（可能是可用摘要片段）；是否计入「正文篇数」由调用方再做长度门槛。
    """
    t = (text or "").strip()
    if not t:
        return False
    try:
        from tools.web_tools import is_search_engine_shell_body

        if is_search_engine_shell_body(t):
            return True
    except Exception:
        pass
    chrome_hits = sum(
        1
        for k in (
            "跳转到内容",
            "移至侧栏",
            "创建账号",
            "个人工具",
            "开关成书子章节",
            "开关目录",
            "编辑链接",
            "不转换",
            "大陆简体",
            "香港繁體",
            "維基共享资源",
            "维基共享资源",
            "主菜单",
            "特殊页面",
            "京公网安备",
            "京ICP备",
            "上网从搜狗开始",
            "查询限制在100个汉字",
        )
        if k in t
    )
    # 导航词密集 + 缺少叙述句 → 视为空壳正文
    if chrome_hits >= 3:
        return True
    if chrome_hits >= 2 and not re.search(r"[。；][^。；]{20,}", t):
        return True
    return False


def is_series_padding_list(text: str) -> bool:
    """同一书名系列用 1～N 编号硬凑条数（如「历史是个什么玩意儿1～8」）。"""
    items = extract_answer_items(text or "")
    if len(items) < 6:
        numbered = []
        for ln in (text or "").splitlines():
            m = re.match(r"^\s*\d+[\.、．]\s*[*《]*\s*([^*\n]{2,80})", ln.strip())
            if m:
                numbered.append(m.group(1).strip().strip("》").strip("*").strip())
        items = numbered
    if len(items) < 6:
        return False
    bases: list[str] = []
    for it in items:
        b = re.sub(r"[\s《》\*·\-—]+", "", it)
        b = re.sub(
            r"(第?[0-9０-９一二三四五六七八九十百]+[册卷部集季册]?|[0-9０-９]+)$",
            "",
            b,
        )
        if len(b) >= 4:
            bases.append(b)
    if len(bases) < 6:
        return False
    from collections import Counter

    cnt = Counter(bases)
    top_n = cnt.most_common(1)[0][1]
    return top_n >= 4 and top_n / len(bases) >= 0.35


def _list_item_titles(text: str) -> list[str]:
    items = extract_answer_items(text or "")
    if len(items) >= 2:
        return items
    numbered: list[str] = []
    for ln in (text or "").splitlines():
        m = re.match(r"^\s*\d+[\.、．]\s*(?:\*\*)?《?([^》\n*]{2,60})", ln.strip())
        if m:
            numbered.append(m.group(1).strip().strip("*").strip())
    return numbered


def is_duplicate_heavy_list(text: str) -> bool:
    """终稿出现完全重复条目（如 19、20 同名）。"""
    items = _list_item_titles(text)
    if len(items) < 2:
        return False
    norms = [_norm_item(x) for x in items if _norm_item(x)]
    if len(norms) < 2:
        return False
    from collections import Counter

    c = Counter(norms)
    return c.most_common(1)[0][1] >= 2


def is_template_fabricated_list(text: str, *, goal: str = "") -> bool:
    """检测模板硬凑清单：同前缀连造、标题高度同构（跨场景通用）。"""
    items = _list_item_titles(text)
    if len(items) < 4:
        return False
    from collections import Counter

    # 「X与Y / X和Y」同前缀连造（如历史与记忆/历史学/政治）
    prefixes: list[str] = []
    for it in items:
        n = re.sub(r"[\s《》\*]+", "", it)
        m = re.match(r"^([\u4e00-\u9fffA-Za-z]{2,8})[与和之]", n)
        if m:
            prefixes.append(m.group(1).lower())
    if prefixes and Counter(prefixes).most_common(1)[0][1] >= 3:
        return True
    # 标题头 3～4 字大量撞车
    heads = [_norm_item(it)[:4] for it in items if len(_norm_item(it)) >= 4]
    if heads and Counter(heads).most_common(1)[0][1] >= 4:
        return True
    # 同一「定语人名/机构」挂在很多条上，且条目本身短而同构
    name_hits = re.findall(
        r"([\u4e00-\u9fff]{1,3}[·・.][\u4e00-\u9fff]{1,4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        text or "",
    )
    if len(name_hits) >= 4 and len(items) >= 10:
        if Counter(name_hits).most_common(1)[0][1] >= 3:
            return True
    return False


def dedupe_numbered_list_answer(text: str) -> str:
    """去掉编号列表中的完全重复条（保留首次）。"""
    t = (text or "").strip()
    if not t:
        return t
    lines = t.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    num = 0
    for ln in lines:
        m = re.match(r"^(\s*)(\d+)([\.、．])\s*(.+)$", ln)
        if not m:
            out.append(ln)
            continue
        body = m.group(4).strip()
        title_m = re.match(r"(?:\*\*)?《([^》]+)》|(\*\*[^*]+\*\*)|([^\s—\-]{2,40})", body)
        key_src = ""
        if title_m:
            key_src = title_m.group(1) or title_m.group(2) or title_m.group(3) or body[:40]
        key = _norm_item(key_src or body[:40])
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        num += 1
        out.append(f"{m.group(1)}{num}{m.group(3)} {body}")
    return "\n".join(out).strip()


def is_honest_shortfall_answer(text: str) -> bool:
    """是否为「材料不足、明确未凑满」的诚实短答（可放行薄列表门控）。"""
    t = text or ""
    return any(
        k in t
        for k in (
            "未凑满",
            "暂不编造",
            "未能从可核验",
            "未能打开",
            "不够可核验",
            "不硬凑",
            "不是完整",
        )
    )


def honest_grounded_list_answer(goal: str, facts: list[str] | None = None) -> str:
    """弱材料时：只交材料可核验条目；绝不靠常识硬凑满 N（通用办公场景）。"""
    facts = facts or []
    ents = [e for e in extract_grounded_entities_from_facts(facts, goal=goal) if not is_junk_entity_name(e)]
    ents = ents[:12]
    n_want = requested_list_count(goal)
    unit = requested_list_unit(goal)
    head = (
        "以下内容未充分联网核实，仅供参考。\n"
        "本轮未能打开足够的正文来源，为避免编造条目凑数，"
        "只整理材料中可核验的具体项"
    )
    if n_want:
        head += f"（未凑满要求的 {n_want} {unit}）"
    head += "。"
    if ents:
        mark = prefers_title_marks(goal)
        lines = [head, ""]
        for i, e in enumerate(ents, 1):
            lines.append(f"{i}. 《{e}》" if mark else f"{i}. {e}")
        lines.append("")
        lines.append("若需要更完整清单，请稍后再试，或提供可访问的来源链接。")
        return "\n".join(lines)
    return (
        f"{head}\n\n"
        "当前检索摘要里也没有足够可核验的具体条目，暂不编造清单。"
        "请换个更具体的问法，或指定可打开的来源后再试。"
    )


# 兼容旧调用名
def honest_short_book_answer(goal: str, facts: list[str] | None = None) -> str:
    return honest_grounded_list_answer(goal, facts)


def sanitize_hallucinated_list_answer(
    text: str, *, goal: str = "", facts: list[str] | None = None
) -> str:
    """终稿清洗：去重；模板/重复时从原文抢救条目，禁止用跑题 facts 顶替已总结清单。"""
    t = dedupe_numbered_list_answer(sanitize_public_answer(text or ""))
    if not t:
        return t
    if not is_count_list_goal(goal):
        return t

    # 文本里已有足够书名号 → 一律先抢救成干净编号列表（去重、去错类型）
    if t.count("《") >= 3:
        rescued = rescue_count_list_answer(t, goal=goal, facts=facts)
        if rescued.count("《") >= 3:
            return rescued

    if is_duplicate_heavy_list(t) or is_template_fabricated_list(t, goal=goal) or is_series_padding_list(t):
        return rescue_count_list_answer(t, goal=goal, facts=facts)

    items = _list_item_titles(t)
    if items:
        bad = sum(1 for it in items if is_off_type_list_item(it, goal))
        if bad >= max(1, (len(items) + 1) // 2):
            return rescue_count_list_answer(t, goal=goal, facts=facts)
    return t


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
            if is_nav_chrome_body(f):
                continue
            # 真正有叙述内容
            if len(re.sub(r"\s+", "", f)) >= 120 and (
                "。" in f or "；" in f or len(f) >= 280
            ):
                return True
            if len(f) >= 200 and not is_nav_chrome_body(f):
                return True
            continue
        if f.startswith("搜索结果"):
            continue
        # 其它较长事实也视为已有实质内容
        if len(f) >= 100 and not f.startswith("页面拦截") and not is_nav_chrome_body(f):
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


# 易 403/验证码的内容站：有替代源时后取，避免首条就卡住
_FETCH_DEPRIORITIZE_HOSTS = (
    "zhihu.com",
    "zhuanlan.zhihu.com",
    "xiaohongshu.com",
    "weixin.qq.com",
    "mp.weixin.qq.com",
)


def _url_goal_relevance(url: str, facts: list[str], goal: str) -> int:
    """按搜索命中标题/摘要与目标主题重合度打分；无命中信息时返回中性分。"""
    if not url or not goal:
        return 1
    core = goal_core_tokens(goal)
    cards = extract_search_hit_cards(facts)
    blob = ""
    for c in cards:
        if url.rstrip("/") in (c.get("url") or "").rstrip("/") or (c.get("url") or "") in url:
            blob = f"{c.get('title') or ''} {c.get('snippet') or ''}"
            break
    if not blob:
        # URL 路径里带目标核也加分
        blob = url
    if not core:
        return 1
    return sum(1 for c in core if c in blob)


def pick_fetch_url(
    facts: list[str], *, skip: set[str] | None = None, goal: str = ""
) -> str | None:
    """取下一条可抓取内容 URL（跳过已失败；与目标无关/易墙站点后置）。"""
    skip = skip or set()
    scored: list[tuple[int, int, str]] = []
    for i, u in enumerate(first_content_urls_from_facts(facts, limit=10)):
        if u in skip:
            continue
        if any(x in u for x in ("unhuman", "captcha", "challenge", "verify")):
            continue
        rel = _url_goal_relevance(u, facts, goal)
        # 与目标几乎无关的链接后置（常见：百科定义页、同主题故事站）
        penalty = 0
        if goal and rel == 0:
            penalty = 5
        if any(h in u for h in _FETCH_DEPRIORITIZE_HOSTS):
            penalty += 2
        scored.append((penalty, -rel, u))
    if not scored:
        return None
    scored.sort()
    return scored[0][2]


def enrich_finish_answer(
    finish_text: str,
    *,
    thought: str = "",
    facts: list[str] | None = None,
    goal: str = "",
) -> str:
    """若 finish 空壳：优先用 thought 中的要点列表，其次用搜索事实重写。

    回填后若质量门控不通过（标题清单/薄列表），返回空串，迫使走合成。
    """
    from agent.delivery_gate import get_default_delivery_gate

    text = sanitize_public_answer(finish_text or "")
    facts = facts or []
    if not is_hollow_answer(text):
        cleaned = _strip_search_engine_urls(text)
        candidate = cleaned or text
        # 不合格草稿保留原文，由 finalize 强制扩写；此处不清空以免丢失扩写种子
        return candidate

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
        candidate = sanitize_public_answer(body)
        v = get_default_delivery_gate().check_draft(goal=goal, draft=candidate, facts=facts)
        if not v.ok:
            return ""
        return candidate

    from_entities = format_entity_list_answer(goal, extract_grounded_entities_from_facts(facts, goal=goal))
    if from_entities and not is_thin_list_draft(from_entities):
        v = get_default_delivery_gate().check_draft(goal=goal, draft=from_entities, facts=facts)
        if not v.ok:
            return ""
        return from_entities

    return text


def reject_or_pass_final_answer(
    *,
    goal: str,
    answer: str,
    facts: list[str] | None = None,
) -> str | None:
    """终稿质量门：合格返回文本，否则 None（编排层应扩写或兜底）。"""
    from agent.delivery_gate import reject_or_pass_final

    return reject_or_pass_final(goal=goal, answer=answer, facts=facts)


def first_content_urls_from_facts(facts: list[str], *, limit: int = 3) -> list[str]:
    """从搜索事实里抽出可 web_fetch 的内容站链接（跳过搜索引擎结果页/跳转壳）。"""
    try:
        from tools.web_tools import is_content_fetch_url
    except Exception:

        def is_content_fetch_url(u: str) -> bool:  # type: ignore
            low = (u or "").lower()
            return not any(
                x in low
                for x in (
                    "sogou.com",
                    "bing.com/search",
                    "duckduckgo.com",
                    "google.com/search",
                )
            )

    urls: list[str] = []
    for f in facts:
        for m in re.finditer(r"https?://[^\s\]\)\"\'<>]+", f):
            u = m.group(0).rstrip(".,;，。")
            if not is_content_fetch_url(u):
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
    brief = re.sub(r"\s+", " ", text).strip()[:2200]
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
