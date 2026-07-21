"""回答安全限制：违规问题统一拒答，避免进入工具链或产出危险内容。"""

from __future__ import annotations

import re

# 统一对外拒答文案（勿改风格，前后端一致）
SAFETY_REFUSAL = "当前问题暂不支持回答哦~"

SAFETY_POLICY_PROMPT = """
# 回答限制

## 禁止回答的问题

对于以下问题，你必须拒绝回答，且 **不得** 调用任何工具（含 web_search / web_fetch / run_code / file_write_* / kb_search / browser_*）：

### 违法违规内容

包括但不限于：

- 政治敏感（如分裂国家、颠覆政权、涉台「独立/建国/就是一个国家」等错误主张与求证）
- 色情低俗
- 暴力血腥（含详细伤害、制造武器伤人指南）
- 赌博技巧
- BUG利用（漏洞利用、入侵、免杀等）
- 黑产内容
- 侵权盗版
- 非法交易
- 人身攻击
- 仇恨言论
- 违法犯罪相关内容（含毒品/管制品制作、合成、提炼、提纯、分子式制作原理等）

统一回复风格（finish 的 action_input 必须原样输出，禁止解释、禁止搜索、禁止给步骤）：
当前问题暂不支持回答哦~

示例：
{"thought":"该问题属于禁止回答范围","action":"finish","action_input":"当前问题暂不支持回答哦~"}
""".strip()


# —— 高置信规则：命中则硬拦截（不依赖模型自觉）——

# 常见毒品/管制品分子式（去分隔符后匹配）
_ILLICIT_FORMULAS = {
    "c21h23no5",  # 海洛因
    "c17h19no3",  # 吗啡
    "c18h21no3",  # 可待因
    "c17h21no4",  # 可卡因
    "c10h15n",  # 甲基苯丙胺（常见写法）
    "c9h13no",  # 麻黄碱
    "c16h14f3n3o2s",  # 氟胺酮相关常见式之一，宽匹配用下面别名
}

_DRUG_NAMES = (
    r"毒品|制毒|吸毒|贩毒|海洛因|吗啡|可卡因|冰毒|甲基苯丙胺|麻黄碱|麻黄素|"
    r"摇头丸|芬太尼|氯胺酮|k粉|大麻精油|鸦片|罂粟|美沙酮|杜冷丁|diacetylmorphine|"
    r"heroin|cocaine|methamphetamine|fentanyl|ketamine|opium|morphine"
)

# 「原理/做法」等制作意图（单独出现也要命中分子式场景）
_DRUG_PROCESS = (
    r"制作|合成|提炼|提纯|乙酰化|生产工艺|制作原理|怎么做|如何做|怎样做|"
    r"制取|配方|工序|制备|制法|作法|做法|怎么制|如何制|怎样制|"
    r"合成路线|反应条件|工艺流程|告诉我.{0,12}原理|讲解.{0,12}原理"
)

_POLITICAL = (
    r"台独|藏独|疆独|港独|分裂国家|颠覆国家|推翻.{0,8}政权|"
    r"一中一台|两个中国|台湾独立|台湾建国|台湾独立运动|"
    # 独立相关
    r"台湾是(个|一個)?独立(的)?国家|台湾是不是独立|"
    r"台湾.{0,8}(什么时候|何时|哪年|几时).{0,12}独立|"
    r"台湾独立(了|了吗|吗|嘛|没)|"
    # 「台湾就是/是一个国家」类主权主张（排除「台湾是中国…」由下方负向过滤）
    r"台湾就是(一个|一個|一)?国家|"
    r"台湾是(一个|一個|一)?国家|"
    r"台湾.{0,6}(主权国家|独立主权)|"
    r"承认台湾(为|是|当作).{0,6}国家|"
    r"中华民国是(一个|一個)?(独立)?主权国家"
)

_PORN = r"色情|淫秽|成人视频|黄片|约炮|裸聊|乱伦|儿童色情|萝莉色情"

_VIOLENCE = r"杀人教程|如何杀人|虐杀|人体分解|自制炸弹详细|土制炸弹配方|暗杀技巧"

_GAMBLE = r"赌博技巧|出千方法|赌博必赢|赌场作弊|透视扑克"

_HACK = (
    r"漏洞利用|免杀木马|钓鱼邮件教程|入侵他人|撞库教程|社工库|"
    r"sql注入实战入侵|勒索软件编写|ddos攻击教程"
)

_BLACKHAT = r"黑产|洗钱教程|地下钱庄|假证办理|办假证|伪造证件|盗刷信用卡"

_PIRACY = r"破解版下载站推荐|盗版资源站|免费看会员电影破解"

