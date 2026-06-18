export interface TranscriptUtterance {
  speaker: string
  text: string
  colorIndex: number
}

export interface SummaryMeta {
  topic?: string
  time?: string
  participants?: string
}

export type SummaryBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'h2'; text: string }
  | { type: 'h3'; text: string }
  | { type: 'ul'; items: string[] }

const SPEAKER_LINE_RE = /^\[(.+?)\]\s*(.*)$/
const META_RE = /^(主题|时间|参与人)\s*[:：]\s*(.+)$/

export function parseTranscript(raw: string): TranscriptUtterance[] {
  if (!raw?.trim()) return []

  const utterances: TranscriptUtterance[] = []
  const speakerIndex = new Map<string, number>()

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) continue

    const match = trimmed.match(SPEAKER_LINE_RE)
    if (match) {
      const speaker = match[1].trim()
      const text = match[2].trim()
      if (!speakerIndex.has(speaker)) {
        speakerIndex.set(speaker, speakerIndex.size)
      }
      utterances.push({
        speaker,
        text,
        colorIndex: speakerIndex.get(speaker) ?? 0,
      })
      continue
    }

    if (utterances.length) {
      const last = utterances[utterances.length - 1]
      last.text = last.text ? `${last.text} ${trimmed}` : trimmed
    } else {
      utterances.push({ speaker: '内容', text: trimmed, colorIndex: 0 })
    }
  }

  return utterances.filter((item) => item.text)
}

export function parseSummary(raw: string): { meta: SummaryMeta; blocks: SummaryBlock[] } {
  const meta: SummaryMeta = {}
  const blocks: SummaryBlock[] = []
  if (!raw?.trim()) return { meta, blocks }

  let paragraphLines: string[] = []
  let bulletItems: string[] = []

  const flushParagraph = () => {
    const text = paragraphLines.join(' ').trim()
    if (text) blocks.push({ type: 'paragraph', text })
    paragraphLines = []
  }

  const flushBullets = () => {
    if (bulletItems.length) blocks.push({ type: 'ul', items: [...bulletItems] })
    bulletItems = []
  }

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) {
      flushBullets()
      flushParagraph()
      continue
    }

    const metaMatch = trimmed.match(META_RE)
    if (metaMatch) {
      flushBullets()
      flushParagraph()
      const key = metaMatch[1]
      const value = metaMatch[2].trim()
      if (key === '主题') meta.topic = value
      if (key === '时间') meta.time = value
      if (key === '参与人') meta.participants = value
      continue
    }

    if (trimmed.startsWith('## ')) {
      flushBullets()
      flushParagraph()
      blocks.push({ type: 'h2', text: trimmed.slice(3).trim() })
      continue
    }

    if (trimmed.startsWith('### ')) {
      flushBullets()
      flushParagraph()
      blocks.push({ type: 'h3', text: trimmed.slice(4).trim() })
      continue
    }

    if (trimmed.startsWith('- ')) {
      flushParagraph()
      bulletItems.push(trimmed.slice(2).trim())
      continue
    }

    flushBullets()
    paragraphLines.push(trimmed)
  }

  flushBullets()
  flushParagraph()
  return { meta, blocks }
}

export const SPEAKER_COLORS = [
  { bg: '#eef5ff', border: '#b3d4ff', text: '#1d5fbf' },
  { bg: '#f0fdf4', border: '#a7f3d0', text: '#047857' },
  { bg: '#fff7ed', border: '#fed7aa', text: '#c2410c' },
  { bg: '#faf5ff', border: '#e9d5ff', text: '#7e22ce' },
  { bg: '#fef2f2', border: '#fecaca', text: '#b91c1c' },
  { bg: '#f0fdfa', border: '#99f6e4', text: '#0f766e' },
]

export function speakerStyle(colorIndex: number) {
  return SPEAKER_COLORS[colorIndex % SPEAKER_COLORS.length]
}
