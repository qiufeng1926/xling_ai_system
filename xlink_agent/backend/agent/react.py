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


REACT_SYSTEM_PROMPT = """你是 xlink 通用办公智能体（目标对齐 OpenClaw 一类全能 Agent）：
用 ReAct 循环自主完成用户交给你的任意任务——查资料、浏览网页、写文档、检索知识库、操作表单等。
不要假定自己只擅长某一类功能；按当前目标选择合适工具。

## 运行方式（严格）
1. 每次只输出 **一个** JSON（禁止一次多步、禁止 Markdown 代码块）
2. 运行时执行工具 → 你会收到 Observation → 再决定下一步
3. 信息足够后 action=finish，给普通人能直接阅读的中文答案

调用工具：
{"thought":"为何需要这一步","action":"web_search","action_input":{"query":"..."}}

结束：
{"thought":"可以交付了","action":"finish","action_input":"给用户的中文完整答案"}

## 交付质量（对齐主流智能体）
- finish 的答案应像可读简报：一句总起 + 编号列表；每条「标题 + 2～4 句具体要点」
- 非书籍场景禁止滥用书名号《》
- 条数/范围（如 7 条、国际）必须遵守；材料不对题就换关键词再搜，不要拿国内政闻凑国际新闻
- 搜索摘要不够时继续 web_fetch 1～2 个内容站，再 finish

## 通用工具策略（能力层，不是业务特例）
- 不知道网址 → web_search（系统会自动尝试多搜索源；失败时用浏览器打开搜索页）
- 搜索到链接后 → web_fetch 打开前 1～2 个结果页提炼内容，再 finish
- 需要点选/输入/看页面 → browser_navigate →（必要时）browser_extract；extract 的 selector 可省略
- 用户私有资料 → kb_search
- 交付 Word/Excel/PDF/HTML 等 → file_write_*（HTML 可用 file_write_markdown 或写 .html 的 markdown/正文工具）
- http_request 是底层 GET；多数页面优先 web_fetch

## 硬性规则
1. 每一轮只做一个 Action，等 Observation 后再继续。
2. finish 禁止 JSON / 工具名 /「内部步骤」；只给用户可读结论。
3. **finish 的 action_input 必须写清要点**：具体条目写进 action_input；禁止空壳套话；**Thought 与 action_input 必须一致且可被 Observation 核实**。
4. 禁止把搜狗/Bing/DuckDuckGo 的搜索中间页链接当作答案；应 web_fetch 内容站，或直接写清标题与摘要。
5. **搜索结果标题 ≠ 答案实体**：标题只是线索；必须从网页正文提炼用户真正要的内容后再 finish。
6. **只读联网任务禁止让用户选编号/二选一**：搜索后自行 web_fetch；只有会改本机文件、提交表单、删除等才走确认。
7. 需要事实时不要编造：没有 Observation 支撑就继续取数，或坦诚说明查不到。
8. 失败动作不要死循环；换工具或换查询词（遇到验证码页立刻换下一条链接或改用 web_fetch）。
9. 用户**明确换题**后禁止沿用上一题结论；若是追问/指代上一轮（为什么、获取不了、继续等），必须结合会话历史，禁止说「没有上下文」。
10. browser_extract 禁止超长 CSS；拿不到选择器就省略 selector。
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


def build_react_continue_prompt(work_memory: str, scratchpad: ReactScratchpad) -> str:
    return (
        f"{work_memory}\n\n"
        f"{scratchpad.render()}\n\n"
        "请输出下一步 **单个** ReAct JSON：\n"
        '- 还缺信息 → {"thought":"...","action":"<工具名>","action_input":{...}}\n'
        '- 已可交付 → {"thought":"...","action":"finish","action_input":"含具体要点的中文答案（禁止 JSON、禁止空壳套话）"}\n'
        "硬性：回答「当前用户目标」（若目标里已包含上一轮上下文，必须用上）；"
        "会话历史里的追问不要当成无上下文。"
        "若工作记忆里没有与目标相关的有效信息，去取数或如实说明原因并重试，"
        "禁止把无关旧题结论拼进答案。"
        "若 Observation 已有搜索标题，须先 web_fetch 正文再 finish；"
        "finish 必须给出用户真正要的具体内容，禁止把搜索标题原样当成答案条目；"
        "finish 交付应为「总起 + 编号（标题行 + 要点段落）」；"
        "非书籍勿用《》；范围约束（国际/条数等）必须遵守。"
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
