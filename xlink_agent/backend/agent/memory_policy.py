"""记忆分层与相关性策略。

三层记忆（不得互相污染）：

1. 本轮任务记忆 TaskContext
   - 只服务「当前这一句用户目标」
   - 只写入本轮工具 Observation 提炼出的有效事实
   - 禁止把上一轮助手结论、浏览器残留页塞进 facts

2. 会话对话记忆（messages）
   - 给模型看「聊过什么」，但要做主题切分与脱敏
   - 主题明显切换时，旧轮只留极短摘要，避免新闻污染书单

3. 长期画像记忆（MemoryProfile / MemoryItem）
   - 只存稳定偏好（我喜欢/请记住…）
   - 注入系统提示前按当前目标做相关性过滤
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# 主题词袋：用于切分任务边界与事实相关性
TOPIC_BAGS: dict[str, tuple[str, ...]] = {
    "news": ("新闻", "热点", "资讯", "头条", "要闻", "时事"),
    "weather": ("天气", "气温", "下雨", "预报", "台风", "气象", "℃", "温度"),
    "books": ("书", "书籍", "阅读", "小说", "治愈", "推荐书", "书单", "文学", "绘本", "书籍相关摘录"),
    "docs": ("日报", "周报", "文档", "docx", "生成文件", "写一份", "导出"),
    "kb": ("知识库", "我的文档", "公司资料"),
    "browse": ("打开网页", "浏览", "搜索网页", "帮我查一下网站"),
}

_NOISE_FACTS = (
    "知识库未命中",
    "未命中相关内容",
    "InspirationalBooks",
    "Recommendations",
    "ChoiceAwards",
    "Goodreads",
    "无法直接获取",
    "可以尝试使用手机",
    "（上轮",
    "细节略",
)


def classify_topics(text: str) -> set[str]:
    t = text or ""
    hits = {name for name, kws in TOPIC_BAGS.items() if any(k in t for k in kws)}
    return hits or {"general"}


def topics_related(a: Iterable[str], b: Iterable[str]) -> bool:
    sa, sb = set(a), set(b)
    if "general" in sa or "general" in sb:
        # general 与任意主题弱相关：只有双方都只有 general 才算相关
        return sa == {"general"} and sb == {"general"} or bool((sa - {"general"}) & (sb - {"general"}))
    return bool(sa & sb)


def is_noise_fact(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if any(n.lower() in t.lower() for n in _NOISE_FACTS):
        return True
    # 纯英文短标签（爬站菜单）
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{2,40}", t):
        return True
    if t.startswith("已打开页面:"):
        return True
    return False


def fact_relevant_to_goal(fact: str, goal: str) -> bool:
    """本轮事实是否与当前用户目标相关（主题/实体重叠，无业务特判）。"""
    if is_noise_fact(fact):
        return False
    goal_topics = classify_topics(goal)
    fact_topics = classify_topics(fact)

    concrete_g = goal_topics - {"general"}
    concrete_f = fact_topics - {"general"}
    # 双方都有具体主题且无交集 → 不相关（防跨题污染）
    if concrete_g and concrete_f and not (concrete_g & concrete_f):
        # 仍允许字面实体命中
        tokens = [
            w
            for w in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", goal)
            if w not in {"帮我", "一下", "一些", "推荐", "给我", "可以", "什么", "怎么", "请问"}
        ]
        if tokens and any(tok in fact for tok in tokens):
            return True
        return False

    if topics_related(goal_topics, fact_topics):
        return True

    tokens = [
        w
        for w in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", goal)
        if w not in {"帮我", "一下", "一些", "推荐", "给我", "可以", "什么", "怎么", "请问"}
    ]
    if tokens and any(tok in fact for tok in tokens):
        return True

    if goal_topics == {"general"} and fact_topics == {"general"}:
        return 8 <= len(fact) <= 120 and not is_noise_fact(fact)

    return False


def is_new_independent_question(curr_user: str) -> bool:
    """独立新问题（概念解释/新任务），不应继承上一轮话题。"""
    cur = (curr_user or "").strip()
    if not cur:
        return False
    # 明确指代上一轮 → 不是独立新题
    if re.search(r"(刚才|上面|之前|上一[轮题]|这本|那本|这本书|那本书|这个|那个|继续|再来|为什么获取|获取不了)", cur):
        return False
    # 概念/定义类
    if re.match(r"^(什么是|什么叫|何为|谁是|啥是)\s*", cur, re.I):
        return True
    if re.match(r"^(介绍|讲解|解释|定义|阐述)\s*(一下|下)?\s*[「\"'《A-Za-z\u4e00-\u9fff]", cur):
        # 「介绍一下创新者的窘境」若带书名且像续作，上面指代已排除；纯新概念走这里
        if re.search(r"《[^》]+》", cur):
            return False  # 点名某一本书，多半是续作深挖
        return True
    # 全新任务动词 + 足够内容（排除「再来三本」）
    if re.match(r"^(帮我|给我|请|我想|我要|麻烦)", cur) and not re.search(r"再(来|给|推荐|找|说)", cur):
        return True
    if re.search(r"(推荐\d+|推荐几|找一下|查一下|搜索).{2,}", cur) and not re.search(
        r"再(来|给|推荐)|继续|刚才", cur
    ):
        return True
    return False


def is_dialog_followup(curr_user: str, prev_user: str = "") -> bool:
    """真正的多轮追问：指代/续作上一任务。独立新问题一律 False。"""
    cur = (curr_user or "").strip()
    if not cur:
        return False
    if is_new_independent_question(cur):
        return False
    # 编号选择
    if re.fullmatch(r"\d{1,2}", cur):
        return True
    if re.match(
        r"^(?:请?(?:帮我)?(?:看|打开|详细)?(?:一下)?|选)?\s*(?:第)?\s*\d+\s*[条项个号]?",
        cur,
    ):
        return True
    # 续作推荐数量
    if re.search(r"再(来|给|推荐|找)\s*\d*|再来几|还有吗|多来几|补充几", cur):
        return True
    # 深挖某一实体（带书名号/引号）
    if re.search(r"(详细|展开|讲讲|说说|介绍).{0,12}《[^》]{1,40}》", cur):
        return True
    # 失败追问 / 指代
    if re.search(
        r"(为什么|为啥|怎么回事|获取不了|查不到|打不开|失败了|不行|没用|"
        r"重试|再试|继续|刚才|上面|之前|上一|这个|那个|它们|上述|"
        r"呢\s*$|吗\s*$)",
        cur,
    ):
        return True
    if re.match(r"^(那|所以|然后|还有|继续|再帮|再给|为什么|为啥|好的|嗯)", cur):
        return True
    return False


def goal_shifted(prev_user: str, curr_user: str) -> bool:
    """相邻两轮是否换题：独立新问题强制换题；追问不换题。"""
    cur = (curr_user or "").strip()
    if is_dialog_followup(cur, prev_user):
        return False
    if is_new_independent_question(cur):
        return True
    a, b = classify_topics(prev_user), classify_topics(curr_user)
    if a == {"general"} or b == {"general"}:
        prev_toks = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", prev_user or ""))
        curr_toks = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", curr_user or ""))
        stop = {
            "帮我", "一下", "一些", "推荐", "给我", "可以", "什么", "怎么", "请问",
            "最近", "今天", "一个", "这个", "那个", "一下", "是否",
        }
        prev_toks -= stop
        curr_toks -= stop
        if not prev_toks or not curr_toks:
            # 无法判断重叠时：若当前像完整问句则视为换题，避免误串
            if len(cur) >= 6 and classify_topics(cur) == {"general"}:
                return True
            return False
        return len(prev_toks & curr_toks) == 0
    return not topics_related(a, b)


def expand_dialog_followup(
    user_text: str,
    history: list[Any],
    *,
    sanitize_fn=None,
) -> str | None:
    """把追问展开为带上轮上下文的明确目标；独立新问题不展开。"""
    raw = (user_text or "").strip()
    if not raw or is_new_independent_question(raw):
        return None

    msgs: list[tuple[str, str]] = []
    for item in history:
        role = getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else None)
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "") or ""
        if role in {"user", "assistant"}:
            msgs.append((role, content))
    if len(msgs) < 2 or msgs[-1][0] != "user":
        return None

    curr = raw
    prev_user = ""
    prev_assistant = ""
    for role, content in reversed(msgs[:-1]):
        if role == "assistant" and not prev_assistant:
            prev_assistant = content
        elif role == "user" and not prev_user:
            prev_user = content
        if prev_user and prev_assistant:
            break
    if not prev_user or not is_dialog_followup(curr, prev_user):
        return None

    ans = prev_assistant or ""
    if sanitize_fn:
        try:
            ans = sanitize_fn(ans) or ans
        except Exception:
            pass
    ans = re.sub(r"\s+", " ", ans).strip()
    if len(ans) > 360:
        ans = ans[:360] + "…"

    # 深挖单点
    m_book = re.search(r"《([^》]{1,40})》", curr)
    if m_book and re.search(r"(详细|展开|讲讲|说说|介绍)", curr):
        title = m_book.group(1)
        return (
            f"多轮续作：用户只要深入了解「{title}」。\n"
            f"上一轮用户目标：{prev_user.strip()}\n"
            f"要求：只讲述「{title}」，不要重复上一轮完整清单，不要扯到其它条目。\n"
            f"用户原话：{curr}"
        )

    if re.search(r"再(来|给|推荐|找)\s*(\d+|几|[一二三四五六七八九十]+)|再来几|补充", curr):
        return (
            f"多轮续作：在上一轮同类推荐基础上追加，不要重复已出现过的条目。\n"
            f"上一轮用户目标：{prev_user.strip()}\n"
            f"上一轮答复摘要：{ans or '（无）'}\n"
            f"用户现在要求：{curr}"
        )

    return (
        f"多轮追问：必须结合上一轮上下文，禁止说没有上下文；也禁止跑题到更早无关话题。\n"
        f"上一轮用户目标：{prev_user.strip()}\n"
        f"上一轮助手答复摘要：{ans or '（无有效答复，可能工具失败）'}\n"
        f"用户现在追问：{curr}\n"
        f"请针对追问作答；若上一轮失败则解释原因并重试完成上一轮目标。"
    )


def build_dialog_messages(
    history: list[Any],
    *,
    current_goal: str,
    sanitize_fn,
    looks_internal_fn,
) -> list[dict[str, str]]:
    """会话记忆三态：新题硬隔离 / 追问保留同题 / 默认短窗。"""
    msgs: list[tuple[str, str]] = []
    for m in history:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
        if role not in {"user", "assistant"}:
            continue
        msgs.append((role, content or ""))

    if not msgs:
        return []

    user_indices = [i for i, (r, _) in enumerate(msgs) if r == "user"]
    if len(user_indices) >= 2:
        prev_u = msgs[user_indices[-2]][1]
        curr_u = msgs[user_indices[-1]][1]
        followup = is_dialog_followup(curr_u, prev_u)
        shifted = goal_shifted(prev_u, curr_u)
        independent = is_new_independent_question(curr_u)
    else:
        followup = False
        shifted = False
        independent = False

    out: list[dict[str, str]] = []

    # 新题：硬隔离 —— 不注入任何上一轮正文，避免「创新者的窘境」污染「什么是 AI Agent」
    if (shifted or independent) and not followup:
        out.append(
            {
                "role": "system",
                "content": (
                    "【新问题·硬隔离】本轮是独立新任务，与会话中更早的问题无关。"
                    "禁止提及、联想或续写上一轮主题；禁止把上一轮书名/新闻/结论拼进本轮答案。"
                    f"本轮唯一目标：{current_goal[:500]}"
                ),
            }
        )
        out.append({"role": "user", "content": (current_goal or curr_u)[:2500]})
        return out

    keep_n = 3 if followup else 2
    keep_from = user_indices[-keep_n] if len(user_indices) >= keep_n else 0
    if followup:
        out.append(
            {
                "role": "system",
                "content": (
                    "【多轮追问】用户在延续上一轮同一任务。"
                    "结合最近对话理解指代；只回答追问点，不要无必要重复整份旧列表；"
                    "禁止跳到更早无关主题。"
                ),
            }
        )
    for role, content in msgs[keep_from:]:
        if role == "assistant":
            clean = sanitize_fn(content)
            if not clean or looks_internal_fn(clean) or is_noise_fact(clean):
                clean = "（上轮已回复）"
            elif clean.startswith("这是我目前整理到的要点") or "线索，不是最终答案" in clean:
                clean = "（上轮材料未形成可用答复）"
            out.append({"role": "assistant", "content": clean[:1800]})
        else:
            if (
                user_indices
                and content.strip() == msgs[user_indices[-1]][1].strip()
                and current_goal
                and current_goal != content
            ):
                out.append({"role": "user", "content": current_goal[:2500]})
            else:
                out.append({"role": "user", "content": content[:1500]})
    return out


def answer_relevant_to_goal(answer: str, goal: str) -> bool:
    """最终答复是否像在回答当前目标（拦截串题 / 机械 dump）。

    用主题交集与字面实体重叠，不做「荐书/新闻/天气」产品级特判。
    """
    text = (answer or "").strip()
    if not text or is_noise_fact(text):
        return False
    if text.startswith("这是我目前整理到的要点"):
        body = text.split("：", 1)[-1] if "：" in text else text
        return fact_relevant_to_goal(body, goal)

    goal_topics = classify_topics(goal)
    ans_topics = classify_topics(text)

    # 双方都有具体主题且完全无交集 → 视为串题
    concrete_g = goal_topics - {"general"}
    concrete_a = ans_topics - {"general"}
    if concrete_g and concrete_a and not (concrete_g & concrete_a):
        # 允许答案偏 general（兜底说明）
        if concrete_a and len(text) > 80:
            # 再看实体字面重叠
            tokens = [
                w
                for w in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", goal)
                if w not in {"帮我", "一下", "一些", "推荐", "给我", "可以", "什么", "怎么", "请问"}
            ]
            if tokens and any(tok in text for tok in tokens):
                return True
            return False
    return True


def filter_long_term_memory_lines(memory_blob: str, goal: str) -> str:
    """长期记忆按目标过滤；无关偏好不注入。"""
    if not (memory_blob or "").strip():
        return ""
    goal_topics = classify_topics(goal)
    kept: list[str] = []
    for ln in memory_blob.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("用户画像") or s.startswith("用户偏好"):
            # 画像仅在有主题交集或 general 时保留短摘要
            if goal_topics == {"general"} or topics_related(goal_topics, classify_topics(s)):
                kept.append(s[:300])
            continue
        if fact_relevant_to_goal(s, goal) or topics_related(goal_topics, classify_topics(s)):
            kept.append(s[:300])
    return "\n".join(kept[:8])
