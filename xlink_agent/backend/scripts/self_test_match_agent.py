"""商单筛库 / 隔离 自测（改代码后应跑通）。

用法（在 xlink_agent/backend 下）:
  set PYTHONPATH=.
  python scripts/self_test_match_agent.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AGENT = "http://127.0.0.1:8003"
PORTAL = "http://127.0.0.1:8000"


def _client(**kwargs) -> httpx.Client:
    # Windows 系统代理可能导致本机 127.0.0.1 被错误代理成 502
    kwargs.setdefault("trust_env", False)
    kwargs.setdefault("timeout", 30.0)
    return httpx.Client(**kwargs)


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def login_portal() -> str:
    candidates = [
        ("qiufengai", "qfai12@@"),
        ("admin", "admin123"),
        ("admin", "change-me-on-first-run"),
    ]
    with _client(timeout=15.0) as c:
        for user, pwd in candidates:
            r = c.post(
                f"{PORTAL}/api/v1/auth/login",
                data={"username": user, "password": pwd},
            )
            if r.status_code != 200:
                continue
            body = r.json()
            token = body.get("access_token")
            if not token and isinstance(body.get("data"), dict):
                token = body["data"].get("access_token")
            if token:
                _ok(f"portal login as {user}")
                return str(token)
    _fail(f"portal login failed（请确认 :8000 可用）。last={r.status_code} {r.text[:200]}")


def test_openapi_has_match() -> None:
    with _client(timeout=15.0) as c:
        r = c.get(f"{AGENT}/openapi.json")
        if r.status_code != 200:
            _fail(f"openapi {r.status_code}")
        paths = set((r.json().get("paths") or {}).keys())
    need = {
        "/api/agent/v1/match/conversations",
        "/api/agent/v1/match/conversations/{conversation_id}/chat",
        "/api/agent/v1/match/conversations/{conversation_id}/messages",
    }
    missing = need - paths
    if missing:
        _fail(f"openapi 缺少 match 路由: {missing}（需重启 :8003）")
    _ok("openapi 含商单筛库路由")


def test_match_crud(token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    with _client(timeout=30.0) as c:
        r = c.get(f"{AGENT}/api/agent/v1/match/conversations", headers=headers)
        if r.status_code != 200:
            _fail(f"GET match/conversations -> {r.status_code} {r.text[:300]}")
        _ok(f"list match conversations ({len(r.json().get('items') or [])})")

        r = c.post(
            f"{AGENT}/api/agent/v1/match/conversations",
            headers=headers,
            json={"title": "自测商单筛库"},
        )
        if r.status_code != 200:
            _fail(f"POST match/conversations -> {r.status_code} {r.text[:300]}")
        cid = int(r.json()["id"])
        if r.json().get("skill_slug") != "influencer-match":
            _fail(f"skill_slug 应为 influencer-match, got {r.json().get('skill_slug')}")
        _ok(f"create match conversation id={cid}")

        # 通用接口不得创建筛库会话
        r = c.post(
            f"{AGENT}/api/agent/v1/conversations",
            headers=headers,
            json={"title": "非法", "skill_slug": "influencer-match"},
        )
        if r.status_code == 200:
            _fail("通用 conversations 不应允许 skill_slug=influencer-match")
        _ok(f"通用接口拒绝筛库 slug ({r.status_code})")

        # 通用列表不应混入筛库会话（默认过滤）
        r = c.get(f"{AGENT}/api/agent/v1/conversations", headers=headers)
        if r.status_code != 200:
            _fail(f"list general conversations {r.status_code}")
        for it in r.json().get("items") or []:
            if it.get("id") == cid:
                _fail("通用会话列表泄漏了商单筛库会话")
        _ok("通用会话列表未泄漏筛库会话")
        return cid


def test_isolation_tools() -> None:
    from agent.orchestrator import KNOWN_TOOLS, _active_skills, _merge_tools
    from db.session import SessionLocal

    if any(str(t).startswith("influencer_") for t in KNOWN_TOOLS):
        _fail("通用 KNOWN_TOOLS 仍含 influencer_*")
    if "call_influencer_match" not in KNOWN_TOOLS:
        _fail("通用 KNOWN_TOOLS 缺少 call_influencer_match")
    db = SessionLocal()
    try:
        tools, _ = _merge_tools(_active_skills(db, 1))
    finally:
        db.close()
    if any(str(t).startswith("influencer_") for t in tools):
        _fail("通用 merge_tools 泄漏 influencer_*")
    if "call_influencer_match" not in tools:
        _fail("通用 merge_tools 缺少 call_influencer_match")
    if "web_search" not in tools:
        _fail("通用 merge_tools 缺少 web_search")
    _ok("工具隔离：通用可 call_influencer_match，无 influencer_*")


def test_runtime_blocks_direct_influencer() -> None:
    import asyncio

    from db.session import SessionLocal
    from tools.runtime import execute_tool

    db = SessionLocal()

    async def _run():
        return await execute_tool(
            "influencer_search",
            {"platform": "douyin"},
            db=db,
            user_id=1,
            conversation_id=1,
        )

    try:
        result = asyncio.run(_run())
    finally:
        db.close()
    if result.get("ok") is not False:
        _fail(f"通用 runtime 应拦截 influencer_search, got {result}")
    _ok("通用 runtime 拦截直接达人库工具")


def test_grounding() -> None:
    from match_agent.grounding import (
        build_grounded_answer,
        build_influencer_cards,
        ingest_observation_catalog,
    )

    cat: dict = {}
    ingest_observation_catalog(
        cat,
        {
            "ok": True,
            "items": [
                {
                    "id": 9,
                    "nickname": "真实达人",
                    "platform": "douyin",
                    "platform_uid": "uid9",
                    "follower_count": 1000,
                    "avatar_url": "https://example.com/a.png",
                    "contact": {"phone": "13800000009", "wechat": "wx9"},
                    "cooperation_policy": "政策A",
                    "shooting_style": ["口播"],
                    "persona_traits": ["亲和"],
                    "tags": ["探店"],
                }
            ],
        },
    )
    ans = build_grounded_answer(cat, brief="测试商单", draft="我编造假达人张三丰")
    if "张三丰" in ans:
        _fail("grounded 终稿混入了模型草稿编造")
    if "筛选出 1 位" not in ans and "1 位达人" not in ans:
        _fail(f"grounded 总起异常: {ans[:200]}")
    cards = build_influencer_cards(cat)
    if len(cards) != 1 or cards[0]["id"] != 9:
        _fail(f"cards 异常: {cards}")
    if cards[0].get("detail_path") != "/influencer/influencers/9":
        _fail(f"detail_path 异常: {cards[0]}")
    if cards[0].get("contact", {}).get("phone") != "13800000009":
        _fail("card 缺少联系方式")
    _ok("grounded 总起 + 卡片载荷仅含库记录")


def test_match_messages(token: str, cid: int) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    with _client(timeout=15.0) as c:
        r = c.get(f"{AGENT}/api/agent/v1/match/conversations/{cid}/messages", headers=headers)
        if r.status_code != 200:
            _fail(f"messages {r.status_code} {r.text[:200]}")
        _ok("match messages 可读")


def main() -> None:
    print("=== self_test_match_agent ===")
    with _client(timeout=10.0) as c:
        try:
            h = c.get(f"{AGENT}/health")
        except Exception as exc:
            _fail(f"agent :8003 不可达: {exc}")
        if h.status_code != 200:
            _fail(f"agent health {h.status_code}")
    _ok("agent health")

    test_openapi_has_match()
    test_isolation_tools()
    test_runtime_blocks_direct_influencer()
    test_grounding()
    token = login_portal()
    cid = test_match_crud(token)
    test_match_messages(token, cid)
    print("=== ALL PASSED ===")


if __name__ == "__main__":
    main()
