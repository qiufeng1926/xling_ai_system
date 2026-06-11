"""将图文速览 JSON 导出为可离线打开的 HTML 文件"""
import html
import json
import re
from datetime import datetime
from typing import Any

VISUAL_ICONS = {
    'doc': '📄', 'trophy': '🏆', 'people': '👥', 'policy': '📋', 'chat': '💬',
    'star': '⭐', 'calendar': '📅', 'money': '💰', 'check': '✅', 'warn': '⚠️',
    'idea': '💡', 'target': '🎯', 'handshake': '🤝', 'chart': '📊', 'time': '⏱️',
}

TAG_CSS = {
    '重点': 'tag-focus',
    '待跟进': 'tag-todo',
    '已决策': 'tag-done',
    '风险': 'tag-risk',
    '待确认': 'tag-pending',
}

_EXPORT_CSS = """
body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; background: #f0f2f5; margin: 0; padding: 24px; color: #333; }
.wrap { max-width: 960px; margin: 0 auto; }
.page-title { font-size: 26px; font-weight: bold; margin-bottom: 6px; }
.page-subtitle { color: #888; font-size: 14px; margin-bottom: 8px; }
.meta { color: #aaa; font-size: 12px; margin-bottom: 24px; }
.visual-summary-root { background: #f5f6fa; border-radius: 12px; padding: 20px; }
.visual-section { margin-bottom: 28px; }
.visual-section-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.visual-section-num { width: 36px; height: 36px; border-radius: 8px; color: white; font-weight: bold; display: flex; align-items: center; justify-content: center; font-size: 14px; }
.visual-section-title { font-size: 17px; font-weight: bold; }
.visual-cards { display: grid; gap: 12px; }
.layout-grid-2 { grid-template-columns: repeat(2, 1fr); }
.layout-grid-3 { grid-template-columns: repeat(3, 1fr); }
.layout-grid-4 { grid-template-columns: repeat(4, 1fr); }
.layout-full { grid-template-columns: 1fr; }
.visual-card { background: white; border-radius: 10px; padding: 14px; border: 1px solid #eee; }
.visual-card-head { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 10px; }
.visual-card-title { font-weight: bold; font-size: 15px; flex: 1; }
.visual-card-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #f0f0f0; color: #666; }
.visual-card-bullets { margin: 0 0 10px 0; padding-left: 18px; color: #555; font-size: 13px; line-height: 1.6; }
.visual-card-highlight { font-size: 12px; padding: 8px 10px; border-radius: 6px; margin-top: 8px; }
.visual-footer-block { background: white; border-radius: 10px; padding: 16px; margin-top: 12px; border: 1px solid #eee; }
.visual-footer-block h4 { margin: 0 0 10px 0; color: #667eea; font-size: 15px; }
.visual-consensus-banner { background: linear-gradient(135deg, #667eea15, #764ba215); border-left: 4px solid #667eea; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; }
.visual-consensus-banner h4 { margin: 0 0 8px 0; color: #667eea; font-size: 15px; }
.visual-card-tag.tag-focus { background: #fff3e0; color: #e65100; }
.visual-card-tag.tag-todo { background: #e3f2fd; color: #1565c0; }
.visual-card-tag.tag-done { background: #e8f5e9; color: #2e7d32; }
.visual-card-tag.tag-risk { background: #ffebee; color: #c62828; }
.visual-card-tag.tag-pending { background: #f3e5f5; color: #7b1fa2; }
.disclaimer { font-size: 12px; color: #999; text-align: center; margin-top: 20px; }
.theme-green .visual-section-num { background: #27ae60; }
.theme-green .visual-card-highlight { background: #e8f8ef; color: #27ae60; }
.theme-orange .visual-section-num { background: #e67e22; }
.theme-orange .visual-card-highlight { background: #fef5e7; color: #e67e22; }
.theme-blue .visual-section-num { background: #3498db; }
.theme-blue .visual-card-highlight { background: #ebf5fb; color: #3498db; }
.theme-pink .visual-section-num { background: #e91e63; }
.theme-pink .visual-card-highlight { background: #fce4ec; color: #e91e63; }
.theme-teal .visual-section-num { background: #16a085; }
.theme-teal .visual-card-highlight { background: #e8f6f3; color: #16a085; }
.theme-brown .visual-section-num { background: #795548; }
.theme-brown .visual-card-highlight { background: #efebe9; color: #795548; }
.theme-purple .visual-section-num { background: #9b59b6; }
.theme-purple .visual-card-highlight { background: #f4ecf7; color: #9b59b6; }
.theme-red .visual-section-num { background: #e74c3c; }
.theme-red .visual-card-highlight { background: #fdedec; color: #e74c3c; }
@media print { body { background: white; } .wrap { max-width: none; } }
@media (max-width: 720px) {
  .layout-grid-3, .layout-grid-4 { grid-template-columns: repeat(2, 1fr); }
  .layout-grid-2 { grid-template-columns: 1fr; }
}
"""


