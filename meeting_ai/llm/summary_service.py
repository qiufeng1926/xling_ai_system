"""
双轨总结：Markdown 速览 + 图文 JSON（并行生成，均可重试）
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime

from config.config import (
    markdown_summary_retry_max,
    visual_chunk_chars,
    visual_chunk_overlap,
    visual_json_repair,
    visual_summary_retry_max,
)
from llm.base_client import BaseLLMClient
from llm.visual_schema import (
    VisualSummary,
    merge_visual_parts,
    normalize_visual_summary,
    parse_visual_summary_with_repair,
    split_transcript_chunks,
    visual_summary_to_dict,
    visual_summary_to_json,
)
from utils.logger import get_logger

logger = get_logger("summary_service")

# 瞬时网络/SSL/连接类错误：值得退避重试
_TRANSIENT_ERROR_MARKERS = (
    "connection error",
    "connection reset",
    "connection aborted",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "ssl",
    "eof occurred",
    "broken pipe",
    "remote end closed",
    "server disconnected",
    "503",
    "502",
    "429",
    "rate limit",
)


def _is_transient_llm_error(exc: BaseException | str) -> bool:
    text = str(exc).lower()
    return any(m in text for m in _TRANSIENT_ERROR_MARKERS)


@dataclass
class DualSummaryResult:
    markdown: str | None
    markdown_error: str | None
    visual: VisualSummary | None
    visual_json: str | None
    visual_status: str  # completed | failed | skipped
    visual_error: str | None


async def _parse_raw_visual(client: BaseLLMClient, raw: str) -> VisualSummary:
    repair_fn = client.repair_json_async if visual_json_repair else None
    return await parse_visual_summary_with_repair(raw, repair_fn=repair_fn)


async def _generate_markdown_with_retry(
    client: BaseLLMClient,
    transcript: str,
    meeting_name: str | None,
    meeting_started_at: datetime | str | None,
    max_retries: int,
) -> str:
    """Markdown 速览：对连接类瞬时错误做指数退避重试。"""
    last_error: BaseException | None = None
    attempts = max(1, max_retries + 1)
    for attempt in range(attempts):
        try:
            result = await client.summary_meeting_async(
                transcript, meeting_name, meeting_started_at
            )
            if not (result or "").strip():
                raise RuntimeError("Markdown 速览返回为空")
            return result
        except Exception as e:
            last_error = e
            transient = _is_transient_llm_error(e)
            logger.warning(
                f"Markdown 速览生成失败 (attempt {attempt + 1}/{attempts}): {e}",
                extra={"output_params": {"transient": transient}},
            )
            if attempt >= attempts - 1:
                break
            if not transient:
                break
            await asyncio.sleep(min(2 ** attempt, 8))
    assert last_error is not None
    raise last_error


async def _generate_visual_once(
    client: BaseLLMClient,
    transcript: str,
    meeting_name: str | None,
    part_index: int | None = None,
    total_parts: int | None = None,
) -> VisualSummary:
    raw = await client.summary_visual_async(
        transcript,
        meeting_name,
        part_index=part_index,
        total_parts=total_parts,
    )
    return await _parse_raw_visual(client, raw)


async def _generate_visual_chunked(
    client: BaseLLMClient,
    transcript: str,
    meeting_name: str | None,
) -> VisualSummary:
    chunks = split_transcript_chunks(
        transcript,
        max_chars=visual_chunk_chars,
        overlap=visual_chunk_overlap,
    )
    if not chunks:
        raise ValueError('转写为空')
    if len(chunks) == 1:
        return await _generate_visual_once(client, chunks[0], meeting_name)

    logger.info(f"图文速览分 {len(chunks)} 段生成")
    parts: list[VisualSummary] = []
    for i, chunk in enumerate(chunks):
        part = await _generate_visual_once(
            client,
            chunk,
            meeting_name,
            part_index=i + 1,
            total_parts=len(chunks),
        )
        parts.append(part)

    merged = merge_visual_parts(parts)
    return normalize_visual_summary(merged)


async def _generate_visual_with_retry(
    client: BaseLLMClient,
    transcript: str,
    meeting_name: str | None,
    max_retries: int,
) -> tuple[VisualSummary | None, str | None, str | None]:
    last_error = None
    use_chunks = len(transcript) > visual_chunk_chars

    for attempt in range(max_retries + 1):
        try:
            if use_chunks:
                visual = await _generate_visual_chunked(client, transcript, meeting_name)
            else:
                visual = await _generate_visual_once(client, transcript, meeting_name)
                visual = normalize_visual_summary(visual)
            return visual, visual_summary_to_json(visual), None
        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"图文速览生成失败 (attempt {attempt + 1}/{max_retries + 1}): {last_error}"
            )
            if attempt < max_retries:
                await asyncio.sleep(1)
    return None, None, last_error


async def generate_dual_summaries(
    client: BaseLLMClient,
    transcript: str,
    meeting_name: str | None = None,
    meeting_started_at: datetime | str | None = None,
) -> DualSummaryResult:
    """并行生成 Markdown 与图文 JSON；Markdown 失败则整体失败，图文失败可重试后标 failed"""
    from utils.executors import get_llm_summary_semaphore

    async with get_llm_summary_semaphore():
        return await _generate_dual_summaries_inner(
            client, transcript, meeting_name, meeting_started_at
        )


async def _generate_dual_summaries_inner(
    client: BaseLLMClient,
    transcript: str,
    meeting_name: str | None = None,
    meeting_started_at: datetime | str | None = None,
) -> DualSummaryResult:
    markdown_task = asyncio.create_task(
        _generate_markdown_with_retry(
            client,
            transcript,
            meeting_name,
            meeting_started_at,
            markdown_summary_retry_max,
        )
    )
    visual_task = asyncio.create_task(
        _generate_visual_with_retry(client, transcript, meeting_name, visual_summary_retry_max)
    )

    markdown_result, visual_result = await asyncio.gather(
        markdown_task, visual_task, return_exceptions=True
    )

    markdown = None
    markdown_error = None
    if isinstance(markdown_result, Exception):
        markdown_error = str(markdown_result)
        logger.error(f"Markdown 速览生成失败: {markdown_error}")
    else:
        markdown = markdown_result

    visual = None
    visual_json = None
    visual_status = 'failed'
    visual_error = None

    if isinstance(visual_result, Exception):
        visual_error = str(visual_result)
    else:
        visual, visual_json, visual_error = visual_result
        visual_status = 'completed' if visual else 'failed'

    if not transcript or not transcript.strip():
        visual_status = 'skipped'
        visual_error = visual_error or '转写为空'

    return DualSummaryResult(
        markdown=markdown,
        markdown_error=markdown_error,
        visual=visual,
        visual_json=visual_json,
        visual_status=visual_status,
        visual_error=visual_error,
    )


def dual_result_to_db_fields(result: DualSummaryResult) -> dict:
    """写入 meetings 表的字段"""
    return {
        'summary': result.markdown,
        'summary_visual': result.visual_json,
        'summary_visual_status': result.visual_status,
    }


def visual_dict_from_result(result: DualSummaryResult) -> dict | None:
    from llm.visual_schema import visual_dict_for_display

    if result.visual:
        return visual_summary_to_dict(result.visual)
    if result.visual_json:
        return visual_dict_for_display(result.visual_json)
    return None
