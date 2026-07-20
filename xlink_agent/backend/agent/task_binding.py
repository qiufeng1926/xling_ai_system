"""会话任务绑定（方案第一步：TaskID 强绑定）。

目标体验：
- 追问/续作 → 绑定同一 TaskID，注入任务链摘要
- 明显换题 → 关闭旧任务，开启新 TaskID
- 为后续实体匹配 / 向量召回预留同一任务载体

不在本模块做意图分类模型或向量检索。
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from agent.memory_policy import (
    goal_shifted,
    is_dialog_followup,
    is_new_independent_question,
)
from db.models import ConversationTask
from utils.logger import get_logger

logger = get_logger("task_binding")

TASK_STATUS_OPEN = "open"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_ABANDONED = "abandoned"

BIND_CONTINUE = "continue"
BIND_NEW = "new"
BIND_SWITCH = "switch"


@dataclass
class ActiveTask:
    task_id: str
    goal: str
    status: str = TASK_STATUS_OPEN
    constraints: list[str] = field(default_factory=list)
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    bind_mode: str = BIND_NEW
    previous_task_id: str = ""

    def render_injection(self) -> str:
        """结构化注入块：时间/场景由编排层外层补充，这里只放任务核心。"""
        lines = [
            "# 活动任务绑定（强制关联，办公多轮核心）",
            f"- TaskID: {self.task_id}",
            f"- 绑定模式: {self.bind_mode}",
            f"- 根目标: {self.goal}",
        ]
        if self.previous_task_id:
            lines.append(f"- 已关闭上一任务: {self.previous_task_id}")
        if self.constraints:
            lines.append("- 用户约束:")
            for c in self.constraints[-8:]:
                lines.append(f"  · {c}")
        if self.artifacts:
            lines.append("- 已生成产物: " + "、".join(self.artifacts[-6:]))
        if self.summary:
            lines.append(f"- 任务摘要: {self.summary[:500]}")
        if self.bind_mode == BIND_CONTINUE:
            lines.append(
                "- 规则: 本轮是同一任务的续作/追问；必须沿用上述目标与约束，"
                "禁止当作无关新题，禁止串到更早已关闭任务。"
            )
        elif self.bind_mode == BIND_SWITCH:
            lines.append(
                "- 规则: 用户已换题；禁止提及或续写已关闭任务的主题与结论。"
            )
        else:
            lines.append("- 规则: 新任务开始；仅服务当前根目标。")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "constraints": list(self.constraints),
            "summary": self.summary,
            "artifacts": list(self.artifacts),
            "bind_mode": self.bind_mode,
            "previous_task_id": self.previous_task_id,
        }


def extract_constraints(text: str) -> list[str]:
    """从用户话术抽出可复用约束（轻量规则，后续可扩展实体匹配）。"""
    t = (text or "").strip()
    if not t:
        return []
    out: list[str] = []
    m = re.search(r"(\d+)\s*(本|个|条|款|篇|首|部|份)", t)
    if m:
        out.append(f"数量约 {m.group(1)}{m.group(2)}")
    for fmt, label in (
        (r"\bdocx\b|word|Word|文档", "输出 Word/docx"),
        (r"\bxlsx\b|excel|Excel|表格", "输出 Excel/xlsx"),
        (r"\bpptx\b|PPT|幻灯片", "输出 PPT"),
        (r"\bpdf\b|PDF", "输出 PDF"),
        (r"markdown|\.md\b", "输出 Markdown"),
    ):
        if re.search(fmt, t, re.I):
            out.append(label)
    if re.search(r"不要重复|别重复|去重", t):
        out.append("不要重复已出现条目")
    if re.search(r"只要中文|用中文|中文回答", t):
        out.append("使用中文")
    if re.search(r"详细|深入|全面|完整", t):
        out.append("需要较详细展开")
    if re.search(r"简短|简要|一句话", t):
        out.append("答复尽量简短")
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _prev_user_text(history: list[Any]) -> str:
    msgs: list[str] = []
    for item in history:
        role = getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else None)
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "") or ""
        if role == "user":
            msgs.append(content)
    if len(msgs) >= 2:
        return msgs[-2]
    if len(msgs) == 1:
        # 当前用户句已写入 history 时，倒二才是上轮；若只有一句则无上轮
        return ""
    return ""


def _load_open_task(db: Session, user_id: int, conversation_id: int) -> ConversationTask | None:
    return (
        db.query(ConversationTask)
        .filter(
            ConversationTask.user_id == user_id,
            ConversationTask.conversation_id == conversation_id,
            ConversationTask.status == TASK_STATUS_OPEN,
        )
        .order_by(ConversationTask.created_at.desc(), ConversationTask.task_id.desc())
        .first()
    )


def _row_to_active(row: ConversationTask, *, bind_mode: str, previous_task_id: str = "") -> ActiveTask:
    try:
        constraints = json.loads(row.constraints_json or "[]")
    except Exception:
        constraints = []
    try:
        artifacts = json.loads(row.artifacts_json or "[]")
    except Exception:
        artifacts = []
    if not isinstance(constraints, list):
        constraints = []
    if not isinstance(artifacts, list):
        artifacts = []
    return ActiveTask(
        task_id=row.task_id,
        goal=row.goal or "",
        status=row.status,
        constraints=[str(c) for c in constraints if c],
        summary=row.summary or "",
        artifacts=[str(a) for a in artifacts if a],
        bind_mode=bind_mode,
        previous_task_id=previous_task_id,
    )


def _create_task(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    goal: str,
    constraints: list[str] | None = None,
) -> ConversationTask:
    row = ConversationTask(
        task_id=uuid.uuid4().hex,
        user_id=user_id,
        conversation_id=conversation_id,
        status=TASK_STATUS_OPEN,
        goal=(goal or "")[:1000],
        constraints_json=json.dumps(constraints or [], ensure_ascii=False),
        summary="",
        artifacts_json="[]",
        last_run_id="",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def resolve_task_binding(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    user_text: str,
    history: list[Any],
    effective_goal: str,
    forced_followup: bool = False,
) -> ActiveTask:
    """根据用户本轮话术决定：续绑 / 新开 / 换题切换。"""
    raw = (user_text or "").strip()
    goal = (effective_goal or raw).strip()
    open_row = _load_open_task(db, user_id, conversation_id)
    prev_user = _prev_user_text(history)
    followup = forced_followup or (bool(prev_user) and is_dialog_followup(raw, prev_user))
    independent = is_new_independent_question(raw)
    shifted = bool(prev_user) and goal_shifted(prev_user, raw)

    should_continue = False
    if open_row:
        if followup and not independent:
            should_continue = True
        elif not prev_user:
            # 同轮重复解析等边界：保持开放任务
            should_continue = True
        elif not shifted and not independent:
            # 同会话弱相关粘性：未明确换题则续绑
            should_continue = True

    if open_row and should_continue:
        extra = extract_constraints(raw)
        try:
            existing = json.loads(open_row.constraints_json or "[]")
        except Exception:
            existing = []
        if not isinstance(existing, list):
            existing = []
        merged = list(existing)
        for c in extra:
            if c not in merged:
                merged.append(c)
        open_row.constraints_json = json.dumps(merged, ensure_ascii=False)
        if goal and goal != open_row.goal and len(goal) > len(open_row.goal or ""):
            tip = f"最近追问展开：{goal[:240]}"
            open_row.summary = ((open_row.summary or "") + "\n" + tip).strip()[:800]
        db.commit()
        db.refresh(open_row)
        logger.info(
            "task continue id=%s conv=%s goal=%s",
            open_row.task_id[:8],
            conversation_id,
            (open_row.goal or "")[:40],
        )
        return _row_to_active(open_row, bind_mode=BIND_CONTINUE)

    previous_id = ""
    if open_row:
        open_row.status = (
            TASK_STATUS_ABANDONED if (shifted or independent) else TASK_STATUS_COMPLETED
        )
        previous_id = open_row.task_id
        db.commit()

    constraints = extract_constraints(raw) or extract_constraints(goal)
    row = _create_task(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        goal=goal or raw,
        constraints=constraints,
    )
    mode = BIND_SWITCH if previous_id else BIND_NEW
    logger.info(
        "task %s id=%s conv=%s goal=%s",
        mode,
        row.task_id[:8],
        conversation_id,
        (row.goal or "")[:40],
    )
    return _row_to_active(row, bind_mode=mode, previous_task_id=previous_id)


def update_task_after_turn(
    db: Session,
    *,
    task_id: str,
    user_id: int,
    run_id: str = "",
    artifacts: list[str] | None = None,
    answer_preview: str = "",
    mark_completed: bool = False,
) -> None:
    """本轮交付后回写任务摘要/产物；换题时由 resolve 关闭，此处默认可保持 open 供续问。"""
    row = (
        db.query(ConversationTask)
        .filter(ConversationTask.task_id == task_id, ConversationTask.user_id == user_id)
        .first()
    )
    if not row:
        return
    if run_id:
        row.last_run_id = run_id
    if artifacts:
        try:
            existing = json.loads(row.artifacts_json or "[]")
        except Exception:
            existing = []
        if not isinstance(existing, list):
            existing = []
        for a in artifacts:
            if a and a not in existing:
                existing.append(a)
        row.artifacts_json = json.dumps(existing[-20:], ensure_ascii=False)
    preview = re.sub(r"\s+", " ", (answer_preview or "").strip())
    if preview:
        row.summary = f"最近交付摘要：{preview[:400]}"
    if mark_completed:
        row.status = TASK_STATUS_COMPLETED
    db.commit()


def expand_goal_with_task(effective_goal: str, task: ActiveTask) -> str:
    """续作时把 Task 约束并入有效目标，便于调研/写文件门控看到同一任务。"""
    goal = (effective_goal or task.goal or "").strip()
    if task.bind_mode != BIND_CONTINUE:
        return goal
    parts = [goal]
    if task.constraints:
        parts.append("任务约束：" + "；".join(task.constraints[-6:]))
    if task.artifacts:
        parts.append("已有产物：" + "、".join(task.artifacts[-4:]))
    if task.summary:
        parts.append(task.summary[:200])
    return "\n".join(parts)
