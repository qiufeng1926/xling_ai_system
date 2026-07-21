"""单智能体 ReAct 循环：Thought → Action → Observation → …

协议兼容：
- 规范 ReAct：{"thought":"...","action":"tool_name","action_input":{...}}
- 结束：{"thought":"...","action":"finish","action_input":"给用户的答案"}
- 兼容旧协议：action=tool / action=final
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agent.model_router import extract_json_block

# 与 orchestrator.KNOWN_TOOLS 对齐的动作名；finish 为终止符
FINISH_ACTIONS = {"finish", "final", "answer", "done"}


@dataclass
class ReactStep:
    thought: str = ""
    action: str = ""  # tool name or "finish"
    action_input: Any = None
    observation: str = ""
    round_i: int = 0


@dataclass
class ReactScratchpad:
    """累积的 ReAct 轨迹，每轮喂回模型。"""

    steps: list[ReactStep] = field(default_factory=list)

    def add_thought_action(self, thought: str, action: str, action_input: Any, round_i: int) -> ReactStep:
        step = ReactStep(
            thought=(thought or "").strip(),
            action=action,
            action_input=action_input,
            round_i=round_i,
        )
        self.steps.append(step)
        return step

    def set_observation(self, observation: str) -> None:
        if not self.steps:
            return
        self.steps[-1].observation = (observation or "").strip()[:4000]

    def render(self, *, max_steps: int = 10) -> str:
        if not self.steps:
            return "（尚无 ReAct 步骤）"
        lines: list[str] = ["# ReAct 轨迹（按顺序继续，不要忽略 Observation）"]
        for i, s in enumerate(self.steps[-max_steps:], start=1):
            lines.append(f"\n## Step {i}")
            if s.thought:
                lines.append(f"Thought: {s.thought}")
            lines.append(f"Action: {s.action}")
            if s.action_input is not None:
                if isinstance(s.action_input, (dict, list)):
                    lines.append(
                        "Action Input: " + json.dumps(s.action_input, ensure_ascii=False)[:1500]
                    )
                else:
                    lines.append(f"Action Input: {str(s.action_input)[:1500]}")
            if s.observation:
                lines.append(f"Observation: {s.observation}")
            else:
                lines.append("Observation: （等待中）")
        return "\n".join(lines)


REACT_SYSTEM_PROMPT = """你是 xlink 通用办公智能体（能力对齐主流办公 Agent / OpenClaw 一类）：
用 ReAct 循环自主完成查资料、浏览网页、写文档、检索知识库、操作表单等任务。
按当前目标选择工具；不要自我设限为「只能做某一类事」。

## 运行方式
1. 每次只输出 **一个** JSON（禁止一次多步、禁止 Markdown 代码块）
2. 工具执行后你会收到 Observation → 再决定下一步
3. 材料足够后再 action=finish

调用工具：
{"thought":"为何需要这一步","action":"web_search","action_input":{"query":"..."}}

结束：
{"thought":"可以交付了","action":"finish","action_input":"给用户的中文完整答案"}

## 调研协议（能力核心）
对「详细说说 / 深入介绍 / 全面分析 / 全书结构」等深度问题，必须先取够材料再答：
1. **多角度搜索**：至少 2 次 web_search（换关键词：主题本身、内容结构/章节、核心观点/评价等）
2. **多页抓取**：对搜索结果中至少 3 个内容站执行 web_fetch（遇验证码立刻换下一条）
3. **再汇总**：材料覆盖概览、结构、要点、启示后再 finish
简单问答（一句话、是谁、简要）可少搜少抓，但仍须有依据。

禁止：搜到一两段摘要就 finish；禁止只交标题清单；禁止让用户在只读任务里选编号（自行 fetch）。

## 交付质量
- 简单题：总起 + 要点即可
- 深度题：总起 + 分节（概览 / 结构或阶段 / 核心观点 / 小结或启示）；分节须有 Observation 依据
- 编号项：标题行 + 说明；禁止纯书名堆砌；材料不够就少写，禁止虚构条目
- 非书籍勿滥用《》；条数/范围约束必须遵守
- **接地优先**：finish 内容须来自 Observation/检索材料；实时数据核验不到就如实说明
- 禁止用「稳定知识」编造材料中没有的具体事实、数据、人名；宁可短而准确

## 工具策略
- 不知网址 → web_search；有链接 → web_fetch（深度任务多抓）
- 点选/输入 → browser_*；私有资料 → kb_search；文档 → file_write_*
- 算数/清洗/校验 → run_code（短 Python，禁止网络与危险模块）
- **写文件时 action_input.content 必须是完整正文**（分析/总结全文），禁止只传文件名导致空文件
- 一般优先 web_fetch，少用裸 http_request
- 只读任务禁止让用户「回复编号」；自行 web_fetch 后一次交付

