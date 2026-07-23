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
    "调研",
    "研究报告",
    "市场情况",
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


def is_deep_research_goal(goal: str, *, profile: Any | None = None) -> bool:
    g = (goal or "").strip()
    if not g:
        return False
    # 意图驱动：调研 / 高事实风险默认更深
    if profile is not None:
        intent = getattr(profile, "intent", None)
        risk = getattr(profile, "risk", None)
        intent_v = getattr(intent, "value", intent)
        risk_v = getattr(risk, "value", risk)
        if intent_v in {"chitchat", "code_gen"}:
            return False
        if intent_v == "research" or risk_v == "high_fact":
            return True
        if intent_v == "list_recommend":
            return False  # 清单题走材料可用判定，不强制深研正文数
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


def count_body_facts(facts: list[str], *, goal: str = "") -> int:
    from agent.answer import is_nav_chrome_body, is_off_topic_body_for_goal

    n = 0
    for f in facts or []:
        if f.startswith(
            ("网页正文摘要", "网页内容摘要", "页面内容摘要", "网页摘录")
        ) or "正文条目线索" in f[:24]:
            if len(f) >= 80 and not is_nav_chrome_body(f):
                if goal and is_off_topic_body_for_goal(f, goal):
                    continue
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
    from agent.answer import is_count_list_goal

    if is_count_list_goal(g):
        cands = [
            g,
            f"{core} 清单 具体名称",
            f"{core} 推荐 盘点",
            f"{core} 入门 列表",
            f"{core} 排行 具体条目",
        ] + cands
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


def prefers_openlibrary_catalog(goal: str) -> bool:
    """目标像书籍/作品清单时，可用 Open Library 核验或发现。"""
    g = goal or ""
    return any(k in g for k in ("书", "书籍", "书单", "小说", "著作", "阅读"))


def openlibrary_discover_args(goal: str, *, want: int = 10) -> dict[str, Any]:
    """从用户目标抽出发现检索参数。"""
    from agent.answer import requested_list_count

    g = (goal or "").strip()
    core = re.sub(
        r"(给我|请|帮我)?(推荐|介绍|盘点|整理|列出)?\s*\d*\s*(本|部|册|种)?",
        "",
        g,
    )
    core = re.sub(
        r"(相关的?)?(书籍|书单|图书|小说|著作|读物|书)(推荐|清单)?",
        "",
        core,
    ).strip(" ：:，,。.")
    if not core or len(core) < 2:
        core = g[:40]
    n = requested_list_count(g) or want
    limit = max(5, min(12, int(n)))
    subject = ""
    subject_map = {
        "历史": "history",
        "经济": "economics",
        "哲学": "philosophy",
        "科学": "science",
        "计算机": "computers",
        "心理": "psychology",
    }
    for zh, en in subject_map.items():
        if zh in core:
            subject = en
            break
    args: dict[str, Any] = {"q": core[:80], "limit": limit}
    if subject:
        args["subject"] = subject
    return args


def prior_openlibrary_fingerprints(steps: list[Any]) -> list[str]:
    out: list[str] = []
    for s in steps or []:
        action = getattr(s, "action", None) or (s.get("action") if isinstance(s, dict) else "")
        if action != "openlibrary_lookup":
            continue
        ain = getattr(s, "action_input", None)
        if ain is None and isinstance(s, dict):
            ain = s.get("action_input")
        if not isinstance(ain, dict):
            continue
        qs = ain.get("queries") or []
        if isinstance(qs, list):
            key = "|".join(sorted(str(x).strip().lower() for x in qs if str(x).strip()))
        else:
            key = ""
        topic = str(ain.get("subject") or ain.get("q") or "").strip().lower()
        fp = f"q={key};t={topic}"
        if fp not in out:
            out.append(fp)
    return out


def openlibrary_args_fingerprint(args: dict[str, Any] | None) -> str:
    ain = args or {}
    qs = ain.get("queries") or []
    if isinstance(qs, list):
        key = "|".join(sorted(str(x).strip().lower() for x in qs if str(x).strip()))
    else:
        key = ""
    topic = str(ain.get("subject") or ain.get("q") or "").strip().lower()
    return f"q={key};t={topic}"


def has_openlibrary_facts(facts: list[str]) -> bool:
    return any(
        (f or "").startswith("书目核验(Open Library)")
        or "书目发现(Open Library)" in (f or "")[:80]
        for f in (facts or [])
    )


