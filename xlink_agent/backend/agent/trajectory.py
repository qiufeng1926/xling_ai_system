"""人话轨迹步骤：给前端 trajectory.step 事件。"""

from __future__ import annotations

from typing import Any


TOOL_KIND: dict[str, str] = {
    "web_search": "search",
    "web_fetch": "fetch",
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
    "http_request_write": "write",
    "finish": "finish",
}

TOOL_TITLE: dict[str, str] = {
    "web_search": "搜索公开网页",
    "web_fetch": "打开网页正文",
    "http_request": "抓取网页",
    "browser_navigate": "浏览器打开页面",
    "browser_extract": "提取页面内容",
    "browser_click": "点击页面元素",
    "browser_type": "在页面输入",
    "browser_screenshot": "页面截图",
    "browser_submit": "提交表单",
    "kb_search": "检索知识库",
    "file_write_markdown": "生成 Markdown",
    "file_write_html": "生成 HTML",
    "file_write_docx": "生成 Word 文档",
    "file_write_xlsx": "生成 Excel",
    "file_write_pptx": "生成 PPT",
    "file_write_pdf": "生成 PDF",
    "file_delete": "删除工作区文件",
    "http_request_write": "外呼写操作",
    "finish": "整理最终答复",
}

INTERCEPT_TITLE: dict[str, str] = {
    "duplicate_web_search": "跳过重复搜索",
    "auto_web_fetch": "自动打开搜索结果",
    "premature_finish_auto_search": "补充搜索后再回答",
    "file_claim_recover": "改为实际生成文件",
    "need_alt_search": "换角度补充检索",
    "need_more_bodies": "继续抓取更多正文",
    "search_for_more_sources": "再搜补充来源",
    "no_search_yet": "先搜索再回答",
}


def tool_kind(tool: str) -> str:
    return TOOL_KIND.get(tool, "tool")


def tool_title(tool: str) -> str:
    return TOOL_TITLE.get(tool, f"执行 {tool}")


def tool_detail(tool: str, args: dict[str, Any] | str | None) -> str:
    if isinstance(args, str):
        return args[:160]
    args = args or {}
    if tool == "web_search":
        q = str(args.get("query") or "")
        return f"关键词：{q[:120]}" if q else ""
    url = str(args.get("url") or "")
    if url:
        return f"地址：{url[:140]}"
    name = str(args.get("name") or args.get("filename") or "")
    if name:
        return f"文件：{name[:80]}"
    return ""


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
        "title": tool_title(tool),
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
    return {
        "round": round_i,
        "kind": tool_kind(tool),
        "title": tool_title(tool),
        "detail": (summary or "")[:220],
        "status": "ok" if ok else "fail",
        "reason": reason or ("" if ok else (summary or "执行失败")[:160]),
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
