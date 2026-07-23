"""人话轨迹步骤：给前端 trajectory.step 事件（对齐豆包「能看见在干活」）。"""

from __future__ import annotations

from typing import Any


TOOL_KIND: dict[str, str] = {
    "web_search": "search",
    "web_fetch": "fetch",
    "openlibrary_lookup": "search",
    "http_request": "fetch",
    "browser_navigate": "browse",
    "browser_extract": "browse",
    "browser_click": "browse",
    "browser_type": "browse",
    "browser_screenshot": "browse",
    "browser_submit": "browse",
    "kb_search": "kb",
    "file_write_markdown": "write",
    "file_write_html": "write",
    "file_write_docx": "write",
    "file_write_xlsx": "write",
    "file_write_pptx": "write",
    "file_write_pdf": "write",
    "file_delete": "write",
    "file_list": "write",
    "http_request_write": "write",
    "run_code": "code",
    "memory_recall": "kb",
    "finish": "finish",
}

TOOL_TITLE: dict[str, str] = {
    "web_search": "正在搜索",
    "web_fetch": "正在打开正文",
    "openlibrary_lookup": "正在核验书目",
    "http_request": "正在抓取网页",
    "browser_navigate": "浏览器打开页面",
    "browser_extract": "提取页面内容",
    "browser_click": "点击页面元素",
    "browser_type": "在页面输入",
    "browser_screenshot": "页面截图",
    "browser_submit": "提交表单（需确认）",
    "kb_search": "检索知识库",
    "file_list": "查看工作区文件",
    "file_write_markdown": "正在生成 Markdown",
    "file_write_html": "正在生成 HTML",
    "file_write_docx": "正在生成 Word",
    "file_write_xlsx": "正在生成 Excel",
    "file_write_pptx": "正在生成 PPT",
    "file_write_pdf": "正在生成 PDF",
    "file_delete": "删除工作区文件（需确认）",
    "http_request_write": "外呼写操作（需确认）",
    "run_code": "运行代码计算",
    "memory_recall": "召回会话记忆",
    "finish": "整理最终答复",
}

TOOL_TITLE_DONE: dict[str, str] = {
    "web_search": "搜索完成",
    "web_fetch": "正文已打开",
    "openlibrary_lookup": "书目核验完成",
    "http_request": "网页已抓取",
    "browser_navigate": "页面已打开",
    "browser_extract": "内容已提取",
    "browser_click": "点击完成",
    "browser_type": "输入完成",
    "browser_screenshot": "截图完成",
    "browser_submit": "表单已提交",
    "kb_search": "知识库检索完成",
    "file_list": "文件列表已就绪",
    "file_write_markdown": "Markdown 已生成",
    "file_write_html": "HTML 已生成",
    "file_write_docx": "Word 已生成",
    "file_write_xlsx": "Excel 已生成",
    "file_write_pptx": "PPT 已生成",
    "file_write_pdf": "PDF 已生成",
    "file_delete": "文件已删除",
    "http_request_write": "写操作已完成",
    "run_code": "代码执行完成",
    "memory_recall": "记忆召回完成",
    "finish": "答复已就绪",
}

TOOL_TITLE_FAIL: dict[str, str] = {
    "web_search": "搜索未拿到结果",
    "web_fetch": "正文打开失败",
    "openlibrary_lookup": "书目核验失败",
    "http_request": "网页抓取失败",
    "browser_navigate": "页面打开失败",
    "browser_extract": "提取失败",
    "browser_click": "点击失败",
    "browser_type": "输入失败",
    "browser_screenshot": "截图失败",
    "browser_submit": "提交失败",
    "kb_search": "知识库未命中或失败",
    "file_write_markdown": "Markdown 生成失败",
    "file_write_html": "HTML 生成失败",
    "file_write_docx": "Word 生成失败",
    "file_write_xlsx": "Excel 生成失败",
    "file_write_pptx": "PPT 生成失败",
    "file_write_pdf": "PDF 生成失败",
    "file_delete": "删除失败",
    "http_request_write": "写操作失败",
    "run_code": "代码执行失败",
    "memory_recall": "记忆召回失败",
}

INTERCEPT_TITLE: dict[str, str] = {
    "duplicate_web_search": "跳过重复搜索",
    "search_hits_prefer_fetch": "已有搜索，改为抓正文",
    "auto_web_fetch": "自动打开搜索结果",
    "premature_finish_auto_search": "补充搜索后再回答",
    "fact_tier_a_force_search": "A 类强制检索",
    "fact_tier_post_scan": "A 类后置扫描清洗",
    "openlibrary_catalog": "用书目库补充材料",
    "file_claim_recover": "改为实际生成文件",
    "missing_file_write": "约束要求文档，先写文件",
    "duplicate_file_write": "文档已生成，停止重复写入",
    "llm_unavailable_auto_tool": "模型中断，自动继续取数",
    "need_alt_search": "换角度补充检索",
    "need_more_bodies": "继续抓取更多正文",
    "search_for_more_sources": "再搜补充来源",
    "no_search_yet": "先搜索再回答",
    "search_hits_no_body": "先打开正文再总结",
    "need_more_research": "材料不足，继续取数",
    "llm_unavailable": "模型连接中断，改用已有材料",
    "safety_block": "安全策略：暂不支持该问题",
    "weak_materials": "材料偏弱，强制充实成稿",
    "poor_grounding": "答案与材料脱节，已拦截幻觉",
    "series_padding": "拒绝系列编号凑数",
    "duplicate_items": "拒绝重复条目",
    "fabricated_template": "拒绝模板硬凑伪书名",
    "wrong_item_type": "拒绝与目标类型不符的条目",
    "parrot_titles": "拒绝标题清单交差",
    "thin_list": "条目过薄，继续扩写",
    "quality_force_expand": "质量门控强制扩写",
    "task_continue": "续作同一任务",
    "task_switch": "换题，开启新任务",
}

