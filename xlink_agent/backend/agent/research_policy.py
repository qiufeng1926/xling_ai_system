"""调研深度策略：决定何时继续搜/抓，避免材料不足就 finish。

能力层通用规则，不绑定具体书名/新闻业务。
"""

from __future__ import annotations

import re
from typing import Any

from agent.answer import (
    has_substantive_content_facts,
    pick_fetch_url,
)

_DEEP_MARKERS = (
    "详细",
    "深入",
    "仔细",
    "全面",
    "系统",
    "完整",
    "讲讲",
    "说说",
    "介绍一下",
    "介绍下",
    "展开",
    "解读",
    "分析",
    "综述",
    "概览",
    "全书",
    "大纲",
    "结构",
    "章节",
    "详解",
    "深度",
    "尽量多",
    "越详细越好",
)

_SHALLOW_MARKERS = (
    "一句话",
    "简短",
    "简要",
    "简介",
    "是谁",
    "是什么意思",
)


def is_deep_research_goal(goal: str) -> bool:
    g = (goal or "").strip()
    if not g:
        return False
    if any(k in g for k in _SHALLOW_MARKERS):
        return False
    if any(k in g for k in _DEEP_MARKERS):
        return True
    # 「说说/讲讲 XXX」类
    if re.search(r"(详细|深入)?(说|讲|介绍|解读|分析).{0,6}(一下|下)?", g):
        return True
    # 较长的说明类问题
    if len(g) >= 16 and re.search(r"(什么|如何|怎样|为何|为什么|哪些|怎么看)", g):
        return True
    return False


def count_search_steps(steps: list[Any]) -> int:
    n = 0
    for s in steps or []:
        action = getattr(s, "action", None) or (s.get("action") if isinstance(s, dict) else "")
        if action == "web_search":
            n += 1
    return n


def count_fetch_steps(steps: list[Any]) -> int:
    n = 0
    for s in steps or []:
        action = getattr(s, "action", None) or (s.get("action") if isinstance(s, dict) else "")
        if action in {"web_fetch", "http_request", "browser_extract", "browser_navigate"}:
            n += 1
    return n


def count_body_facts(facts: list[str]) -> int:
    from agent.answer import is_nav_chrome_body

    n = 0
    for f in facts or []:
        if f.startswith(
            ("网页正文摘要", "网页内容摘要", "页面内容摘要", "网页摘录")
        ) or "正文条目线索" in f[:24]:
            if len(f) >= 80 and not is_nav_chrome_body(f):
                n += 1
    return n


def min_searches_for_goal(goal: str) -> int:
    return 2 if is_deep_research_goal(goal) else 1


def min_bodies_for_goal(goal: str) -> int:
    return 3 if is_deep_research_goal(goal) else 1


def alt_search_queries(goal: str, prior_queries: list[str] | None = None) -> list[str]:
    """为深度调研生成补充检索词（去重）。"""
    g = re.sub(r"\s+", " ", (goal or "").strip())
    # 去掉「详细说说」等动词，抽出主题核
    core = re.sub(
        r"(请|帮我|给我|详细|深入|仔细|全面|系统|完整)?(说|讲|介绍|解读|分析|聊聊|讲讲|说说)(一下|下)?",
        "",
        g,
    ).strip(" ：:，,")
    if not core:
        core = g
    prior = {p.strip() for p in (prior_queries or []) if p and p.strip()}
    cands = [
        g,
        core,
        f"{core} 内容结构 章节",
        f"{core} 核心观点 综述",
        f"{core} 作者简介 评价",
        f"{core} summary outline",
    ]
    out: list[str] = []
    for q in cands:
        q = re.sub(r"\s+", " ", q).strip()
        if len(q) < 2 or q in prior or q in out:
            continue
        out.append(q)
        if len(out) >= 4:
            break
    return out


def prior_search_queries(steps: list[Any]) -> list[str]:
    qs: list[str] = []
    for s in steps or []:
        action = getattr(s, "action", None) or (s.get("action") if isinstance(s, dict) else "")
        if action != "web_search":
            continue
        ain = getattr(s, "action_input", None)
        if ain is None and isinstance(s, dict):
            ain = s.get("action_input")
        if isinstance(ain, dict):
            q = str(ain.get("query") or "").strip()
        else:
            q = str(ain or "").strip()
        if q:
            qs.append(q)
    return qs


def has_search_hit_facts(facts: list[str]) -> bool:
    return any((f or "").startswith("搜索结果") for f in (facts or []))


