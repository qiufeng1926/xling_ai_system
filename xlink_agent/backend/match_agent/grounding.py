"""终稿精准性：只允许使用工具 Observation 中出现过的达人记录。"""

from __future__ import annotations

import json
from typing import Any


def ingest_observation_catalog(
    catalog: dict[int, dict[str, Any]],
    result: dict[str, Any] | None,
) -> None:
    """把工具返回里的达人写入 catalog（以 id 为键）。"""
    if not isinstance(result, dict) or not result.get("ok"):
        return
    items: list[Any] = []
    if isinstance(result.get("items"), list):
        items.extend(result["items"])
    if isinstance(result.get("item"), dict):
        items.append(result["item"])
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            iid = int(it.get("id"))
        except Exception:
            continue
        prev = catalog.get(iid) or {}
        merged = {**prev, **{k: v for k, v in it.items() if v is not None}}
        catalog[iid] = merged


def order_catalog_items(
    catalog: dict[int, dict[str, Any]],
    *,
    ranked_ids: list[int] | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    if ranked_ids:
        ordered = [catalog[i] for i in ranked_ids if i in catalog]
    else:
        ordered = sorted(
            catalog.values(),
            key=lambda x: float(x.get("match_score") or 0),
            reverse=True,
        )
    seen: set[int] = set()
    uniq: list[dict[str, Any]] = []
    for it in ordered:
        try:
            iid = int(it["id"])
        except Exception:
            continue
        if iid in seen:
            continue
        seen.add(iid)
        uniq.append(it)
        if len(uniq) >= limit:
            break
    return uniq


def build_influencer_cards(
    catalog: dict[int, dict[str, Any]],
    *,
    ranked_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """前端卡片用结构化载荷（字段均来自库 Observation）。"""
    cards: list[dict[str, Any]] = []
    for rank, it in enumerate(order_catalog_items(catalog, ranked_ids=ranked_ids), start=1):
        contact = it.get("contact") if isinstance(it.get("contact"), dict) else {}
        cards.append(
            {
                "rank": rank,
                "id": it.get("id"),
                "platform": it.get("platform"),
                "platform_uid": it.get("platform_uid"),
                "nickname": it.get("nickname"),
                "avatar_url": it.get("avatar_url"),
                "follower_count": it.get("follower_count") or 0,
                "engagement_rate": it.get("engagement_rate"),
                "agency_name": it.get("agency_name"),
                "tags": list(it.get("tags") or [])[:8],
                "shooting_style": list(it.get("shooting_style") or [])[:6],
                "persona_traits": list(it.get("persona_traits") or [])[:6],
                "cooperation_policy": it.get("cooperation_policy"),
                "internal_notes": it.get("internal_notes"),
                "contact": {
                    "phone": contact.get("phone"),
                    "wechat": contact.get("wechat"),
                },
                "match_score": it.get("match_score"),
                "match_reasons": list(it.get("match_reasons") or [])[:5],
                "detail_path": f"/influencer/influencers/{it.get('id')}",
            }
        )
    return cards


def build_grounded_answer(
    catalog: dict[int, dict[str, Any]],
    *,
    brief: str,
    ranked_ids: list[int] | None = None,
    draft: str = "",
) -> str:
    """简短总起文案；详细字段由前端卡片展示。"""
    _ = draft
    uniq = order_catalog_items(catalog, ranked_ids=ranked_ids)
    n = len(uniq)
    head = (
        f"已根据商单要求，仅从达人库筛选出 {n} 位达人"
        + ("（达到建议的至少 5 人）" if n >= 5 else "（少于建议的 5 人，以下为库内全部可匹配结果）")
        + "。信息均来自达人库，点击卡片可查看详情。"
    )
    if brief.strip():
        head = f"商单摘要：{brief.strip()[:200]}\n\n" + head
    if not uniq:
        return (
            head
            + "\n\n当前筛选条件下达人库无可用记录。请放宽平台/粉丝/标签后再试；"
            "禁止用外部搜索补人。"
        )
    return head


def extract_ranked_ids_from_last_rank(result: dict[str, Any] | None) -> list[int]:
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        return []
    out: list[int] = []
    for it in result["items"]:
        if isinstance(it, dict) and it.get("id") is not None:
            try:
                out.append(int(it["id"]))
            except Exception:
                pass
    return out


def observation_preview(result: Any, *, limit: int = 3500) -> str:
    try:
        text = json.dumps(result, ensure_ascii=False)
    except Exception:
        text = str(result)
    return text[:limit]
