from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"


@dataclass
class SkillDef:
    name: str
    slug: str
    description: str
    version: int
    tools: list[str]
    body_md: str
    confirm: list[str]


def parse_skill_markdown(text: str) -> SkillDef:
    fm: dict[str, Any] = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if m:
        fm = yaml.safe_load(m.group(1)) or {}
        body = m.group(2)
    perms = fm.get("permissions") or {}
    return SkillDef(
        name=str(fm.get("name") or "unnamed"),
        slug=str(fm.get("slug") or fm.get("name") or "unnamed"),
        description=str(fm.get("description") or ""),
        version=int(fm.get("version") or 1),
        tools=list(fm.get("tools") or []),
        body_md=body.strip(),
        confirm=list(perms.get("confirm") or []),
    )


def load_builtin_skills() -> list[SkillDef]:
    out: list[SkillDef] = []
    if not BUILTIN_DIR.exists():
        return out
    for path in sorted(BUILTIN_DIR.glob("*.md")):
        out.append(parse_skill_markdown(path.read_text(encoding="utf-8")))
    return out


def skill_to_tools_json(tools: list[str]) -> str:
    return json.dumps(tools, ensure_ascii=False)
