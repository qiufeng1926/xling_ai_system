#!/usr/bin/env python
"""诊断听悟实时连接：打印 CreateTask 与 StartTranscription 后的首条服务端消息。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets

from asr.tingwu_realtime import _create_realtime_task_sync, _speech_message
from config.config import tingwu_audio_format


async def main():
    info = _create_realtime_task_sync()
    print("CreateTask OK:", json.dumps(info, ensure_ascii=False, indent=2))

    url = info["MeetingJoinUrl"]
    async with websockets.connect(url, ping_interval=20) as ws:
        start_msg = _speech_message(
            "StartTranscription",
            {"format": tingwu_audio_format},
        )
        print("Send:", start_msg)
        await ws.send(start_msg)

        for i in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except asyncio.TimeoutError:
                print(f"[{i}] timeout waiting for message")
                break
            if isinstance(msg, bytes):
                print(f"[{i}] binary {len(msg)} bytes")
            else:
                print(f"[{i}] {msg}")


if __name__ == "__main__":
    asyncio.run(main())
