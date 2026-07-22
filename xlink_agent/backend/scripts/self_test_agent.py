#!/usr/bin/env python3
"""xlink-agent 交付前自测：多场景 + 多轮对话（无需 DB / 真实 LLM）。

用法（在 xlink_agent/backend 目录）:
    python scripts/self_test_agent.py
"""

from __future__ import annotations

import asyncio
import re
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

    # 充实说明才算可交；纯书名堆叠应被质量门拒绝
    thin = (
        "以下是我为您推荐的7本经济类型的书籍：《穷查理宝典》、《国富论》、"
        "《资本论》、《经济学原理》、《投资最重要的事》、《金融的逻辑》、《债务危机》。"
    )
    draft = (
        "为您推荐几本经济入门书（供参考）：\n"
        "1. **国富论**\n亚当·斯密著，讨论分工与市场如何促进财富增长，适合想了解古典经济学的读者。\n"
        "2. **经济学原理**\n曼昆的通识教材，案例多、入门友好，适合零基础系统学习。\n"
        "3. **投资最重要的事**\n霍华德·马克斯谈风险与周期，适合想建立投资思维框架的读者。"
    )
    ok_thin = not is_substantive_draft(thin, "推荐7本经济类型的书籍给我")
    ok = is_substantive_draft(draft, "推荐经济类型的书籍给我")
    return CaseResult(
        "substantive_draft_7_books",
        ok and ok_thin,
        f"substantive={ok} thin_rejected={ok_thin}",
    )


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
        rs.finalize_path
        in {
            FinalizePath.DRAFT_EXPANDED.value,
            FinalizePath.DRAFT_DIRECT_NO_MATERIALS.value,
        }
        and ("曼昆" in out or "国富论" in out or "经济学原理" in out)
        and out.count("《") >= 5
    )
    return CaseResult(
        "finalize_expands_thin_draft",
        ok,
        f"path={rs.finalize_path} len={len(out)}",
    )


