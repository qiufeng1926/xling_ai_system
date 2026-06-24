"""递归列举用户云空间文件"""

from __future__ import annotations

from integrations.feishu.docs import enrich_file_item, list_files
from integrations.feishu.file_types import LISTABLE_TYPES


def list_all_files_recursive(user_access_token: str, *, max_files: int = 500) -> list[dict]:
    """广度优先遍历文件夹，收集可镜像的文件元数据"""
    collected: list[dict] = []
    folder_queue: list[str] = [""]
    seen_folders: set[str] = set()

    while folder_queue and len(collected) < max_files:
        folder = folder_queue.pop(0)
        if folder in seen_folders:
            continue
        seen_folders.add(folder)
        page_token = ""
        for _ in range(50):
            data = list_files(
                user_access_token,
                folder_token=folder,
                page_size=100,
                page_token=page_token,
            )
            for item in data.get("files") or []:
                if not isinstance(item, dict):
                    continue
                file_type = (item.get("type") or "").strip()
                token = (item.get("token") or "").strip()
                if file_type == "folder" and token:
                    folder_queue.append(token)
                    continue
                if file_type in LISTABLE_TYPES and token:
                    collected.append(enrich_file_item(item))
                    if len(collected) >= max_files:
                        break
            if len(collected) >= max_files:
                break
            if not data.get("has_more"):
                break
            page_token = data.get("page_token") or ""
            if not page_token:
                break
    return collected
