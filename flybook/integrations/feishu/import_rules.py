"""本地文件导入云文档规则"""

from __future__ import annotations

IMPORT_MAX_BYTES = 20 * 1024 * 1024  # upload_all 单文件上限

# 导入目标 -> 允许的扩展名（小写，不含点）
IMPORT_TARGET_EXTENSIONS: dict[str, frozenset[str]] = {
    "docx": frozenset({"doc", "docx", "txt", "md", "mark", "markdown", "html"}),
    "sheet": frozenset({"xlsx", "xls", "csv"}),
    "bitable": frozenset({"xlsx", "csv"}),
}

IMPORT_TARGET_LABELS: dict[str, str] = {
    "docx": "文档",
    "sheet": "表格",
    "bitable": "多维表格",
}

# 扩展名别名（飞书要求 file_extension 与实际后缀严格一致时，优先用文件名后缀）
MARKDOWN_ALIASES = frozenset({"markdown", "mark", "md"})


def normalize_extension(filename: str) -> str:
    name = (filename or "").strip().lower()
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1]


def import_targets_for_extension(ext: str) -> list[str]:
    ext = ext.strip().lower()
    if not ext:
        return []
    return [t for t, allowed in IMPORT_TARGET_EXTENSIONS.items() if ext in allowed]


def validate_import_request(*, filename: str, target_type: str, size: int) -> str:
    ext = normalize_extension(filename)
    if not ext:
        raise ValueError("无法识别文件扩展名")
    target = (target_type or "").strip().lower()
    if target not in IMPORT_TARGET_EXTENSIONS:
        raise ValueError(f"不支持的导入目标: {target_type}")
    allowed = IMPORT_TARGET_EXTENSIONS[target]
    if ext not in allowed:
        raise ValueError(f".{ext} 不能导入为{IMPORT_TARGET_LABELS.get(target, target)}")
    if size <= 0:
        raise ValueError("文件为空")
    if size > IMPORT_MAX_BYTES:
        raise ValueError(f"文件超过 {IMPORT_MAX_BYTES // (1024 * 1024)}MB 上限，请压缩后重试")
    return ext
