"""提示词模板注册表：按名称加载 Markdown 模板（改完重启生效）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# 逻辑名 → 文件名
_TEMPLATE_FILES: dict[str, str] = {
    "react_base": "react_base.md",
    "synthesize_grounded": "synthesize_grounded.md",
    "synthesize_expand": "synthesize_expand.md",
    "finalize_list": "finalize_list.md",
    "fallback_honest": "fallback_honest.md",
}


@lru_cache(maxsize=32)
def load_template(name: str) -> str:
    """加载模板正文；缺失时返回空串。"""
    fname = _TEMPLATE_FILES.get(name)
    if not fname:
        return ""
    path = _TEMPLATES_DIR / fname
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def clear_template_cache() -> None:
    load_template.cache_clear()
