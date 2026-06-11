<template>
  <div v-if="!sections.length" class="visual-empty">
    <template v-if="status === 'failed'">图文速览生成失败，请查看文字速览。</template>
    <template v-else>暂无图文速览</template>
  </div>
  <div v-else class="visual-summary">
    <h3 v-if="visual?.title" class="visual-summary__title">{{ visual.title }}</h3>
    <p v-if="visual?.subtitle" class="visual-summary__subtitle">{{ visual.subtitle }}</p>

    <el-alert
      v-if="visual?.footer?.core_consensus"
      type="success"
      :closable="false"
      show-icon
      title="核心共识"
      class="visual-summary__consensus"
    >
      {{ visual.footer.core_consensus }}
    </el-alert>

    <section
      v-for="(sec, idx) in sections"
      :key="sec.id || idx"
      class="visual-section"
      :class="`visual-section--${sec.theme || 'green'}`"
    >
      <div class="visual-section__head">
        <span class="visual-section__num">{{ sec.id || String(idx + 1).padStart(2, '0') }}</span>
        <span class="visual-section__title">{{ sec.title }}</span>
      </div>
      <el-row :gutter="12">
        <el-col
          v-for="(card, cardIdx) in sec.cards"
          :key="cardIdx"
          :xs="24"
          :sm="layoutSpan(sec.layout)"
        >
          <el-card shadow="never" class="visual-card">
            <div class="visual-card__head">
              <span class="visual-card__icon">{{ iconOf(card.icon) }}</span>
              <strong>{{ card.title }}</strong>
              <el-tag v-if="card.tag" size="small" type="warning">{{ card.tag }}</el-tag>
            </div>
            <ul v-if="card.bullets?.length" class="visual-card__bullets">
              <li v-for="(bullet, bi) in card.bullets" :key="bi">{{ bullet }}</li>
            </ul>
            <div v-if="card.highlight" class="visual-card__highlight">{{ card.highlight }}</div>
          </el-card>
        </el-col>
      </el-row>
    </section>

    <el-card v-if="visual?.footer?.contacts?.length" shadow="never" class="visual-footer">
      <template #header>联系人</template>
      <ul class="visual-card__bullets">
        <li v-for="(item, i) in visual.footer.contacts" :key="i">{{ item }}</li>
      </ul>
    </el-card>

    <el-card v-if="visual?.footer?.next_steps?.length" shadow="never" class="visual-footer">
      <template #header>下一步</template>
      <ul class="visual-card__bullets">
        <li v-for="(item, i) in visual.footer.next_steps" :key="i">{{ item }}</li>
      </ul>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { VisualSummary, VisualSummaryCard, VisualSummarySection } from '@/api/meetings'

const props = defineProps<{
  visual: VisualSummary | null
  status?: string | null
}>()

const ICONS: Record<string, string> = {
  doc: '📄',
  chart: '📊',
  people: '👥',
  target: '🎯',
  warn: '⚠️',
  check: '✅',
  idea: '💡',
  clock: '⏰',
}

const sections = computed(() => {
  const raw = props.visual?.sections || []
  return raw
    .map((sec) => ({
      ...sec,
      cards: (sec.cards || []).filter(
        (card: VisualSummaryCard) =>
          (card.title || '').trim() ||
          (card.bullets || []).length ||
          (card.highlight || '').trim()
      ),
    }))
    .filter((sec: VisualSummarySection) => sec.cards?.length)
})

function iconOf(name?: string) {
  return ICONS[name || 'doc'] || '📄'
}

function layoutSpan(layout?: string) {
  if (layout === 'grid-2') return 12
  if (layout === 'grid-4') return 6
  if (layout === 'full') return 24
  return 8
}
</script>

<style scoped>
.visual-empty {
  color: #909399;
  text-align: center;
  padding: 24px;
}
.visual-summary__title {
  margin: 0 0 8px;
  font-size: 20px;
  color: #303133;
}
.visual-summary__subtitle {
  margin: 0 0 16px;
  color: #606266;
}
.visual-summary__consensus {
  margin-bottom: 16px;
}
.visual-section {
  margin-bottom: 20px;
  padding: 16px;
  border-radius: 8px;
  background: #f5f7fa;
}
.visual-section--green { border-left: 4px solid #67c23a; }
.visual-section--orange { border-left: 4px solid #e6a23c; }
.visual-section--blue { border-left: 4px solid #409eff; }
.visual-section--pink { border-left: 4px solid #f56c6c; }
.visual-section--teal { border-left: 4px solid #13c2c2; }
.visual-section--brown { border-left: 4px solid #8d6e63; }
.visual-section--purple { border-left: 4px solid #9c27b0; }
.visual-section--red { border-left: 4px solid #f44336; }
.visual-section__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.visual-section__num {
  font-weight: 700;
  color: #409eff;
}
.visual-section__title {
  font-size: 16px;
  font-weight: 600;
}
.visual-card {
  margin-bottom: 12px;
  height: 100%;
}
.visual-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.visual-card__icon {
  font-size: 18px;
}
.visual-card__bullets {
  margin: 0;
  padding-left: 20px;
  color: #606266;
  line-height: 1.7;
}
.visual-card__highlight {
  margin-top: 8px;
  padding: 8px 10px;
  background: #ecf5ff;
  border-radius: 6px;
  color: #409eff;
  font-size: 13px;
}
.visual-footer {
  margin-top: 12px;
}
</style>