_FAIL_SHORT: tuple[tuple[str, str], ...] = (
    ("验证码", "遇到验证码，已换源"),
    ("风控", "页面被风控拦截"),
    ("超时", "请求超时"),
    ("timeout", "请求超时"),
    ("正文为空", "页面无有效正文"),
    ("正文过短", "页面正文过短"),
    ("禁止访问内网", "禁止访问内网地址"),
    ("参数无效", "工具参数无效"),
    ("未写入", "正文为空，未写入文件"),
    ("几乎为空", "生成文件几乎为空"),
    ("blocked", "页面被拦截"),
)


def tool_kind(tool: str) -> str:
    return TOOL_KIND.get(tool, "tool")


def tool_title(tool: str, *, status: str = "running") -> str:
    if status == "ok":
        return TOOL_TITLE_DONE.get(tool, TOOL_TITLE.get(tool, f"完成 {tool}"))
    if status in {"fail", "error"}:
        return TOOL_TITLE_FAIL.get(tool, TOOL_TITLE.get(tool, f"失败 {tool}"))
    if status == "pending":
        return TOOL_TITLE.get(tool, f"待确认 {tool}")
    return TOOL_TITLE.get(tool, f"执行 {tool}")


def tool_detail(tool: str, args: dict[str, Any] | str | None) -> str:
    if isinstance(args, str):
        return args[:160]
    args = args or {}
    if tool == "web_search":
        q = str(args.get("query") or "")
        return f"关键词：{q[:120]}" if q else ""
    if tool == "openlibrary_lookup":
        qs = args.get("queries") or []
        if isinstance(qs, list) and qs:
            return f"核验：{', '.join(str(x) for x in qs[:4])}"[:140]
        topic = str(args.get("subject") or args.get("q") or "")
        return f"发现：{topic[:120]}" if topic else "书目查询"
    if tool == "run_code":
        code = str(args.get("code") or args.get("source") or "")
        first = code.strip().splitlines()[0] if code.strip() else ""
        return f"代码：{first[:120]}" if first else ""
    url = str(args.get("url") or "")
    if url:
        return f"地址：{url[:140]}"
    name = str(args.get("name") or args.get("filename") or "")
    if name:
        return f"文件：{name[:80]}"
    return ""


def short_fail_reason(reason: str = "", summary: str = "") -> str:
    blob = f"{reason or ''} {summary or ''}"
    for key, label in _FAIL_SHORT:
        if key.lower() in blob.lower():
            return label
    text = (reason or summary or "执行失败").strip()
    return text[:80]


def intercept_step(reason: str, *, round_i: int, detail: str = "") -> dict[str, Any]:
    title = INTERCEPT_TITLE.get(reason, "调整执行策略")
    return {
        "round": round_i,
        "kind": "intercept",
        "title": title,
        "detail": detail[:200],
        "status": "skip",
        "reason": reason,
    }


def action_step(
    tool: str,
    args: dict[str, Any] | str | None,
    *,
    round_i: int,
    status: str = "running",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "round": round_i,
        "kind": tool_kind(tool),
        "title": tool_title(tool, status=status),
        "detail": tool_detail(tool, args),
        "status": status,
        "reason": reason,
        "tool": tool,
    }


def observation_step(
    tool: str,
    *,
    round_i: int,
    ok: bool,
    summary: str = "",
    reason: str = "",
) -> dict[str, Any]:
    status = "ok" if ok else "fail"
    fail = "" if ok else short_fail_reason(reason, summary)
    detail = (summary or "")[:220]
    if not ok and fail and fail not in detail:
        detail = f"{fail}" + (f"：{detail[:160]}" if detail else "")
    return {
        "round": round_i,
        "kind": tool_kind(tool),
        "title": tool_title(tool, status=status),
        "detail": detail[:220],
        "status": status,
        "reason": fail if not ok else "",
        "tool": tool,
    }


def finish_step(*, round_i: int, detail: str = "") -> dict[str, Any]:
    return {
        "round": round_i,
        "kind": "finish",
        "title": "整理最终答复",
        "detail": detail[:160],
        "status": "ok",
        "reason": "",
    }


def confirm_tool_label(tool: str) -> str:
    return TOOL_TITLE.get(tool, tool)
