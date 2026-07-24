"""达人库筛库工具：经门户 API 读取 influencers / tags / agencies。"""

from __future__ import annotations

from typing import Any

from services.portal_influencer_client import PortalInfluencerClient

# 模型常把契约里的「douyin|xiaohongshu」整段抄进 platform；统一归一
_PLATFORM_ALIASES = {
    "douyin": "douyin",
    "抖音": "douyin",
    "dy": "douyin",
    "tiktok": "douyin",
    "xiaohongshu": "xiaohongshu",
    "小红书": "xiaohongshu",
    "xhs": "xiaohongshu",
    "red": "xiaohongshu",
}
_PLACEHOLDER_TAG_IDS = {1, 2, 12, 123, 456, 1234, 111, 222, 999}


def _normalize_platform(raw: Any) -> tuple[str | None, str | None]:
    """返回 (platform|None, warning)。非法/多平台写法 → 省略平台（不限）。"""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    lower = text.lower().replace(" ", "")
    # 契约抄写 / 多选：一律视为不限，避免精确等值把结果打成 0
    if any(sep in text for sep in ("|", "/", ",", "，", "或", "和", "&")):
        return None, f"platform「{text}」不是单值枚举，已忽略（按不限平台检索）"
    if lower in _PLATFORM_ALIASES:
        return _PLATFORM_ALIASES[lower], None
    # 尝试拆出单个已知别名
    for alias, code in _PLATFORM_ALIASES.items():
        if alias in lower:
            return code, f"platform 已归一为 {code}"
    return None, f"未知 platform「{text}」，已忽略（按不限平台检索）"


def _clean_tag_ids(raw: Any) -> tuple[list[int], list[str]]:
    warnings: list[str] = []
    ids: list[int] = []
    if isinstance(raw, list):
        src = raw
    elif raw is not None and str(raw).strip().isdigit():
        src = [raw]
    else:
        return [], warnings
    for x in src:
        try:
            n = int(x)
        except Exception:
            continue
        if n <= 0:
            continue
        if n in _PLACEHOLDER_TAG_IDS:
            warnings.append(f"疑似示例 tag_id={n} 已丢弃；请先 influencer_list_tags 取真实 id")
            continue
        ids.append(n)
    # 去重保序
    seen: set[int] = set()
    out: list[int] = []
    for n in ids:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out, warnings


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
    warnings: list[str] = []

    platform, plat_warn = _normalize_platform(args.get("platform"))
    if plat_warn:
        warnings.append(plat_warn)

    keyword = str(args.get("keyword") or args.get("q") or "").strip()
    # 过长 brief 整句 like 几乎必空；截成短检索词
    if len(keyword) > 40:
        warnings.append("keyword 过长，已截断为前 40 字；建议用短主题词或 tag_ids")
        keyword = keyword[:40]

    tag_ids, tag_warns = _clean_tag_ids(args.get("tag_ids") or args.get("required_tag_ids"))
    warnings.extend(tag_warns)

    follower_min = None
    follower_max = None
    if args.get("follower_min") is not None:
        try:
            follower_min = int(args["follower_min"])
        except Exception:
            warnings.append("follower_min 非法，已忽略")
    if args.get("follower_max") is not None:
        try:
            follower_max = int(args["follower_max"])
        except Exception:
            warnings.append("follower_max 非法，已忽略")

    agency_id = None
    if args.get("agency_id") is not None:
        try:
            agency_id = int(args["agency_id"])
        except Exception:
            warnings.append("agency_id 非法，已忽略")

    async def _once(
        *,
        use_platform: bool,
        use_keyword: bool,
        use_tags: bool,
        use_followers: bool,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "status": 1,
        }
        if use_platform and platform:
            params["platform"] = platform
        if use_keyword and keyword:
            params["keyword"] = keyword
        if use_followers and follower_min is not None:
            params["follower_min"] = follower_min
        if use_followers and follower_max is not None:
            params["follower_max"] = follower_max
        if agency_id is not None:
            params["agency_id"] = agency_id
        if use_tags and tag_ids:
            params["tag_ids"] = tag_ids
        if args.get("source"):
            params["source"] = str(args["source"]).strip()
        return await client._get("/api/v1/influencers", params)

    # 逐步放宽：完整条件 → 丢标签 → 丢关键词 → 仅粉丝 → 不限
    attempts = [
        (True, True, True, True, "full"),
        (True, True, False, True, "drop_tags"),
        (True, False, False, True, "followers_platform"),
        (False, False, False, True, "followers_only"),
        (False, False, False, False, "unfiltered"),
    ]
    # 若调用方本来就没有某条件，跳过等价重复尝试
    res: dict[str, Any] = {"ok": False, "error": "未执行检索"}
    used_attempt = "full"
    for use_plat, use_kw, use_tags, use_fol, name in attempts:
        if name != "full":
            # 仅在上一轮 0 命中时放宽
            if res.get("ok") and int((res.get("data") or {}).get("total") or 0) > 0:
                break
            if name == "drop_tags" and not tag_ids:
                continue
            if name == "followers_platform" and not keyword and not tag_ids:
                continue
            if name == "followers_only" and follower_min is None and follower_max is None:
                continue
            if name == "unfiltered" and follower_min is None and not keyword and not tag_ids and not platform:
                continue
        res = await _once(
            use_platform=use_plat,
            use_keyword=use_kw,
            use_tags=use_tags,
            use_followers=use_fol,
        )
        used_attempt = name
        if not res.get("ok"):
            return res
        total_try = int((res.get("data") or {}).get("total") or 0)
        if total_try > 0:
            if name != "full":
                warnings.append(f"原条件 0 命中，已自动放宽策略={name}")
            break

    data = res.get("data") or {}
    if not isinstance(data, dict):
        return {"ok": False, "error": "达人列表格式异常"}
    raw_items = data.get("items") if isinstance(data.get("items"), list) else []
    items = [_brief_item(x) for x in raw_items if isinstance(x, dict)]

    # 可选：按运营资料关键词二次过滤（含 tags）
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
            "请先 influencer_list_tags 取真实 tag_ids；"
            "或去掉 platform/tag_ids，仅保留 follower_min + 短 keyword 再 search。"
        )
    return {
        "ok": True,
        "count": len(items),
        "total": total,
        "page": data.get("page") or page,
        "page_size": data.get("page_size") or page_size,
        "items": items,
        "hint": hint,
        "warnings": warnings or None,
        "applied": {
            "platform": platform if used_attempt in {"full", "drop_tags", "followers_platform"} else None,
            "keyword": keyword if used_attempt in {"full", "drop_tags"} else None,
            "tag_ids": tag_ids if used_attempt == "full" else [],
            "follower_min": follower_min if used_attempt != "unfiltered" else None,
            "widen": used_attempt,
        },
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