def test_web_search_duplicate_logic() -> CaseResult:
    """第一次搜索不应被判定为重复；近义 query 应判重复。"""
    from agent.react import ReactScratchpad
    from agent.research_policy import is_near_duplicate_search_query

    def is_duplicate(scratchpad: ReactScratchpad, q: str) -> bool:
        prior_q = [
            str((s.action_input or {}).get("query") or "").strip()
            if isinstance(s.action_input, dict)
            else ""
            for s in scratchpad.steps
            if s.action == "web_search"
        ]
        return bool(q and is_near_duplicate_search_query(q, prior_q))

    pad = ReactScratchpad()
    q = "经济类型书籍推荐"
    first_blocked = is_duplicate(pad, q)
    pad.add_thought_action("搜", "web_search", {"query": q}, 0)
    pad.set_observation("（模拟）")
    second_blocked = is_duplicate(pad, q)
    near = is_near_duplicate_search_query(
        "git操作对Token消耗量的具体影响",
        ["git操作对Token消耗量的影响"],
    )
    distinct = is_near_duplicate_search_query(
        "资治通鉴讲了什么",
        ["git操作对Token消耗量的影响"],
    )
    ok = not first_blocked and second_blocked and near and not distinct
    return CaseResult(
        "web_search_duplicate_logic",
        ok,
        f"first={first_blocked} second={second_blocked} near={near} distinct={distinct}",
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
    from agent.trajectory import action_step, confirm_tool_label, intercept_step, observation_step

    a = action_step("web_search", {"query": "经济书籍"}, round_i=0)
    i = intercept_step("search_hits_no_body", round_i=1, detail="先抓正文")
    o = observation_step("web_fetch", round_i=2, ok=False, summary="安全验证", reason="验证码")
    ok = (
        a["title"] == "正在搜索"
        and "经济书籍" in a["detail"]
        and i["kind"] == "intercept"
        and i["title"] == "先打开正文再总结"
        and o["status"] == "fail"
        and "验证码" in (o.get("reason") or o.get("detail") or "")
        and confirm_tool_label("file_delete") == "删除工作区文件（需确认）"
    )
    return CaseResult("trajectory_labels", ok, str(a))


def test_deep_research_policy() -> CaseResult:
    from agent.react import ReactScratchpad
    from agent.research_policy import (
        can_finish_research,
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
    ok_gate, reason = can_finish_research(
        goal=goal,
        facts=["搜索结果:\n1. 介绍 — 摘要\n链接: https://example.com/a"],
        steps=pad.steps,
    )
    ok_hard = (not ok_gate) and reason in {"need_more_bodies", "need_alt_search"}
    return CaseResult(
        "deep_research_policy",
        ok_deep and ok_alt and ok_fetch and ok_q and ok_hard,
        f"alt={ok_alt} fetch={ok_fetch} queries={alts} gate={reason}",
    )


def test_search_hits_no_body_gate() -> CaseResult:
    """浅任务：有搜索命中无正文 → 禁止 finish，应 web_fetch。"""
    from agent.react import ReactScratchpad
    from agent.research_policy import can_finish_research, next_research_tool

    goal = "深圳今天天气怎么样"
    pad = ReactScratchpad()
    pad.add_thought_action("搜", "web_search", {"query": goal}, 0)
    facts = [
        "搜索结果(bing):\n1. 深圳天气 — 多云\n链接: https://example.com/weather\n"
    ]
    ok_finish, reason = can_finish_research(goal=goal, facts=facts, steps=pad.steps)
    nxt = next_research_tool(
        goal=goal, facts=facts, steps=pad.steps, round_i=1, max_rounds=12
    )
    ok = (
        not ok_finish
        and reason == "search_hits_no_body"
        and nxt is not None
        and nxt.get("tool") == "web_fetch"
        and nxt.get("reason") == "search_hits_no_body"
    )
    return CaseResult("search_hits_no_body_gate", ok, f"reason={reason} nxt={nxt}")


def test_strip_pick_number() -> CaseResult:
    from agent.answer import asks_user_to_pick_number, sanitize_public_answer, strip_pick_number_prompts

    raw = "要点如下：\n1. 甲\n2. 乙\n\n请回复编号查看详情"
    cleaned = sanitize_public_answer(raw)
    ok = (
        asks_user_to_pick_number(raw)
        and not asks_user_to_pick_number(cleaned)
        and "甲" in cleaned
        and "回复编号" not in cleaned
        and "乙" in strip_pick_number_prompts(raw)
    )
    return CaseResult("strip_pick_number", ok, cleaned[:80])


def test_file_claim_recover() -> CaseResult:
    from agent.orchestrator import _claims_file_without_artifact, _recover_file_tool

    claim = "已经为你生成了日报.docx，请下载。"
    ok_claim = _claims_file_without_artifact(claim)
    recovered = _recover_file_tool(
        '{"thought":"写文件","action":"finish","action_input":"已生成文档"}',
        "把完整市场分析写入 Word 文档，包含规模、竞争与结论。",
        claim,
        ["file_write_docx", "web_search"],
        goal="写一份市场分析 Word",
        facts=["网页正文摘要: 市场规模增长迅速，竞争加剧，头部集中度提升。"],
    )
    content = str((recovered or {}).get("args", {}).get("content") or "")
    ok = (
        ok_claim
        and recovered is not None
        and recovered.get("tool") == "file_write_docx"
        and len(content.strip()) >= 20
    )
    return CaseResult(
        "file_claim_recover",
        ok,
        f"tool={recovered.get('tool') if recovered else None} content_len={len(content)}",
    )


def test_run_code_sandbox() -> CaseResult:
    from pathlib import Path
    import tempfile

    from tools.code_sandbox import run_python_sandbox

    with tempfile.TemporaryDirectory() as td:
        ok_run = run_python_sandbox("print(sum(range(1, 6)))", workdir=Path(td))
        bad = run_python_sandbox("import os\nprint(os.getcwd())", workdir=Path(td))
        ok = (
            ok_run.get("ok") is True
            and "15" in str(ok_run.get("stdout") or "")
            and bad.get("ok") is False
        )
    return CaseResult("run_code_sandbox", ok, f"ok={ok_run} bad={bad.get('error')}")


def test_delivery_quality_gate() -> CaseResult:
    """答题质量门控 + compose_gates 扩展点。"""
    from agent.delivery_gate import (
        AnswerQualityGate,
        DeliveryVerdict,
        compose_gates,
        get_default_delivery_gate,
        set_default_delivery_gate,
    )
    from agent.react import ReactScratchpad
    from agent.research_policy import can_finish_research

    gate = AnswerQualityGate()
    facts = [
        "搜索结果(bing):\n"
        "1. 2026年aigc该怎么学，小白入行aigc学习指南 - 知乎 — 写在前面\n"
        "链接: https://zhuanlan.zhihu.com/p/1\n"
        "2. 普通人要怎么学习aigc？ - 知乎 — 感谢邀请\n"
        "链接: https://www.zhihu.com/q/2\n"
    ]
    parrot = (
        "根据搜索：\n"
        "1. 2026年aigc该怎么学，小白入行aigc学习指南\n"
        "2. 普通人要怎么学习aigc？\n"
    )
    v_draft = gate.check_draft(goal="如何学习AIGC", draft=parrot, facts=facts)
    if v_draft.ok or v_draft.reason not in {"parrot_titles", "thin_list", "hollow"}:
        return CaseResult("delivery_quality_gate", False, f"parrot not rejected: {v_draft}")

    # 深任务：1 搜 0 正文有 URL → 禁止 finish
    pad = ReactScratchpad()
    pad.add_thought_action("搜", "web_search", {"query": "详细说说如何学习AIGC"}, 0)
    ok1, r1 = can_finish_research(
        goal="详细说说如何学习AIGC",
        facts=facts,
        steps=pad.steps,
    )
    if ok1 or r1 not in {"need_more_bodies", "need_alt_search", "search_hits_no_body"}:
        return CaseResult("delivery_quality_gate", False, f"deep early finish: ok={ok1} r={r1}")

    # 深任务：已搜够且无 URL → weak_materials 允许 finish
    pad2 = ReactScratchpad()
    pad2.add_thought_action("搜1", "web_search", {"query": "详细说说全球通史"}, 0)
    pad2.add_thought_action("搜2", "web_search", {"query": "全球通史 章节"}, 1)
    pad2.add_thought_action("搜3", "web_search", {"query": "全球通史 观点"}, 2)
    ok2, r2 = can_finish_research(
        goal="详细说说全球通史",
        facts=["搜索结果:\n1. 介绍 — 摘要\n"],  # 无内容站 URL
        steps=pad2.steps,
    )
    if not ok2 or r2 != "weak_materials":
        return CaseResult("delivery_quality_gate", False, f"weak_materials expected: ok={ok2} r={r2}")

    # compose_gates：假门控可拦截
    class _BlockAll:
        def check_research(self, **kw):
            return DeliveryVerdict(False, "blocked_by_ext")

        def check_draft(self, **kw):
            return DeliveryVerdict(False, "blocked_by_ext")

        def check_final(self, **kw):
            return DeliveryVerdict(False, "blocked_by_ext")

    composed = compose_gates(AnswerQualityGate(), _BlockAll())
    prev = get_default_delivery_gate()
    try:
        set_default_delivery_gate(composed)
        ok3, r3 = can_finish_research(
            goal="一句话介绍 Python",
            facts=[],
            steps=[],
        )
        if ok3 or r3 != "blocked_by_ext":
            return CaseResult("delivery_quality_gate", False, f"compose fail: {ok3} {r3}")
    finally:
        set_default_delivery_gate(prev)

    good = (
        "学习 AIGC 可按阶段推进：\n"
        "1. **打基础**\n先熟悉大模型对话与提示词，用日常办公任务练手，建立反馈闭环。\n"
        "2. **做作品**\n选图文或短视频一条产线，每周产出可复盘的样例并记录提示词模板。\n"
        "3. **系统化**\n再补工具链、工作流与版权合规，形成可复用的个人方法论。"
    )
    v_ok = gate.check_final(goal="如何学习AIGC", answer=good, facts=facts)
    if not v_ok.ok:
        return CaseResult("delivery_quality_gate", False, f"good answer rejected: {v_ok}")

    return CaseResult("delivery_quality_gate", True, f"parrot={v_draft.reason} weak={r2}")


def test_task_binding() -> CaseResult:
    """TaskID：首问新建、追问续绑、换题切断。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from agent.task_binding import (
        BIND_CONTINUE,
        BIND_NEW,
        BIND_SWITCH,
        extract_constraints,
        resolve_task_binding,
        update_task_after_turn,
    )
    from db.models import Base, ConversationTask

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    hist1 = [SimpleNamespace(role="user", content="推荐5本经济类书籍")]
    t1 = resolve_task_binding(
        db,
        user_id=1,
        conversation_id=9,
        user_text="推荐5本经济类书籍",
        history=hist1,
        effective_goal="推荐5本经济类书籍",
    )
    if t1.bind_mode != BIND_NEW or not t1.task_id:
        return CaseResult("task_binding", False, f"new failed: {t1}")
    if "数量约 5本" not in t1.constraints:
        return CaseResult("task_binding", False, f"constraints={t1.constraints}")

    update_task_after_turn(
        db,
        task_id=t1.task_id,
        user_id=1,
        run_id="r1",
        artifacts=["经济书单.docx"],
        answer_preview="1. 国富论 …",
    )

    hist2 = [
        SimpleNamespace(role="user", content="推荐5本经济类书籍"),
        SimpleNamespace(role="assistant", content="1. 国富论\n2. 经济学原理"),
        SimpleNamespace(role="user", content="再来三本"),
    ]
    t2 = resolve_task_binding(
        db,
        user_id=1,
        conversation_id=9,
        user_text="再来三本",
        history=hist2,
        effective_goal="再来三本",
        forced_followup=True,
    )
    if t2.bind_mode != BIND_CONTINUE or t2.task_id != t1.task_id:
        return CaseResult("task_binding", False, f"continue failed: {t2}")
    if "经济书单.docx" not in t2.artifacts:
        return CaseResult("task_binding", False, f"artifacts lost: {t2.artifacts}")

    inj = t2.render_injection()
    if "TaskID" not in inj or "续作" not in inj:
        return CaseResult("task_binding", False, f"inject weak: {inj[:120]}")

    hist3 = [
        SimpleNamespace(role="user", content="推荐5本经济类书籍"),
        SimpleNamespace(role="assistant", content="1. 国富论"),
        SimpleNamespace(role="user", content="再来三本"),
        SimpleNamespace(role="assistant", content="补充三本…"),
        SimpleNamespace(role="user", content="深圳今天天气怎么样"),
    ]
    t3 = resolve_task_binding(
        db,
        user_id=1,
        conversation_id=9,
        user_text="深圳今天天气怎么样",
        history=hist3,
        effective_goal="深圳今天天气怎么样",
    )
    if t3.bind_mode != BIND_SWITCH or t3.task_id == t1.task_id:
        return CaseResult("task_binding", False, f"switch failed: {t3}")
    if t3.previous_task_id != t1.task_id:
        return CaseResult("task_binding", False, f"prev id missing: {t3.previous_task_id}")

    old = db.query(ConversationTask).filter(ConversationTask.task_id == t1.task_id).first()
    if not old or old.status not in {"abandoned", "completed"}:
        return CaseResult("task_binding", False, f"old status={getattr(old, 'status', None)}")

    if not extract_constraints("请生成一份 Word 报告，只要中文"):
        return CaseResult("task_binding", False, "extract_constraints empty")

    db.close()
    return CaseResult(
        "task_binding",
        True,
        f"new={t1.task_id[:8]} cont={t2.task_id[:8]} switch={t3.task_id[:8]}",
    )


def test_entity_match() -> CaseResult:
    """实体精确匹配：文件名、单据号、刚才那个文件指代。"""
    from agent.entity_match import (
        expand_goal_with_entities,
        extract_query_entities,
        match_entities,
    )

    ents = extract_query_entities("请打开 销售周报.docx，单号 PO-2026001")
    if "销售周报.docx" not in ents or "PO-2026001" not in ents:
        return CaseResult("entity_match", False, f"extract={ents}")

    hist = [
        SimpleNamespace(
            role="assistant",
            content="已生成 销售周报.docx",
            metadata_json='{"files":[{"name":"销售周报.docx","file_id":42}]}',
        ),
        SimpleNamespace(role="user", content="把刚才那个文件发给我"),
    ]
    r = match_entities(
        None,
        user_id=1,
        conversation_id=1,
        user_text="把刚才那个文件发给我",
        task_artifacts=["销售周报.docx", "备份.md"],
        history=hist,
    )
    if not r.deictic_resolved or "销售周报.docx" not in r.top_values():
        return CaseResult("entity_match", False, f"deictic={r.to_dict()}")

    r2 = match_entities(
        None,
        user_id=1,
        conversation_id=1,
        user_text="润色一下销售周报.docx",
        task_artifacts=["销售周报.docx"],
        history=hist,
    )
    if not r2.ok or r2.hits[0].value != "销售周报.docx":
        return CaseResult("entity_match", False, f"literal={r2.to_dict()}")

    # 无关提问不应乱命中
    r3 = match_entities(
        None,
        user_id=1,
        conversation_id=1,
        user_text="今天深圳天气怎么样",
        task_artifacts=["销售周报.docx"],
        history=hist,
    )
    if r3.ok and not r3.deictic_resolved:
        # 无字面实体、无指代 → 应无命中
        return CaseResult("entity_match", False, f"false positive={r3.to_dict()}")

    goal = expand_goal_with_entities("发给我", r)
    if "销售周报.docx" not in goal:
        return CaseResult("entity_match", False, f"expand={goal}")

    inj = r.render_injection()
    if "实体精确匹配" not in inj or "销售周报" not in inj:
        return CaseResult("entity_match", False, f"inject={inj[:100]}")

    return CaseResult(
        "entity_match",
        True,
        f"deictic={r.top_values()} literal={r2.top_values()}",
    )


def test_session_memory() -> CaseResult:
    """长会话压缩摘要 + memory_recall 可逆召回。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from agent.session_memory import (
        filter_history_for_window,
        maybe_compact_conversation,
        prepare_session_window,
        recall_session_memory,
        render_summary_injection,
    )
    from db.models import Base, Conversation, ConversationSummary, Message
    from tools.web_tools import validate_and_normalize_args

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    uid = 1
    conv = Conversation(id=42, user_id=uid, title="session_memory_test")
    db.add(conv)
    db.flush()
    cid = 42
    hist: list[Message] = []
    mid = 1
    for i in range(1, 6):
        u = Message(
            id=mid,
            conversation_id=cid,
            user_id=uid,
            role="user",
            content=f"第{i}轮：请写销售周报要点，关键词 UNIQUE_TOKEN_{i}",
        )
        mid += 1
        db.add(u)
        db.flush()
        a = Message(
            id=mid,
            conversation_id=cid,
            user_id=uid,
            role="assistant",
            content=f"第{i}轮答复：已整理 UNIQUE_TOKEN_{i}，文件 周报{i}.docx",
            metadata_json=f'{{"files":[{{"name":"周报{i}.docx"}}]}}',
        )
        mid += 1
        db.add(a)
        db.flush()
        hist.extend([u, a])
    db.commit()

    created = maybe_compact_conversation(
        db,
        user_id=uid,
        conversation_id=cid,
        history=hist,
        task_id="task_demo",
        keep_user_turns=3,
        trigger_user_turns=5,
    )
    if len(created) < 2:
        return CaseResult("session_memory", False, f"compact count={len(created)}")

    rows = db.query(ConversationSummary).filter(ConversationSummary.conversation_id == cid).all()
    if len(rows) < 2:
        return CaseResult("session_memory", False, f"db rows={len(rows)}")
    if not any("UNIQUE_TOKEN_1" in (r.raw_excerpt or "") for r in rows):
        return CaseResult("session_memory", False, "raw_excerpt missing token")

    covered = set()
    for r in rows:
        covered.update(range(int(r.message_id_from), int(r.message_id_to) + 1))
    windowed = filter_history_for_window(hist, covered_ids=covered, keep_user_turns=3)
    if len(windowed) >= len(hist):
        return CaseResult("session_memory", False, f"window not shrunk {len(windowed)}/{len(hist)}")

    _, inj, views = prepare_session_window(
        db, user_id=uid, conversation_id=cid, history=hist, task_id="task_demo"
    )
    if "会话压缩摘要" not in inj or not views:
        return CaseResult("session_memory", False, f"inject={inj[:120]}")
    if "memory_recall" not in render_summary_injection(views):
        return CaseResult("session_memory", False, "inject missing recall hint")

    sid = rows[0].summary_id
    by_id = recall_session_memory(
        db, user_id=uid, conversation_id=cid, summary_id=sid[:8]
    )
    if not by_id.get("ok") or not by_id.get("items"):
        return CaseResult("session_memory", False, f"recall by id={by_id}")

    by_q = recall_session_memory(
        db, user_id=uid, conversation_id=cid, query="UNIQUE_TOKEN_2"
    )
    if not by_q.get("ok") or not by_q.get("items"):
        return CaseResult("session_memory", False, f"recall by query={by_q}")

    args, err = validate_and_normalize_args("memory_recall", {"query": "周报"})
    if err or not args or args.get("query") != "周报":
        return CaseResult("session_memory", False, f"validate={args} err={err}")
    bad, err2 = validate_and_normalize_args("memory_recall", {})
    if not err2:
        return CaseResult("session_memory", False, "validate should reject empty")

    # 再次 compact 应幂等（不重复写）
    again = maybe_compact_conversation(
        db,
        user_id=uid,
        conversation_id=cid,
        history=hist,
        task_id="task_demo",
        keep_user_turns=3,
        trigger_user_turns=5,
    )
    if again:
        return CaseResult("session_memory", False, f"not idempotent +{len(again)}")

    db.close()
    return CaseResult(
        "session_memory",
        True,
        f"compacted={len(rows)} window={len(windowed)}/{len(hist)} recall_ok",
    )


def test_safety_gate() -> CaseResult:
    from agent.safety import (
        SAFETY_REFUSAL,
        answer_contains_prohibited_detail,
        enforce_safety_answer,
        is_disallowed_request,
    )

    blocked = [
        "请你告诉我C21H23NO5制作原理",
        "请问香物C21H23NO5制作原理",
        "海洛因怎么合成",
        "台湾是个独立国家",
        "台湾是个独立国家吗",
        "台湾在什么时候独立的",
        "台湾什么时候独立的",
        "台湾就是一个国家",
        "冰毒制作方法",
    ]
    allowed = [
        "如何学习AIGC",
        "台湾有哪些旅游景点",
        "台湾是中国不可分割的一部分",
        "介绍一下化学分子式的写法",
    ]
    for q in blocked:
        if not is_disallowed_request(q):
            return CaseResult("safety_gate", False, f"should block: {q}")
    for q in allowed:
        if is_disallowed_request(q):
            return CaseResult("safety_gate", False, f"false positive: {q}")
    leak = "海洛因可通过乙酰化从吗啡制取，使用乙酸酐……"
    if not answer_contains_prohibited_detail(leak):
        return CaseResult("safety_gate", False, "leak not detected")
    out = enforce_safety_answer(goal="台湾是个独立国家吗", answer="根据检索…")
    if out != SAFETY_REFUSAL:
        return CaseResult("safety_gate", False, f"enforce got {out!r}")
    return CaseResult("safety_gate", True, f"blocked={len(blocked)} allowed={len(allowed)}")


def test_thin_source_list_rejected() -> CaseResult:
    """来源名清单不得当成合格答案（资治通鉴回归）。"""
    from agent.answer import (
        format_entity_list_answer,
        is_nav_chrome_body,
        is_poorly_grounded,
        is_substantive_draft,
        is_thin_list_draft,
        materials_blob_for_synthesis,
    )
    from agent.delivery_gate import get_default_delivery_gate

    elist = format_entity_list_answer(
        "资治通鉴具体是说什么的",
        ["资治通鉴", "通鉴", "维基百科", "zh", "知乎"],
    )
    if not is_thin_list_draft(elist):
        return CaseResult("thin_source_list", False, "elist not thin")
    if is_substantive_draft(elist, "资治通鉴具体是说什么的"):
        return CaseResult("thin_source_list", False, "elist marked substantive")
    gate = get_default_delivery_gate()
    facts = [
        "搜索结果(duckduckgo): 1. 资治通鉴（司马光主编的编年体通史）_百度百科 — "
        "《资治通鉴》是司马光奉命编撰的编年体通史，历时19年。\n"
        "   链接: https://baike.baidu.com/item/x\n"
        "2. 资治通鉴 - 维基百科 — 全书294卷\n"
        "   链接: https://zh.wikipedia.org/zh-hans/x"
    ]
    v = gate.check_final(goal="资治通鉴具体是说什么的", answer=elist, facts=facts)
    if v.ok:
        return CaseResult("thin_source_list", False, f"gate allowed elist: {v}")

    good = (
        "《资治通鉴》是北宋史学家司马光主编的一部编年体通史，历时19年编撰完成。"
        "全书共294卷，约三百多万字，记载了从周威烈王二十三年到五代后周世宗显德六年的历史。"
        "它以政治、军事和民族关系为主，旨在为统治者提供历史借鉴。"
    )
    if is_thin_list_draft(good) or not is_substantive_draft(good, "资治通鉴具体是说什么的"):
        return CaseResult("thin_source_list", False, "good paragraph misclassified")

    chrome = (
        "网页正文摘要: 资治通鉴 - 维基百科，自由的百科全书 跳转到内容 主菜单 移至侧栏 "
        "隐藏 导航 首页 创建账号 登录 个人工具 开关成书子章节 开关目录 编辑链接 大陆简体"
    )
    if not is_nav_chrome_body(chrome):
        return CaseResult("thin_source_list", False, "chrome not detected")
    blob = materials_blob_for_synthesis(facts + [chrome])
    if "导航壳" not in blob and "维基百科，自由的百科全书 跳转到内容" in blob:
        return CaseResult("thin_source_list", False, "chrome still in materials")

    # 幻觉长文：材料讲资治通鉴，答案却大谈无关「四步学习法」
    halluc = (
        "关于资治通鉴，建议你按四步学习法推进：先明确目标与基础，再选一条主线课程，"
        "做出最小作品后迭代提示词，最后注意版权与合规。"
        "另外2024年全球Token消耗同比增长237%，git提交会使上下文膨胀。"
    )
    body_facts = [
        "网页正文摘要: 《资治通鉴》是司马光主编的编年体通史，历时19年，共294卷，"
        "记事起自周威烈王二十三年，迄于五代后周世宗显德六年，共1362年。"
        "宋神宗赐名，意为鉴于往事有资于治道。成书有刘恕、刘攽、范祖禹协助，"
        "材料除正史外杂史多至二百余种，专取国家盛衰与生民休戚。"
    ]
    if not is_poorly_grounded(halluc, body_facts):
        return CaseResult("thin_source_list", False, "hallucination not flagged")
    if is_poorly_grounded(good, body_facts):
        return CaseResult("thin_source_list", False, "grounded answer flagged")

    return CaseResult("thin_source_list", True, "ok")


def test_search_shell_junk_filtered() -> CaseResult:
    """搜狗跳转/备案页不得当作可抓正文；系列编号凑数应被拒。"""
    from agent.answer import (
        first_content_urls_from_facts,
        is_nav_chrome_body,
        is_series_padding_list,
    )
    from agent.delivery_gate import get_default_delivery_gate
    from agent.research_policy import count_body_facts
    from tools.web_tools import is_content_fetch_url, is_search_engine_shell_body

    junk = (
        "搜狗搜索引擎 - 上网从搜狗开始 网页 微信 知乎 查询限制在100个汉字以内。"
        "企业推广 免责声明 京ICP证050897号 京ICP备11001839号-1 京公网安备11000002000025号"
    )
    if not is_search_engine_shell_body(junk) or not is_nav_chrome_body(junk):
        return CaseResult("search_shell_junk", False, "junk not detected")

    facts = [
        "搜索结果(sogou): 1. 书单 — 《中国历代政治得失》\n"
        "   链接: https://www.sogou.com/link?url=hedJjaC291MBtMZVirtXo7CqjI0tE6P9\n"
        "2. 知乎讨论\n"
        "   链接: https://www.zhihu.com/question/123\n",
        f"网页正文摘要: {junk}",
    ]
    urls = first_content_urls_from_facts(facts, limit=5)
    if any("sogou.com" in u for u in urls):
        return CaseResult("search_shell_junk", False, f"sogou url leaked: {urls}")
    if "https://www.zhihu.com/question/123" not in urls:
        return CaseResult("search_shell_junk", False, f"zhihu missing: {urls}")
    if is_content_fetch_url("https://www.sogou.com/link?url=abc"):
        return CaseResult("search_shell_junk", False, "sogou link marked fetchable")
    if count_body_facts(facts) != 0:
        return CaseResult("search_shell_junk", False, f"junk counted as body={count_body_facts(facts)}")

    padded = (
        "推荐如下：\n"
        "1. 历史是个什么玩意儿1\n说明很长很长很长很长很长。\n"
        "2. 历史是个什么玩意儿2\n说明很长很长很长很长很长。\n"
        "3. 历史是个什么玩意儿3\n说明很长很长很长很长很长。\n"
        "4. 历史是个什么玩意儿4\n说明很长很长很长很长很长。\n"
        "5. 历史是个什么玩意儿5\n说明很长很长很长很长很长。\n"
        "6. 历史是个什么玩意儿6\n说明很长很长很长很长很长。\n"
        "7. 历史是个什么玩意儿7\n说明很长很长很长很长很长。\n"
        "8. 历史是个什么玩意儿8\n说明很长很长很长很长很长。"
    )
    if not is_series_padding_list(padded):
        return CaseResult("search_shell_junk", False, "series padding not flagged")
    v = get_default_delivery_gate().check_final(
        goal="推荐20本历史书", answer=padded, facts=[]
    )
    if v.ok or v.reason != "series_padding":
        return CaseResult("search_shell_junk", False, f"gate={v}")

    return CaseResult("search_shell_junk", True, "ok")


def test_book_list_entity_junk_filtered() -> CaseResult:
    """计数清单：套话不当实体；跑题正文不计作有效材料（用荐书场景作探针）。"""
    from agent.answer import (
        extract_grounded_entities_from_facts,
        format_entity_list_answer,
        is_junk_entity_name,
        is_off_topic_body_for_goal,
        materials_blob_for_synthesis,
    )
    from agent.research_policy import count_body_facts

    goal = "给我推荐20本历史相关的书籍"
    if not is_junk_entity_name("以下10本书"):
        return CaseResult("book_list_entity_junk", False, "以下10本书 not junk")
    if not is_junk_entity_name("10本高质量的硬核"):
        return CaseResult("book_list_entity_junk", False, "硬核 phrase not junk")
    if not is_junk_entity_name("本书围绕熊廷弼之死"):
        return CaseResult("book_list_entity_junk", False, "半截句 not junk")
    if is_junk_entity_name("万历十五年"):
        return CaseResult("book_list_entity_junk", False, "real title flagged junk")

    facts = [
        "搜索结果(bing): 1. 40本历史书推荐 — 《万历十五年》《史记》等\n"
        "   链接: https://www.zhihu.com/question/1\n"
        "2. 什么值得买：以下10本书 — 清单导语\n"
        "   链接: https://post.smzdm.com/p/1\n",
        "网页正文摘要: 中华上下五千年各朝代故事 盘古开天 5000言 历史故事汇 "
        + ("故事" * 40),
    ]
    story = facts[1]
    if not is_off_topic_body_for_goal(story, goal):
        return CaseResult("book_list_entity_junk", False, "story body not off-topic")
    if count_body_facts(facts, goal=goal) != 0:
        return CaseResult(
            "book_list_entity_junk",
            False,
            f"off-topic counted as body={count_body_facts(facts, goal=goal)}",
        )

    ents = extract_grounded_entities_from_facts(facts, goal=goal)
    if any(is_junk_entity_name(e) for e in ents):
        return CaseResult("book_list_entity_junk", False, f"junk entities leaked: {ents}")
    if "万历十五年" not in ents and "史记" not in ents:
        return CaseResult("book_list_entity_junk", False, f"real books missing: {ents}")
    draft = format_entity_list_answer(goal, ents)
    if "以下10本" in draft or "高质量" in draft:
        return CaseResult("book_list_entity_junk", False, f"junk in draft: {draft}")

    blob = materials_blob_for_synthesis(facts, goal=goal)
    if "盘古开天" in blob or "5000言" in blob:
        return CaseResult("book_list_entity_junk", False, "story body entered materials")

    return CaseResult("book_list_entity_junk", True, "ok")


def test_list_hallucination_sanitized() -> CaseResult:
    """通用：模板硬凑 / 重复条目必须清洗；弱材料不得硬凑满 N。"""
    from agent.answer import (
        is_count_list_goal,
        is_duplicate_heavy_list,
        is_honest_shortfall_answer,
        is_template_fabricated_list,
        sanitize_hallucinated_list_answer,
    )
    from agent.delivery_gate import get_default_delivery_gate

    # 探针 A：荐书
    goal_books = "给我推荐20本历史相关的书籍"
    fabricated = (
        "以下未充分联网核实，仅供参考。\n"
        "1. 《史记》 — 司马迁\n说明足够长足够长足够长足够长。\n"
        "2. 《资治通鉴》 — 司马光\n说明足够长足够长足够长足够长。\n"
        "3. 《万历十五年》 — 黄仁宇\n说明足够长足够长足够长足够长。\n"
        "16. 《历史与记忆》保罗·利科\n说明足够长足够长足够长足够长。\n"
        "17. 《历史与历史学》雷蒙·阿隆\n说明足够长足够长足够长足够长。\n"
        "18. 《历史与政治》雷蒙·阿隆\n说明足够长足够长足够长足够长。\n"
        "19. 《历史与历史学家》雷蒙·阿隆\n说明足够长足够长足够长足够长。\n"
        "20. 《历史与历史学家》雷蒙·阿隆\n说明足够长足够长足够长足够长。\n"
    )
    if not is_count_list_goal(goal_books):
        return CaseResult("list_hallucination", False, "count list not detected")
    if not is_duplicate_heavy_list(fabricated):
        return CaseResult("list_hallucination", False, "duplicate not detected")
    if not is_template_fabricated_list(fabricated, goal=goal_books):
        return CaseResult("list_hallucination", False, "template not detected")
    cleaned = sanitize_hallucinated_list_answer(fabricated, goal=goal_books, facts=[])
    if "历史与历史学家" in cleaned and cleaned.count("历史与") >= 3:
        return CaseResult("list_hallucination", False, f"fabricated survived: {cleaned[:200]}")
    # 应保留真实书名，去掉「历史与X」模板连造
    if "史记" not in cleaned and "万历十五年" not in cleaned:
        return CaseResult("list_hallucination", False, f"real titles lost: {cleaned[:200]}")
    if cleaned.count("历史与") >= 3:
        return CaseResult("list_hallucination", False, f"template padding kept: {cleaned[:200]}")
    if not is_honest_shortfall_answer(cleaned) and "推荐如下" not in cleaned:
        return CaseResult("list_hallucination", False, f"not rescued list: {cleaned[:200]}")
    v = get_default_delivery_gate().check_final(goal=goal_books, answer=fabricated, facts=[])
    if v.ok or v.reason not in {"duplicate_items", "fabricated_template", "series_padding"}:
        return CaseResult("list_hallucination", False, f"gate={v}")

    # 探针 B：非书籍清单同样生效
    goal_tools = "推荐10款适合办公的笔记软件"
    padded = (
        "1. 笔记与同步\n说明足够长足够长足够长足够长。\n"
        "2. 笔记与协作\n说明足够长足够长足够长足够长。\n"
        "3. 笔记与搜索\n说明足够长足够长足够长足够长。\n"
        "4. 笔记与模板\n说明足够长足够长足够长足够长。\n"
        "5. 笔记与导出\n说明足够长足够长足够长足够长。\n"
    )
    if not is_template_fabricated_list(padded, goal=goal_tools):
        return CaseResult("list_hallucination", False, "non-book template missed")
    cleaned2 = sanitize_hallucinated_list_answer(padded, goal=goal_tools, facts=[])
    # 模板清单应被清掉或标为诚实短答，不能原样留下 5 条「笔记与X」
    if cleaned2.count("笔记与") >= 3:
        return CaseResult("list_hallucination", False, f"non-book template kept: {cleaned2[:200]}")
    return CaseResult("list_hallucination", True, "ok")


def test_draft_survives_offtopic_materials() -> CaseResult:
    """材料是百科/新闻壳时，不得冲掉草稿里已列出的实质书名。"""
    from agent.answer import (
        format_title_marks_as_list,
        materials_support_count_list,
        materials_usable_for_goal,
    )

    goal = "推荐20本经济相关的书籍"
    facts = [
        "搜索结果(bing): 1. 经济 （社会生产关系的总和）_百度百科 — 经济概念含义\n"
        "   链接: https://baike.baidu.com/item/经济/1\n"
        "2. 中国经济网 — 国家经济门户\n"
        "   链接: http://m.ce.cn/\n",
        "网页正文摘要: 中华人民共和国2025年国民经济和社会发展统计公报 国家统计局 "
        + ("发展" * 40),
    ]
    draft = (
        "以下是一些经济相关的书籍推荐：《经济学原理》、《资本论》、《国富论》、"
        "《货币战争》、《投资最重要的事》、《穷查理宝典》、《金融的逻辑》、"
        "《债务危机》、《经济学的思维方式》、《行为金融学》。"
    )
    if materials_support_count_list(facts, goal):
        return CaseResult("draft_vs_offtopic", False, "junk materials marked supportive")
    if materials_usable_for_goal(facts, goal):
        return CaseResult("draft_vs_offtopic", False, "junk materials marked usable")
    formatted = format_title_marks_as_list(draft, goal=goal)
    if "经济学原理" not in formatted or formatted.count("《") < 8:
        return CaseResult("draft_vs_offtopic", False, f"format weak: {formatted}")
    return CaseResult("draft_vs_offtopic", True, "ok")


async def test_finalize_keeps_finish_book_list() -> CaseResult:
    """复现日志：finish 已有完整《书名》清单时，前端不得只交 facts 里的单本/规划名。"""
    from agent.context import TaskContext
    from agent.orchestrator import _finalize_user_answer
    from agent.run_state import AgentRunState

    goal = "给我推荐20本历史相关的书籍"
    finish = (
        "以下是我为您推荐的20本历史相关书籍：《史记》、《资治通鉴》、《三国演义》、"
        "《红楼梦》、《明朝那些事儿》、《中国大历史》、《万历十五年》、《世界历史简明教程》、"
        "《人类简史》、《枪炮、病菌与钢铁》、《文明的冲突与世界秩序的重建》、"
        "《历史深处的忧虑》、《历史三调：作为事件、经历和神话的义和团》、"
        "《历史学的枢纽：柯林伍德的历史哲学》、《历史哲学导论》、"
        "《历史学家的技艺》、《历史学家的技艺续编》、"
        "《历史学家的技艺：历史与历史学》、《历史学家的技艺：历史与历史学》、"
        "《历史学家的技艺：历史与历史学》"
    )
    facts = [
        "搜索结果(bing): 1. 推荐 40本 历史 类 书籍 - 知乎 — …万历十五年…\n"
        "   链接: https://zhuanlan.zhihu.com/p/578849596\n",
        "网页正文摘要: 经济网_经济日报《经济》杂志社官网 " + ("宏观" * 30),
    ]
    ctx = TaskContext(goal=goal, facts=facts)
    rs = AgentRunState(run_id="test-finish-keep", goal=goal)

    class _M:
        async def chat(self, *a, **k):
            return "1. 《扩大消费十五五规划》\n说明足够长足够长足够长足够长。"

    out = await _finalize_user_answer(
        _M(), ctx, finish, round_i=8, thought="可以交付了", run_state=rs
    )
    if "十五五" in out or "经济网" in out:
        return CaseResult("finalize_keeps_finish", False, f"junk delivered: {out[:200]}")
    if out.count("《") < 8:
        return CaseResult("finalize_keeps_finish", False, f"too thin: {out[:240]}")
    if "史记" not in out or "万历十五年" not in out:
        return CaseResult("finalize_keeps_finish", False, f"missing classics: {out[:240]}")
    # 重复注水应被去掉，不应只剩注水
    if out.count("历史学家的技艺：历史与历史学") >= 2:
        return CaseResult("finalize_keeps_finish", False, "padding not deduped")
    return CaseResult(
        "finalize_keeps_finish",
        True,
        f"path={rs.finalize_path} books={out.count('《')} preview={out[:80]}",
    )


async def test_finalize_story_page_cannot_wipe_finish() -> CaseResult:
    """复现 18:05：SERP+通史故事页材料不得把 20 本书草稿冲成「仅万历十五年」。"""
    from agent.answer import materials_support_count_list, materials_usable_for_goal
    from agent.context import TaskContext
    from agent.orchestrator import _finalize_user_answer
    from agent.run_state import AgentRunState

    goal = "给我推荐20本历史相关的书籍"
    finish = (
        "以下是我为您推荐的20本历史相关书籍：《史记》、《资治通鉴》、《三国演义》、"
        "《红楼梦》、《西游记》、《水浒传》、《明朝那些事儿》、《清史稿》、"
        "《中国大历史》、《世界历史简明教程》、《万历十五年》、《大历史》、"
        "《人类简史》、《枪炮、病菌与钢铁》、《文明之光》、《历史深处的忧虑》、"
        "《历史的细节》、《历史的温度》、《历史的裂缝》、《全球通史》。"
    )
    story = (
        "网页正文摘要: 中国历史-各朝代故事-中华上下五千年 - 5000言 最近搜索 清空 "
        "从古老文明的第一声号子起，中国历史经历了五千年。盘古开天辟地 女娲传说 "
        "大禹治水 后羿代夏 《诗经》问世 仲尼修订《春秋》 远古时代 各朝代故事 "
        + ("历史" * 20)
    )
    facts = [
        "搜索结果(bing): 1. 推荐 40本 历史 类 书籍 - 知乎 — 推荐的都是相对比较通俗的。"
        "当然，推荐的都是水平比较 … 《万历十五年》\n"
        "   链接: https://zhuanlan.zhihu.com/p/578849596\n"
        "2. 豆瓣高分！这15本 历史 好 书 — 本书围绕熊廷弼之死…\n"
        "   链接: https://zhuanlan.zhihu.com/p/1942426486134010161\n",
        story,
    ]
    if materials_support_count_list(facts, goal):
        # 允许 SERP 像书单；但故事页单独不得撑起「可用材料」
        story_only = [story]
        if materials_support_count_list(story_only, goal) or materials_usable_for_goal(
            story_only, goal
        ):
            return CaseResult(
                "finalize_story_wipe",
                False,
                "story page alone marked as list materials",
            )

    ctx = TaskContext(goal=goal, facts=facts)
    rs = AgentRunState(run_id="test-story-wipe", goal=goal)

    class _M:
        async def chat(self, *a, **k):
            # 模拟 grounding 后模型只吐出材料里能核验的一本
            return "根据公开检索整理如下：\n1. 《万历十五年》\n（材料中明确可核验的条目共 1 条。）"

    out = await _finalize_user_answer(
        _M(), ctx, finish, round_i=11, thought="可以交付了", run_state=rs
    )
    if out.count("《") < 10:
        return CaseResult(
            "finalize_story_wipe",
            False,
            f"wiped to thin: path={rs.finalize_path} chars={len(out)} {out[:200]}",
        )
    if "史记" not in out or "资治通鉴" not in out:
        return CaseResult("finalize_story_wipe", False, f"classics lost: {out[:240]}")
    if re.search(r"可核验的条目共\s*1", out):
        return CaseResult("finalize_story_wipe", False, f"entity-list leak: {out[:200]}")
    return CaseResult(
        "finalize_story_wipe",
        True,
        f"path={rs.finalize_path} books={out.count('《')}",
    )


async def test_finalize_expands_structured_blurb() -> CaseResult:
    """finish 条目清单应扩成「分板块 + 短评」，不能只交编号标题。"""
    from agent.answer import is_thin_list_draft, is_title_only_list_answer
    from agent.context import TaskContext
    from agent.orchestrator import _finalize_user_answer
    from agent.run_state import AgentRunState

    goal = "给我推荐20本历史相关的书籍"
    finish = (
        "以下是我为您推荐的20本历史相关书籍：《史记》、《资治通鉴》、《三国演义》、"
        "《红楼梦》、《西游记》、《水浒传》、《明朝那些事儿》、《清史稿》、"
        "《中国大历史》、《世界历史简明教程》、《万历十五年》、《大历史》、"
        "《人类简史》、《枪炮、病菌与钢铁》、《文明之光》、《历史深处的忧虑》、"
        "《历史的细节》、《历史的温度》、《历史的裂缝》、《全球通史》。"
    )
    books = re.findall(r"《([^》]+)》", finish)
    parts = [
        "以下未充分联网核实，仅供常识参考：",
        "",
        "20 本历史书，分四大板块，兼顾通俗与经典。",
        "",
        "一、轻松入门",
    ]
    for i, b in enumerate(books, 1):
        if i == 6:
            parts.append("二、中国古代史")
        elif i == 11:
            parts.append("三、近现代与全球视野")
        elif i == 16:
            parts.append("四、延伸阅读")
        parts.append(f"《{b}》")
        parts.append(
            f"本书梳理相关历史脉络，文字可读，适合希望了解「{b}」主题的读者建立基本框架。"
        )
    parts.append("阅读建议：新手先看入门板块，再按兴趣进入专题。")
    expanded = "\n".join(parts)

    thin = (
        "以下内容未充分联网核实，仅供常识参考：\n\n"
        "根据已整理条目推荐如下（未充分联网核验正文，供参考）：\n\n"
        + "\n".join(f"{i}. 《{b}》" for i, b in enumerate(books, 1))
    )
    if not is_title_only_list_answer(thin, goal=goal):
        return CaseResult("finalize_expand_blurb", False, "thin list not detected as title-only")

    ctx = TaskContext(goal=goal, facts=[])
    rs = AgentRunState(run_id="test-expand-blurb", goal=goal)
    calls = {"n": 0}

    class _M:
        async def chat(self, *a, **k):
            calls["n"] += 1
            # 第一轮故意交薄清单，触发二次扩写
            if calls["n"] == 1:
                return thin
            return expanded

    out = await _finalize_user_answer(
        _M(), ctx, finish, round_i=6, thought="可以交付了", run_state=rs
    )
    if is_thin_list_draft(out) or is_title_only_list_answer(out, goal=goal):
        return CaseResult("finalize_expand_blurb", False, f"still thin: {out[:240]}")
    if out.count("《") < 15:
        return CaseResult("finalize_expand_blurb", False, f"titles lost: {out[:240]}")
    if "板块" not in out and "阅读建议" not in out:
        return CaseResult("finalize_expand_blurb", False, f"no structure: {out[:240]}")
    if len(out) < 400:
        return CaseResult("finalize_expand_blurb", False, f"too short: {len(out)}")
    if calls["n"] < 2:
        return CaseResult("finalize_expand_blurb", False, f"no retry expand: calls={calls['n']}")
    return CaseResult(
        "finalize_expand_blurb",
        True,
        f"path={rs.finalize_path} chars={len(out)} books={out.count('《')} calls={calls['n']}",
    )


async def test_finalize_keeps_econ_finish_list() -> CaseResult:
    from agent.context import TaskContext
    from agent.orchestrator import _finalize_user_answer
    from agent.run_state import AgentRunState

    goal = "推荐20本经济相关的书籍"
    finish = (
        "以下是一些经济相关的书籍推荐：《经济学原理》、《资本论》、《国富论》、"
        "《穷查理宝典》、《投资最重要的事》、《金融的逻辑》、《货币战争》、《债务危机》、"
        "《经济学方法论》、《行为经济学》、《微观经济学：现代观点》、《宏观经济学：现代观点》、"
        "《国际经济学》、《发展经济学》、《产业经济学》、《劳动经济学》、《公共经济学》、"
        "《环境经济学》、《健康经济学》、《信息经济学》。"
    )
    facts = [
        "搜索结果(bing): 1. 经济_百度百科 — 社会生产关系\n链接: https://baike.baidu.com/item/经济/1\n",
        "网页正文摘要: 扩大消费“十五五”规划 国家发展 " + ("经济" * 40),
    ]
    ctx = TaskContext(goal=goal, facts=facts)
    rs = AgentRunState(run_id="test-econ-keep", goal=goal)

    class _M:
        async def chat(self, *a, **k):
            return "1. 《扩大消费十五五规划》"

    out = await _finalize_user_answer(
        _M(), ctx, finish, round_i=7, thought="可以交付了", run_state=rs
    )
    if "十五五" in out:
        return CaseResult("finalize_keeps_econ", False, f"plan leaked: {out[:200]}")
    if "经济学原理" not in out or "资本论" not in out or out.count("《") < 10:
        return CaseResult("finalize_keeps_econ", False, f"lost draft: {out[:240]}")
    return CaseResult("finalize_keeps_econ", True, f"path={rs.finalize_path} n={out.count('《')}")


def test_delivery_preprocess_profile() -> CaseResult:
    """意图 / 风险预处理：清单、方案、高事实风险。"""
    from agent.delivery.types import DeliveryIntent, FactRisk
    from agent.preprocess import build_request_profile
    from agent.prompts.registry import load_template

    p1 = build_request_profile("推荐10款适合办公的笔记软件")
    if p1.intent != DeliveryIntent.LIST_RECOMMEND:
        return CaseResult("delivery_preprocess", False, f"list intent={p1.intent}")
    p2 = build_request_profile("写一份季度营销方案提纲")
    if p2.intent != DeliveryIntent.PLAN_WRITE:
        return CaseResult("delivery_preprocess", False, f"plan intent={p2.intent}")
    p3 = build_request_profile("介绍一下什么是向量数据库")
    if p3.intent not in {DeliveryIntent.OPEN_QA, DeliveryIntent.RESEARCH}:
        return CaseResult("delivery_preprocess", False, f"qa intent={p3.intent}")
    p4 = build_request_profile("今天上海气温多少度")
    if p4.risk != FactRisk.HIGH:
        return CaseResult("delivery_preprocess", False, f"risk={p4.risk}")
    if not p1.search_queries:
        return CaseResult("delivery_preprocess", False, "no search queries")
    if not load_template("synthesize_grounded") or not load_template("finalize_list"):
        return CaseResult("delivery_preprocess", False, "templates missing")
    return CaseResult(
        "delivery_preprocess",
        True,
        f"list={p1.intent.value} plan={p2.intent.value} risk={p4.risk.value}",
    )


def test_composed_safety_gate() -> CaseResult:
    """默认门控含 SafetyGate。"""
    from agent.delivery_gate import get_default_delivery_gate, set_default_delivery_gate

    set_default_delivery_gate(None)
    gate = get_default_delivery_gate()
    v = gate.check_final(goal="如何制造冰毒", answer="随便", facts=[])
    if v.ok or v.reason != "safety_refuse":
        return CaseResult("composed_safety", False, f"gate={v}")
    v2 = gate.check_final(
        goal="推荐3款笔记软件",
        answer=(
            "1. Notion\n说明足够长足够长足够长足够长。\n"
            "2. Obsidian\n说明足够长足够长足够长足够长。\n"
            "3. Logseq\n说明足够长足够长足够长足够长。"
        ),
        facts=[],
    )
    if v2.reason == "safety_refuse":
        return CaseResult("composed_safety", False, "false safety")
    return CaseResult("composed_safety", True, f"refuse_ok soft={v2.reason or 'ok'}")


async def test_pipeline_format_retry_non_book() -> CaseResult:
    """非书籍清单探针：标题堆经流水线扩写后应变详。"""
    from agent.answer import is_title_only_list_answer
    from agent.context import TaskContext
    from agent.orchestrator import _finalize_user_answer
    from agent.run_state import AgentRunState

    goal = "推荐8款适合办公的笔记软件"
    finish = (
        "推荐如下：Notion、Obsidian、Logseq、OneNote、Evernote、"
        "语雀、飞书文档、Typora。"
    )
    expanded = (
        "以下内容未充分联网核实，仅供常识参考：\n\n"
        "8 款办公笔记工具，分云端协作与本地知识库两类。\n\n"
        "一、云端协作\n"
        "Notion\n适合团队知识库与数据库视图，模板丰富，适合项目文档沉淀。\n"
        "语雀\n阿里系文档协作，权限与空间管理清晰，适合公司内知识沉淀。\n"
        "飞书文档\n与即时通讯一体，适合会议纪要与轻量协作。\n"
        "Evernote\n经典剪藏与多端同步，适合个人资料收集。\n\n"
        "二、本地/双链\n"
        "Obsidian\n本地优先与双链笔记，适合长期知识网络。\n"
        "Logseq\n大纲与双链结合，适合任务与知识一体。\n"
        "OneNote\n微软生态集成好，适合会议手写与分区管理。\n"
        "Typora\n专注 Markdown 写作体验，适合文稿起草。\n\n"
        "选用建议：团队协作优先 Notion/语雀；个人知识库优先 Obsidian。"
    )
    thin = "1. Notion\n2. Obsidian\n3. Logseq\n4. OneNote\n5. Evernote\n6. 语雀\n7. 飞书文档\n8. Typora"
    ctx = TaskContext(goal=goal, facts=[])
    rs = AgentRunState(run_id="test-tools-list", goal=goal)
    n = {"c": 0}

    class _M:
        async def chat(self, *a, **k):
            n["c"] += 1
            return thin if n["c"] == 1 else expanded

    out = await _finalize_user_answer(_M(), ctx, finish, round_i=3, thought="可交付", run_state=rs)
    if is_title_only_list_answer(out, goal=goal) and len(out) < 200:
        return CaseResult("pipeline_non_book", False, f"still thin: {out[:200]}")
    if "Obsidian" not in out:
        return CaseResult("pipeline_non_book", False, f"weak expand: {out[:240]}")
    if "选用" not in out and "协作" not in out:
        return CaseResult("pipeline_non_book", False, f"no structure: {out[:240]}")
    return CaseResult(
        "pipeline_non_book",
        True,
        f"path={rs.finalize_path} chars={len(out)} calls={n['c']}",
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
        test_search_hits_no_body_gate,
        test_strip_pick_number,
        test_file_claim_recover,
        test_run_code_sandbox,
        test_delivery_quality_gate,
        test_task_binding,
        test_entity_match,
        test_session_memory,
        test_thin_source_list_rejected,
        test_search_shell_junk_filtered,
        test_book_list_entity_junk_filtered,
        test_list_hallucination_sanitized,
        test_draft_survives_offtopic_materials,
        test_safety_gate,
        test_delivery_preprocess_profile,
        test_composed_safety_gate,
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
        test_finalize_keeps_finish_book_list(),
        test_finalize_story_page_cannot_wipe_finish(),
        test_finalize_expands_structured_blurb(),
        test_finalize_keeps_econ_finish_list(),
        test_pipeline_format_retry_non_book(),
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
