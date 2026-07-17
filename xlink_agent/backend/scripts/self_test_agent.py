#!/usr/bin/env python3
"""xlink-agent 交付前自测：多场景 + 多轮对话（无需 DB / 真实 LLM）。

用法（在 xlink_agent/backend 目录）:
    python scripts/self_test_agent.py
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

# 保证可 import agent.*
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""


class MockModel:
    """可配置 chat 返回值，用于模拟总结器误杀草稿等场景。"""

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[list[dict]] = []

    async def chat(self, messages, temperature=0.2):
        self.calls.append(messages)
        if self.responses:
            return self.responses.pop(0)
        return ""


def _msg(role: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, content=content)


def _history(pairs: list[tuple[str, str]]) -> list[SimpleNamespace]:
    out: list[SimpleNamespace] = []
    for u, a in pairs:
        out.append(_msg("user", u))
        out.append(_msg("assistant", a))
    return out


def test_substantive_draft() -> CaseResult:
    from agent.answer import is_substantive_draft

    draft = (
        "以下是我为您推荐的7本经济类型的书籍：《穷查理宝典》、《国富论》、"
        "《资本论》、《经济学原理》、《投资最重要的事》、《金融的逻辑》、《债务危机》。"
    )
    ok = is_substantive_draft(draft, "推荐7本经济类型的书籍给我")
    return CaseResult("substantive_draft_7_books", ok, "draft should be substantive")


async def test_finalize_keeps_draft_when_no_materials() -> CaseResult:
    """复现用户 bug：总结器说「没有材料」时，应保留 ReAct finish 草稿。"""
    from agent.context import TaskContext
    from agent.orchestrator import _finalize_user_answer
    from agent.run_state import AgentRunState, FinalizePath

    # 已较充实、不应再强制扩写的草稿
    draft = (
        "为您推荐几本经济入门书（供参考）：\n"
        "1. **国富论**\n亚当·斯密著，讨论分工与市场如何促进财富增长，适合想了解古典经济学的读者。\n"
        "2. **经济学原理**\n曼昆的通识教材，案例多、入门友好，适合零基础系统学习。"
    )
    model = MockModel(
        [
            "很抱歉，目前没有提供具体的书籍材料，因此无法根据检索材料推荐。",
        ]
    )
    ctx = TaskContext(goal="推荐经济类型的书籍给我")
    rs = AgentRunState(run_id="test", goal=ctx.goal)
    out = await _finalize_user_answer(
        model, ctx, draft, round_i=3, thought="可以交付了", run_state=rs
    )
    ok = "国富论" in out and "没有材料" not in out
    path_ok = rs.finalize_path in {
        FinalizePath.DRAFT_DIRECT_NO_MATERIALS.value,
        FinalizePath.DRAFT_EXPANDED.value,
    }
    return CaseResult(
        "finalize_no_materials_keeps_draft",
        ok and path_ok,
        f"path={rs.finalize_path} out_preview={out[:80]}",
    )


async def test_synthesize_early_return() -> CaseResult:
    from agent.answer import synthesize_rich_answer

    draft = (
        "以下是我为您推荐的7本经济类型的书籍：《穷查理宝典》、《国富论》、"
        "《资本论》、《经济学原理》、《投资最重要的事》、《金融的逻辑》、《债务危机》。"
    )
    # 模拟总结器误杀：应回退草稿，而不是交「没有材料」
    model = MockModel(["很抱歉，没有检索材料，无法推荐。"])
    out = await synthesize_rich_answer(
        model,
        goal="推荐7本经济书",
        facts=[],
        draft=draft,
        force_expand=True,
    )
    ok = "国富论" in out and "没有材料" not in out and "没有检索" not in out
    return CaseResult("synthesize_early_return_draft", ok, out[:80])


async def test_thin_draft_requests_expand() -> CaseResult:
    from agent.answer import is_thin_list_draft, answer_depth_score

    thin = "推荐如下：《国富论》、《资本论》、《经济学原理》。"
    rich = (
        "以下为经济入门书单（供参考）：\n"
        "1. **国富论**\n亚当·斯密著，奠定古典经济学。书中讨论分工与市场，适合想了解市场经济起源的读者。\n"
        "2. **资本论**\n马克思对资本主义的分析，偏理论，适合有一定基础后再读。"
    )
    ok = is_thin_list_draft(thin) and not is_thin_list_draft(rich) and answer_depth_score(rich) > answer_depth_score(thin)
    return CaseResult("thin_draft_detect", ok)


async def test_finalize_expands_thin_draft() -> CaseResult:
    from agent.context import TaskContext
    from agent.orchestrator import _finalize_user_answer
    from agent.run_state import AgentRunState, FinalizePath

    draft = "推荐7本：《穷查理宝典》、《国富论》、《资本论》、《经济学原理》、《投资最重要的事》、《金融的逻辑》、《债务危机》。"
    expanded = (
        "为您推荐7本经济类书籍（供参考）：\n"
        "1. **穷查理宝典**\n查理·芒格的投资智慧合集，强调多元思维模型，适合投资者与决策者。\n"
        "2. **国富论**\n亚当·斯密奠基之作，讨论分工、市场与财富增长。\n"
        "3. **资本论**\n马克思对资本主义运行的系统分析。\n"
        "4. **经济学原理**\n曼昆教材，入门友好。\n"
        "5. **投资最重要的事**\n霍华德·马克斯谈风险与周期。\n"
        "6. **金融的逻辑**\n陈志武通俗讲解金融作用。\n"
        "7. **债务危机**\n达利欧对债务周期的框架梳理。"
    )
    model = MockModel([expanded])
    ctx = TaskContext(goal="推荐7本经济类型的书籍给我")
    rs = AgentRunState(run_id="test", goal=ctx.goal)
    out = await _finalize_user_answer(
        model, ctx, draft, round_i=2, thought="可以交付了", run_state=rs
    )
    ok = (
        rs.finalize_path == FinalizePath.DRAFT_EXPANDED.value
        and "曼昆" in out
        and len(out) > len(draft)
    )
    return CaseResult(
        "finalize_expands_thin_draft",
        ok,
        f"path={rs.finalize_path} len={len(out)}",
    )


def test_web_search_duplicate_logic() -> CaseResult:
    """第一次搜索不应被判定为重复（曾导致搜索永远不执行）。"""
    from agent.react import ReactScratchpad

    def is_duplicate(scratchpad: ReactScratchpad, q: str) -> bool:
        prior_q = [
            str((s.action_input or {}).get("query") or "").strip()
            if isinstance(s.action_input, dict)
            else ""
            for s in scratchpad.steps
            if s.action == "web_search"
        ]
        return bool(q and q in prior_q)

    pad = ReactScratchpad()
    q = "经济类型书籍推荐"
    first_blocked = is_duplicate(pad, q)
    pad.add_thought_action("搜", "web_search", {"query": q}, 0)
    pad.set_observation("（模拟）")
    second_blocked = is_duplicate(pad, q)
    ok = not first_blocked and second_blocked
    return CaseResult(
        "web_search_duplicate_logic",
        ok,
        f"first={first_blocked} second={second_blocked}",
    )


def test_memory_new_question_isolation() -> CaseResult:
    from agent.memory_policy import (
        build_dialog_messages,
        goal_shifted,
        is_dialog_followup,
        is_new_independent_question,
    )

    prev = "推荐7本经济类型的书籍给我"
    cur = "什么是 AI Agent"
    ok = (
        is_new_independent_question(cur)
        and not is_dialog_followup(cur, prev)
        and goal_shifted(prev, cur)
    )
    hist = _history(
        [
            (prev, "1. 国富论 … 7. 债务危机"),
            (cur, ""),
        ]
    )
    msgs = build_dialog_messages(
        hist,
        current_goal=cur,
        sanitize_fn=lambda x: x,
        looks_internal_fn=lambda x: False,
    )
    # 换题后不应把上一轮书单全文塞进 prompt
    blob = "\n".join(m["content"] for m in msgs if m["role"] == "user")
    no_book_leak = "国富论" not in blob and "债务危机" not in blob
    return CaseResult(
        "memory_new_question_isolation",
        ok and no_book_leak,
        f"msgs={len(msgs)} leak={not no_book_leak}",
    )


def test_dialog_followup_expansion() -> CaseResult:
    from agent.memory_policy import expand_dialog_followup, is_dialog_followup

    # orchestrator 在写入本轮 user 消息后调用 expand；history 末条是当前 user
    hist = _history([("推荐7本经济类型的书籍给我", "（上一轮未能获取完整列表）")])
    hist.append(_msg("user", "你为什么获取不了"))
    cur = "你为什么获取不了"
    ok_follow = is_dialog_followup(cur, "推荐7本经济类型的书籍给我")
    expanded = expand_dialog_followup(cur, hist, sanitize_fn=lambda x: x)
    ok = ok_follow and expanded is not None and "经济" in expanded
    return CaseResult(
        "dialog_followup_why_fail",
        ok,
        f"expanded={expanded!r}" if expanded else "expanded=None",
    )


def test_fact_cross_topic_filter() -> CaseResult:
    from agent.memory_policy import fact_relevant_to_goal

    goal = "推荐7本经济类型的书籍给我"
    news = "国际要闻：某国央行加息引发市场波动"
    book = "经济类经典书籍《国富论》，亚当·斯密著，奠定现代经济学基础"
    ok = not fact_relevant_to_goal(news, goal) and fact_relevant_to_goal(book, goal)
    return CaseResult("fact_cross_topic_filter", ok)


def test_run_state_attribution() -> CaseResult:
    from agent.run_state import AgentRunState, FinalizePath, RunPhase

    rs = AgentRunState(run_id="abc", goal="测试")
    rs.transition(RunPhase.INIT)
    rs.begin_round(0)
    rs.intercept("duplicate_web_search", round_i=0, query="test")
    rs.record_finalize(FinalizePath.DRAFT_DIRECT_NO_MATERIALS, "答案预览", round_i=0)
    rs.record_delivered("答案预览")
    rs.complete()
    d = rs.to_dict()
    ok = (
        rs.phase == RunPhase.COMPLETE
        and rs.finalize_path == FinalizePath.DRAFT_DIRECT_NO_MATERIALS.value
        and len(d["transitions"]) >= 4
        and d["answer_snapshots"][-1]["label"] == "delivered"
    )
    return CaseResult("run_state_attribution", ok, rs.attribution_summary())


def test_continue_recommend_books() -> CaseResult:
    """多轮续作：再来三本 — 应识别为追问而非独立新题。"""
    from agent.memory_policy import expand_dialog_followup, is_dialog_followup, is_new_independent_question

    prev = "推荐5本治愈系书籍"
    cur = "再来三本"
    ok = (
        is_dialog_followup(cur, prev)
        and not is_new_independent_question(cur)
    )
    hist = _history([(prev, "1. 小王子 …")])
    hist.append(_msg("user", cur))
    expanded = expand_dialog_followup(cur, hist, sanitize_fn=lambda x: x)
    return CaseResult(
        "continue_three_more_books",
        ok and expanded is not None and "追加" in (expanded or ""),
        f"expanded={expanded!r}" if expanded else "expanded=None",
    )


def test_checkpoint_roundtrip() -> CaseResult:
    from agent.checkpoint import (
        build_confirm_checkpoint,
        parse_checkpoint,
        restore_scratchpad,
        restore_task_context,
    )
    from agent.context import TaskContext
    from agent.react import ReactScratchpad
    import json

    ctx = TaskContext(goal="删除文件")
    ctx.add_fact("工作区有 a.docx")
    ctx.mark_failed_url("https://bad.example")
    pad = ReactScratchpad()
    pad.add_thought_action("准备删除", "file_delete", {"name": "a.docx"}, 1)
    pad.set_observation("等待确认")
    ckpt = build_confirm_checkpoint(
        tool="file_delete",
        args={"name": "a.docx"},
        task_ctx=ctx,
        scratchpad=pad,
        round_i=1,
        run_id="run123",
        tools=["file_delete", "web_search"],
        effective_goal="删除文件",
    )
    raw = json.dumps(ckpt, ensure_ascii=False)
    data = parse_checkpoint(raw)
    ctx2 = restore_task_context(data.get("task_context"))
    pad2 = restore_scratchpad(data.get("react_steps"))
    ok = (
        ctx2.goal == "删除文件"
        and "工作区有 a.docx" in ctx2.facts
        and "https://bad.example" in ctx2.failed_urls
        and len(pad2.steps) == 1
        and pad2.steps[0].action == "file_delete"
        and data.get("tool") == "file_delete"
        and data.get("round_i") == 1
    )
    return CaseResult("checkpoint_roundtrip", ok)


def test_build_citations() -> CaseResult:
    from agent.answer import build_citations

    facts = [
        "搜索结果(bing):\n"
        "1. 国富论导读 — 亚当斯密经典\n"
        "链接: https://example.com/wealth\n"
        "2. 经济学入门书单 — 合集\n"
        "链接: https://sogou.com/web?query=econ\n",
        "网页正文摘要 标题: 资本论精读\nhttps://example.com/capital 正文……",
    ]
    cites = build_citations(facts)
    urls = [c.get("url") for c in cites]
    ok = (
        any("example.com/wealth" in (u or "") for u in urls)
        and not any("sogou.com/web" in (u or "") for u in urls)
        and len(cites) >= 1
    )
    return CaseResult("build_citations", ok, f"n={len(cites)} urls={urls}")


def test_trajectory_labels() -> CaseResult:
    from agent.trajectory import action_step, confirm_tool_label, intercept_step

    a = action_step("web_search", {"query": "经济书籍"}, round_i=0)
    i = intercept_step("duplicate_web_search", round_i=1, detail="重复")
    ok = (
        a["title"] == "搜索公开网页"
        and "经济书籍" in a["detail"]
        and i["kind"] == "intercept"
        and confirm_tool_label("file_delete") == "删除工作区文件"
    )
    return CaseResult("trajectory_labels", ok, str(a))


def test_deep_research_policy() -> CaseResult:
    from agent.react import ReactScratchpad
    from agent.research_policy import (
        is_deep_research_goal,
        min_bodies_for_goal,
        next_research_tool,
        alt_search_queries,
    )

    goal = "详细说说全球通史"
    ok_deep = is_deep_research_goal(goal) and min_bodies_for_goal(goal) >= 3
    pad = ReactScratchpad()
    pad.add_thought_action("搜", "web_search", {"query": goal}, 0)
    pad.set_observation("搜索结果…")
    # 仅 1 次搜索 → 应要求换角度再搜
    nxt = next_research_tool(
        goal=goal,
        facts=["搜索结果:\n1. 介绍 — 摘要\n链接: https://example.com/a"],
        steps=pad.steps,
        round_i=1,
        max_rounds=12,
    )
    ok_alt = nxt is not None and nxt.get("tool") == "web_search"
    # 已 2 次搜索、0 正文 → 应 fetch
    pad.add_thought_action("再搜", "web_search", {"query": "全球通史 章节"}, 1)
    pad.set_observation("ok")
    nxt2 = next_research_tool(
        goal=goal,
        facts=["搜索结果:\n1. 介绍 — 摘要\n链接: https://example.com/a\n2. 结构 — 摘要\n链接: https://example.com/b"],
        steps=pad.steps,
        round_i=2,
        max_rounds=12,
    )
    ok_fetch = nxt2 is not None and nxt2.get("tool") == "web_fetch"
    alts = alt_search_queries(goal, [goal])
    ok_q = len(alts) >= 1 and all(a != goal for a in alts)
    return CaseResult(
        "deep_research_policy",
        ok_deep and ok_alt and ok_fetch and ok_q,
        f"alt={ok_alt} fetch={ok_fetch} queries={alts}",
    )


async def run_all() -> list[CaseResult]:
    results: list[CaseResult] = []
    sync_tests = [
        test_substantive_draft,
        test_web_search_duplicate_logic,
        test_memory_new_question_isolation,
        test_dialog_followup_expansion,
        test_fact_cross_topic_filter,
        test_run_state_attribution,
        test_continue_recommend_books,
        test_checkpoint_roundtrip,
        test_build_citations,
        test_trajectory_labels,
        test_deep_research_policy,
    ]
    for fn in sync_tests:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(CaseResult(fn.__name__, False, str(exc)))

    for coro in [
        test_finalize_keeps_draft_when_no_materials(),
        test_synthesize_early_return(),
        test_thin_draft_requests_expand(),
        test_finalize_expands_thin_draft(),
    ]:
        try:
            results.append(await coro)
        except Exception as exc:
            results.append(CaseResult("async_test", False, str(exc)))
    return results


def main() -> int:
    results = asyncio.run(run_all())
    passed = sum(1 for r in results if r.ok)
    total = len(results)
    print("=" * 60)
    print(f"xlink-agent self_test: {passed}/{total} passed")
    print("=" * 60)
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] {r.name}")
        if r.detail:
            print(f"         {r.detail}")
    print("=" * 60)
    if passed < total:
        print("FAILED — 请修复后再交付")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