## 硬性规则
1. 每轮只做一个 Action。
2. finish 只给用户可读中文，禁止 JSON / 工具名 / 内部话术。
3. 搜索标题 ≠ 答案实体；须从正文提炼。
4. 失败勿死循环；验证码页立刻换链接。
5. 换题硬隔离；追问必须结合会话上下文。
6. browser_extract 勿写超长 CSS。

## 回答限制（最高优先级，压过调研协议）
对于政治敏感、色情低俗、暴力血腥、赌博技巧、BUG利用、黑产、侵权盗版、非法交易、人身攻击、仇恨言论、违法犯罪（含毒品/管制品制作合成等）等问题：
- **禁止**调用任何工具，**禁止**给步骤/原理/配方/教程
- 必须立刻 finish，action_input **只能**是：当前问题暂不支持回答哦~
- 不得用「材料不足/稍后重试」代替拒答
"""


def format_observation(tool: str, result: Any, *, max_len: int = 2500) -> str:
    if not isinstance(result, dict):
        return f"{tool} → {str(result)[:max_len]}"
    if result.get("error"):
        return f"{tool} 失败: {result['error']}"
    # 压缩常见字段
    slim: dict[str, Any] = {}
    for k in (
        "file_id",
        "name",
        "path",
        "url",
        "title",
        "status",
        "files",
        "hits",
        "text",
        "ok",
    ):
        if k in result and result[k] is not None:
            slim[k] = result[k]
    if "frame" in result:
        slim["frame"] = "(preview omitted)"
    if not slim:
        slim = {k: v for k, v in result.items() if k != "frame"}
    dumped = json.dumps(slim, ensure_ascii=False)
    if len(dumped) > max_len:
        dumped = dumped[:max_len] + "…"
    return f"{tool} 成功: {dumped}"


def _normalize_action_name(action: str, tool_field: str | None = None) -> str:
    a = (action or "").strip()
    if a in {"tool", "call_tool", "use_tool"} and tool_field:
        return str(tool_field).strip()
    if a.lower() in FINISH_ACTIONS:
        return "finish"
    return a


def parse_react_output(raw: str, allowed_tools: list[str], known_tools: set[str]) -> dict[str, Any]:
    """解析模型输出为统一结构：
    {thought, action, action_input, legacy?}
    action 为工具名或 'finish'。
    """
    text = (raw or "").strip()
    if not text:
        return {
            "thought": "",
            "action": "finish",
            "action_input": "（模型无输出）",
        }

    if text.startswith("（内部步骤）") or text.startswith("(内部步骤)"):
        return {"thought": "", "action": "finish", "action_input": text}

    data = extract_json_block(text)
    if isinstance(data, dict):
        thought = str(data.get("thought") or data.get("think") or data.get("reason") or "")

        # 规范 ReAct
        if "action" in data and (
            "action_input" in data
            or data.get("action") in FINISH_ACTIONS
            or str(data.get("action") or "") in known_tools
            or str(data.get("action") or "") in allowed_tools
        ):
            action = _normalize_action_name(str(data.get("action") or ""), data.get("tool"))
            action_input = data.get("action_input")
            if action_input is None:
                action_input = data.get("args") or data.get("content") or data.get("input") or {}
            if action == "finish" and isinstance(action_input, dict) and "content" in action_input:
                action_input = action_input.get("content")
            return {"thought": thought, "action": action, "action_input": action_input}

        # 旧协议 action=tool / final
        if data.get("action") in {"tool", "final"}:
            if data["action"] == "tool":
                tool = str(data.get("tool") or "")
                args = data.get("args") if isinstance(data.get("args"), dict) else {}
                return {
                    "thought": thought,
                    "action": tool,
                    "action_input": args,
                    "legacy": True,
                }
            return {
                "thought": thought,
                "action": "finish",
                "action_input": str(data.get("content") or ""),
                "legacy": True,
            }

        # {"tool":"...","args":{...}}
        if data.get("tool") or data.get("name"):
            tool = str(data.get("tool") or data.get("name") or "")
            args = data.get("args") or data.get("parameters") or data.get("arguments") or data.get("action_input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"input": args}
            if not isinstance(args, dict):
                args = {}
            return {"thought": thought, "action": tool, "action_input": args}

        if "url" in data and len(data) <= 3:
            return {
                "thought": thought or "打开网页",
                "action": "browser_navigate",
                "action_input": {"url": data["url"]},
            }

    # 文本式 ReAct: Thought: ...\nAction: ...\nAction Input: ...
    thought_m = re.search(r"Thought\s*[:：]\s*(.+?)(?=\n\s*Action\s*[:：]|\Z)", text, re.I | re.S)
    action_m = re.search(r"Action\s*[:：]\s*([a-zA-Z_][\w]*)", text, re.I)
    input_m = re.search(r"Action\s*Input\s*[:：]\s*(.+)$", text, re.I | re.S)
    if action_m:
        action = _normalize_action_name(action_m.group(1))
        action_input: Any = {}
        if input_m:
            blob = extract_json_block(input_m.group(1).strip())
            action_input = blob if blob is not None else input_m.group(1).strip()
        return {
            "thought": (thought_m.group(1).strip() if thought_m else ""),
            "action": action,
            "action_input": action_input,
        }

    # 行式：tool_name\n{json}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        first = lines[0].strip("` ").strip()
        first = re.sub(r"^工具[：:]\s*", "", first)
        m = re.match(
            r"^(?:action\s*=\s*tool[,，\s]*)?(?:tool\s*[:=]\s*)?([a-zA-Z_][\w]*)\s*$",
            first,
        )
        tool_cand = m.group(1) if m else first
        if tool_cand in known_tools or tool_cand in allowed_tools or tool_cand.lower() in FINISH_ACTIONS:
            args: Any = {}
            rest = "\n".join(lines[1:])
            blob = extract_json_block(rest) if rest else None
            if isinstance(blob, dict):
                args = blob.get("args") if isinstance(blob.get("args"), dict) else blob
            elif rest:
                url_m = re.search(r"https?://[^\s\"']+", rest)
                if url_m:
                    args = {"url": url_m.group(0)}
            action = _normalize_action_name(tool_cand)
            return {
                "thought": f"调用 {tool_cand}",
                "action": action,
                "action_input": args if action != "finish" else (rest or text),
            }

    for tool in sorted(known_tools, key=len, reverse=True):
        if tool in text and (tool in allowed_tools or tool in known_tools):
            idx = text.find(tool)
            after = text[idx + len(tool) :]
            blob = extract_json_block(after)
            args = blob if isinstance(blob, dict) else {}
            if isinstance(args, dict) and "args" in args and isinstance(args["args"], dict):
                args = args["args"]
            if not args:
                url_m = re.search(r"https?://[^\s\"']+", after)
                if url_m:
                    args = {"url": url_m.group(0)}
            if args or tool.startswith("browser_") or tool.startswith("file_") or tool == "kb_search":
                return {
                    "thought": f"识别到工具 {tool}",
                    "action": tool,
                    "action_input": args or {},
                }

    # 当作最终回答
    return {"thought": "直接回复", "action": "finish", "action_input": text}


def build_react_continue_prompt(
    work_memory: str,
    scratchpad: ReactScratchpad,
    *,
    goal: str = "",
    facts: list[str] | None = None,
) -> str:
    from agent.research_policy import research_status_line

    g = goal
    if not g:
        for line in (work_memory or "").splitlines():
            if "用户目标:" in line or "用户目标：" in line:
                g = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                break
    status = research_status_line(g, facts or [], scratchpad.steps) if g else ""
    return (
        f"{work_memory}\n"
        f"{status}\n\n"
        f"{scratchpad.render()}\n\n"
        "请输出下一步 **单个** ReAct JSON：\n"
        '- 还缺信息 → {"thought":"...","action":"<工具名>","action_input":{...}}\n'
        '- 已可交付 → {"thought":"...","action":"finish","action_input":"信息充分的中文答案"}\n'
        "硬性：回答当前用户目标；追问须用会话上下文。"
        "深度任务须多角度搜索 + 多页 web_fetch 后再 finish；"
        "禁止把搜索标题当答案；finish 为「总起 + 分节/编号（每条多句说明）」；"
        "非书籍勿用《》；范围约束必须遵守。"
    )


def coerce_action_input(action: str, action_input: Any) -> Any:
    """规范化 action_input：finish→str；工具优先 dict，也允许短字符串交给校验层。"""
    if action == "finish":
        if isinstance(action_input, dict):
            return str(
                action_input.get("content")
                or action_input.get("answer")
                or action_input.get("text")
                or json.dumps(action_input, ensure_ascii=False)
            )
        return str(action_input or "").strip()
    if isinstance(action_input, dict):
        return action_input
    if isinstance(action_input, str):
        blob = extract_json_block(action_input)
        if isinstance(blob, dict):
            return blob
        # 保留短字符串，供 validate_and_normalize_args 兼容（如 browser_type）
        return action_input.strip()
    return {}
