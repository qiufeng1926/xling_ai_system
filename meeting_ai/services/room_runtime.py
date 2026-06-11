"""协作会议运行时：内存房间、连接、转写合并与广播"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from utils.logger import get_logger

logger = get_logger("room_runtime")

OnBroadcast = Callable[[str, dict], Awaitable[None]]


@dataclass
class LiveParticipant:
    connection_id: str
    username: str
    nickname: str
    role: str
    is_recording: bool = False


@dataclass
class TranscriptLine:
    ts: float
    username: str
    nickname: str
    text: str

    def formatted(self) -> str:
        label = self.nickname or self.username
        return f"[{label}] {self.text}"


@dataclass
class RuntimeRoom:
    room_code: str
    file_id: str
    host_username: str
    status: str = "waiting"
    participants: dict[str, LiveParticipant] = field(default_factory=dict)
    connection_map: dict[str, str] = field(default_factory=dict)  # conn_id -> username
    transcript_lines: list[TranscriptLine] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def merged_text(self) -> str:
        if not self.transcript_lines:
            return ""
        return "\n".join(line.formatted() for line in self.transcript_lines) + "\n"

    def online_participants(self) -> list[dict]:
        return [
            {
                "username": p.username,
                "nickname": p.nickname,
                "role": p.role,
                "is_recording": p.is_recording,
                "online": True,
            }
            for p in self.participants.values()
        ]

    def active_recorder_count(self) -> int:
        return sum(
            1
            for p in self.participants.values()
            if p.is_recording and p.role in ("host", "recorder")
        )


class MeetingRoomManager:
    def __init__(self) -> None:
        self._rooms: dict[str, RuntimeRoom] = {}
        self._conn_to_room: dict[str, str] = {}
        self._send_callbacks: dict[str, OnBroadcast] = {}

    def register_sender(self, connection_id: str, sender: OnBroadcast) -> None:
        self._send_callbacks[connection_id] = sender

    def unregister_connection(self, connection_id: str) -> str | None:
        self._send_callbacks.pop(connection_id, None)
        room_code = self._conn_to_room.pop(connection_id, None)
        if not room_code:
            return None
        room = self._rooms.get(room_code)
        if not room:
            return room_code
        username = room.connection_map.pop(connection_id, None)
        if username and username in room.participants:
            part = room.participants[username]
            part.is_recording = False
            if not any(cid for cid, u in room.connection_map.items() if u == username):
                del room.participants[username]
        if not room.connection_map and room.status in ("waiting", "live"):
            pass
        return room_code

    def get_room(self, room_code: str) -> RuntimeRoom | None:
        return self._rooms.get(room_code.upper())

    def ensure_room(
        self,
        room_code: str,
        file_id: str,
        host_username: str,
        status: str = "waiting",
    ) -> RuntimeRoom:
        code = room_code.upper()
        if code not in self._rooms:
            self._rooms[code] = RuntimeRoom(
                room_code=code,
                file_id=file_id,
                host_username=host_username,
                status=status,
            )
        else:
            room = self._rooms[code]
            room.status = status
        return self._rooms[code]

    async def join(
        self,
        room_code: str,
        connection_id: str,
        username: str,
        nickname: str,
        role: str,
        file_id: str,
        host_username: str,
        status: str,
    ) -> RuntimeRoom:
        room = self.ensure_room(room_code, file_id, host_username, status)
        async with room.lock:
            room.connection_map[connection_id] = username
            self._conn_to_room[connection_id] = room.room_code
            room.participants[username] = LiveParticipant(
                connection_id=connection_id,
                username=username,
                nickname=nickname,
                role=role,
            )
        return room

    async def set_recording(self, room_code: str, username: str, recording: bool) -> None:
        room = self.get_room(room_code)
        if not room:
            return
        async with room.lock:
            part = room.participants.get(username)
            if part:
                part.is_recording = recording

    async def append_transcript(
        self,
        room_code: str,
        username: str,
        nickname: str,
        text: str,
    ) -> str:
        room = self.get_room(room_code)
        if not room:
            return ""
        line = TranscriptLine(ts=time.time(), username=username, nickname=nickname, text=text.strip())
        async with room.lock:
            room.transcript_lines.append(line)
            return room.merged_text()

    async def broadcast(self, room_code: str, payload: dict, exclude: str | None = None) -> None:
        room = self.get_room(room_code)
        if not room:
            return
        for conn_id in list(room.connection_map.keys()):
            if exclude and conn_id == exclude:
                continue
            sender = self._send_callbacks.get(conn_id)
            if sender:
                try:
                    await sender(conn_id, payload)
                except Exception as exc:
                    logger.warning(f"广播失败: {exc}")

    async def room_state_payload(self, room_code: str) -> dict[str, Any]:
        room = self.get_room(room_code)
        if not room:
            return {}
        async with room.lock:
            return {
                "type": "room_state",
                "room_code": room.room_code,
                "file_id": room.file_id,
                "status": room.status,
                "participants": room.online_participants(),
                "merged_transcript": room.merged_text(),
                "active_recorders": room.active_recorder_count(),
            }

    def remove_room(self, room_code: str) -> None:
        code = room_code.upper()
        room = self._rooms.pop(code, None)
        if not room:
            return
        for conn_id in list(room.connection_map.keys()):
            self._conn_to_room.pop(conn_id, None)


room_manager = MeetingRoomManager()
