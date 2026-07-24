"""达人库筛库工具：经门户 API 读取 influencers / tags / agencies。"""

from __future__ import annotations

from typing import Any

from services.portal_influencer_client import PortalInfluencerClient


def _brief_item(item: dict[str, Any]) -> dict[str, Any]:
    profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
    contact = profile.get("contact_info") if isinstance(profile.get("contact_info"), dict) else {}
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    tag_names = []
    for t in tags:
        if isinstance(t, dict) and t.get("name"):
            tag_names.append(str(t["name"]))
    return {
        "id": item.get("id"),
        "platform": item.get("platform"),
        "platform_uid": item.get("platform_uid"),
        "nickname": item.get("nickname"),
        "avatar_url": item.get("avatar_url"),
        "follower_count": item.get("follower_count"),
        "engagement_rate": item.get("engagement_rate"),
        "agency_id": item.get("agency_id"),
        "agency_name": item.get("agency_name"),
        "tags": tag_names,
        "profile_url": item.get("profile_url"),
        "contact": {
            "phone": contact.get("phone"),
            "wechat": contact.get("wechat"),
        },
        "shooting_style": profile.get("shooting_style") or [],
        "persona_traits": profile.get("persona_traits") or [],
        "cooperation_policy": profile.get("cooperation_policy"),
        "internal_notes": profile.get("internal_notes"),
        "last_contact_date": str(profile.get("last_contact_date") or "") or None,
    }


async def influencer_list_tags(args: dict[str, Any]) -> dict[str, Any]:
    client = PortalInfluencerClient()
    res = await client._get("/api/v1/tags")
    if not res.get("ok"):
        return res
    data = res.get("data") or []
    if not isinstance(data, list):
        return {"ok": False, "error": "标签列表格式异常"}
    items = []
    for t in data:
        if not isinstance(t, dict):
            continue
        items.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "category": t.get("category"),
                "level": t.get("level"),
                "parent_id": t.get("parent_id"),
            }
        )
    q = str(args.get("query") or args.get("keyword") or "").strip().lower()
    if q:
        items = [
            x
            for x in items
            if q in str(x.get("name") or "").lower() or q in str(x.get("category") or "").lower()
        ]
    return {"ok": True, "count": len(items), "items": items[:200]}


async def influencer_list_agencies(args: dict[str, Any]) -> dict[str, Any]:
    client = PortalInfluencerClient()
    # options 更轻量；失败再退回分页列表
    res = await client._get("/api/v1/agencies/options")
    if not res.get("ok"):
        res = await client._get(
            "/api/v1/agencies",
            {"page": 1, "page_size": min(int(args.get("limit") or 50), 100)},
        )
        if not res.get("ok"):
            return res
        page = res.get("data") or {}
        data = page.get("items") if isinstance(page, dict) else []
    else:
        data = res.get("data") or []
    if not isinstance(data, list):
        return {"ok": False, "error": "机构列表格式异常"}
    items = []
    for a in data:
        if not isinstance(a, dict):
            continue
        items.append(
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "platform": a.get("platform"),
            }
        )
    q = str(args.get("query") or args.get("keyword") or "").strip().lower()
    if q:
        items = [x for x in items if q in str(x.get("name") or "").lower()]
    return {"ok": True, "count": len(items), "items": items[:100]}


async def influencer_search(args: dict[str, Any]) -> dict[str, Any]:
    client = PortalInfluencerClient()
    page = max(1, int(args.get("page") or 1))
    page_size = max(1, min(int(args.get("page_size") or args.get("limit") or 20), 100))
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "status": 1,
    }
    if args.get("platform"):
        params["platform"] = str(args["platform"]).strip()
    if args.get("keyword") or args.get("q"):
        params["keyword"] = str(args.get("keyword") or args.get("q") or "").strip()
    if args.get("follower_min") is not None:
        params["follower_min"] = int(args["follower_min"])
    if args.get("follower_max") is not None:
        params["follower_max"] = int(args["follower_max"])
    if args.get("agency_id") is not None:
        params["agency_id"] = int(args["agency_id"])
    if args.get("source"):
        params["source"] = str(args["source"]).strip()
    tag_ids = args.get("tag_ids") or args.get("required_tag_ids")
    if isinstance(tag_ids, list) and tag_ids:
        # FastAPI list query: tag_ids=1&tag_ids=2
        params["tag_ids"] = [int(x) for x in tag_ids if str(x).isdigit() or isinstance(x, int)]
    elif tag_ids is not None and str(tag_ids).strip().isdigit():
        params["tag_ids"] = [int(tag_ids)]

    res = await client._get("/api/v1/influencers", params)
    if not res.get("ok"):
        return res
    data = res.get("data") or {}
    if not isinstance(data, dict):
        return {"ok": False, "error": "达人列表格式异常"}
    raw_items = data.get("items") if isinstance(data.get("items"), list) else []
    items = [_brief_item(x) for x in raw_items if isinstance(x, dict)]

    # 可选：按运营资料关键词二次过滤（门户 keyword 已覆盖 nickname/uid/profile 文本）
    profile_q = str(args.get("profile_keyword") or "").strip().lower()
    if profile_q:
        filtered = []
        for it in items:
            blob = " ".join(
                [
                    str(it.get("cooperation_policy") or ""),
                    str(it.get("internal_notes") or ""),
                    " ".join(str(x) for x in (it.get("shooting_style") or [])),
                    " ".join(str(x) for x in (it.get("persona_traits") or [])),
                    " ".join(str(x) for x in (it.get("tags") or [])),
                ]
            ).lower()
            if profile_q in blob:
                filtered.append(it)
        items = filtered

    total = int(data.get("total") or len(items))
    hint = None
    if total < 5:
        hint = (
            f"当前筛选仅命中 {total} 人（少于建议的 5 人）。"
            "请放宽粉丝区间/标签/平台后再次 influencer_search，或换关键词。"
        )
    return {
        "ok": True,
        "count": len(items),
        "total": total,
        "page": data.get("page") or page,
        "page_size": data.get("page_size") or page_size,
        "items": items,
        "hint": hint,
        "min_recommended": 5,
    }


