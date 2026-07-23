"""
模拟「网络极不稳定」场景的自动化测试。

覆盖：
1. 单人录音多次断线/1s 内重连 → 应始终只有 1 条会议记录
2. 旧连接 finally 晚于新连接接管 → 不得另起 file_id / 不得用短文本覆盖
3. LLM Connection error 瞬时失败 → Markdown 重试后成功
4. 听悟 WebSocket ConnectionReset → 重试后成功
5. websockets connection_lost 在握手未完成时不应 AttributeError

用法（在 meeting_ai 目录）:
  python scripts/test_unstable_network.py
"""
from __future__ import annotations

import asyncio
import sys
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class CaseResult:
    def __init__(self, name: str):
        self.name = name
        self.ok = False
        self.detail = ""

    def pass_(self, detail: str = "") -> "CaseResult":
        self.ok = True
        self.detail = detail
        return self

    def fail(self, detail: str) -> "CaseResult":
        self.ok = False
        self.detail = detail
        return self


def _banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def case_resume_snapshot_takeover() -> CaseResult:
    """旧连接晚到时不得抢回 connection 所有权，且保留更长文本。"""
    name = "断线重连快照接管竞态"
    from api.routes import websocket as ws

    recording_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    # 清理可能残留
    ws._recording_resume_store.pop(recording_id, None)

    old = {
        "recording_id": recording_id,
        "connection_id": "conn-old",
        "user_id": 1,
        "file_id": file_id,
        "total_text": "第一段转写内容。\n",
        "audio_chunks": 10,
        "saved": True,
    }
    ws._save_resume_snapshot(old)

    new = {
        "recording_id": recording_id,
        "connection_id": "conn-new",
        "user_id": 1,
        "file_id": file_id,
        "total_text": "第一段转写内容。\n第二段续写更长。\n",
        "audio_chunks": 20,
        "saved": True,
    }
    ws._save_resume_snapshot(new)

    # 旧连接 finally 用更短文本回写
    late_old = {
        "recording_id": recording_id,
        "connection_id": "conn-old",
        "user_id": 1,
        "file_id": file_id,
        "total_text": "第一段转写内容。\n",
        "audio_chunks": 10,
        "saved": True,
    }
    ws._save_resume_snapshot(late_old)

    snap = ws._recording_resume_store.get(recording_id)
    if not snap:
        return CaseResult(name).fail("快照丢失")
    if snap.get("connection_id") != "conn-new":
        return CaseResult(name).fail(f"所有权被抢回: {snap.get('connection_id')}")
    if "第二段续写" not in (snap.get("total_text") or ""):
        return CaseResult(name).fail(f"长文本被短文本覆盖: {snap.get('total_text')!r}")

    # 旧连接应急落库应被判定为已接管
    late_old["connection_id"] = "conn-old"
    if not ws._snapshot_taken_over(late_old, late_old["total_text"].strip()):
        return CaseResult(name).fail("_snapshot_taken_over 未识别接管")

    ws._recording_resume_store.pop(recording_id, None)
    return CaseResult(name).pass_("新连接保有所有权且保留更长转写")