def can_finish_research(
    *,
    goal: str,
    facts: list[str],
    steps: list[Any],
    failed_urls: list[str] | None = None,
) -> tuple[bool, str]:
    """finish 前硬门控：(是否允许交付, 拦截 reason)。

    委托 AnswerQualityGate.check_research，保持签名兼容。
    reason 可能为 weak_materials（允许 finish，但 finalize 须强制合成）。
    """
    from agent.delivery_gate import get_default_delivery_gate

    v = get_default_delivery_gate().check_research(
        goal=goal, facts=facts, steps=steps, failed_urls=failed_urls
    )
    return v.ok, v.reason


def next_research_tool(
    *,
    goal: str,
    facts: list[str],
    steps: list[Any],
    failed_urls: list[str] | None = None,
    round_i: int = 0,
    max_rounds: int = 12,
) -> dict[str, Any] | None:
    """若材料不足以支撑充分答复，返回下一步应执行的 tool 动作；否则 None。"""
    if round_i >= max_rounds - 1:
        return None

    from agent.delivery_gate import get_default_delivery_gate

    deep = is_deep_research_goal(goal)
    searches = count_search_steps(steps)
    bodies = count_body_facts(facts)
    min_b = min_bodies_for_goal(goal)
    skip = set(failed_urls or [])

    verdict = get_default_delivery_gate().check_research(
        goal=goal, facts=facts, steps=steps, failed_urls=failed_urls
    )
    # 允许 finish（含 weak_materials）→ 不再强制取数
    if verdict.ok:
        return None

    reason = verdict.reason or "need_more_research"

    if reason in {"no_search_yet", "need_alt_search"} or searches < 1:
        if searches < 1:
            return {
                "tool": "web_search",
                "args": {"query": goal},
                "think": "自动补搜索",
                "reason": "no_search_yet",
            }
        alts = alt_search_queries(goal, prior_search_queries(steps))
        if alts:
            return {
                "tool": "web_search",
                "args": {"query": alts[0]},
                "think": "换角度补充检索",
                "reason": "need_alt_search",
            }

    if reason in {"search_hits_no_body", "need_more_bodies"}:
        next_u = pick_fetch_url(facts, skip=skip)
        if next_u:
            return {
                "tool": "web_fetch",
                "args": {"url": next_u},
                "think": f"继续抓取正文以充实材料（已有 {bodies}/{min_b if deep else 1}）",
                "reason": reason,
            }
        reason = "search_for_more_sources"

    if reason == "search_for_more_sources" and round_i < max_rounds - 2:
        alts = alt_search_queries(goal, prior_search_queries(steps))
        if alts:
            return {
                "tool": "web_search",
                "args": {"query": alts[-1] if len(alts) > 1 else alts[0]},
                "think": "正文不足，再搜补充来源",
                "reason": "search_for_more_sources",
            }

    if deep and bodies < min_b:
        next_u = pick_fetch_url(facts, skip=skip)
        if next_u:
            return {
                "tool": "web_fetch",
                "args": {"url": next_u},
                "think": f"继续抓取正文以充实材料（已有 {bodies}/{min_b}）",
                "reason": "need_more_bodies",
            }

    if (
        not deep
        and has_search_hit_facts(facts)
        and bodies < 1
        and not has_substantive_content_facts(facts)
    ):
        next_u = pick_fetch_url(facts, skip=skip)
        if next_u:
            return {
                "tool": "web_fetch",
                "args": {"url": next_u},
                "think": "已有搜索结果，先打开正文再总结（禁止只交标题或让用户选编号）",
                "reason": "search_hits_no_body",
            }

    return None


def research_status_line(goal: str, facts: list[str], steps: list[Any]) -> str:
    deep = is_deep_research_goal(goal)
    bodies = count_body_facts(facts)
    searches = count_search_steps(steps)
    min_s = min_searches_for_goal(goal)
    min_b = min_bodies_for_goal(goal)
    ok, reason = can_finish_research(goal=goal, facts=facts, steps=steps)
    enough = ok
    tip = "材料可尝试总结交付" if enough else f"材料仍偏少（{reason or '需继续取数'}），请先取数再 finish"
    extra = (
        f"（深度任务建议 ≥{min_s} 次搜索、≥{min_b} 篇正文）" if deep else ""
    )
    return f"- 调研进度: 搜索 {searches} 次 / 正文页 {bodies} 篇{extra}；{tip}"
