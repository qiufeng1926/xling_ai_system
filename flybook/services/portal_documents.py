"""向 xlink 门户注册云文档镜像"""

from __future__ import annotations

import httpx

from config.config import flybook_internal_key, portal_api_url
from utils.logger import get_logger

logger = get_logger("portal_documents")


def register_document_mirror(
    *,
    user_id: int,
    feishu_token: str,
    feishu_type: str,
    title: str = "",
    feishu_url: str = "",
    content: str = "",
) -> None:
    base = (portal_api_url or "").strip().rstrip("/")
    key = (flybook_internal_key or "").strip()
    if not base or not key:
        logger.warning("跳过文档镜像注册：PORTAL_API_URL 或 FLYBOOK_INTERNAL_KEY 未配置")
        return

    body = {
        "user_id": user_id,
        "feishu_token": feishu_token,
        "feishu_type": feishu_type,
        "title": title,
        "feishu_url": feishu_url,
        "content": content,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                f"{base}/api/v1/internal/feishu-documents/register",
                json=body,
                headers={"X-Flybook-Internal-Key": key},
            )
        if resp.status_code != 200:
            logger.warning(
                "文档镜像注册失败",
                extra={"output_params": {"status": resp.status_code, "body": resp.text[:200]}},
            )
    except Exception as exc:
        logger.warning("文档镜像注册异常", extra={"output_params": {"error": str(exc)[:200]}})
