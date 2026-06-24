"""进程内用户通知推送（SSE 订阅）。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class NotificationHub:
    def __init__(self) -> None:
        self._queues: dict[int, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, user_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._queues[user_id].append(queue)
        return queue

    async def unsubscribe(self, user_id: int, queue: asyncio.Queue) -> None:
        async with self._lock:
            queues = self._queues.get(user_id, [])
            if queue in queues:
                queues.remove(queue)
            if not queues:
                self._queues.pop(user_id, None)

    def publish(self, user_id: int, event: dict[str, Any]) -> None:
        for queue in self._queues.get(user_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def publish_many(self, user_ids: list[int], event: dict[str, Any]) -> None:
        for user_id in set(user_ids):
            self.publish(user_id, event)


notification_hub = NotificationHub()
