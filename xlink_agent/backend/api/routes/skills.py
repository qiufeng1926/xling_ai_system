from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import get_current_user, require_user_id
from api.portal_auth import PortalUser
from db.models import Skill, UserSkillInstall
from db.session import get_db
from skills.loader import parse_skill_markdown, skill_to_tools_json

router = APIRouter(prefix="/v1/skills", tags=["skills"])


class SkillCreate(BaseModel):
    body_md: str = Field(min_length=10)


class SkillPatch(BaseModel):
    body_md: str | None = None
    enabled: bool | None = None


def _skill_dict(s: Skill, *, installed: bool | None = None) -> dict:
    d = {
        "id": s.id,
        "scope": s.scope,
        "name": s.name,
        "slug": s.slug,
        "description": s.description,
        "body_md": s.body_md,
        "tools": json.loads(s.tools_json or "[]"),
        "version": s.version,
        "enabled": s.enabled,
        "owner_user_id": s.owner_user_id,
    }
    if installed is not None:
        d["installed"] = installed
    return d


@router.get("")
def list_skills(
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    installed = {
        r.skill_id
        for r in db.query(UserSkillInstall).filter(UserSkillInstall.user_id == uid).all()
    }
    builtins = db.query(Skill).filter(Skill.scope == "builtin", Skill.enabled.is_(True)).all()
    from skills.scoped import CONVERSATION_SCOPED_SKILLS

    builtins = [s for s in builtins if (s.slug or "") not in CONVERSATION_SCOPED_SKILLS]
    mine = (
        db.query(Skill)
        .filter(Skill.scope == "user", Skill.owner_user_id == uid)
        .order_by(Skill.id.desc())
        .all()
    )
    return {
        "builtin": [_skill_dict(s, installed=(s.id in installed or not installed)) for s in builtins],
        "mine": [_skill_dict(s) for s in mine],
    }


@router.post("")
def create_skill(
    body: SkillCreate,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    parsed = parse_skill_markdown(body.body_md)
    row = Skill(
        owner_user_id=uid,
        scope="user",
        name=parsed.name,
        slug=parsed.slug,
        description=parsed.description,
        body_md=body.body_md,
        tools_json=skill_to_tools_json(parsed.tools),
        version=parsed.version,
        enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _skill_dict(row)


@router.post("/install/{skill_id}")
def install_skill(
    skill_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    skill = db.get(Skill, skill_id)
    if not skill or skill.scope != "builtin":
        raise HTTPException(404, "仅可安装官方 Skill")
    exists = (
        db.query(UserSkillInstall)
        .filter(UserSkillInstall.user_id == uid, UserSkillInstall.skill_id == skill_id)
        .first()
    )
    if not exists:
        db.add(UserSkillInstall(user_id=uid, skill_id=skill_id))
        db.commit()
    return {"ok": True}


@router.delete("/install/{skill_id}")
def uninstall_skill(
    skill_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    row = (
        db.query(UserSkillInstall)
        .filter(UserSkillInstall.user_id == uid, UserSkillInstall.skill_id == skill_id)
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.patch("/{skill_id}")
def patch_skill(
    skill_id: int,
    body: SkillPatch,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    skill = db.get(Skill, skill_id)
    if not skill or skill.scope != "user" or skill.owner_user_id != uid:
        raise HTTPException(404, "只能修改自己的 Skill")
    if body.body_md is not None:
        parsed = parse_skill_markdown(body.body_md)
        skill.body_md = body.body_md
        skill.name = parsed.name
        skill.slug = parsed.slug
        skill.description = parsed.description
        skill.tools_json = skill_to_tools_json(parsed.tools)
        skill.version = parsed.version
    if body.enabled is not None:
        skill.enabled = body.enabled
    db.commit()
    return _skill_dict(skill)


@router.delete("/{skill_id}")
def delete_skill(
    skill_id: int,
    user: PortalUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = require_user_id(user)
    skill = db.get(Skill, skill_id)
    if not skill or skill.scope != "user" or skill.owner_user_id != uid:
        raise HTTPException(404, "只能删除自己的 Skill")
    db.delete(skill)
    db.commit()
    return {"ok": True}
