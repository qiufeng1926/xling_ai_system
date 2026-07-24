"""测试用：为达人库全部达人填充完整且互不相同的运营信息。"""

from __future__ import annotations

from datetime import date, timedelta

from app.database import SessionLocal
from app.models import Influencer, InfluencerProfile

STYLES = [
    "真人出镜",
    "口播讲解",
    "剧情短片",
    "Vlog日常",
    "图文种草",
    "测评开箱",
    "探店实拍",
    "教程干货",
    "混剪快剪",
    "直播切片",
    "情景喜剧",
    "分镜叙事",
    "航拍风光",
    "美食制作",
    "穿搭街拍",
    "家居改造",
    "亲子互动",
    "职场分享",
]

TRAITS = [
    "亲和力强",
    "专业严谨",
    "幽默搞笑",
    "知性温柔",
    "活力元气",
    "冷静理性",
    "故事感强",
    "高转化力",
    "圈层影响力",
    "真诚种草",
    "颜值出众",
    "声线出色",
    "适合硬广",
    "适合软植入",
    "适合直播带货",
    "适合品牌联名",
    "适合长合作",
    "适合单次试投",
]

POLICIES = [
    "支持软植入，硬广需提前确认脚本；报价按粉丝层级阶梯；可接受样品置换。",
    "仅接品牌向内容，不接竞品对比；需提供产品合规资料；交付周期7个工作日。",
    "可接探店与本地生活；需提前预约档期；支持二次剪辑授权（限品牌自用）。",
    "优先长约合作；单次投放需加急费；脚本需双方确认后开拍。",
    "可出镜可口播；不接医疗功效承诺类；发票可开对公。",
    "支持矩阵账号联动；主号+小号打包优惠；需预付50%。",
    "适合种草测评；需寄样一周以上；接受效果付费部分结算。",
    "直播专场优先；坑位费+佣金；需提供主播培训素材包。",
    "剧情向内容可定制；需提供品牌视觉规范；成片保留肖像权协商。",
    "图文+短视频组合更优；不接受强制带货话术；可提供数据复盘。",
]

NOTES = [
    "沟通顺畅，回复较快，适合紧急档期。",
    "经纪人对接，决策偏慢，建议提前两周沟通。",
    "对品牌调性要求高，需先过案例审核。",
    "曾合作美妆类，转化稳定，可优先复投。",
    "粉丝偏年轻，适合潮流与数码新品。",
    "粉丝偏母婴家庭，适合日用品与教育。",
    "内容偏职场干货，适合B端或效率工具。",
    "探店口碑好，本地生活转化强。",
    "需注意竞品排他条款，合作前核对。",
    "素材质量高，适合做品牌片头与KV。",
    "价格敏感，可谈样品+现金组合。",
    "适合做系列内容连载，不适合单条硬广。",
]


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.query(Influencer).order_by(Influencer.id.asc()).all()
        print(f"准备填充 {len(rows)} 个达人运营信息")
        for i, inf in enumerate(rows):
            phone = f"138{(inf.id * 7919) % 100000000:08d}"
            uid_tail = (inf.platform_uid or str(i))[-4:]
            wechat = f"ops_{inf.platform}_{inf.id}_{uid_tail}"[:32]
            styles = list(
                dict.fromkeys(
                    [
                        STYLES[(i * 3) % len(STYLES)],
                        STYLES[(i * 3 + 5) % len(STYLES)],
                        STYLES[(i * 7 + 1) % len(STYLES)],
                    ]
                )
            )
            traits = list(
                dict.fromkeys(
                    [
                        TRAITS[(i * 2) % len(TRAITS)],
                        TRAITS[(i * 2 + 7) % len(TRAITS)],
                        TRAITS[(i * 5 + 3) % len(TRAITS)],
                    ]
                )
            )
            policy = (
                POLICIES[i % len(POLICIES)]
                + f"（达人#{inf.id}专属条款：档期周{(i % 5) + 1}优先）"
            )
            nick = inf.nickname or "-"
            note = (
                NOTES[i % len(NOTES)]
                + f" 平台={inf.platform} uid={inf.platform_uid} 昵称={nick}"
            )
            last = date.today() - timedelta(days=(i * 3) % 90 + 1)

            profile = inf.profile
            if profile is None:
                profile = InfluencerProfile(influencer_id=inf.id)
                db.add(profile)

            profile.contact_info = {"phone": phone, "wechat": wechat}
            profile.shooting_style = styles
            profile.persona_traits = traits
            profile.cooperation_policy = policy
            profile.internal_notes = note
            profile.last_contact_date = last
            profile.updated_by = None

        db.commit()

        phones: set[str] = set()
        wechats: set[str] = set()
        policies: set[str] = set()
        notes: set[str] = set()
        incomplete = 0
        total = 0
        for inf in db.query(Influencer).order_by(Influencer.id.asc()).all():
            total += 1
            p = inf.profile
            ok = bool(
                p
                and p.contact_info
                and p.contact_info.get("phone")
                and p.contact_info.get("wechat")
                and p.shooting_style
                and p.persona_traits
                and p.cooperation_policy
                and p.internal_notes
                and p.last_contact_date
            )
            if not ok:
                incomplete += 1
                print(f"INCOMPLETE id={inf.id}")
                continue
            phones.add(str(p.contact_info["phone"]))
            wechats.add(str(p.contact_info["wechat"]))
            policies.add(str(p.cooperation_policy))
            notes.add(str(p.internal_notes))
            if inf.id <= 3 or inf.id == rows[-1].id:
                print(
                    f"#{inf.id} {inf.nickname}: "
                    f"phone={p.contact_info['phone']} wechat={p.contact_info['wechat']} "
                    f"styles={p.shooting_style} traits={p.persona_traits}"
                )
                print(f"   policy={p.cooperation_policy[:48]}...")
                print(f"   notes={p.internal_notes[:48]}... last={p.last_contact_date}")

        print("---")
        print(f"total={total} incomplete={incomplete}")
        print(
            f"unique phones={len(phones)}/{total} "
            f"wechats={len(wechats)}/{total} "
            f"policies={len(policies)}/{total} "
            f"notes={len(notes)}/{total}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
