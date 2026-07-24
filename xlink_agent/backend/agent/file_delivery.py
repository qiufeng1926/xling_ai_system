"""文档/产物交付状态机：要文件 → 写一次 → 就绪 → 交付。

硬契约（不依赖模型自觉）：
- 目标要求落盘且尚无产物 → finish 前必须 force_write
- 本轮已有产物 → 禁止再次 file_write_*，应收束 finish
- 状态可观测，便于拦截埋点与自测
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.task_binding import required_file_write_tool


class FileDeliveryPhase(str, Enum):
    NONE = "none"  # 本轮不要求文件
    NEED_FILE = "need_file"  # 要求文件但尚未落盘
    FILE_READY = "file_ready"  # 已有产物，可交付


class FileDeliveryAction(str, Enum):
    ALLOW = "allow"
    FORCE_WRITE = "force_write"
    FORCE_FINISH = "force_finish"


@dataclass
class FileDeliveryDecision:
    phase: FileDeliveryPhase
    required_tool: str | None
    action: FileDeliveryAction
    tip: str = ""

    @property
    def intercept_reason(self) -> str:
        if self.action == FileDeliveryAction.FORCE_WRITE:
            return "missing_file_write"
        if self.action == FileDeliveryAction.FORCE_FINISH:
            return "duplicate_file_write"
        return ""


def resolve_phase(
    goal: str = "",
    *,
    constraints: list[str] | None = None,
    artifacts: list[str] | None = None,
) -> FileDeliveryPhase:
    tool = required_file_write_tool(goal, constraints)
    if not tool:
        return FileDeliveryPhase.NONE
    if artifacts:
        return FileDeliveryPhase.FILE_READY
    return FileDeliveryPhase.NEED_FILE


def decide_on_finish(
    *,
    goal: str,
    artifacts: list[str] | None = None,
    constraints: list[str] | None = None,
    can_still_tool: bool = True,
) -> FileDeliveryDecision:
    """模型想 finish 时：缺文件则强制写；已有文件则允许交付。"""
    tool = required_file_write_tool(goal, constraints)
    arts = [a for a in (artifacts or []) if a]
    if not tool:
        return FileDeliveryDecision(FileDeliveryPhase.NONE, None, FileDeliveryAction.ALLOW)
    if arts:
        return FileDeliveryDecision(
            FileDeliveryPhase.FILE_READY,
            tool,
            FileDeliveryAction.ALLOW,
            tip="文档已就绪，可以交付",
        )
    if can_still_tool:
        return FileDeliveryDecision(
            FileDeliveryPhase.NEED_FILE,
            tool,
            FileDeliveryAction.FORCE_WRITE,
            tip=f"约束要求输出文档，须先调用 {tool} 再 finish",
        )
    # 末轮仍无文件：允许文字收束，但标明未落盘（由上层处理）
    return FileDeliveryDecision(
        FileDeliveryPhase.NEED_FILE,
        tool,
        FileDeliveryAction.ALLOW,
        tip="已无剩余轮次写文件，将仅文字交付并声明未生成附件",
    )


def decide_on_tool(
    *,
    tool: str,
    goal: str = "",
    artifacts: list[str] | None = None,
    constraints: list[str] | None = None,
) -> FileDeliveryDecision:
    """模型想调工具时：已有产物则禁止再写文件，强制收束。"""
    t = (tool or "").strip()
    arts = [a for a in (artifacts or []) if a]
    req = required_file_write_tool(goal, constraints)
    phase = resolve_phase(goal, constraints=constraints, artifacts=arts)

    if t.startswith("file_write_") and arts:
        names = "、".join(arts[-4:])
        return FileDeliveryDecision(
            FileDeliveryPhase.FILE_READY,
            req or t,
            FileDeliveryAction.FORCE_FINISH,
            tip=(
                f"本轮已生成文档（{names}），禁止再次 {t}。"
                "请直接 finish，并提示用户下载已有文件。"
            ),
        )
    return FileDeliveryDecision(phase, req, FileDeliveryAction.ALLOW)


def finish_content_with_download_hint(content: str, artifacts: list[str] | None) -> str:
    """交付正文末尾补下载提示（若尚未提及文件名）。"""
    text = (content or "").strip()
    arts = [a for a in (artifacts or []) if a]
    if not arts:
        return text
    names = "、".join(arts[-4:])
    if any(a in text for a in arts[-4:]):
        if "下载" not in text and "文件" not in text:
            return text.rstrip() + f"\n\n文件 {names} 已准备好，可点击下方下载。"
        return text
    return text.rstrip() + f"\n\n文件 {names} 已准备好，可点击下方下载。"


def should_promote_root_goal(stored_goal: str, user_text: str) -> str | None:
    """续作时若用户话术明显升级任务（尤其补上调研/文档），返回新根目标。

    典型：根目标「怎么是token」← 用户「做一份市场调研，以文档形式给我」
    """
    stored = (stored_goal or "").strip()
    raw = (user_text or "").strip()
    if not raw or len(raw) < 10:
        return None
    # 新话术要求文档，而旧根目标没有（或旧根过短像碎句）
    new_needs = bool(required_file_write_tool(raw))
    old_needs = bool(required_file_write_tool(stored))
    substantive = any(
        k in raw
        for k in ("调研", "报告", "市场", "分析", "总结", "写入", "文档", "docx", "Word")
    )
    short_root = len(stored) < 36 or stored.count("\n") == 0 and len(stored) < 48
    if new_needs and substantive and (not old_needs or short_root):
        if raw != stored and (len(raw) >= len(stored) or not old_needs):
            return raw[:1000]
    # 无文档但新话术是完整调研任务、旧根是短问句
    if (
        substantive
        and short_root
        and len(raw) >= 16
        and any(k in raw for k in ("调研", "报告", "帮我", "请", "做一份"))
        and len(raw) > len(stored) + 6
    ):
        return raw[:1000]
    return None


def seed_write_content(
    *,
    draft: str = "",
    think: str = "",
    facts: list[str] | None = None,
    goal: str = "",
) -> str:
    """为强制写文件准备正文种子：优先草稿/Thought，其次 facts。"""
    for cand in (draft, think):
        c = (cand or "").strip()
        if len(c) >= 40 and not c.startswith("{"):
            return c[:12000]
    parts: list[str] = []
    if goal:
        parts.append(str(goal).split("\n", 1)[0][:200])
    for f in facts or []:
        if f and len(f) >= 40:
            parts.append(f[:800])
        if sum(len(p) for p in parts) >= 200:
            break
    body = "\n\n".join(parts).strip()
    return body[:12000] if body else (goal or "（自动生成正文）")[:2000]
