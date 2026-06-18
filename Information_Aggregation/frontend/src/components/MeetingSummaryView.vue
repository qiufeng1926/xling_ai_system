<template>
  <div v-if="!hasContent" class="summary-empty">暂无文字速览</div>
  <article v-else class="summary-view">
    <header v-if="metaItems.length" class="summary-view__meta">
      <div v-for="item in metaItems" :key="item.label" class="summary-view__meta-item">
        <span class="summary-view__meta-label">{{ item.label }}</span>
        <span class="summary-view__meta-value">{{ item.value }}</span>
      </div>
    </header>

    <template v-for="(block, index) in parsed.blocks" :key="index">
      <p v-if="block.type === 'paragraph'" class="summary-view__lead">{{ block.text }}</p>
      <h2 v-else-if="block.type === 'h2'" class="summary-view__h2">{{ block.text }}</h2>
      <h3 v-else-if="block.type === 'h3'" class="summary-view__h3">{{ block.text }}</h3>
      <ul v-else-if="block.type === 'ul'" class="summary-view__list">
        <li v-for="(item, li) in block.items" :key="li">{{ item }}</li>
      </ul>
    </template>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { parseSummary } from '@/utils/meetingContent'

const props = defineProps<{
  summary: string | null | undefined
}>()

const parsed = computed(() => parseSummary(props.summary || ''))

const metaItems = computed(() => {
  const items: Array<{ label: string; value: string }> = []
  if (parsed.value.meta.topic) items.push({ label: '主题', value: parsed.value.meta.topic })
  if (parsed.value.meta.time) items.push({ label: '时间', value: parsed.value.meta.time })
  if (parsed.value.meta.participants) {
    items.push({ label: '参与人', value: parsed.value.meta.participants })
  }
  return items
})

const hasContent = computed(
  () => metaItems.value.length > 0 || parsed.value.blocks.length > 0
)
</script>

<style scoped>
.summary-view {
  padding: 4px 2px 8px;
  color: #303133;
}
.summary-view__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 16px;
  margin-bottom: 20px;
  padding: 14px 16px;
  border-radius: 10px;
  background: #f7f9fc;
  border: 1px solid #ebeef5;
}
.summary-view__meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.summary-view__meta-label {
  color: #909399;
  font-size: 12px;
}
.summary-view__meta-value {
  color: #303133;
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
}
.summary-view__lead {
  margin: 0 0 18px;
  color: #606266;
  font-size: 15px;
  line-height: 1.85;
}
.summary-view__h2 {
  margin: 22px 0 10px;
  color: #1f2d3d;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.4;
}
.summary-view__h2:first-child {
  margin-top: 0;
}
.summary-view__h3 {
  margin: 14px 0 8px;
  color: #34495e;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
}
.summary-view__list {
  margin: 0 0 12px;
  padding-left: 1.2em;
  color: #303133;
  font-size: 14px;
  line-height: 1.75;
}
.summary-view__list li + li {
  margin-top: 6px;
}
.summary-empty {
  padding: 24px 0;
  color: #909399;
  text-align: center;
}
</style>