async def influencer_get(args: dict[str, Any]) -> dict[str, Any]:
    client = PortalInfluencerClient()
    iid = args.get("influencer_id") or args.get("id")
    try:
        influencer_id = int(iid)
    except Exception:
        return {"ok": False, "error": "influencer_get 需要整数 influencer_id"}
    res = await client._get(f"/api/v1/influencers/{influencer_id}")
    if not res.get("ok"):
        return res
    data = res.get("data")
    if not isinstance(data, dict):
        return {"ok": False, "error": "达人详情格式异常"}
    return {"ok": True, "item": _brief_item(data)}


async def influencer_rank(args: dict[str, Any]) -> dict[str, Any]:
    """对已检索到的候选做简单本地打分排序（不依赖旧 match API）。"""
    candidates = args.get("candidates") or args.get("items") or []
    if not isinstance(candidates, list) or not candidates:
        return {"ok": False, "error": "influencer_rank 需要 candidates 数组（来自 influencer_search）"}

    preferred_tags = {
        str(x).strip().lower()
        for x in (args.get("preferred_tags") or args.get("preferred_tag_names") or [])
        if str(x).strip()
    }
    required_tags = {
        str(x).strip().lower()
        for x in (args.get("required_tags") or args.get("required_tag_names") or [])
        if str(x).strip()
    }
    keyword = str(args.get("keyword") or "").strip().lower()
    must_contact = bool(args.get("must_have_contact"))
    limit = max(5, min(int(args.get("limit") or 10), 50))

    scored: list[dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        tags = {str(t).strip().lower() for t in (raw.get("tags") or []) if str(t).strip()}
        if required_tags and not required_tags.issubset(tags):
            continue
        contact = raw.get("contact") if isinstance(raw.get("contact"), dict) else {}
        has_contact = bool(contact.get("phone") or contact.get("wechat"))
        if must_contact and not has_contact:
            continue

        score = 40.0
        reasons: list[str] = []
        if preferred_tags:
            hit = len(preferred_tags & tags)
            score += hit * 8
            if hit:
                reasons.append(f"优先标签命中 {hit}/{len(preferred_tags)}")
        if required_tags:
            score += 15
            reasons.append("满足必选标签")
        followers = int(raw.get("follower_count") or 0)
        if followers >= 1_000_000:
            score += 15
            reasons.append("粉丝百万级")
        elif followers >= 100_000:
            score += 10
            reasons.append("粉丝十万级")
        elif followers >= 10_000:
            score += 6
            reasons.append("粉丝过万")
        er = float(raw.get("engagement_rate") or 0)
        if er >= 0.05:
            score += 10
            reasons.append(f"互动率 {er:.2%}")
        elif er > 0:
            score += 5
        if has_contact:
            score += 8
            reasons.append("有联系方式")
        if raw.get("cooperation_policy"):
            score += 5
            reasons.append("有合作政策")
        if keyword:
            blob = " ".join(
                [
                    str(raw.get("nickname") or ""),
                    str(raw.get("cooperation_policy") or ""),
                    str(raw.get("internal_notes") or ""),
                    " ".join(str(x) for x in (raw.get("persona_traits") or [])),
                    " ".join(str(x) for x in (raw.get("shooting_style") or [])),
                ]
            ).lower()
            if keyword in blob:
                score += 10
                reasons.append(f"命中关键词「{keyword}」")

        scored.append(
            {
                **raw,
                "match_score": round(score, 1),
                "match_reasons": reasons or ["综合匹配"],
            }
        )

    scored.sort(key=lambda x: float(x.get("match_score") or 0), reverse=True)
    top = scored[:limit]
    hint = None
    if len(top) < 5:
        hint = (
            f"排序后仅 {len(top)} 人。请放宽筛选条件重新 influencer_search，"
            "或去掉 must_have_contact / 必选标签后再 rank。"
        )
    return {
        "ok": True,
        "count": len(top),
        "total_scored": len(scored),
        "items": top,
        "hint": hint,
        "min_recommended": 5,
    }


INFLUENCER_TOOL_HANDLERS = {
    "influencer_list_tags": influencer_list_tags,
    "influencer_list_agencies": influencer_list_agencies,
    "influencer_search": influencer_search,
    "influencer_get": influencer_get,
    "influencer_rank": influencer_rank,
}