def _esc(text: str | None) -> str:
    return html.escape(text or '', quote=True)


def _layout_class(layout: str | None) -> str:
    if layout in ('grid-2', 'grid-3', 'grid-4', 'full'):
        return f'layout-{layout}'
    return 'layout-grid-3'


def _tag_class(tag: str | None) -> str:
    if not tag:
        return 'visual-card-tag'
    return 'visual-card-tag ' + TAG_CSS.get(tag, '')


def _render_body_html(visual: dict[str, Any]) -> str:
    parts: list[str] = []
    title = visual.get('title')
    subtitle = visual.get('subtitle')
    if title:
        parts.append(f'<div class="page-title">{_esc(title)}</div>')
    if subtitle:
        parts.append(f'<div class="page-subtitle">{_esc(subtitle)}</div>')

    footer = visual.get('footer') or {}
    if footer.get('core_consensus'):
        parts.append('<div class="visual-consensus-banner">')
        parts.append('<h4>核心共识</h4>')
        parts.append(f'<p style="margin:0;line-height:1.7;color:#444;">{_esc(footer.get("core_consensus"))}</p>')
        parts.append('</div>')

    parts.append('<div class="visual-summary-root">')
    for idx, sec in enumerate(visual.get('sections') or []):
        theme = sec.get('theme') or 'green'
        if theme not in ('green', 'orange', 'blue', 'pink', 'teal', 'brown', 'purple', 'red'):
            theme = 'green'
        sec_id = sec.get('id') or str(idx + 1).zfill(2)
        layout = _layout_class(sec.get('layout'))
        parts.append(f'<div class="visual-section theme-{theme}">')
        parts.append('<div class="visual-section-head">')
        parts.append(f'<div class="visual-section-num">{_esc(str(sec_id))}</div>')
        parts.append(f'<div class="visual-section-title">{_esc(sec.get("title"))}</div>')
        parts.append('</div>')
        parts.append(f'<div class="visual-cards {layout}">')
        for card in sec.get('cards') or []:
            icon = VISUAL_ICONS.get(card.get('icon') or '', '📄')
            parts.append('<div class="visual-card">')
            parts.append('<div class="visual-card-head">')
            parts.append(f'<span>{icon}</span>')
            parts.append(f'<span class="visual-card-title">{_esc(card.get("title"))}</span>')
            if card.get('tag'):
                parts.append(f'<span class="{_tag_class(card.get("tag"))}">{_esc(card.get("tag"))}</span>')
            parts.append('</div>')
            bullets = card.get('bullets') or []
            if bullets:
                parts.append('<ul class="visual-card-bullets">')
                for b in bullets:
                    parts.append(f'<li>{_esc(b)}</li>')
                parts.append('</ul>')
            if card.get('highlight'):
                parts.append(f'<div class="visual-card-highlight">{_esc(card.get("highlight"))}</div>')
            parts.append('</div>')
        parts.append('</div></div>')

    footer = visual.get('footer') or {}
    if footer.get('contacts'):
        parts.append('<div class="visual-footer-block"><h4>联系人</h4><ul class="visual-card-bullets">')
        for c in footer['contacts']:
            parts.append(f'<li>{_esc(c)}</li>')
        parts.append('</ul></div>')
    if footer.get('next_steps'):
        parts.append('<div class="visual-footer-block"><h4>下一步</h4><ul class="visual-card-bullets">')
        for s in footer['next_steps']:
            parts.append(f'<li>{_esc(s)}</li>')
        parts.append('</ul></div>')
    parts.append('</div>')
    return '\n'.join(parts)


def visual_summary_to_html(visual: dict[str, Any], page_title: str | None = None) -> str:
    """生成完整 HTML 文档字符串"""
    doc_title = _esc(page_title or visual.get('title') or '图文速览')
    exported_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    body = _render_body_html(visual)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{doc_title}</title>
<style>{_EXPORT_CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<p class="meta">导出时间：{exported_at}</p>
<p class="disclaimer">图文内容由 AI 根据会议转写整理，如有出入以转写原文为准。</p>
</div>
</body>
</html>"""


def visual_summary_to_json_bytes(visual: dict[str, Any]) -> bytes:
    return json.dumps(visual, ensure_ascii=False, indent=2).encode('utf-8')


def build_visual_export_filename(title: str, file_id: str | None = None, ext: str = 'html') -> str:
    safe = re.sub(r'[\\/:*?"<>|]', '_', title).strip() or '图文速览'
    if len(safe) > 50:
        safe = safe[:50]
    suffix = f'_{file_id[:8]}' if file_id else ''
    return f'{safe}{suffix}_图文.{ext}'
