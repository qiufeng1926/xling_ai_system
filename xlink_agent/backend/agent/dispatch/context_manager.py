"""上下文管理器：分区保护 + Token/字符水位治理。

永久区：活跃任务目标/约束/最新工具结构化结果（禁删）
可保留区：最近若干轮完整对话
可淘汰区：老旧闲聊、已完结任务（软阈值压缩 / 硬阈值剔除）
"""

from __future__ import annotations

from typing import Any, Callable

from agent.dispatch.types import ContextBundle, MemoryHit, SessionRuntime
from agent.memory_policy import build_dialog_messages
from agent.task_binding import ActiveTask


class ContextManager:
    """设计稿 §3.4。P1 用字符近似 Token；压缩 ≠ 删除（淘汰区仅移出窗口）。"""

    def build(
        self,
        *,
        session: SessionRuntime,
        active_task: ActiveTask,
        effective_goal: str,
        memory_hits: list[MemoryHit],
        window_history: list[Any],
        sanitize_fn: Callable[[str], str],
        looks_internal_fn: Callable[[str], bool],
        tool_facts: list[str] | None = None,
    ) -> ContextBundle:
        soft = int(session.max_context_chars * session.context_soft_ratio)
        hard = int(session.max_context_chars * session.context_hard_ratio)

        permanent: list[str] = []
        if active_task.goal:
            permanent.append(f"活跃任务目标：{active_task.goal[:500]}")
        if active_task.constraints:
            permanent.append("任务约束：" + "；".join(active_task.constraints[-6:]))
        if tool_facts:
            permanent.append("最新工具结果：" + " | ".join(tool_facts[-3:])[:1200])

        # 召回片段：仅摘要，限制条数
        recalled = list(memory_hits[:6])
        recall_block_lines = [
            f"- [{h.source} {h.score:.2f}] {h.text[:200]}" for h in recalled
        ]
        recall_block = ""
        if recall_block_lines:
            recall_block = (
                "# 调度层召回历史（已筛选，请只采纳与当前目标相关的条目）\n"
                + "\n".join(recall_block_lines)
            )

        dialog = build_dialog_messages(
            window_history,
            current_goal=effective_goal,
            sanitize_fn=sanitize_fn,
            looks_internal_fn=looks_internal_fn,
        )

        soft_hit = False
        hard_hit = False
        used = sum(len(p) for p in permanent) + len(recall_block) + sum(
            len(m.get("content") or "") for m in dialog
        )
        if used > soft:
            soft_hit = True
            # 软阈值：缩短可保留对话，保留最近 4 条
            dialog = dialog[-4:] if len(dialog) > 4 else dialog
            used = sum(len(p) for p in permanent) + len(recall_block) + sum(
                len(m.get("content") or "") for m in dialog
            )
        if used > hard:
            hard_hit = True
            # 硬阈值：只留最近 2 条 + 永久区 + 召回截断
            dialog = dialog[-2:] if len(dialog) > 2 else dialog
            recalled = recalled[:3]
            recall_block_lines = [
                f"- [{h.source} {h.score:.2f}] {h.text[:120]}" for h in recalled
            ]
            recall_block = (
                (
                    "# 调度层召回历史（硬阈值截断）\n"
                    + "\n".join(recall_block_lines)
                )
                if recall_block_lines
                else ""
            )
            used = sum(len(p) for p in permanent) + len(recall_block) + sum(
                len(m.get("content") or "") for m in dialog
            )

        system_extra_parts = []
        if permanent:
            system_extra_parts.append("# 永久保护区（禁止忽略）\n" + "\n".join(f"- {p}" for p in permanent))
        if recall_block:
            system_extra_parts.append(recall_block)

        return ContextBundle(
            permanent=permanent,
            retain=dialog,
            recalled=recalled,
            messages=dialog,
            system_extra="\n\n".join(system_extra_parts),
            char_used=used,
            soft_triggered=soft_hit,
            hard_triggered=hard_hit,
        )
