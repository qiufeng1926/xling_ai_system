"""
E2E：模拟长会议断连重连，并在每一步打印会议记录数量。

两种模式：
  1) 按时长（推荐长测）: --duration-minutes 30
  2) 按次数（短测）:     --cycles 5

流程对齐真实前端：
  record_start → 稳定录音一段时间 → 断连应急落库 → sleep(1s) →
  resume 重连 → … → 最终停止

断言：同一场录音始终只有 1 条 meetings 记录。

用法:
  cd meeting_ai
  python scripts/test_disconnect_reconnect_meeting_count.py --duration-minutes 30
  python scripts/test_disconnect_reconnect_meeting_count.py --cycles 5
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _count_meetings_by_file_id(file_id: str) -> int:
    from db.models import Meeting
    from db.session import SessionFactory

    with SessionFactory() as session:
        return session.query(Meeting).filter(Meeting.file_id == file_id).count()


def _count_meetings_by_name_prefix(prefix: str) -> int:
    from db.models import Meeting
    from db.session import SessionFactory

    with SessionFactory() as session:
        return (
            session.query(Meeting)
            .filter(Meeting.meeting_name.like(f"{prefix}%"))
            .count()
        )


def _get_meeting_summary(file_id: str) -> dict | None:
    from db.models import Meeting
    from db.session import SessionFactory

    with SessionFactory() as session:
        m = session.query(Meeting).filter(Meeting.file_id == file_id).first()
        if not m:
            return None
        return {
            "file_id": m.file_id,
            "status": m.status,
            "transcript_length": m.transcript_length,
            "meeting_name": m.meeting_name,
            "preview": (m.transcript or "")[:80].replace("\n", " "),
        }


def _pick_user_id() -> int | None:
    from db.models import User
    from db.session import SessionFactory

    with SessionFactory() as session:
        u = session.query(User).order_by(User.id.asc()).first()
        return u.id if u else None


def _elapsed_str(started_at: float) -> str:
    sec = int(time.time() - started_at)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _print_count_row(
    step: str,
    file_id: str,
    name_prefix: str,
    *,
    started_at: float | None = None,
) -> dict:
    by_id = _count_meetings_by_file_id(file_id)
    by_name = _count_meetings_by_name_prefix(name_prefix)
    info = _get_meeting_summary(file_id)
    status = info["status"] if info else "-"
    length = info["transcript_length"] if info else 0
    clock = f"t+{_elapsed_str(started_at)} " if started_at else ""
    line = (
        f"  [{clock}{step:<22}] "
        f"by_file_id={by_id}  by_name_prefix={by_name}  "
        f"status={status:<12} transcript_len={length}"
    )
    print(line, flush=True)
    return {"by_file_id": by_id, "by_name_prefix": by_name, "status": status, "length": length}


async def _stable_record(
    session_info: dict,
    *,
    cycle: int,
    stable_seconds: float,
    chunk_interval: float,
    ws,
) -> None:
    """稳定录音一段时间，周期性追加转写（模拟持续说话）。"""
    deadline = time.time() + max(0.0, stable_seconds)
    chunk_i = 0
    while time.time() < deadline:
        wait = min(chunk_interval, max(0.0, deadline - time.time()))
        if wait > 0:
            await asyncio.sleep(wait)
        if time.time() >= deadline and chunk_i > 0:
            break
        chunk_i += 1
        session_info["audio_chunks"] = int(session_info.get("audio_chunks") or 0) + 4
        elapsed_min = int((time.time() - float(session_info["recording_started_at"])) / 60)
        session_info["total_text"] = (session_info.get("total_text") or "") + (
            f"[段{cycle}.{chunk_i}|{elapsed_min}min] "
            f"长会议不稳定网络模拟转写内容。\n"
        )
        ws._save_resume_snapshot(session_info)


async def _disconnect_and_reconnect(
    *,
    cycle: int,
    session_info: dict,
    recording_id: str,
    file_id: str,
    name_prefix: str,
    meeting_name: str,
    user_id: int | None,
    reconnect_delay: float,
    started_at: float,
    counts: list,
    ws,
) -> tuple[dict, int]:
    """执行一次断连应急落库 + 延迟重连，返回 (新 session_info, 失败则非0)。"""
    session_info["connection_id"] = f"conn-live-{cycle}"
    ws._save_resume_snapshot(session_info)

    print(
        f"\n[DISCONNECT #{cycle}] t+{_elapsed_str(started_at)} "
        f"模拟网络断开 → 应急备份",
        flush=True,
    )
    await ws._persist_realtime_session_emergency(
        session_info,
        connection_id=session_info["connection_id"],
        start_time=started_at,
        reason="interrupted",
    )
    row = _print_count_row(
        f"after_disconnect_{cycle}",
        file_id,
        name_prefix,
        started_at=started_at,
    )
    counts.append(row)
    if row["by_file_id"] != 1 or row["by_name_prefix"] != 1:
        print(
            f"  !! FAIL: 断连后记录数异常 by_file_id={row['by_file_id']} "
            f"by_name_prefix={row['by_name_prefix']}",
            flush=True,
        )
        return session_info, 1

    print(f"[WAIT] {reconnect_delay}s 后自动重连…", flush=True)
    await asyncio.sleep(reconnect_delay)

    print(
        f"[RECONNECT #{cycle}] t+{_elapsed_str(started_at)} "
        f"resume_recording_id={recording_id[:8]}…",
        flush=True,
    )
    snap = ws._load_resume_snapshot(recording_id, user_id) if user_id is not None else None
    if snap is None:
        snap = ws._recording_resume_store.get(recording_id)
    if not snap:
        print("  !! FAIL: 重连时快照丢失", flush=True)
        return session_info, 1
    if snap.get("file_id") != file_id:
        print(
            f"  !! FAIL: file_id 变化 {snap.get('file_id')} != {file_id}",
            flush=True,
        )
        return session_info, 1

    client_transcript = (session_info.get("total_text") or "").strip()
    new_info = {
        "recording_id": recording_id,
        "connection_id": f"conn-resume-{cycle}",
        "user_id": user_id,
        "file_id": file_id,
        "meeting_name": snap.get("meeting_name") or meeting_name,
        "transcript_path": snap.get("transcript_path") or session_info.get("transcript_path"),
        "total_text": (snap.get("total_text") or client_transcript or ""),
        "audio_chunks": int(snap.get("audio_chunks") or 0),
        "saved": bool(snap.get("saved")),
        "recording_started_at": snap.get("recording_started_at")
        or session_info.get("recording_started_at"),
        "start_time": session_info.get("start_time"),
        "transcriber": None,
        "resumed": True,
    }
    if client_transcript and len(client_transcript) > len(
        (new_info["total_text"] or "").strip()
    ):
        new_info["total_text"] = (
            client_transcript if client_transcript.endswith("\n") else client_transcript + "\n"
        )
    ws._save_resume_snapshot(new_info)

    row = _print_count_row(
        f"after_reconnect_{cycle}",
        file_id,
        name_prefix,
        started_at=started_at,
    )
    counts.append(row)
    if row["by_file_id"] != 1 or row["by_name_prefix"] != 1:
        print("  !! FAIL: 重连后会议记录数异常", flush=True)
        return new_info, 1
    return new_info, 0


async def simulate_session(
    *,
    cycles: int | None,
    duration_minutes: float | None,
    stable_seconds: float,
    chunk_interval: float,
    reconnect_delay: float,
    keep: bool,
) -> int:
    from api.routes import websocket as ws
    from db.session import delete_meeting, save_meeting_to_db

    user_id = _pick_user_id()
    recording_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    name_prefix = f"E2E断连重连测试_{run_tag}"
    meeting_name = f"{name_prefix}_主会话"

    transcripts_dir = ROOT / "output" / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcripts_dir / f"e2e_{file_id}_realtime.txt"

    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    progress_log = log_dir / f"e2e_disconnect_reconnect_{run_tag}.log"

    duration_mode = duration_minutes is not None and duration_minutes > 0
    duration_sec = float(duration_minutes) * 60.0 if duration_mode else 0.0
    started_at = time.time()
    end_at = started_at + duration_sec if duration_mode else None

    print("=" * 72, flush=True)
    print("E2E 断连重连 → 会议记录数量验证", flush=True)
    print("=" * 72, flush=True)
    print(f"  recording_id   : {recording_id}", flush=True)
    print(f"  file_id        : {file_id}", flush=True)
    print(f"  meeting_name   : {meeting_name}", flush=True)
    if duration_mode:
        print(f"  mode           : duration {duration_minutes} min", flush=True)
        print(f"  stable_seconds : {stable_seconds}s（两次断连之间的稳定录音）", flush=True)
        print(f"  chunk_interval : {chunk_interval}s", flush=True)
        est_cycles = max(1, int(duration_sec / max(stable_seconds + reconnect_delay, 1)))
        print(f"  est_cycles     : ~{est_cycles}", flush=True)
    else:
        print(f"  mode           : cycles={cycles}", flush=True)
    print(f"  reconnect_delay: {reconnect_delay}s", flush=True)
    print(f"  keep_meeting   : {keep}", flush=True)
    print(f"  progress_log   : {progress_log}", flush=True)
    print("-" * 72, flush=True)

    # 同时 tee 到进度日志
    class _Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()

        def flush(self):
            for s in self.streams:
                s.flush()

    log_fp = progress_log.open("w", encoding="utf-8")
    old_stdout = sys.stdout
    sys.stdout = _Tee(old_stdout, log_fp)

    session_info = {
        "recording_id": recording_id,
        "connection_id": "conn-start",
        "user_id": user_id,
        "file_id": file_id,
        "meeting_name": meeting_name,
        "transcript_path": str(transcript_path),
        "total_text": "",
        "audio_chunks": 0,
        "saved": False,
        "recording_started_at": started_at,
        "start_time": datetime.now().isoformat(),
        "transcriber": None,
        "resumed": False,
    }

    ws._save_resume_snapshot(session_info)
    print("\n[START] 开始录音（尚未落库）", flush=True)
    counts = [_print_count_row("start(no_db_yet)", file_id, name_prefix, started_at=started_at)]
    exit_code = 1

    try:
        cycle = 0
        while True:
            cycle += 1
            if duration_mode:
                remaining = (end_at or 0) - time.time()
                if remaining <= 0:
                    print(
                        f"\n[TIME UP] 已达到 {duration_minutes} 分钟，准备停止",
                        flush=True,
                    )
                    break
                # 最后不足一轮稳定录音时，缩短本轮
                this_stable = min(stable_seconds, remaining)
            else:
                if cycles is None or cycle > cycles:
                    break
                this_stable = stable_seconds if cycles and cycles > 0 else 0.0
                # 短测：几乎不等稳定期，快速打点
                if cycles and stable_seconds <= 0:
                    this_stable = 0.0

            print(
                f"\n[RECORD #{cycle}] t+{_elapsed_str(started_at)} "
                f"稳定录音 {this_stable:.0f}s…",
                flush=True,
            )
            if this_stable > 0:
                await _stable_record(
                    session_info,
                    cycle=cycle,
                    stable_seconds=this_stable,
                    chunk_interval=chunk_interval,
                    ws=ws,
                )
            else:
                session_info["audio_chunks"] = int(session_info.get("audio_chunks") or 0) + 8
                session_info["total_text"] = (session_info.get("total_text") or "") + (
                    f"[段{cycle}] 模拟不稳定网络下的转写内容，第 {cycle} 次会话片段。\n"
                )
                ws._save_resume_snapshot(session_info)

            if duration_mode and time.time() >= (end_at or 0):
                print(
                    f"\n[TIME UP] 稳定录音结束时已到点，跳过本轮断连直接停止",
                    flush=True,
                )
                break

            session_info, err = await _disconnect_and_reconnect(
                cycle=cycle,
                session_info=session_info,
                recording_id=recording_id,
                file_id=file_id,
                name_prefix=name_prefix,
                meeting_name=meeting_name,
                user_id=user_id,
                reconnect_delay=reconnect_delay,
                started_at=started_at,
                counts=counts,
                ws=ws,
            )
            if err:
                return err

            if not duration_mode and cycles is not None and cycle >= cycles:
                break

        # —— 用户主动停止 ——
        wall = _elapsed_str(started_at)
        print(f"\n[STOP] t+{wall} 用户停止录音 → 写入 processing", flush=True)
        final_text = (session_info.get("total_text") or "") + (
            f"[结束] 用户停止录音，会议时长约 {wall}。\n"
        )
        Path(session_info["transcript_path"]).write_text(final_text, encoding="utf-8")
        save_meeting_to_db(
            {
                "file_id": file_id,
                "user_id": user_id,
                "meeting_name": meeting_name,
                "original_filename": Path(session_info["transcript_path"]).name,
                "meeting_type": "realtime",
                "transcript_file_path": session_info["transcript_path"],
                "transcript": final_text,
                "transcript_length": len(final_text),
                "summary": None,
                "summary_length": 0,
                "total_duration_ms": round((time.time() - started_at) * 1000, 2),
                "status": "processing",
                "error_message": None,
            }
        )
        ws._clear_resume_snapshot(recording_id)

        row = _print_count_row("after_stop", file_id, name_prefix, started_at=started_at)
        counts.append(row)

        info = _get_meeting_summary(file_id)
        print("\n" + "=" * 72, flush=True)
        print("最终会议记录", flush=True)
        print("=" * 72, flush=True)
        if info:
            for k, v in info.items():
                print(f"  {k}: {v}", flush=True)
        else:
            print("  (未找到会议记录)", flush=True)

        max_by_id = max(c["by_file_id"] for c in counts)
        max_by_name = max(c["by_name_prefix"] for c in counts)
        final_ok = (
            row["by_file_id"] == 1
            and row["by_name_prefix"] == 1
            and max_by_id == 1
            and max_by_name == 1
            and info is not None
            and info["status"] == "processing"
        )

        print("\n" + "-" * 72, flush=True)
        print(f"  disconnect_cycles: {cycle if duration_mode else cycles}", flush=True)
        print(f"  wall_clock       : {_elapsed_str(started_at)}", flush=True)
        print(f"  max_by_file_id   : {max_by_id}", flush=True)
        print(f"  max_by_name      : {max_by_name}", flush=True)

        if final_ok:
            print(
                f"PASS: 全程会议记录始终只有 1 条 (file_id={file_id})",
                flush=True,
            )
            exit_code = 0
        else:
            print(
                f"FAIL: max(by_file_id)={max_by_id}, max(by_name_prefix)={max_by_name}, "
                f"final={row}",
                flush=True,
            )
            exit_code = 1
        return exit_code
    finally:
        sys.stdout = old_stdout
        log_fp.close()
        if not keep:
            try:
                delete_meeting(file_id)
            except Exception:
                pass
            if transcript_path.exists():
                try:
                    transcript_path.unlink()
                except OSError:
                    pass
            print(f"\n[CLEANUP] 已删除测试会议 file_id={file_id}", flush=True)
        else:
            print(
                f"\n[KEEP] 保留测试会议便于核查 file_id={file_id}\n"
                f"       name={meeting_name}",
                flush=True,
            )
        ws._recording_resume_store.pop(recording_id, None)
        print(f"[LOG] 进度已写入 {progress_log}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="断连重连后验证会议记录数量")
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=None,
        help="按时长跑（分钟）。例如 30 表示真实跑约 30 分钟",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="按断连次数跑（与 --duration-minutes 二选一；都不传则默认 cycles=5）",
    )
    parser.add_argument(
        "--stable-seconds",
        type=float,
        default=90.0,
        help="两次断连之间的稳定录音秒数（时长模式默认 90）",
    )
    parser.add_argument(
        "--chunk-interval",
        type=float,
        default=15.0,
        help="稳定录音期间追加转写的间隔秒数（默认 15）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="重连前等待秒数（默认 1.0，对齐前端）",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="结束后保留会议记录，不自动删除",
    )
    parser.add_argument(
        "--no-keep",
        action="store_true",
        help="结束后删除会议记录（时长模式默认保留）",
    )
    args = parser.parse_args()

    duration = args.duration_minutes
    cycles = args.cycles
    if duration is None and cycles is None:
        cycles = 5

    # 时长模式默认 keep；短测默认清理
    keep = True if (duration and duration > 0 and not args.no_keep) else bool(args.keep)
    if args.no_keep:
        keep = False

    stable = args.stable_seconds
    if cycles is not None and duration is None and stable == 90.0:
        # 短测默认不空等 90s
        stable = 0.0

    return asyncio.run(
        simulate_session(
            cycles=cycles,
            duration_minutes=duration,
            stable_seconds=max(0.0, stable),
            chunk_interval=max(1.0, args.chunk_interval),
            reconnect_delay=max(0.0, args.delay),
            keep=keep,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
