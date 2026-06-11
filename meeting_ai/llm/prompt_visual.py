"""
图文速览 Prompt：动态分区 + 卡片结构，仅基于转写
"""

SYSTEM_PROMPT_VISUAL = """
你是会议内容结构化助手，将口语化转写整理为图文卡片式 JSON，便于网页信息图展示。

工作原则：
1. 严格基于转写内容，禁止编造未出现的人名、机构、数字、决策
2. 信息不足时写「未提及」，不要猜测
3. 分区与卡片标题由本场会议内容自然决定，不要套用固定行业模板
4. 将口语整理为简洁书面语，删除语气词与重复
"""


def build_visual_prompt(transcript: str, meeting_name: str | None = None) -> str:
    title_hint = meeting_name.strip() if meeting_name else ''
    title_line = f'会议名称参考（若转写未体现可自拟简短标题）：{title_hint}' if title_hint else ''

    return f"""
请根据以下会议转写，生成「图文速览」JSON（用于网页卡片展示）。

{title_line}

【输出要求】
1. 只输出一个合法 JSON 对象，不要 Markdown、不要代码块标记、不要任何解释文字
2. 根据转写自然划分 3～8 个 section，每个 section 必须含 1～6 张 card（禁止只输出 section 标题而无 cards）
3. section.title 为本场自拟话题名；layout 取 grid-2 | grid-3 | grid-4 | full 之一
4. theme 取 green | orange | blue | pink | teal | brown | purple | red 之一，各 section 可不同
5. card 字段：title, icon（简短英文如 doc/trophy/people/policy/chat/money/calendar/star，无合适用 doc）, tag（可选，仅从：重点、待跟进、已决策、风险、待确认 中选）, bullets（必填，每条 card 至少 2 条要点字符串）, highlight（可选，一句收束）
6. 禁止把要点只写在 section.title 里；每个 section 的 cards 数组不能为空
7. footer：contacts（联系人/角色，无则 []）, next_steps（下一步，无则 []）, core_consensus（核心共识一段话，无则 null）
8. 禁止输出转写中未出现的事实

【JSON 结构】
{{
  "title": "会议主题",
  "subtitle": "可选副标题或会议类型",
  "sections": [
    {{
      "id": "1",
      "title": "分区标题",
      "theme": "green",
      "layout": "grid-3",
      "cards": [
        {{
          "title": "卡片标题",
          "icon": "doc",
          "tag": "重点",
          "bullets": ["要点1", "要点2"],
          "highlight": "可选总结句"
        }}
      ]
    }}
  ],
  "footer": {{
    "contacts": [],
    "next_steps": [],
    "core_consensus": null
  }}
}}

【转写内容】
{transcript}
"""


def build_visual_chunk_prompt(
    transcript: str,
    meeting_name: str | None,
    part_index: int,
    total_parts: int,
) -> str:
    title_hint = meeting_name.strip() if meeting_name else ''
    title_line = f'会议名称参考：{title_hint}' if title_hint else ''
    footer_rule = (
        'footer 中 contacts、next_steps 留空数组，core_consensus 为 null。'
        if part_index < total_parts
        else 'footer 可归纳本段出现的联系人、下一步与核心共识（仅本段已提及内容）。'
    )

    return f"""
请根据以下会议转写片段，生成「图文速览」JSON 的 sections 部分（共 {total_parts} 段之第 {part_index} 段）。

{title_line}
{footer_rule}
- 只输出一个合法 JSON 对象，不要 Markdown 或解释
- 本段转写能支撑几个话题就几个 section（1～4 个），不要编造
- 若 part_index 为 1，请填写合适的 title/subtitle；否则 title/subtitle 可与首段一致或简短占位
- section.id 可临时用 "1","2"，后续会统一编号

【JSON 结构】同标准图文速览（含 title, subtitle, sections, footer）

【本段转写】
{transcript}
"""
