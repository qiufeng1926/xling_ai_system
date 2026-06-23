"""本地文件上传并导入为飞书云文档"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from config.config import feishu_api_base
from integrations.feishu.docs import _normalize_created
from integrations.feishu.errors import FeishuError
from integrations.feishu.import_rules import (
    IMPORT_MAX_BYTES,
    IMPORT_TARGET_EXTENSIONS,
    IMPORT_TARGET_LABELS,
    import_targets_for_extension,
    normalize_extension,
    validate_import_request,
)

_IMPORT_POLL_INTERVAL = 1.5
_IMPORT_POLL_TIMEOUT = 90.0

# job_status != 0/1/2 时的常见错误说明
_IMPORT_JOB_ERRORS: dict[int, str] = {
    3: "飞书导入内部错误",
    100: "导入文档已加密，无法转换",
    104: "租户云空间容量不足",
    108: "导入处理超时",
    110: "无权限导入到目标目录",
    112: "文件格式不支持",
    115: "导入文件过大",
    116: "无权限导入到该文件夹",
    118: "文件后缀与导入任务不匹配",
    129: "文件格式损坏，请另存为新文件后重试",
}


def _headers(user_access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_access_token}"}


def _check(data: dict[str, Any], *, action: str) -> dict[str, Any]:
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("msg") or f"{action}失败"),
        )
    return data.get("data") or {}


def get_import_formats() -> dict[str, Any]:
    return {
        "max_size_bytes": IMPORT_MAX_BYTES,
        "targets": [
            {
                "type": target,
                "label": IMPORT_TARGET_LABELS.get(target, target),
                "extensions": sorted(IMPORT_TARGET_EXTENSIONS[target]),
            }
            for target in ("docx", "sheet", "bitable")
        ],
    }


def upload_import_source(
    user_access_token: str,
    *,
    filename: str,
    content: bytes,
    target_type: str,
    file_extension: str,
) -> str:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/drive/v1/medias/upload_all"
    extra = json.dumps(
        {"obj_type": target_type, "file_extension": file_extension},
        ensure_ascii=False,
    )
    data = {
        "file_name": filename,
        "parent_type": "ccm_import_open",
        "parent_node": "",
        "size": str(len(content)),
        "extra": extra,
    }
    files = {"file": (filename, content, "application/octet-stream")}
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), data=data, files=files)
    body = resp.json()
    if body.get("code", 0) != 0:
        raise FeishuError(
            int(body.get("code", -1)),
            str(body.get("msg") or "上传导入源文件失败"),
        )
    file_token = (body.get("data") or {}).get("file_token") or ""
    if not file_token:
        raise FeishuError(-1, "飞书未返回 file_token")
    return file_token


def create_import_task(
    user_access_token: str,
    *,
    file_token: str,
    file_extension: str,
    target_type: str,
    file_name: str,
    folder_token: str = "",
) -> str:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/drive/v1/import_tasks"
    body: dict[str, Any] = {
        "file_extension": file_extension,
        "file_token": file_token,
        "type": target_type,
        "file_name": file_name,
        "point": {
            "mount_type": 1,
            "mount_key": folder_token or "",
        },
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), json=body)
    data = _check(resp.json(), action="创建导入任务")
    ticket = (data.get("ticket") or "").strip()
    if not ticket:
        raise FeishuError(-1, "飞书未返回导入任务 ID")
    return ticket


def get_import_task_result(user_access_token: str, ticket: str) -> dict[str, Any]:
    url = f"{feishu_api_base.rstrip('/')}/open-apis/drive/v1/import_tasks/{ticket}"
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, headers=_headers(user_access_token))
    data = _check(resp.json(), action="查询导入任务")
    return data.get("result") or {}


def _wait_import_task(user_access_token: str, ticket: str) -> dict[str, Any]:
    deadline = time.monotonic() + _IMPORT_POLL_TIMEOUT
    while time.monotonic() < deadline:
        result = get_import_task_result(user_access_token, ticket)
        status = result.get("job_status")
        if status == 0:
            return result
        if status in (1, 2):
            time.sleep(_IMPORT_POLL_INTERVAL)
            continue
        msg = (result.get("job_error_msg") or "").strip()
        if not msg:
            msg = _IMPORT_JOB_ERRORS.get(int(status or -1), f"导入失败 (status={status})")
        raise FeishuError(int(status or -1), msg)
    raise FeishuError(-1, "导入超时，请稍后在飞书云空间中查看")


def import_local_file(
    user_access_token: str,
    *,
    filename: str,
    content: bytes,
    target_type: str,
    folder_token: str = "",
    display_name: str = "",
) -> dict[str, Any]:
    ext = validate_import_request(
        filename=filename,
        target_type=target_type,
        size=len(content),
    )
    title = (display_name or filename).strip()
    if title.lower().endswith(f".{ext}"):
        title = title[: -(len(ext) + 1)].strip() or title

    file_token = upload_import_source(
        user_access_token,
        filename=filename,
        content=content,
        target_type=target_type,
        file_extension=ext,
    )
    ticket = create_import_task(
        user_access_token,
        file_token=file_token,
        file_extension=ext,
        target_type=target_type,
        file_name=title,
        folder_token=folder_token,
    )
    result = _wait_import_task(user_access_token, ticket)

    result_type = (result.get("type") or target_type).strip().lower()
    if result_type == "doc":
        result_type = "docx"
    token = (result.get("token") or "").strip()
    if not token:
        raise FeishuError(-1, "导入完成但未返回文档 token")

    created = _normalize_created(
        file_type=result_type,
        token=token,
        title=title,
        url=result.get("url"),
    )
    extra = result.get("extra") or []
    if extra:
        created["import_warnings"] = [str(x) for x in extra]
    return created


def suggest_import_target(filename: str) -> dict[str, Any]:
    ext = normalize_extension(filename)
    targets = import_targets_for_extension(ext)
    return {
        "extension": ext,
        "targets": targets,
        "default_target": targets[0] if len(targets) == 1 else "",
    }
