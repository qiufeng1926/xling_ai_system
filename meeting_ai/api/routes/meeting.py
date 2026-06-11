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
from llm.client_holder import get_glm_client
from llm.summary_service import generate_dual_summaries, visual_dict_from_result
from utils.logger import get_logger
from utils.executors import _get_batch_sem, run_io
from db.session import save_meeting_to_db_async

router = APIRouter()
logger = get_logger("meeting_route")

# 创建目录结构
os.makedirs(upload_dir, exist_ok=True)
os.makedirs(os.path.join(output_dir, "transcripts"), exist_ok=True)
os.makedirs(os.path.join(output_dir, "summaries"), exist_ok=True)


@router.post("/meeting/upload")
async def upload_meeting_audio(
    file: UploadFile = File(...),
    meeting_name: str = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    异步批量上传音频文件并处理
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    # 记录请求参数
    input_params = {
        "filename": file.filename,
        "content_type": file.content_type,
        "file_size": None,  # 稍后填充
        "meeting_name": meeting_name,
    }
    
    logger.info(f"收到音频文件上传请求", extra={'request_id': request_id, 'input_params': input_params})

    content = await file.read()
    if len(content) > max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大允许 {max_upload_bytes // (1024 * 1024)}MB",
        )

    if not meeting_name or not meeting_name.strip():
        raise HTTPException(status_code=400, detail='会议名称为必填项')
    meeting_name = meeting_name.strip()

    async with _get_batch_sem():
        return await _process_meeting_upload(
            content=content,
            filename=file.filename,
            meeting_name=meeting_name,
            request_id=request_id,
            input_params=input_params,
            start_time=start_time,
            current_user=current_user,
        )


async def _process_meeting_upload(
    content: bytes,
    filename: str,
    meeting_name: str | None,
    request_id: str,
    input_params: dict,
    start_time: float,
    current_user: User,
):
    try:
        input_params["file_size"] = len(content)
        # 处理会议名称
        if meeting_name:
            safe_name = "".join(c for c in meeting_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name.replace(' ', '_')
            name_prefix = f"{safe_name}_"
            logger.info(f"设置会议名称", extra={'request_id': request_id, 'input_params': {'meeting_name': meeting_name, 'safe_name': safe_name}})
        else:
            name_prefix = ""

        # 生成文件名
        file_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = filename.split(".")[-1] if "." in filename else "wav"

        # 异步保存上传的音频文件
        save_path = os.path.join(upload_dir, f"{file_id}.{ext}")
        await run_io(Path(save_path).write_bytes, content)
        logger.info(f"音频文件已保存", extra={'request_id': request_id, 'output_params': {'save_path': save_path, 'file_size': len(content)}})

        # 异步 ASR 语音转文字
        logger.info(f"开始语音识别...", extra={'request_id': request_id})
        asr_start = time.time()
        transcript = await get_asr_engine().transcribe_async(save_path)
        asr_duration = (time.time() - asr_start) * 1000
        logger.info(f"语音识别完成", extra={
            'request_id': request_id, 
            'output_params': {
                'transcript_length': len(transcript),
                'asr_duration_ms': round(asr_duration, 2)
            }
        })

        # 异步保存转写文本
        transcript_path = os.path.join(output_dir, "transcripts", f"{name_prefix}{file_id}_{timestamp}.txt")
        await run_io(Path(transcript_path).write_text, transcript, encoding='utf-8')
        logger.info(f"转写文本已保存", extra={'request_id': request_id, 'output_params': {'transcript_file': transcript_path}})

        # 并行生成 Markdown 速览 + 图文 JSON
        logger.info(f"开始生成会议纪要（双轨）...", extra={'request_id': request_id})
        llm_start = time.time()
        dual = await generate_dual_summaries(get_glm_client(), transcript, meeting_name)
        llm_duration = (time.time() - llm_start) * 1000

        if dual.markdown_error or not dual.markdown:
            raise RuntimeError(dual.markdown_error or 'Markdown 速览生成失败')

        summary = dual.markdown
        summary_visual_dict = visual_dict_from_result(dual)
        logger.info(f"会议纪要生成完成", extra={
            'request_id': request_id,
            'output_params': {
                'summary_length': len(summary),
                'visual_status': dual.visual_status,
                'llm_duration_ms': round(llm_duration, 2),
            },
        })

        summary_path = os.path.join(output_dir, "summaries", f"{name_prefix}{file_id}_{timestamp}.md")
        await run_io(Path(summary_path).write_text, summary, encoding='utf-8')
        visual_path = os.path.join(output_dir, "summaries", f"{name_prefix}{file_id}_{timestamp}_visual.json")
        if dual.visual_json:
            await run_io(Path(visual_path).write_text, dual.visual_json, encoding='utf-8')
        logger.info(f"会议纪要已保存", extra={
            'request_id': request_id,
            'output_params': {'summary_file': summary_path, 'visual_file': visual_path},
        })

        # 计算总耗时
        total_duration_ms = (time.time() - start_time) * 1000

        # 保存到数据库
        try:
            meeting_data = {
                'file_id': file_id,
                'user_id': current_user.id,
                'meeting_name': meeting_name,
                'original_filename': filename,
                'meeting_type': 'batch',
                'audio_file_path': save_path,
                'transcript_file_path': transcript_path,
                'summary_file_path': summary_path,
                'transcript': transcript,
                'summary': summary,
                'summary_visual': dual.visual_json,
                'summary_visual_status': dual.visual_status,
                'transcript_length': len(transcript),
                'summary_length': len(summary),
                'asr_duration_ms': round(asr_duration, 2),
                'llm_duration_ms': round(llm_duration, 2),
                'total_duration_ms': round(total_duration_ms, 2),
                'status': 'completed'
            }
            await save_meeting_to_db_async(meeting_data)
            logger.info(f"会议数据已保存到数据库", extra={'request_id': request_id})
        except Exception as db_error:
            logger.error(f"保存会议数据到数据库失败: {str(db_error)}", exc_info=True, extra={'request_id': request_id})
        
        # 准备输出参数
        output_params = {
            "success": True,
            "file_id": file_id,
            "transcript_length": len(transcript),
            "summary_length": len(summary),
            "transcript_file": transcript_path,
            "summary_file": summary_path,
            "total_duration_ms": round(total_duration_ms, 2),
            "asr_duration_ms": round(asr_duration, 2),
            "llm_duration_ms": round(llm_duration, 2)
        }
        
        logger.info(f"会议处理完成", extra={'request_id': request_id, 'input_params': input_params, 'output_params': output_params, 'duration_ms': total_duration_ms})
        
        return {
            "success": True,
            "filename": filename,
            "file_id": file_id,
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
            "duration_ms": round(total_duration_ms, 2)
        }
        logger.error(f"会议处理失败", exc_info=True, extra={'request_id': request_id, 'input_params': input_params, 'output_params': error_params, 'duration_ms': total_duration_ms})
        return {
            "success": False,
            "error": "处理失败，请稍后重试",
        }


