import os
import uuid
import time
import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    Depends,
    HTTPException,
)

from api.auth_utils import get_current_user
from db.models import User

from config.config import upload_dir, output_dir, max_upload_bytes
from asr.holder import get_asr_engine
from llm.client_holder import get_llm_client
from llm.summary_service import generate_dual_summaries, visual_dict_from_result
from utils.logger import get_logger
from utils.meeting_name import resolve_meeting_name, safe_filename_prefix
from utils.executors import _get_batch_sem, run_io
from db.session import save_meeting_to_db_async

router = APIRouter()
logger = get_logger("meeting_route")

# 创建目录结构
os.makedirs(upload_dir, exist_ok=True)
os.makedirs(os.path.join(output_dir, "transcripts"), exist_ok=True)
os.makedirs(os.path.join(output_dir, "summaries"), exist_ok=True)

# 批量上传后台任务状态（file_id -> job）
_upload_jobs: dict[str, dict] = {}
_upload_jobs_lock = asyncio.Lock()

# 分片上传会话（upload_id -> session）
_chunk_sessions: dict[str, dict] = {}
_chunk_sessions_lock = asyncio.Lock()
CHUNK_UPLOAD_DIR = os.path.join(upload_dir, "_chunks")
os.makedirs(CHUNK_UPLOAD_DIR, exist_ok=True)

_STAGE_LABELS = {
    "queued": "排队中…",
    "asr": "语音识别中…",
    "summary": "生成会议纪要中…",
    "saving": "保存结果中…",
}


def _set_job(file_id: str, **fields) -> None:
    job = _upload_jobs.setdefault(file_id, {})
    job.update(fields)


async def _get_job_for_user(file_id: str, user_id: int) -> dict | None:
    async with _upload_jobs_lock:
        job = _upload_jobs.get(file_id)
        if not job or job.get("user_id") != user_id:
            return None
        return dict(job)


