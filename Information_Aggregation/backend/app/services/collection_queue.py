"""采集任务队列：同一时间仅运行一个 Playwright 子进程"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_task_queue: queue.Queue[int] = queue.Queue()
_worker_lock = threading.Lock()
_worker_started = False
_running_task_id: int | None = None


def enqueue_task(task_id: int) -> None:
    _ensure_worker()
    _task_queue.put(task_id)
    logger.info("Task %s enqueued (queue size=%s)", task_id, _task_queue.qsize())


def queue_size() -> int:
    return _task_queue.qsize()


def running_task_id() -> int | None:
    return _running_task_id


def _ensure_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker_loop, name="collection-queue", daemon=True)
        thread.start()
        _worker_started = True
        logger.info("Collection queue worker started")


def _worker_loop() -> None:
    global _running_task_id
    from app.services.collection_service import CollectionService

    runner: Callable[[int], None] = CollectionService._run_worker_subprocess
    while True:
        task_id = _task_queue.get()
        _running_task_id = task_id
        try:
            runner(task_id)
        except Exception:
            logger.exception("Collection queue failed for task %s", task_id)
        finally:
            _running_task_id = None
            _task_queue.task_done()
