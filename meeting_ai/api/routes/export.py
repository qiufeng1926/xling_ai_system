"""AI 总结导出 API"""
import json
import os
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import get_current_user, get_db
from api.permissions import can_download_files
from config.config import output_dir
from db.models import User
from db.session import check_meeting_access, get_meeting_by_file_id, log_meeting_download
from utils.docx_export import build_export_filename, markdown_to_docx
from utils.visual_export import (
    build_visual_export_filename,
    visual_summary_to_html,
    visual_summary_to_json_bytes,
)
from utils.logger import get_logger

router = APIRouter()
logger = get_logger("export_route")


def _require_download_permission(user: User) -> None:
    if not can_download_files(user):
        raise HTTPException(
            status_code=403,
            detail='暂无下载/导出权限，请在账户管理中向超级管理员申请',
        )


class SummaryExportRequest(BaseModel):
    content: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=100)


class VisualExportRequest(BaseModel):
    visual: dict[str, Any] = Field(...)
    title: str = Field(..., min_length=1, max_length=100)


def _docx_response(content: str, title: str, file_id: str | None = None) -> Response:
    docx_bytes = markdown_to_docx(content, title=title)
    filename = build_export_filename(title, file_id)
    encoded = quote(filename)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=\"{encoded}\"; filename*=UTF-8''{encoded}",
        },
    )


def _load_summary_for_meeting(file_id: str) -> tuple[str, str]:
    meeting = get_meeting_by_file_id(file_id)
    title = "AI 智能速览"
    summary = None

    if meeting:
        if meeting.meeting_name:
            title = meeting.meeting_name
        if meeting.summary:
            summary = meeting.summary

    if not summary:
        summaries_dir = os.path.join(output_dir, "summaries")
        if os.path.isdir(summaries_dir):
            for name in os.listdir(summaries_dir):
                if file_id in name and name.endswith(".md"):
                    path = os.path.join(summaries_dir, name)
                    with open(path, "r", encoding="utf-8") as f:
                        summary = f.read()
                    break

    if not summary:
        raise HTTPException(status_code=404, detail="该会议暂无 AI 总结")

    return summary, title


def _load_visual_for_meeting(file_id: str) -> tuple[dict, str]:
    meeting = get_meeting_by_file_id(file_id)
    title = "AI 智能速览"
    visual = None

    if meeting:
        if meeting.meeting_name:
            title = meeting.meeting_name
        if meeting.summary_visual:
            from llm.visual_schema import visual_dict_for_display
            visual = visual_dict_for_display(meeting.summary_visual)

    if visual is None:
        summaries_dir = os.path.join(output_dir, "summaries")
        if os.path.isdir(summaries_dir):
            for name in os.listdir(summaries_dir):
                if file_id in name and name.endswith('_visual.json'):
                    path = os.path.join(summaries_dir, name)
                    from llm.visual_schema import visual_dict_for_display
                    with open(path, 'r', encoding='utf-8') as f:
                        visual = visual_dict_for_display(f.read())
                    break

    if not visual:
        raise HTTPException(status_code=404, detail='该会议暂无图文速览')

    return visual, title


def _html_attachment_response(html: str, title: str, file_id: str | None = None) -> Response:
    filename = build_visual_export_filename(title, file_id, ext='html')
    encoded = quote(filename)
    return Response(
        content=html.encode('utf-8'),
        media_type='text/html; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{encoded}"; filename*=UTF-8\'\'{encoded}',
        },
    )


def _json_attachment_response(visual: dict, title: str, file_id: str | None = None) -> Response:
    filename = build_visual_export_filename(title, file_id, ext='json')
    encoded = quote(filename)
    return Response(
        content=visual_summary_to_json_bytes(visual),
        media_type='application/json; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{encoded}"; filename*=UTF-8\'\'{encoded}',
        },
    )


def _meeting_owner_id(file_id: str) -> int | None:
    meeting = get_meeting_by_file_id(file_id)
    return meeting.user_id if meeting else None


@router.get("/meetings/{file_id}/export/summary")
async def export_meeting_summary_docx(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出指定会议的 AI 总结为 Word 文档"""
    _require_download_permission(current_user)
    exists, allowed = check_meeting_access(file_id, current_user)
    if not exists:
        raise HTTPException(status_code=404, detail="会议不存在")
    if not allowed:
        raise HTTPException(status_code=403, detail="无权导出该会议")

    summary, title = _load_summary_for_meeting(file_id)
    log_meeting_download(
        db,
        user_id=current_user.id,
        meeting_name=title,
        export_type='summary_docx',
        file_id=file_id,
        meeting_user_id=_meeting_owner_id(file_id),
    )
    logger.info(f"导出 AI 总结: file_id={file_id}, user={current_user.username}")
    return _docx_response(summary, title, file_id)


@router.post("/export/summary")
async def export_summary_content_docx(
    body: SummaryExportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """根据总结正文直接导出 Word（用于刚生成尚未跳转历史的场景）"""
    _require_download_permission(current_user)
    title = body.title.strip()
    log_meeting_download(
        db,
        user_id=current_user.id,
        meeting_name=title,
        export_type='summary_docx',
    )
    logger.info(f"导出 AI 总结内容: user={current_user.username}, title={title}")
    return _docx_response(body.content.strip(), title)


@router.get("/meetings/{file_id}/export/visual")
async def export_meeting_visual(
    file_id: str,
    format: str = 'html',
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出指定会议的图文速览（html 或 json）"""
    _require_download_permission(current_user)
    exists, allowed = check_meeting_access(file_id, current_user)
    if not exists:
        raise HTTPException(status_code=404, detail='会议不存在')
    if not allowed:
        raise HTTPException(status_code=403, detail='无权导出该会议')

    visual, title = _load_visual_for_meeting(file_id)
    fmt = (format or 'html').lower()
    export_type = 'visual_json' if fmt == 'json' else 'visual_html'
    log_meeting_download(
        db,
        user_id=current_user.id,
        meeting_name=title,
        export_type=export_type,
        file_id=file_id,
        meeting_user_id=_meeting_owner_id(file_id),
    )
    logger.info(f"导出图文速览: file_id={file_id}, format={fmt}, user={current_user.username}")

    if fmt == 'json':
        return _json_attachment_response(visual, title, file_id)
    return _html_attachment_response(visual_summary_to_html(visual, title), title, file_id)


@router.post("/export/visual")
async def export_visual_content(
    body: VisualExportRequest,
    format: str = 'html',
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """根据图文 JSON 直接导出（用于刚生成尚未入库的场景）"""
    _require_download_permission(current_user)
    title = body.title.strip()
    fmt = (format or 'html').lower()
    export_type = 'visual_json' if fmt == 'json' else 'visual_html'
    log_meeting_download(
        db,
        user_id=current_user.id,
        meeting_name=title,
        export_type=export_type,
    )
    logger.info(f"导出图文速览内容: user={current_user.username}, title={title}, format={fmt}")

    if fmt == 'json':
        return _json_attachment_response(body.visual, title)
    return _html_attachment_response(visual_summary_to_html(body.visual, title), title)
