"""飞书模块配置与状态"""

from fastapi import APIRouter, Depends

from api.auth_utils import get_current_user
from api.portal_auth import PortalUser
from config.config import (
    feishu_docs_component_sdk_url,
    feishu_doc_base_url,
    feishu_messenger_url,
    feishu_oauth_scope,
)
from integrations.feishu import FeishuClient

router = APIRouter(prefix="/config", tags=["飞书配置"])


@router.get("")
def get_flybook_config(_user: PortalUser = Depends(get_current_user)):
    """返回前端可用的飞书入口与后端集成状态（需登录）"""
    return {
        "messenger_url": feishu_messenger_url,
        "doc_base_url": feishu_doc_base_url,
        "docs_component_sdk_url": feishu_docs_component_sdk_url,
        "oauth_scope": feishu_oauth_scope,
        "open_api_configured": FeishuClient.is_configured(),
    }
