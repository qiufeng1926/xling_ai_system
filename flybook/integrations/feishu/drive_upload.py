"""飞书云空间文件上传（用户身份）"""

from __future__ import annotations

import httpx

from config.config import feishu_api_base
from integrations.feishu.docs import get_root_folder_meta
from integrations.feishu.errors import FeishuError


def _headers(user_access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_access_token}"}


def upload_file_to_drive(
    user_access_token: str,
    *,
    filename: str,
    content: bytes,
    folder_token: str = "",
) -> str:
    """上传文件到云空间，返回 file_token"""
    if not content:
        raise ValueError("文件为空")
    folder = (folder_token or "").strip()
    if not folder:
        meta = get_root_folder_meta(user_access_token)
        folder = (meta.get("token") or meta.get("id") or "").strip()
    if not folder:
        raise FeishuError(-1, "无法获取飞书云空间根目录")

    url = f"{feishu_api_base.rstrip('/')}/open-apis/drive/v1/files/upload_all"
    data = {
        "file_name": filename,
        "parent_type": "explorer",
        "parent_node": folder,
        "size": str(len(content)),
    }
    files = {"file": (filename, content, "application/octet-stream")}
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(url, headers=_headers(user_access_token), data=data, files=files)
    body = resp.json()
    if body.get("code", 0) != 0:
        raise FeishuError(
            int(body.get("code", -1)),
            str(body.get("msg") or "上传文件到云空间失败"),
        )
    file_token = (body.get("data") or {}).get("file_token") or ""
    if not file_token:
        raise FeishuError(-1, "飞书未返回 file_token")
    return file_token