_ATTACK = r"去死吧|杂种|滚出中国.*(骂)|仇恨某民族灭绝"

# 明确合法表述：不因「台湾」「国家」误伤
_POLITICAL_ALLOW = (
    r"台湾是中国|台湾属于中国|台湾是中国的|一个中国|一中原则|"
    r"台湾(旅游|美食|景点|天气|高铁|夜市|果蔬|水果|小吃|酒店|机票)"
)


def _norm(text: str) -> str:
    """小写、去空白；全角字母数字转半角，便于分子式匹配。"""
    s = (text or "").strip().lower()
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        # 全角！到～ → 半角
        if 0xFF01 <= o <= 0xFF5E:
            out.append(chr(o - 0xFEE0))
        elif ch in "\u3000\t\r\n ":
            continue
        else:
            out.append(ch)
    return "".join(out)


def _compact_alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(text))


def _has_illicit_formula(text: str) -> bool:
    compact = _compact_alnum(text)
    if any(f in compact for f in _ILLICIT_FORMULAS):
        return True
    # 宽松：C21 H23 NO5 / C21-H23-NO5
    if re.search(r"c\s*21\s*h\s*23\s*n\s*o\s*5", _norm(text), re.I):
        return True
    return False


def _political_hit(text: str) -> bool:
    t = _norm(text)
    if re.search(_POLITICAL_ALLOW, t, re.I):
        # 仍拦截「台湾是中国的一个独立国家」等夹带独立
        if re.search(r"独立|台独|一中一台|两个中国", t, re.I):
            return True
        return False
    return bool(re.search(_POLITICAL, t, re.I))


def is_disallowed_request(text: str) -> bool:
    """用户目标/追问是否属于禁止回答范围（启发式硬拦截）。"""
    t = _norm(text)
    if not t:
        return False

    # 管制品分子式 + 制作/原理意图
    if _has_illicit_formula(t) and re.search(_DRUG_PROCESS, t, re.I):
        return True
    # 分子式本身出现在「告诉我/讲解 … 制作|原理」语境
    if _has_illicit_formula(t) and re.search(
        r"(告诉我|讲解|介绍|说明|详解|请问).{0,24}(原理|制作|合成|制法|配方)", t, re.I
    ):
        return True
    # 毒品名 + 制作意图
    if re.search(_DRUG_NAMES, t, re.I) and re.search(_DRUG_PROCESS, t, re.I):
        return True
    if re.search(r"(制毒|贩毒|教.{0,6}制毒|毒品制作|制毒方法)", t, re.I):
        return True

    if _political_hit(t):
        return True
    if re.search(_PORN, t, re.I):
        return True
    if re.search(_VIOLENCE, t, re.I):
        return True
    if re.search(_GAMBLE, t, re.I):
        return True
    if re.search(_HACK, t, re.I):
        return True
    if re.search(_BLACKHAT, t, re.I):
        return True
    if re.search(_PIRACY, t, re.I):
        return True
    if re.search(_ATTACK, t, re.I):
        return True

    return False


def answer_contains_prohibited_detail(text: str) -> bool:
    """终稿是否已泄漏禁止内容（模型越狱后兜底）。"""
    t = _norm(text)
    if not t or t == _norm(SAFETY_REFUSAL):
        return False
    if re.search(_DRUG_NAMES, t, re.I) and re.search(
        r"乙酰化|乙酸酐|提纯步骤|合成路线|从鸦片|吗啡.{0,8}乙酰|制作原理", t, re.I
    ):
        return True
    if _has_illicit_formula(t) and re.search(r"乙酰化|乙酸酐|合成|制作步骤", t, re.I):
        return True
    if re.search(
        r"台湾.{0,24}(独立国家|已经独立|正式独立|宣布独立|就是(一个|一個)?国家|是(一个|一個)?国家)",
        t,
        re.I,
    ):
        # 允许「台湾是中国的一部分」类表述
        if re.search(r"台湾是中国|台湾属于中国|一个中国", t, re.I) and not re.search(
            r"独立|台独", t, re.I
        ):
            return False
        return True
    return False


def enforce_safety_answer(*, goal: str = "", answer: str = "") -> str:
    """若用户目标违规，或终稿泄漏禁止细节，强制替换为统一拒答。

    注意：不得对终稿套用 is_disallowed_request——行业报告常出现
    「色情/暴力内容监管」等合规表述，会误杀正常办公写作。
    """
    if is_disallowed_request(goal):
        return SAFETY_REFUSAL
    if answer_contains_prohibited_detail(answer):
        return SAFETY_REFUSAL
    return answer or ""


def is_safety_refusal(text: str) -> bool:
    return _norm(text) == _norm(SAFETY_REFUSAL)
