"""实体抽取：人名/题名/年份/术语等，供检索与校验下游使用。"""

from __future__ import annotations

import re

from agent.entity_match import extract_query_entities


_YEAR_RE = re.compile(r"(?:公元\s*)?((?:19|20)\d{2})\s*年?")
_TERM_RE = re.compile(
    r"([\u4e00-\u9fff]{2,12}(?:算法|框架|协议|模型|系统|平台|标准|政策|规划))"
)
_PERSON_HINT_RE = re.compile(
    r"(?:作者|作家|学者|教授|导演|创始人)[:：\s]*([\u4e00-\u9fff·]{2,12})"
)


def extract_delivery_entities(goal: str, *, draft: str = "") -> list[str]:
    """抽取关键实体（去重保序）。"""
    blob = f"{goal or ''}\n{draft or ''}"
    out: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        n = (name or "").strip().strip("《》\"'「」")
        if not n or len(n) < 2 or len(n) > 40:
            return
        key = n.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(n)

    # 复用办公实体：文件名、单据号、《题名》
    for val in extract_query_entities(goal or ""):
        _add(str(val))

    for m in re.finditer(r"《([^》]{1,40})》", blob):
        _add(m.group(1))
    for m in _YEAR_RE.finditer(blob):
        _add(m.group(1) + "年")
    for m in _PERSON_HINT_RE.finditer(blob):
        _add(m.group(1))
    for m in _TERM_RE.finditer(blob):
        _add(m.group(1))

    return out[:40]
