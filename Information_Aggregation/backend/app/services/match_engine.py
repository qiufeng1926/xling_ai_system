"""达人库智能匹配打分引擎"""

from dataclasses import dataclass, field

from app.models import Influencer, InfluencerTag
from app.schemas.match import MatchReasonDetail, MatchReasonOut, MatchRequirements


@dataclass
class ScoredInfluencer:
    influencer: Influencer
    score: float
    reason: MatchReasonOut
    details: list[MatchReasonDetail] = field(default_factory=list)


def _influencer_tag_ids(influencer: Influencer) -> set[int]:
    return {it.tag_id for it in influencer.tags if it.tag_id}


def _influencer_tag_names(influencer: Influencer) -> list[str]:
    return [it.tag.name for it in influencer.tags if it.tag is not None]


def _has_contact(influencer: Influencer) -> bool:
    profile = influencer.profile
    if profile is None:
        return False
    contact = profile.contact_info or {}
    return bool(contact.get("phone") or contact.get("wechat"))


def passes_hard_filters(influencer: Influencer, req: MatchRequirements) -> bool:
    if req.platform and influencer.platform != req.platform:
        return False
    if req.follower_min is not None and influencer.follower_count < req.follower_min:
        return False
    if req.follower_max is not None and influencer.follower_count > req.follower_max:
        return False
    if req.engagement_rate_min is not None:
        rate = float(influencer.engagement_rate or 0)
        if rate < req.engagement_rate_min:
            return False
    if req.keyword:
        kw = req.keyword.lower()
        nickname = (influencer.nickname or "").lower()
        uid = influencer.platform_uid.lower()
        if kw not in nickname and kw not in uid:
            return False
    if req.required_tag_ids:
        tag_ids = _influencer_tag_ids(influencer)
        if not all(tid in tag_ids for tid in req.required_tag_ids):
            return False
    if req.must_have_contact and not _has_contact(influencer):
        return False
    return True


def _score_tags(influencer: Influencer, req: MatchRequirements) -> MatchReasonDetail:
    max_score = 40.0
    tag_ids = _influencer_tag_ids(influencer)
    names = _influencer_tag_names(influencer)

    required = req.required_tag_ids or []
    preferred = req.preferred_tag_ids or []

    score = 0.0
    notes: list[str] = []

    if required:
        matched = sum(1 for tid in required if tid in tag_ids)
        score += (matched / len(required)) * 25
        notes.append(f"必选标签 {matched}/{len(required)}")
    elif preferred:
        score += 10.0
        notes.append("无必选标签，基础分")
    else:
        score += 15.0
        notes.append("未设标签条件")

    if preferred:
        matched_pref = sum(1 for tid in preferred if tid in tag_ids)
        score += (matched_pref / len(preferred)) * 15
        notes.append(f"优先标签 {matched_pref}/{len(preferred)}")

    if names:
        notes.append(f"标签: {', '.join(names[:5])}")

    return MatchReasonDetail(
        dimension="tags",
        score=round(min(score, max_score), 1),
        max_score=max_score,
        note="；".join(notes),
    )


def _score_followers(influencer: Influencer, req: MatchRequirements) -> MatchReasonDetail:
    max_score = 25.0
    count = influencer.follower_count
    fmin = req.follower_min
    fmax = req.follower_max

    if fmin is None and fmax is None:
        return MatchReasonDetail(
            dimension="followers",
            score=15.0,
            max_score=max_score,
            note=f"粉丝 {count}，未设区间",
        )

    lo = fmin if fmin is not None else 0
    hi = fmax if fmax is not None else max(count, lo + 1)
    if hi < lo:
        lo, hi = hi, lo

    if lo <= count <= hi:
        mid = (lo + hi) / 2
        span = max(hi - lo, 1)
        closeness = 1 - abs(count - mid) / (span / 2)
        closeness = max(0.0, min(1.0, closeness))
        score = 15 + closeness * 10
        note = f"粉丝 {count}，位于 {lo}–{hi} 区间内"
    else:
        score = 0.0
        note = f"粉丝 {count}，不在 {lo}–{hi} 区间"

    return MatchReasonDetail(
        dimension="followers",
        score=round(min(score, max_score), 1),
        max_score=max_score,
        note=note,
    )


def _score_engagement(influencer: Influencer, req: MatchRequirements) -> MatchReasonDetail:
    max_score = 15.0
    rate = float(influencer.engagement_rate or 0)
    threshold = req.engagement_rate_min

    if threshold is None:
        if rate > 0:
            score = min(10 + rate * 100, max_score)
            note = f"互动率 {rate:.2%}"
        else:
            score = 5.0
            note = "无互动率数据"
    elif rate >= threshold:
        bonus = min((rate - threshold) * 200, 5)
        score = 10 + bonus
        note = f"互动率 {rate:.2%}，高于阈值 {threshold:.2%}"
    else:
        score = 0.0
        note = f"互动率 {rate:.2%}，低于阈值"

    return MatchReasonDetail(
        dimension="engagement",
        score=round(min(score, max_score), 1),
        max_score=max_score,
        note=note,
    )


def _score_agency(influencer: Influencer, req: MatchRequirements) -> MatchReasonDetail:
    max_score = 10.0
    if req.agency_id is None:
        return MatchReasonDetail(
            dimension="agency",
            score=5.0,
            max_score=max_score,
            note="未指定机构偏好",
        )
    if influencer.agency_id == req.agency_id:
        name = influencer.agency.name if influencer.agency else "目标机构"
        return MatchReasonDetail(
            dimension="agency",
            score=max_score,
            max_score=max_score,
            note=f"所属机构: {name}",
        )
    return MatchReasonDetail(
        dimension="agency",
        score=0.0,
        max_score=max_score,
        note="机构不匹配",
    )


def _score_profile(influencer: Influencer) -> MatchReasonDetail:
    max_score = 10.0
    score = 0.0
    notes: list[str] = []

    if _has_contact(influencer):
        score += 5
        notes.append("有联系方式")
    profile = influencer.profile
    if profile and profile.cooperation_policy:
        score += 3
        notes.append("有合作政策")
    if profile and profile.internal_notes:
        score += 2
        notes.append("有内部备注")

    if not notes:
        notes.append("档案信息较少")

    return MatchReasonDetail(
        dimension="profile",
        score=round(min(score, max_score), 1),
        max_score=max_score,
        note="；".join(notes),
    )


def score_influencer(influencer: Influencer, req: MatchRequirements) -> ScoredInfluencer:
    details = [
        _score_tags(influencer, req),
        _score_followers(influencer, req),
        _score_engagement(influencer, req),
        _score_agency(influencer, req),
        _score_profile(influencer),
    ]
    total = round(sum(d.score for d in details), 1)
    summary_parts = [d.note for d in details if d.score > 0][:3]
    reason = MatchReasonOut(
        summary="；".join(summary_parts) if summary_parts else "综合匹配",
        details=details,
    )
    return ScoredInfluencer(influencer=influencer, score=total, reason=reason, details=details)


def rank_influencers(
    influencers: list[Influencer],
    req: MatchRequirements,
) -> list[ScoredInfluencer]:
    scored: list[ScoredInfluencer] = []
    for influencer in influencers:
        if not passes_hard_filters(influencer, req):
            continue
        scored.append(score_influencer(influencer, req))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[: req.limit]