# 搜索词噪声：去掉后用于近义重复判定（「…影响」vs「…具体影响」）
_SEARCH_QUERY_NOISE = re.compile(
    r"(具体|详细|深入|进一步|全面|系统|完整|简要|简介|"
    r"的影响|影响|分析|了解|查询|搜索|调研|情况|问题|"
    r"是什么|如何|怎样|怎么|为何|为什么|哪些|多少|"
    r"吗|呢|啊|吧|了|的|与|和|对|关于)"
)


def normalize_search_query(q: str) -> str:
    """归一化搜索词，便于近义重复判定。"""
    t = (q or "").strip().lower()
    t = re.sub(r"\s+", "", t)
    t = _SEARCH_QUERY_NOISE.sub("", t)
    return t


def is_near_duplicate_search_query(q: str, prior: list[str]) -> bool:
    """相同或近义搜索词（仅改「具体/详细」等）视为重复。"""
    nq = normalize_search_query(q)
    raw_q = re.sub(r"\s+", "", (q or "").strip().lower())
    if not nq and not raw_q:
        return False
    for p in prior or []:
        if not p:
            continue
        raw_p = re.sub(r"\s+", "", p.strip().lower())
        if raw_q and raw_q == raw_p:
            return True
        np = normalize_search_query(p)
        if nq and np and nq == np:
            return True
        # 归一化后互相包含（且足够长，避免短词误伤）
        if nq and np and len(nq) >= 4 and len(np) >= 4 and (nq in np or np in nq):
            return True
        # 字符集合高度重合
        if nq and np and len(nq) >= 6 and len(np) >= 6:
            sa, sb = set(nq), set(np)
            inter = len(sa & sb)
            union = len(sa | sb) or 1
            if inter / union >= 0.78 and abs(len(nq) - len(np)) <= max(4, len(nq) // 3):
                return True
    return False


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
    profile: Any | None = None,
) -> dict[str, Any] | None:
    """若材料不足以支撑充分答复，返回下一步应执行的 tool 动作；否则 None。"""
    if round_i >= max_rounds - 1:
        return None

    from agent.delivery.types import FactTier
    from agent.delivery_gate import get_default_delivery_gate

    tier = getattr(profile, "tier", None) if profile is not None else None
    # C 类：不强制检索
    if tier == FactTier.C:
        return None

    deep = is_deep_research_goal(goal, profile=profile)
    searches = count_search_steps(steps)
    bodies = count_body_facts(facts, goal=goal)
    min_b = min_bodies_for_goal(goal)
    skip = set(failed_urls or [])

    # A 类：尚无任何检索 → 强制先搜（可用 profile.search_queries）
    if tier == FactTier.A and searches < 1 and not facts:
        q = goal
        sq = getattr(profile, "search_queries", None) or []
        if sq:
            q = sq[0]
        return {
            "tool": "web_search",
            "args": {"query": q},
            "think": "A 类高事实清单，强制先检索",
            "reason": "fact_tier_a_force_search",
        }

    # A 类荐书：Open Library 发现（仅开关开启时）
    if tier == FactTier.A and prefers_openlibrary_catalog(goal) and not has_openlibrary_facts(facts):
        try:
            from config import config as cfg

            ol_on = bool(getattr(cfg, "openlibrary_enabled", False))
        except Exception:
            ol_on = False
        if ol_on:
            ol_args = openlibrary_discover_args(goal)
            if openlibrary_args_fingerprint(ol_args) not in prior_openlibrary_fingerprints(steps):
                return {
                    "tool": "openlibrary_lookup",
                    "args": ol_args,
                    "think": "A 类：用书目库发现/核验，禁止脱离材料扩条",
                    "reason": "openlibrary_catalog",
                }

    verdict = get_default_delivery_gate().check_research(
        goal=goal, facts=facts, steps=steps, failed_urls=failed_urls
    )
    # 允许 finish（含 weak_materials）→ 不再强制取数；但 A 类无搜索时仍强制
    if verdict.ok and not (tier == FactTier.A and searches < 1):
        return None

    reason = verdict.reason or "need_more_research"

    if reason in {"no_search_yet", "need_alt_search"} or searches < 1:
        if searches < 1:
            q = goal
            sq = getattr(profile, "search_queries", None) or []
            if sq:
                q = sq[0]
            return {
                "tool": "web_search",
                "args": {"query": q},
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
        next_u = pick_fetch_url(facts, skip=skip, goal=goal)
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
        next_u = pick_fetch_url(facts, skip=skip, goal=goal)
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
        next_u = pick_fetch_url(facts, skip=skip, goal=goal)
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
    bodies = count_body_facts(facts, goal=goal)
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
