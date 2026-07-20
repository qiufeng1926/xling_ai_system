"""任务工作记忆：跨工具轮次 / 跨用户轮次的上下文压缩与拼装"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from agent.answer import summarize_http_or_extract_for_memory
from typing import Any


@dataclass
class TaskContext:
    goal: str
    browser_url: str = "about:blank"
    browser_title: str = ""
    steps: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)
    failed_calls: dict[str, int] = field(default_factory=dict)
    last_tool: str = ""
    last_ok: bool = True
    last_error: str = ""
    task_id: str = ""
    task_bind_mode: str = ""

    def add_step(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            self.steps.append(text[:300])
            if len(self.steps) > 12:
                self.steps = self.steps[-12:]

    def add_fact(self, text: str) -> None:
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return
        self.facts.append(text[:800])
        if len(self.facts) > 24:
            self.facts = self.facts[-24:]

    def add_artifact(self, name: str) -> None:
        if name and name not in self.artifacts:
            self.artifacts.append(name)

    def mark_failed_url(self, url: str) -> None:
        url = (url or "").strip()
        if url and url not in self.failed_urls:
            self.failed_urls.append(url)
            if len(self.failed_urls) > 10:
                self.failed_urls = self.failed_urls[-10:]

    def call_key(self, tool: str, args: dict[str, Any]) -> str:
        url = str(args.get("url") or "")
        return f"{tool}|{url}|{json.dumps(args, ensure_ascii=False, sort_keys=True)[:180]}"

    def record_call(self, tool: str, args: dict[str, Any], ok: bool) -> int:
        key = self.call_key(tool, args)
        if ok:
            self.failed_calls.pop(key, None)
            return 0
        self.failed_calls[key] = self.failed_calls.get(key, 0) + 1
        return self.failed_calls[key]

    def already_failed(self, tool: str, args: dict[str, Any], limit: int = 1) -> bool:
        return self.failed_calls.get(self.call_key(tool, args), 0) >= limit

    def render(self) -> str:
        lines = [
            "# 当前任务工作记忆（仅服务「这一句」用户目标，禁止沿用其它话题）",
            f"- 用户目标: {self.goal}",
        ]
        if self.task_id:
            lines.append(f"- TaskID: {self.task_id}（绑定={self.task_bind_mode or 'n/a'}）")
        lines.append(
            f"- 本轮浏览器 URL: {self.browser_url or 'about:blank'}（若与目标无关请重新 navigate，勿沿用旧页面）"
        )
        if self.browser_title:
            lines.append(f"- 页面标题: {self.browser_title}")
        if self.failed_urls:
            lines.append("- 已失败且禁止再试的 URL:")
            for u in self.failed_urls[-6:]:
                lines.append(f"  · {u}")
            lines.append(
                "  → 对这些 URL 不要再次 browser_navigate；改用 http_request 抓取，或换其他公开站点。"
            )
        if self.steps:
            lines.append("- 本轮已执行步骤:")
            for s in self.steps[-8:]:
                lines.append(f"  · {s}")
        if self.facts:
            lines.append("- 本轮有效信息（已按目标过滤）:")
            for f in self.facts[-10:]:
                lines.append(f"  · {f}")
        else:
            lines.append("- 本轮有效信息: （尚无，请针对当前目标取数，不要使用历史聊天里的旧结论）")
        if self.artifacts:
            lines.append("- 已生成文件: " + ", ".join(self.artifacts))
        if self.last_tool:
            lines.append(
                f"- 上一工具: {self.last_tool} ({'成功' if self.last_ok else '失败'})"
                + (f" 错误={self.last_error}" if self.last_error else "")
            )
        lines.append(
            "- 规则提醒: 换题后旧新闻/天气/文件结论一律作废；同一失败操作禁止原地重试。"
        )
        return "\n".join(lines)


def summarize_tool_result(tool: str, result: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """返回 (ok, fact_summary, state_updates)。"""
    if not isinstance(result, dict):
        return False, f"{tool} 返回异常", {}

    if result.get("error"):
        return False, f"{tool} 失败: {result['error']}", {}

    updates: dict[str, Any] = {}
    if tool == "browser_navigate":
        url = str(result.get("url") or "")
        title = str(result.get("title") or "")
        updates = {"browser_url": url, "browser_title": title}
        return True, f"已打开页面: {title or url}", updates

    if tool == "browser_extract":
        text = str(result.get("text") or "").strip()
        url = str(result.get("url") or "")
        if url:
            updates["browser_url"] = url
        if not text:
            return False, "页面正文为空（可能尚未打开有效页面，或选择器无匹配）", updates
        return True, summarize_http_or_extract_for_memory(tool, result), updates

    if tool == "browser_screenshot":
        url = str(result.get("url") or "")
        if url:
            updates["browser_url"] = url
        return True, f"已截图，当前页 {url or ''}", updates

    if tool in {"browser_click", "browser_type", "browser_submit"}:
        url = str(result.get("url") or "")
        if url:
            updates["browser_url"] = url
        return True, f"{tool} 完成，当前 URL={url}", updates

    if tool == "kb_search":
        hits = result.get("hits") or []
        if not hits:
            return True, "知识库未命中相关内容", {}
        titles = []
        for h in hits[:5]:
            titles.append(str(h.get("filename") or h.get("text") or "")[:80])
        return True, "知识库命中: " + "；".join(titles), {}

    if tool == "web_search":
        text = str(result.get("text") or "").strip()
        if result.get("error") and not text:
            return False, f"搜索失败: {result['error']}", {}
        if not text:
            return False, "搜索无结果", {}
        src = result.get("source") or ""
        prefix = f"搜索结果({src}): " if src else "搜索结果: "
        return True, prefix + text[:2800], {}

    if tool == "web_fetch":
        text = str(result.get("text") or "").strip()
        if result.get("error") or result.get("ok") is False:
            return False, f"抓取失败: {result.get('error') or '无有效正文'}", {}
        status = result.get("status")
        if isinstance(status, int) and status >= 400:
            return False, f"抓取失败: HTTP {status}", {}
        return True, summarize_http_or_extract_for_memory(tool, result), {}

    if tool.startswith("file_write_"):
        name = str(result.get("name") or "")
        fid = result.get("file_id")
        if result.get("ok") is False or (result.get("error") and not fid):
            return False, f"{tool} 失败: {result.get('error') or '未落盘'}", {}
        note = f"已生成文件 {name}" + (f" (id={fid})" if fid else "")
        return True, note, {"artifact": name}

    if tool == "run_code":
        if result.get("ok") is False or result.get("error"):
            return False, f"代码执行失败: {result.get('error') or 'unknown'}", {}
        out = str(result.get("stdout") or "").strip()
        if not out:
            return True, "代码执行成功（无 stdout 输出）", {}
        return True, f"代码输出: {out[:600]}", {}

    if tool == "file_list":
        files = result.get("files") or []
        return True, f"工作区文件: {', '.join(files[:20])}", {}

    if tool.startswith("http_request"):
        if not result.get("text") and result.get("status") is None:
            return False, f"{tool} 无内容", {}
        return True, summarize_http_or_extract_for_memory(tool, result), {}

    # 通用压缩
    dumped = json.dumps(result, ensure_ascii=False)
    if len(dumped) > 500:
        dumped = dumped[:500] + "…"
    return True, f"{tool} 结果: {dumped}", {}


def apply_result_to_context(
    ctx: TaskContext,
    tool: str,
    result: dict[str, Any],
    *,
    args: dict[str, Any] | None = None,
) -> None:
    ok, summary, updates = summarize_tool_result(tool, result)
    call_args = args or {}
    if not call_args and isinstance(result, dict):
        if result.get("failed_url"):
            call_args = {"url": result.get("failed_url")}
        elif result.get("url") and not ok and tool == "browser_navigate":
            call_args = {"url": result.get("url")}
    ctx.record_call(tool, call_args or {"_": summary[:80]}, ok)
    ctx.last_tool = tool
    ctx.last_ok = ok
    ctx.last_error = "" if ok else summary
    ctx.add_step(f"{tool}: {summary}")
    if ok:
        # 只把与当前目标相关的结果写入 facts，避免新闻污染书单等跨题串味
        from agent.memory_policy import fact_relevant_to_goal

        if tool.startswith("file_write_") or tool in {"web_search", "web_fetch"} or fact_relevant_to_goal(
            summary, ctx.goal
        ):
            # 搜索/抓取结果一律入库，避免「有 Observation 却无 facts」导致误判失败
            ctx.add_fact(summary)
        elif tool.startswith("http") or tool.startswith("browser_"):
            text = str(result.get("text") or "")
            if text and fact_relevant_to_goal(text[:500], ctx.goal):
                snippet = re.sub(r"\s+", " ", text)[:240]
                ctx.add_fact(f"网页摘录: {snippet}")
    else:
        failed = str(result.get("failed_url") or (call_args.get("url") if call_args else "") or result.get("url") or "")
        if tool in {"browser_navigate", "web_fetch", "http_request"} and failed:
            ctx.mark_failed_url(failed)
    if updates.get("browser_url"):
        ctx.browser_url = str(updates["browser_url"])
    if updates.get("browser_title"):
        ctx.browser_title = str(updates["browser_title"])
    if updates.get("artifact"):
        ctx.add_artifact(str(updates["artifact"]))


def infer_default_news_url(goal: str) -> str | None:
    """已废弃：通用 Agent 不做「新闻站默认跳转」。保留符号以免旧导入报错。"""
    return None


def build_continue_prompt(ctx: TaskContext) -> str:
    """兼容旧调用；主路径已改用 agent.react.build_react_continue_prompt。"""
    return (
        f"{ctx.render()}\n\n"
        "请继续完成用户目标（ReAct）。\n"
        '若信息已足够 → {"thought":"...","action":"finish","action_input":"中文答案"}\n'
        '若还缺信息 → {"thought":"...","action":"<工具>","action_input":{...}}\n'
        "禁止把工具名当作对用户的回答；写文件必须先调用 file_write_*。"
    )


def compact_history(messages: list[dict[str, str]], limit_pairs: int = 6) -> list[dict[str, str]]:
    """保留全部 system + 最近若干轮 user/assistant，去掉过长内容。"""
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") in {"user", "assistant"}]
    rest = rest[-(limit_pairs * 2) :]
    out = list(system)
    for m in rest:
        content = m.get("content") or ""
        if len(content) > 2500:
            content = content[:2500] + "…"
        out.append({"role": m["role"], "content": content})
    return out
