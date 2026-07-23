"""Open Library 工具自测（由 self_test_agent 调用）。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import unquote


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""


def test_openlibrary_lookup_mock() -> CaseResult:
    """mock HTTP：命中 / 歧义 / 未命中；单轮 HTTP ≤ 查询数；缓存命中不再打网。"""
    from agent.answer import materials_support_count_list
    from agent.context import TaskContext, apply_result_to_context
    from agent.research_policy import (
        openlibrary_discover_args,
        prefers_openlibrary_catalog,
    )
    from tools.openlibrary import (
        MAX_QUERIES,
        clear_cache,
        openlibrary_lookup,
        set_http_get_json,
    )
    from tools.web_tools import validate_and_normalize_args

    calls: list[str] = []

    async def fake_get(url: str, headers: dict[str, str]):
        calls.append(url)
        ua = headers.get("User-Agent") or ""
        if "XlinkAgent-OpenLibrary" not in ua:
            raise AssertionError(f"bad UA: {ua}")
        decoded = unquote(url)
        if "q=人类简史" in decoded or "q=Sapiens" in decoded:
            return {
                "num_found": 1,
                "docs": [
                    {
                        "key": "/works/OL123W",
                        "title": "人类简史",
                        "author_name": ["Yuval Noah Harari"],
                        "first_publish_year": 2011,
                        "edition_count": 40,
                    }
                ],
            }
        if "subject=history" in decoded or "q=world history" in decoded:
            return {
                "num_found": 3,
                "docs": [
                    {
                        "key": "OL1W",
                        "title": "Guns, Germs, and Steel",
                        "author_name": ["Jared Diamond"],
                        "first_publish_year": 1997,
                        "edition_count": 20,
                    },
                    {
                        "key": "OL2W",
                        "title": "A Short History of Nearly Everything",
                        "author_name": ["Bill Bryson"],
                        "first_publish_year": 2003,
                        "edition_count": 15,
                    },
                    {
                        "key": "OL3W",
                        "title": "The History of the Ancient World",
                        "author_name": ["Susan Wise Bauer"],
                        "first_publish_year": 2007,
                        "edition_count": 5,
                    },
                ],
            }
        if "q=AmbiguousBook" in decoded:
            return {
                "num_found": 3,
                "docs": [
                    {"key": "OL10W", "title": "Ambiguous Book Alpha", "author_name": ["A"]},
                    {"key": "OL11W", "title": "Ambiguous Book Beta", "author_name": ["B"]},
                    {"key": "OL12W", "title": "Ambiguous Book Gamma", "author_name": ["C"]},
                ],
            }
        return {"num_found": 0, "docs": []}

    async def _main() -> CaseResult:
        clear_cache()
        set_http_get_json(fake_get)
        calls.clear()
        try:
            bad, err = validate_and_normalize_args("openlibrary_lookup", {})
            if bad is not None or not err:
                return CaseResult("openlibrary_lookup", False, "empty args should fail")

            norm, err2 = validate_and_normalize_args(
                "openlibrary_lookup",
                {"queries": ["人类简史", "虚构怪书XYZ999"]},
            )
            if err2 or not norm:
                return CaseResult("openlibrary_lookup", False, f"normalize fail: {err2}")

            r1 = await openlibrary_lookup(queries=["人类简史", "虚构怪书XYZ999"])
            n1 = len(calls)
            await openlibrary_lookup(queries=["人类简史"])
            n2 = len(calls)
            r3 = await openlibrary_lookup(queries=["AmbiguousBook"])
            r4 = await openlibrary_lookup(
                q="world history primers", subject="history", limit=5
            )
            r5 = await openlibrary_lookup(queries=[f"Book{i}" for i in range(30)])

            if not r1.get("ok"):
                return CaseResult("openlibrary_lookup", False, f"r1 fail: {r1}")
            statuses = {it["query"]: it["status"] for it in r1.get("items") or []}
            if statuses.get("人类简史") != "matched":
                return CaseResult("openlibrary_lookup", False, f"expect matched: {statuses}")
            if statuses.get("虚构怪书XYZ999") != "not_found":
                return CaseResult("openlibrary_lookup", False, f"expect not_found: {statuses}")
            if n1 > 2:
                return CaseResult("openlibrary_lookup", False, f"too many http: {n1}")
            if n2 != n1:
                return CaseResult(
                    "openlibrary_lookup", False, f"cache missed http {n1}->{n2}"
                )
            if (r3.get("items") or [{}])[0].get("status") != "ambiguous":
                return CaseResult("openlibrary_lookup", False, f"expect ambiguous: {r3}")
            if len(r4.get("discover") or []) < 2:
                return CaseResult("openlibrary_lookup", False, f"discover weak: {r4}")
            if len(r5.get("items") or []) > MAX_QUERIES:
                return CaseResult(
                    "openlibrary_lookup",
                    False,
                    f"queries not capped: {len(r5.get('items') or [])}",
                )

            ctx = TaskContext(goal="推荐20本历史相关的书籍", facts=[])
            apply_result_to_context(
                ctx, "openlibrary_lookup", r1, args={"queries": ["人类简史"]}
            )
            if not any("书目核验(Open Library)" in f for f in ctx.facts):
                return CaseResult(
                    "openlibrary_lookup", False, f"facts not written: {ctx.facts}"
                )
            if not materials_support_count_list(
                [
                    "书目核验(Open Library):\n"
                    "- [matched] a → 《史记》 — 司马迁 (0)\n"
                    "- [matched] b → 《资治通鉴》 — 司马光 (0)\n"
                    "- [matched] c → 《人类简史》 — Harari (2011)\n"
                ],
                "推荐20本历史相关的书籍",
            ):
                return CaseResult(
                    "openlibrary_lookup", False, "OL facts not list-supportive"
                )

            if not prefers_openlibrary_catalog("给我推荐20本历史相关的书籍"):
                return CaseResult("openlibrary_lookup", False, "prefers catalog missed")
            dargs = openlibrary_discover_args("给我推荐20本历史相关的书籍")
            if "q" not in dargs or dargs.get("limit", 0) < 5:
                return CaseResult("openlibrary_lookup", False, f"discover args: {dargs}")

            return CaseResult(
                "openlibrary_lookup",
                True,
                f"matched/not_found/ambiguous/discover ok http={n1} cache_ok={n2 == n1}",
            )
        finally:
            set_http_get_json(None)
            clear_cache()

    return asyncio.run(_main())
