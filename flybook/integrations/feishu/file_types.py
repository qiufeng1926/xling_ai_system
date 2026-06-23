"""云文档类型常量与 URL 构建"""

from __future__ import annotations

from config.config import feishu_doc_base_url

# 可在云空间 / 我的文档库创建的类型
CREATE_TYPE_ORDER = ("docx", "sheet", "bitable", "slides", "mindnote")
CREATE_TYPES = frozenset(CREATE_TYPE_ORDER)

# 列表展示 & 可打开的类型
LISTABLE_TYPES = frozenset({"docx", "doc", "sheet", "bitable", "slides", "mindnote", "file"})

# 可用 DocComponentSdk 内嵌编辑
EMBED_EDIT_TYPES = frozenset({"docx", "doc"})

CREATE_TYPE_LABELS: dict[str, str] = {
    "docx": "文档",
    "sheet": "表格",
    "bitable": "多维表格",
    "slides": "幻灯片",
    "mindnote": "思维笔记",
}

# 飞书云空间 URL 路径段（不含 doc 旧版）
URL_PATH_BY_TYPE: dict[str, str] = {
    "docx": "docx",
    "doc": "docx",
    "sheet": "sheets",
    "bitable": "base",
    "slides": "slides",
    "mindnote": "mindnote",
    "file": "file",
}


def build_file_url(file_type: str, token: str, fallback_url: str | None = None) -> str:
    if fallback_url:
        return fallback_url
    if not token:
        return ""
    base = (feishu_doc_base_url or "https://bytedance.feishu.cn").rstrip("/")
    path = URL_PATH_BY_TYPE.get(file_type, file_type)
    return f"{base}/{path}/{token}"