@router.post("/meeting/upload")
async def upload_meeting_audio(
    file: UploadFile = File(...),
    meeting_name: str = Form(None),
    current_user: User = Depends(get_current_user),
):
    """接收音频文件并排队后台处理，立即返回 file_id 供前端轮询。"""
    start_time = time.time()
    request_id = str(uuid.uuid4())

    input_params = {
        "filename": file.filename,
        "content_type": file.content_type,
        "file_size": None,
        "meeting_name": meeting_name,
    }

    logger.info("收到音频文件上传请求", extra={"request_id": request_id, "input_params": input_params})

    meeting_name = (meeting_name or "").strip() or None

    file_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "wav"
    save_path = os.path.join(upload_dir, f"{file_id}.{ext}")

    total_size = 0
    chunk_size = 4 * 1024 * 1024
    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_upload_bytes:
                if os.path.exists(save_path):
                    await run_io(os.remove, save_path)
                logger.warning(
                    "音频文件超过大小上限",
                    extra={
                        "request_id": request_id,
                        "input_params": {
                            **input_params,
                            "file_size": total_size,
                            "max_upload_bytes": max_upload_bytes,
                        },
                    },
                )
                raise HTTPException(
                    status_code=413,
                    detail=f"文件过大（{total_size // (1024 * 1024)}MB），最大允许 {max_upload_bytes // (1024 * 1024)}MB",
                )
            await run_io(_append_bytes, save_path, chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(save_path):
            await run_io(os.remove, save_path)
        logger.error("音频文件保存失败", exc_info=True, extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}") from e

    input_params["file_size"] = total_size
    upload_duration_ms = (time.time() - start_time) * 1000
    logger.info(
        "音频文件已保存，开始后台处理",
        extra={
            "request_id": request_id,
            "output_params": {
                "save_path": save_path,
                "file_size": total_size,
                "file_id": file_id,
                "upload_duration_ms": round(upload_duration_ms, 2),
            },
        },
    )

    async with _upload_jobs_lock:
        _upload_jobs[file_id] = {
            "user_id": current_user.id,
            "status": "processing",
            "stage": "queued",
            "meeting_name": meeting_name,
            "filename": file.filename,
            "created_at": time.time(),
        }

    asyncio.create_task(
        _run_upload_job(
            file_id=file_id,
            save_path=save_path,
            filename=file.filename or f"{file_id}.{ext}",
            meeting_name=meeting_name,
            request_id=request_id,
            input_params=input_params,
            start_time=start_time,
            user_id=current_user.id,
            timestamp=timestamp,
        )
    )

    return {
        "success": True,
        "accepted": True,
        "file_id": file_id,
        "status": "processing",
        "stage": "queued",
        "message": "文件已上传，正在后台处理，请稍候…",
    }


@router.post("/meeting/upload/init")
async def init_chunked_upload(
    meeting_name: str = Form(None),
    filename: str = Form(...),
    total_size: int = Form(...),
    total_chunks: int = Form(...),
    current_user: User = Depends(get_current_user),
):
    """分片上传初始化（大文件经 cpolar 等代理时避免单次请求超时）。"""
    meeting_name = (meeting_name or "").strip() or None
    if total_size <= 0 or total_chunks <= 0:
        raise HTTPException(status_code=400, detail="无效的文件大小或分片数")
    if total_size > max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大允许 {max_upload_bytes // (1024 * 1024)}MB",
        )

    upload_id = str(uuid.uuid4())
    chunk_dir = os.path.join(CHUNK_UPLOAD_DIR, upload_id)
    await run_io(os.makedirs, chunk_dir, exist_ok=True)

    async with _chunk_sessions_lock:
        _chunk_sessions[upload_id] = {
            "user_id": current_user.id,
            "meeting_name": meeting_name,
            "filename": filename or "audio.m4a",
            "total_size": total_size,
            "total_chunks": total_chunks,
            "received": set(),
            "chunk_dir": chunk_dir,
            "created_at": time.time(),
        }

    return {"success": True, "upload_id": upload_id}


@router.post("/meeting/upload/chunk")
async def upload_meeting_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """接收单个分片。"""
    async with _chunk_sessions_lock:
        session = _chunk_sessions.get(upload_id)
        if not session or session.get("user_id") != current_user.id:
            raise HTTPException(status_code=404, detail="上传会话不存在或已过期")
        if chunk_index < 0 or chunk_index >= session["total_chunks"]:
            raise HTTPException(status_code=400, detail="分片序号无效")
        chunk_dir = session["chunk_dir"]

    chunk_path = os.path.join(chunk_dir, f"{chunk_index:06d}.part")
    data = await file.read()
    await run_io(Path(chunk_path).write_bytes, data)

    async with _chunk_sessions_lock:
        session = _chunk_sessions.get(upload_id)
        received_count = 0
        if session:
            session["received"].add(chunk_index)
            received_count = len(session["received"])

    return {
        "success": True,
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "received_count": received_count,
    }


@router.post("/meeting/upload/complete")
async def complete_chunked_upload(
    upload_id: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """合并分片并启动后台处理。"""
    async with _chunk_sessions_lock:
        session = _chunk_sessions.pop(upload_id, None)
        if not session or session.get("user_id") != current_user.id:
            raise HTTPException(status_code=404, detail="上传会话不存在或已过期")
        if len(session["received"]) != session["total_chunks"]:
            raise HTTPException(
                status_code=400,
                detail=f"分片不完整（{len(session['received'])}/{session['total_chunks']}）",
            )

    meeting_name = session["meeting_name"]
    filename = session["filename"]
    file_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = filename.split(".")[-1] if "." in filename else "wav"
    save_path = os.path.join(upload_dir, f"{file_id}.{ext}")
    request_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        await run_io(_merge_chunk_files, session["chunk_dir"], session["total_chunks"], save_path)
    except Exception as e:
        logger.error("分片合并失败", exc_info=True, extra={"upload_id": upload_id})
        raise HTTPException(status_code=500, detail=f"文件合并失败: {e}") from e
    finally:
        await run_io(_cleanup_chunk_dir, session["chunk_dir"])

    total_size = session["total_size"]
    input_params = {
        "filename": filename,
        "file_size": total_size,
        "meeting_name": meeting_name,
        "chunked": True,
        "total_chunks": session["total_chunks"],
    }
    logger.info(
        "分片上传已合并，开始后台处理",
        extra={
            "request_id": request_id,
            "output_params": {"file_id": file_id, "file_size": total_size},
        },
    )

    async with _upload_jobs_lock:
        _upload_jobs[file_id] = {
            "user_id": current_user.id,
            "status": "processing",
            "stage": "queued",
            "meeting_name": meeting_name,
            "filename": filename,
            "created_at": time.time(),
        }

    asyncio.create_task(
        _run_upload_job(
            file_id=file_id,
            save_path=save_path,
            filename=filename,
            meeting_name=meeting_name,
            request_id=request_id,
            input_params=input_params,
            start_time=start_time,
            user_id=current_user.id,
            timestamp=timestamp,
        )
    )

    return {
        "success": True,
        "accepted": True,
        "file_id": file_id,
        "status": "processing",
        "stage": "queued",
        "message": "文件已上传，正在后台处理，请稍候…",
    }


@router.get("/meeting/upload/{file_id}/status")
async def get_upload_job_status(
    file_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询批量上传后台任务进度与结果。"""
    job = await _get_job_for_user(file_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或无权查看")

    status = job.get("status", "processing")
    if status == "completed":
        result = job.get("result") or {}
        return {
            "success": True,
            "status": "completed",
            "stage": "done",
            **result,
        }
    if status == "failed":
        return {
            "success": False,
            "status": "failed",
            "error": job.get("error") or "处理失败，请稍后重试",
        }

    stage = job.get("stage", "processing")
    return {
        "success": True,
        "status": "processing",
        "stage": stage,
        "message": _STAGE_LABELS.get(stage, "处理中…"),
    }


def _append_bytes(path: str, data: bytes) -> None:
    with open(path, "ab") as f:
        f.write(data)


def _merge_chunk_files(chunk_dir: str, total_chunks: int, dest_path: str) -> None:
    with open(dest_path, "wb") as out:
        for i in range(total_chunks):
            part_path = os.path.join(chunk_dir, f"{i:06d}.part")
            with open(part_path, "rb") as part:
                while True:
                    block = part.read(4 * 1024 * 1024)
                    if not block:
                        break
                    out.write(block)


def _cleanup_chunk_dir(chunk_dir: str) -> None:
    if not os.path.isdir(chunk_dir):
        return
    for name in os.listdir(chunk_dir):
        try:
            os.remove(os.path.join(chunk_dir, name))
        except OSError:
            pass
    try:
        os.rmdir(chunk_dir)
    except OSError:
        pass


async def _run_upload_job(
    *,
    file_id: str,
    save_path: str,
    filename: str,
    meeting_name: str | None,
    request_id: str,
    input_params: dict,
    start_time: float,
    user_id: int,
    timestamp: str,
) -> None:
    async with _get_batch_sem():
        try:
            _set_job(file_id, stage="asr")
            result = await _process_meeting_upload(
                save_path=save_path,
                filename=filename,
                meeting_name=meeting_name,
                file_id=file_id,
                request_id=request_id,
                input_params=input_params,
                start_time=start_time,
                user_id=user_id,
                timestamp=timestamp,
                on_stage=lambda stage: _set_job(file_id, stage=stage),
            )
            _set_job(file_id, status="completed", stage="done", result=result)
        except Exception as e:
            logger.error(
                "批量上传后台任务失败",
                exc_info=True,
                extra={"request_id": request_id, "file_id": file_id},
            )
            _set_job(
                file_id,
                status="failed",
                error="处理失败，请稍后重试",
                detail=str(e),
            )


async def _process_meeting_upload(
    *,
    save_path: str,
    filename: str,
    meeting_name: str | None,
    file_id: str,
    request_id: str,
    input_params: dict,
    start_time: float,
    user_id: int,
    timestamp: str,
    on_stage=None,
):
    def _stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    try:
        name_prefix = safe_filename_prefix(meeting_name)

        _stage("asr")
        logger.info("开始语音识别...", extra={"request_id": request_id})
        asr_start = time.time()
        transcript = await get_asr_engine().transcribe_async(save_path)
        asr_duration = (time.time() - asr_start) * 1000
        logger.info(
            "语音识别完成",
            extra={
                "request_id": request_id,
                "output_params": {
                    "transcript_length": len(transcript),
                    "asr_duration_ms": round(asr_duration, 2),
                },
            },
        )

        transcript_path = os.path.join(
            output_dir, "transcripts", f"{name_prefix}{file_id}_{timestamp}.txt"
        )
        await run_io(Path(transcript_path).write_text, transcript, encoding="utf-8")
        logger.info(
            "转写文本已保存",
            extra={"request_id": request_id, "output_params": {"transcript_file": transcript_path}},
        )

        _stage("summary")
        logger.info("开始生成会议纪要（双轨）...", extra={"request_id": request_id})
        llm_start = time.time()
        dual = await generate_dual_summaries(
            get_llm_client(),
            transcript,
            meeting_name,
            datetime.fromtimestamp(start_time),
        )
        llm_duration = (time.time() - llm_start) * 1000

        if dual.markdown_error or not dual.markdown:
            raise RuntimeError(dual.markdown_error or "Markdown 速览生成失败")

        summary = dual.markdown
        summary_visual_dict = visual_dict_from_result(dual)
        visual_title = (
            summary_visual_dict.get("title")
            if isinstance(summary_visual_dict, dict)
            else None
        )
        resolved_name = resolve_meeting_name(
            meeting_name,
            summary=summary,
            visual_title=visual_title,
            at=datetime.fromtimestamp(start_time),
        )
        logger.info(
            "会议纪要生成完成",
            extra={
                "request_id": request_id,
                "output_params": {
                    "summary_length": len(summary),
                    "visual_status": dual.visual_status,
                    "llm_duration_ms": round(llm_duration, 2),
                },
            },
        )

        _stage("saving")
        summary_path = os.path.join(
            output_dir, "summaries", f"{name_prefix}{file_id}_{timestamp}.md"
        )
        await run_io(Path(summary_path).write_text, summary, encoding="utf-8")
        visual_path = os.path.join(
            output_dir, "summaries", f"{name_prefix}{file_id}_{timestamp}_visual.json"
        )
        if dual.visual_json:
            await run_io(Path(visual_path).write_text, dual.visual_json, encoding="utf-8")
        logger.info(
            "会议纪要已保存",
            extra={
                "request_id": request_id,
                "output_params": {"summary_file": summary_path, "visual_file": visual_path},
            },
        )

        total_duration_ms = (time.time() - start_time) * 1000

        try:
            meeting_data = {
                "file_id": file_id,
                "user_id": user_id,
                "meeting_name": resolved_name,
                "original_filename": filename,
                "meeting_type": "batch",
                "audio_file_path": save_path,
                "transcript_file_path": transcript_path,
                "summary_file_path": summary_path,
                "transcript": transcript,
                "summary": summary,
                "summary_visual": dual.visual_json,
                "summary_visual_status": dual.visual_status,
                "transcript_length": len(transcript),
                "summary_length": len(summary),
                "asr_duration_ms": round(asr_duration, 2),
                "llm_duration_ms": round(llm_duration, 2),
                "total_duration_ms": round(total_duration_ms, 2),
                "status": "completed",
            }
            await save_meeting_to_db_async(meeting_data)
            logger.info("会议数据已保存到数据库", extra={"request_id": request_id})
        except Exception as db_error:
            logger.error(
                f"保存会议数据到数据库失败: {str(db_error)}",
                exc_info=True,
                extra={"request_id": request_id},
            )

        output_params = {
            "success": True,
            "file_id": file_id,
            "transcript_length": len(transcript),
            "summary_length": len(summary),
            "transcript_file": transcript_path,
            "summary_file": summary_path,
            "total_duration_ms": round(total_duration_ms, 2),
            "asr_duration_ms": round(asr_duration, 2),
            "llm_duration_ms": round(llm_duration, 2),
        }

        logger.info(
            "会议处理完成",
            extra={
                "request_id": request_id,
                "input_params": input_params,
                "output_params": output_params,
                "duration_ms": total_duration_ms,
            },
        )

        return {
            "filename": filename,
            "file_id": file_id,
            "meeting_name": resolved_name,
            "transcript": transcript,
            "summary": summary,
            "summary_visual": summary_visual_dict,
            "summary_visual_status": dual.visual_status,
            "transcript_file": transcript_path,
            "summary_file": summary_path,
        }

    except Exception as e:
        total_duration_ms = (time.time() - start_time) * 1000
        error_params = {
            "error": str(e),
            "error_type": type(e).__name__,
            "duration_ms": round(total_duration_ms, 2),
        }
        logger.error(
            "会议处理失败",
            exc_info=True,
            extra={
                "request_id": request_id,
                "input_params": input_params,
                "output_params": error_params,
                "duration_ms": total_duration_ms,
            },
        )
        raise