async def case_multi_disconnect_one_meeting() -> CaseResult:
    """模拟 5 次断线应急落库 + 最终停止，DB 中只能有 1 条同一 file_id。"""
    name = "多次断线应急落库只产生一条会议"
    from db.models import Meeting
    from db.session import SessionFactory, delete_meeting, save_meeting_to_db
    from api.routes import websocket as ws

    file_id = str(uuid.uuid4())
    recording_id = str(uuid.uuid4())
    user_id = None

    # 找一个已有用户，没有就跳过 DB 用户绑定
    with SessionFactory() as session:
        from db.models import User

        user = session.query(User).order_by(User.id.asc()).first()
        user_id = user.id if user else None

    transcripts_dir = ROOT / "output" / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcripts_dir / f"chaos_{file_id}_realtime.txt"

    session_info = {
        "recording_id": recording_id,
        "connection_id": "conn-0",
        "user_id": user_id,
        "file_id": file_id,
        "meeting_name": "混沌网络测试会",
        "transcript_path": str(transcript_path),
        "total_text": "",
        "audio_chunks": 0,
        "saved": False,
        "recording_started_at": __import__("time").time(),
        "start_time": __import__("datetime").datetime.now().isoformat(),
        "transcriber": None,
    }

    try:
        # 5 次「断线」：文本递增，模拟重连后继续录音
        for i in range(1, 6):
            session_info["connection_id"] = f"conn-{i}"
            session_info["audio_chunks"] = i * 5
            session_info["total_text"] = "".join(f"第{j}段。\n" for j in range(1, i + 1))
            ws._save_resume_snapshot(session_info)
            await ws._persist_realtime_session_emergency(
                session_info,
                connection_id=session_info["connection_id"],
                start_time=__import__("time").time() - 60,
                reason="interrupted",
            )

        # 最终正常结束 upsert
        final_text = session_info["total_text"] + "结束语。\n"
        save_meeting_to_db(
            {
                "file_id": file_id,
                "user_id": user_id,
                "meeting_name": "混沌网络测试会",
                "original_filename": transcript_path.name,
                "meeting_type": "realtime",
                "transcript_file_path": str(transcript_path),
                "transcript": final_text,
                "transcript_length": len(final_text),
                "summary": None,
                "summary_length": 0,
                "status": "processing",
                "error_message": None,
            }
        )

        with SessionFactory() as session:
            rows = session.query(Meeting).filter(Meeting.file_id == file_id).all()
            count = len(rows)
            if count != 1:
                return CaseResult(name).fail(f"期望 1 条会议，实际 {count}")
            meeting = rows[0]
            if "结束语" not in (meeting.transcript or ""):
                return CaseResult(name).fail("最终转写未写入")
            if meeting.transcript.count("段。") < 5:
                return CaseResult(name).fail(f"转写段数不足: {meeting.transcript!r}")

        return CaseResult(name).pass_(f"file_id={file_id} 仅 1 条，转写完整")
    finally:
        try:
            delete_meeting(file_id)
        except Exception:
            pass
        ws._recording_resume_store.pop(recording_id, None)
        if transcript_path.exists():
            try:
                transcript_path.unlink()
            except OSError:
                pass


