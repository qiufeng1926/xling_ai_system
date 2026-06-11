"""
全局线程池与并发限流，避免实时转写与批量处理互相阻塞事件循环。
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar('T')

# 文件 I/O、数据库、听悟同步 API 等
io_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='meeting-io')

# 批量 FunASR 推理（CPU 密集，单线程排队避免占满 CPU）
asr_batch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='meeting-asr-batch')

# 同一时刻仅允许一个批量上传流水线（ASR + 双轨总结）
batch_pipeline_semaphore: asyncio.Semaphore | None = None

# 限制同时进行的双轨 LLM 总结（实时结束 + 批量可并发但限流）
llm_summary_semaphore: asyncio.Semaphore | None = None


def _get_batch_sem() -> asyncio.Semaphore:
    global batch_pipeline_semaphore
    if batch_pipeline_semaphore is None:
        batch_pipeline_semaphore = asyncio.Semaphore(1)
    return batch_pipeline_semaphore


def get_llm_summary_semaphore() -> asyncio.Semaphore:
    global llm_summary_semaphore
    if llm_summary_semaphore is None:
        from config.config import llm_summary_max_concurrent
        llm_summary_semaphore = asyncio.Semaphore(llm_summary_max_concurrent)
    return llm_summary_semaphore


async def run_io(func: Callable[..., T], *args, **kwargs) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        io_executor,
        lambda: func(*args, **kwargs),
    )


async def run_asr_batch(func: Callable[..., T], *args, **kwargs) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        asr_batch_executor,
        lambda: func(*args, **kwargs),
    )
