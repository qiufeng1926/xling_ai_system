from __future__ import annotations

import json
from typing import Any, AsyncIterator


def sse(event: str, data: Any) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def iter_sse(events: AsyncIterator[tuple[str, Any]]) -> AsyncIterator[str]:
    async for name, data in events:
        yield sse(name, data)
