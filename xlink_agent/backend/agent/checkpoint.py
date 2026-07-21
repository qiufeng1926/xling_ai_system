"""确认暂停检查点：序列化 / 恢复 TaskContext 与 Scratchpad。"""

from __future__ import annotations

import json
from typing import Any

from agent.context import TaskContext
from agent.react import ReactScratchpad, ReactStep


def serialize_task_context(ctx: TaskContext) -> dict[str, Any]:
    return {
        "goal": ctx.goal,
        "browser_url": ctx.browser_url,
        "browser_title": ctx.browser_title,
        "steps": list(ctx.steps),
        "facts": list(ctx.facts),
        "artifacts": list(ctx.artifacts),
        "failed_urls": list(ctx.failed_urls),
        "fetched_urls": list(ctx.fetched_urls),
        "failed_calls": dict(ctx.failed_calls),
        "last_tool": ctx.last_tool,
        "last_ok": ctx.last_ok,
        "last_error": ctx.last_error,
        "task_id": ctx.task_id,
        "task_bind_mode": ctx.task_bind_mode,
    }


def restore_task_context(data: dict[str, Any] | None) -> TaskContext:
    d = data or {}
    ctx = TaskContext(goal=str(d.get("goal") or ""))
    ctx.browser_url = str(d.get("browser_url") or "about:blank")
    ctx.browser_title = str(d.get("browser_title") or "")
    ctx.steps = list(d.get("steps") or [])
    ctx.facts = list(d.get("facts") or [])
    ctx.artifacts = list(d.get("artifacts") or [])
    ctx.failed_urls = list(d.get("failed_urls") or [])
    ctx.fetched_urls = list(d.get("fetched_urls") or [])
    ctx.failed_calls = dict(d.get("failed_calls") or {})
    ctx.last_tool = str(d.get("last_tool") or "")
    ctx.last_ok = bool(d.get("last_ok", True))
    ctx.last_error = str(d.get("last_error") or "")
    ctx.task_id = str(d.get("task_id") or "")
    ctx.task_bind_mode = str(d.get("task_bind_mode") or "")
    return ctx


def serialize_scratchpad(pad: ReactScratchpad) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in pad.steps:
        out.append(
            {
                "thought": s.thought,
                "action": s.action,
                "action_input": s.action_input,
                "observation": s.observation,
                "round_i": s.round_i,
            }
        )
    return out


def restore_scratchpad(steps: list[dict[str, Any]] | None) -> ReactScratchpad:
    pad = ReactScratchpad()
    for item in steps or []:
        pad.steps.append(
            ReactStep(
                thought=str(item.get("thought") or ""),
                action=str(item.get("action") or ""),
                action_input=item.get("action_input"),
                observation=str(item.get("observation") or ""),
                round_i=int(item.get("round_i") or 0),
            )
        )
    return pad


def build_confirm_checkpoint(
    *,
    tool: str,
    args: dict[str, Any] | str,
    task_ctx: TaskContext,
    scratchpad: ReactScratchpad,
    round_i: int,
    run_id: str,
    tools: list[str],
    effective_goal: str,
) -> dict[str, Any]:
    return {
        "tool": tool,
        "args": args if isinstance(args, dict) else {"_raw": args},
        "task_context": serialize_task_context(task_ctx),
        "react_steps": serialize_scratchpad(scratchpad),
        "round_i": round_i,
        "run_id": run_id,
        "tools": list(tools),
        "effective_goal": effective_goal,
    }


def parse_checkpoint(payload_json: str | None) -> dict[str, Any]:
    try:
        data = json.loads(payload_json or "{}")
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}
