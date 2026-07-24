"""工具控制器：是否挂工具、Schema 强校验、转发工具网关。"""

from __future__ import annotations

from typing import Any

from agent.dispatch.types import DispatchQuery, TaskTransition
from agent.delivery.types import FactTier
from tools.web_tools import render_tool_contracts, validate_and_normalize_args


class ToolController:
    """设计稿 §3.6：校验失败返回纠错信息，不依赖模型自行修正。"""

    def should_enable_tools(self, query: DispatchQuery, transition: TaskTransition) -> bool:
        if transition == TaskTransition.CHITCHAT and query.fact_tier == FactTier.C.value:
            # 闲聊默认可不挂重工具，但仍保留基础能力（由调用方决定裁剪）
            return True
        return True

    def filter_tools_for_intent(
        self,
        tools: list[str],
        *,
        query: DispatchQuery,
        transition: TaskTransition,
    ) -> list[str]:
        if not self.should_enable_tools(query, transition):
            return []
        # 闲聊：去掉写文件 / 浏览器等重工具，保留搜索与记忆
        if transition == TaskTransition.CHITCHAT or query.intent == "chitchat":
            # 商单筛库会话：保留 influencer_*，勿裁剪
            if any(str(t).startswith("influencer_") for t in tools):
                return list(tools)
            light = {
                "web_search",
                "web_fetch",
                "kb_search",
                "memory_recall",
                "run_code",
                "call_influencer_match",
            }
            return [t for t in tools if t in light] or tools
        return list(tools)

    def render_contracts(self, tools: list[str]) -> str:
        return render_tool_contracts(tools)

    def validate(
        self, tool: str, args: Any
    ) -> tuple[dict[str, Any] | None, str | None]:
        """返回 (规范化 args, error)。error 非空时应回灌模型纠错。"""
        return validate_and_normalize_args(tool, args)

    def correction_observation(self, tool: str, error: str) -> str:
        return (
            f"工具参数校验失败（{tool}）：{error}。"
            "请按工具契约修正 action_input 后重试，禁止省略必填字段。"
        )
