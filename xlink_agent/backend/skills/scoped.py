"""会话级 Skill 黑名单：通用 agent 永不加载。商单筛库已迁至 match_agent。"""

from __future__ import annotations

CONVERSATION_SCOPED_SKILLS = frozenset({"influencer-match"})

# 保留常量以免旧引用报错；通用编排不再使用
SCOPED_SKILL_EXTRA_TOOLS = (
    "file_write_markdown",
    "file_write_xlsx",
    "memory_recall",
)