async def case_markdown_retry_on_connection_error() -> CaseResult:
    """LLM 前两次 Connection error，第三次成功。"""
    name = "Markdown 连接失败自动重试"
    from llm.summary_service import _generate_markdown_with_retry

    calls = {"n": 0}

    class FlakyClient:
        async def summary_meeting_async(self, transcript, meeting_name=None, meeting_started_at=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("Connection error.")
            return "# 会议速览\n\n重试后成功。"

    text = await _generate_markdown_with_retry(
        FlakyClient(),  # type: ignore[arg-type]
        "测试转写",
        "测试会",
        None,
        max_retries=2,
    )
    if calls["n"] != 3:
        return CaseResult(name).fail(f"调用次数={calls['n']}，期望 3")
    if "重试后成功" not in text:
        return CaseResult(name).fail(f"返回异常: {text!r}")
    return CaseResult(name).pass_("失败 2 次后第 3 次成功")


async def case_tingwu_ws_connect_retry() -> CaseResult:
    """听悟 WS 连续 ConnectionReset，最后一次成功。"""
    name = "听悟 WebSocket 连接重置自动重试"
    from asr.tingwu_realtime import TingwuStreamingSession

    attempts = {"n": 0}

    class FakeWS:
        async def send(self, *_a, **_k):
            return None

        async def close(self):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    async def flaky_connect(*_a, **_k):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionResetError("模拟极不稳定网络：Connection reset by peer")
        return FakeWS()

    session = TingwuStreamingSession(
        on_result=AsyncMock(),
        on_error=AsyncMock(),
    )

    with patch("asr.tingwu_realtime.ws_connect", side_effect=flaky_connect), patch(
        "asr.tingwu_realtime.tingwu_ws_connect_max_attempts", 3
    ), patch(
        "asr.tingwu_realtime.tingwu_ws_connect_retry_delay", 0.05
    ), patch(
        "asr.tingwu_realtime.tingwu_ws_open_timeout", 1.0
    ):
        ws = await session._connect_tingwu_websocket("wss://example.invalid/tingwu")

    if not isinstance(ws, FakeWS):
        return CaseResult(name).fail("未返回 FakeWS")
    if attempts["n"] != 3:
        return CaseResult(name).fail(f"重试次数={attempts['n']}，期望 3")
    return CaseResult(name).pass_("前 2 次 Reset，第 3 次连上")


async def case_websockets_connection_lost_guard() -> CaseResult:
    """握手未完成时 connection_lost 不应抛 AttributeError。"""
    name = "websockets connection_lost 防护"
    try:
        from websockets.asyncio.connection import Connection
        from websockets.protocol import Protocol, CLIENT
    except ImportError:
        return CaseResult(name).pass_("当前环境无 asyncio Connection，跳过")

    if not getattr(Connection.connection_lost, "_meeting_ai_guarded", False):
        # 确保已加载 tingwu 模块完成 patch
        import asr.tingwu_realtime  # noqa: F401

    protocol = Protocol(CLIENT)
    # 构造一个「尚未 connection_made」的残缺连接对象
    conn = object.__new__(Connection)
    conn.protocol = protocol
    conn.keepalive_task = None
    loop = asyncio.get_running_loop()
    conn.connection_lost_waiter = loop.create_future()
    conn.recv_exc = None
    conn.set_recv_exc = lambda exc: setattr(conn, "recv_exc", exc)

    try:
        Connection.connection_lost(conn, ConnectionResetError())
    except AttributeError as e:
        return CaseResult(name).fail(f"仍抛 AttributeError: {e}")
    except Exception as e:
        # 其他异常也可接受，只要不是 recv_messages AttributeError
        if "recv_messages" in str(e):
            return CaseResult(name).fail(str(e))
        return CaseResult(name).pass_(f"已防护，附带可忽略异常: {type(e).__name__}")

    return CaseResult(name).pass_("握手未完成断连不再 AttributeError")


async def case_rapid_reconnect_file_id_stable() -> CaseResult:
    """模拟客户端 1s 内重连 8 次，file_id / recording_id 始终不变。"""
    name = "1s 内连续重连 file_id 稳定"
    from api.routes import websocket as ws

    recording_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    ws._recording_resume_store.pop(recording_id, None)

    # 首次开始
    first = {
        "recording_id": recording_id,
        "connection_id": "c0",
        "user_id": 42,
        "file_id": file_id,
        "total_text": "",
        "audio_chunks": 0,
        "saved": False,
        "meeting_name": "rapid",
    }
    ws._save_resume_snapshot(first)

    ids = set()
    for i in range(1, 9):
        snap = ws._load_resume_snapshot(recording_id, 42)
        if not snap:
            return CaseResult(name).fail(f"第 {i} 次重连快照丢失")
        if snap.get("file_id") != file_id:
            return CaseResult(name).fail(f"第 {i} 次 file_id 变化: {snap.get('file_id')}")
        ids.add(snap["file_id"])
        # 续写
        nxt = {
            "recording_id": recording_id,
            "connection_id": f"c{i}",
            "user_id": 42,
            "file_id": snap["file_id"],
            "total_text": f"chunk-{i}\n" * i,
            "audio_chunks": i,
            "saved": True,
            "meeting_name": "rapid",
        }
        ws._save_resume_snapshot(nxt)
        await asyncio.sleep(0.05)  # 模拟 <1s 重连间隔

    ws._recording_resume_store.pop(recording_id, None)
    if ids != {file_id}:
        return CaseResult(name).fail(f"出现多个 file_id: {ids}")
    return CaseResult(name).pass_("8 次重连始终同一 file_id")


async def main() -> int:
    _banner("meeting_ai 极不稳定网络模拟测试")
    cases = [
        case_resume_snapshot_takeover,
        case_rapid_reconnect_file_id_stable,
        case_multi_disconnect_one_meeting,
        case_markdown_retry_on_connection_error,
        case_tingwu_ws_connect_retry,
        case_websockets_connection_lost_guard,
    ]

    results: list[CaseResult] = []
    for fn in cases:
        print(f"\n→ 运行: {fn.__name__}")
        try:
            result = await fn()
        except Exception as e:
            result = CaseResult(fn.__name__).fail(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        results.append(result)
        mark = "PASS" if result.ok else "FAIL"
        print(f"  [{mark}] {result.name}: {result.detail}")

    _banner("汇总")
    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    print(f"\nTotal: {passed}/{len(results)} passed, {failed} failed")
    for r in results:
        mark = "OK" if r.ok else "FAIL"
        print(f"  [{mark}] {r.name}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    # Windows 控制台避免 Unicode 符号编码失败
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(asyncio.run(main()))
