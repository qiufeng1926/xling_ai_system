"""
图文速览 JSON 结构与校验、版式规范化、长文本分块
"""
import json
import re
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

THEMES = ('green', 'orange', 'blue', 'pink', 'teal', 'brown', 'purple', 'red')
LAYOUTS = ('grid-2', 'grid-3', 'grid-4', 'full')
TAG_LABELS = ('重点', '待跟进', '已决策', '风险', '待确认')
MAX_SECTIONS = 8


class VisualCard(BaseModel):
    title: str = ''
    icon: str = 'doc'
    tag: str | None = None
    bullets: list[str] = Field(default_factory=list)
    highlight: str | None = None

    @field_validator('bullets', mode='before')
    @classmethod
    def coerce_bullets(cls, v):
        return _coerce_str_list(v)


class VisualSection(BaseModel):
    id: str = '1'
    title: str = ''
    theme: str = 'green'
    layout: str = 'grid-3'
    cards: list[VisualCard] = Field(default_factory=list)

    @field_validator('theme')
    @classmethod
    def validate_theme(cls, v: str) -> str:
        return v if v in THEMES else 'green'

    @field_validator('layout')
    @classmethod
    def validate_layout(cls, v: str) -> str:
        return v if v in LAYOUTS else 'grid-3'


def _coerce_str_list(value) -> list[str]:
    """LLM 常把列表字段输出成字符串，统一转为字符串列表"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parts = re.split(r'[\n；;]+', text)
        if len(parts) == 1 and ('，' in text or ',' in text):
            parts = re.split(r'[，,]+', text)
        return [p.strip() for p in parts if p.strip()]
    return [str(value).strip()] if str(value).strip() else []


class VisualFooter(BaseModel):
    contacts: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    core_consensus: str | None = None

    @field_validator('contacts', 'next_steps', mode='before')
    @classmethod
    def coerce_list_fields(cls, v):
        return _coerce_str_list(v)


class VisualSummary(BaseModel):
    title: str = '会议纪要'
    subtitle: str | None = None
    sections: list[VisualSection] = Field(default_factory=list)
    footer: VisualFooter = Field(default_factory=VisualFooter)


def _extract_json_object(text: str) -> str:
    text = text.strip()
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        return text[start:end + 1]
    return text


def _pick_str(data: dict, *keys: str) -> str:
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ''


def _card_dict_has_content(card: dict) -> bool:
    if not isinstance(card, dict):
        return False
    return bool(
        _pick_str(card, 'title', 'name', 'heading')
        or _coerce_str_list(card.get('bullets') or card.get('points') or card.get('items'))
        or _pick_str(card, 'highlight', 'summary', 'content')
    )


def _section_dict_to_cards(sec: dict) -> list[dict]:
    """将 LLM 多种字段写法统一为 cards 列表"""
    raw_cards = sec.get('cards') or sec.get('items') or sec.get('children') or []
    cards: list[dict] = []

    if isinstance(raw_cards, list):
        for item in raw_cards:
            if isinstance(item, str) and item.strip():
                cards.append({'title': '', 'bullets': [item.strip()]})
            elif isinstance(item, dict):
                cards.append({
                    'title': _pick_str(item, 'title', 'name', 'heading'),
                    'icon': item.get('icon') or 'doc',
                    'tag': item.get('tag'),
                    'bullets': _coerce_str_list(
                        item.get('bullets') or item.get('points') or item.get('items')
                    ),
                    'highlight': _pick_str(item, 'highlight', 'summary', 'content') or None,
                })

    section_points = _coerce_str_list(
        sec.get('bullets') or sec.get('points') or sec.get('items') or sec.get('content')
    )
    section_title = _pick_str(sec, 'title', 'name', 'heading', 'topic')

    if not cards and section_points:
        cards.append({
            'title': section_title or '要点',
            'icon': 'doc',
            'bullets': section_points,
        })
    elif not cards and section_title:
        desc = _pick_str(sec, 'description', 'summary', 'content', 'highlight')
        bullets = [desc] if desc else []
        cards.append({
            'title': section_title,
            'icon': 'doc',
            'bullets': bullets,
        })

    return [c for c in cards if _card_dict_has_content(c)]


def _sanitize_visual_payload(payload: dict) -> dict:
    """校验前修正常见 LLM 输出格式问题"""
    footer = payload.get('footer')
    if isinstance(footer, dict):
        for key in ('contacts', 'next_steps'):
            if key in footer:
                footer[key] = _coerce_str_list(footer.get(key))

    sections_in = payload.get('sections') or payload.get('items') or []
    sections_out: list[dict] = []
    for sec in sections_in:
        if not isinstance(sec, dict):
            if isinstance(sec, str) and sec.strip():
                sections_out.append({
                    'title': sec.strip(),
                    'cards': [{'title': sec.strip(), 'bullets': []}],
                })
            continue
        cards = _section_dict_to_cards(sec)
        title = _pick_str(sec, 'title', 'name', 'heading', 'topic')
        if not title and cards:
            title = _pick_str(cards[0], 'title', 'name', 'heading') or '未命名分区'
        if not title and not cards:
            continue
        sections_out.append({
            'id': sec.get('id'),
            'title': title,
            'theme': sec.get('theme') or 'green',
            'layout': sec.get('layout') or 'grid-3',
            'cards': cards,
        })

    payload['sections'] = sections_out
    return payload


def parse_visual_summary(raw: str) -> VisualSummary:
    """解析并校验 LLM 输出的 JSON"""
    payload = json.loads(_extract_json_object(raw))
    payload = _sanitize_visual_payload(payload)
    return VisualSummary.model_validate(payload)


def layout_for_card_count(count: int) -> str:
    if count <= 1:
        return 'full'
    if count == 2:
        return 'grid-2'
    if count <= 4:
        return 'grid-3'
    return 'grid-4'


def _card_has_content(card: VisualCard) -> bool:
    return bool(
        (card.title or '').strip()
        or card.bullets
        or (card.highlight or '').strip()
    )


def _fill_card_defaults(card: VisualCard, section_title: str) -> VisualCard:
    if not (card.title or '').strip():
        if card.bullets:
            card.title = (card.bullets[0][:24] + '…') if len(card.bullets[0]) > 24 else card.bullets[0]
        elif section_title:
            card.title = section_title
        else:
            card.title = '要点'
    if not card.bullets and (card.highlight or '').strip():
        card.bullets = [card.highlight.strip()]
    return card


def normalize_visual_summary(visual: VisualSummary) -> VisualSummary:
    """分区编号 01/02…、按卡片数自动布局、规范 tag、补齐空卡片"""
    normalized_sections: list[VisualSection] = []

    for i, sec in enumerate(visual.sections):
        sec_title = (sec.title or '').strip()
        cards = [_fill_card_defaults(c, sec_title) for c in sec.cards if _card_has_content(c)]

        if not cards and sec_title:
            cards = [VisualCard(title=sec_title, bullets=['（该主题详情见文字速览）'])]

        if not cards:
            continue

        sec.cards = cards
        sec.id = str(len(normalized_sections) + 1).zfill(2)
        sec.theme = THEMES[len(normalized_sections) % len(THEMES)]
        sec.layout = layout_for_card_count(len(cards))
        for card in sec.cards:
            if card.tag and card.tag not in TAG_LABELS:
                for label in TAG_LABELS:
                    if label in card.tag:
                        card.tag = label
                        break
        normalized_sections.append(sec)

    visual.sections = normalized_sections[:MAX_SECTIONS]
    return visual


def visual_dict_for_display(data: dict | str | None) -> dict | None:
    """将库中/文件中的图文 JSON 规范为可展示结构（兼容历史脏数据）"""
    if not data:
        return None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    try:
        payload = _sanitize_visual_payload(dict(data))
        visual = VisualSummary.model_validate(payload)
        return visual_summary_to_dict(normalize_visual_summary(visual))
    except (json.JSONDecodeError, ValueError, ValidationError):
        return None


def split_transcript_chunks(text: str, max_chars: int, overlap: int = 400) -> list[str]:
    """按段落合并为不超过 max_chars 的块，块间保留 overlap 字符避免断句"""
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if not paragraphs:
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars - overlap)]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush():
        nonlocal current, current_len
        if current:
            chunks.append('\n\n'.join(current))
            current = []
            current_len = 0

    for para in paragraphs:
        plen = len(para) + 2
        if plen > max_chars:
            flush()
            for i in range(0, len(para), max_chars - overlap):
                chunks.append(para[i:i + max_chars])
            continue
        if current_len + plen > max_chars and current:
            flush()
            if chunks and overlap > 0:
                tail = chunks[-1][-overlap:].strip()
                if tail:
                    current = [tail]
                    current_len = len(tail) + 2
        current.append(para)
        current_len += plen

    flush()
    return chunks if chunks else [text[:max_chars]]


def _dedupe_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def merge_visual_parts(parts: list[VisualSummary]) -> VisualSummary:
    """合并多段图文结果"""
    if not parts:
        return VisualSummary()
    if len(parts) == 1:
        return parts[0]

    title = parts[0].title or '会议纪要'
    subtitle = parts[0].subtitle
    sections: list[VisualSection] = []
    all_contacts: list[str] = []
    all_steps: list[str] = []
    consensuses: list[str] = []

    for part in parts:
        sections.extend(part.sections)
        all_contacts.extend(part.footer.contacts or [])
        all_steps.extend(part.footer.next_steps or [])
        if part.footer.core_consensus:
            consensuses.append(part.footer.core_consensus.strip())

    if len(consensuses) > 1:
        core = ' '.join(consensuses[:2])
    elif consensuses:
        core = consensuses[0]
    else:
        core = None

    return VisualSummary(
        title=title,
        subtitle=subtitle,
        sections=sections,
        footer=VisualFooter(
            contacts=_dedupe_ordered(all_contacts),
            next_steps=_dedupe_ordered(all_steps),
            core_consensus=core,
        ),
    )


def visual_summary_to_dict(summary: VisualSummary) -> dict[str, Any]:
    return summary.model_dump()


def visual_summary_to_json(summary: VisualSummary) -> str:
    return json.dumps(summary.model_dump(), ensure_ascii=False)


async def parse_visual_summary_with_repair(
    raw: str,
    repair_fn: Callable[[str], Any] | None = None,
) -> VisualSummary:
    """解析 JSON，失败时可选调用 repair_fn 修复后再解析"""
    try:
        visual = parse_visual_summary(raw)
    except (json.JSONDecodeError, ValueError, ValidationError) as first_error:
        if not repair_fn:
            raise first_error
        repaired_raw = await repair_fn(raw)
        visual = parse_visual_summary(repaired_raw)
    return normalize_visual_summary(visual)
