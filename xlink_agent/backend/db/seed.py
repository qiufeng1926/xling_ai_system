from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Skill
from skills.loader import load_builtin_skills, skill_to_tools_json
from utils.logger import get_logger

logger = get_logger("seed")


def seed_builtin_skills(db: Session) -> None:
    builtins = load_builtin_skills()
    for s in builtins:
        exists = (
            db.query(Skill)
            .filter(Skill.scope == "builtin", Skill.slug == s.slug)
            .first()
        )
        if exists:
            exists.name = s.name
            exists.description = s.description
            exists.body_md = s.body_md
            exists.tools_json = skill_to_tools_json(s.tools)
            exists.version = s.version
            exists.enabled = True
        else:
            db.add(
                Skill(
                    owner_user_id=None,
                    scope="builtin",
                    name=s.name,
                    slug=s.slug,
                    description=s.description,
                    body_md=s.body_md,
                    tools_json=skill_to_tools_json(s.tools),
                    version=s.version,
                    enabled=True,
                )
            )
    # 商单筛库已迁至独立 match_agent 运行时，禁用旧会话级 Skill 残留
    stale = (
        db.query(Skill)
        .filter(Skill.scope == "builtin", Skill.slug == "influencer-match")
        .first()
    )
    if stale:
        stale.enabled = False
    db.commit()
    logger.info("已同步官方 Skill %s 个", len(builtins))
