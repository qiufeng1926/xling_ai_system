"""将采集 filters JSON 格式化为可读摘要"""

from app.constants.xingtu_filters import FILTER_GROUPS

_LABEL_MAP: dict[str, str] = {}
for group in FILTER_GROUPS:
    for field in group["fields"]:
        _LABEL_MAP[field["key"]] = field["label"]


def build_filter_summary(filters: dict | None) -> list[str]:
    if not filters:
        return ["不限"]

    parts: list[str] = []
    for key, value in filters.items():
        if key.startswith("_") or value in (None, "", []):
            continue
        label = _LABEL_MAP.get(key, key)
        if isinstance(value, list):
            parts.append(f"{label}: {', '.join(str(v) for v in value)}")
        else:
            parts.append(f"{label}: {value}")

    return parts or ["不限"]
