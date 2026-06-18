<template>
  <div v-if="!utterances.length" class="transcript-empty">暂无转写内容</div>
  <div v-else class="transcript-view">
    <div
      v-for="(item, index) in utterances"
      :key="index"
      class="transcript-view__item"
    >
      <div
        class="transcript-view__speaker"
        :style="{
          color: speakerStyle(item.colorIndex).text,
          background: speakerStyle(item.colorIndex).bg,
          borderColor: speakerStyle(item.colorIndex).border,
        }"
      >
        {{ item.speaker }}
      </div>
      <p class="transcript-view__text">{{ item.text }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { parseTranscript, speakerStyle } from '@/utils/meetingContent'

const props = defineProps<{
  transcript: string | null | undefined
}>()

const utterances = computed(() => parseTranscript(props.transcript || ''))
</script>

<style scoped>
.transcript-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px 8px;
}
.transcript-view__item {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 12px;
  align-items: start;
}
.transcript-view__speaker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 4px 8px;
  border: 1px solid;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
  text-align: center;
  word-break: break-all;
}
.transcript-view__text {
  margin: 2px 0 0;
  color: #303133;
  font-size: 14px;
  line-height: 1.75;
  word-break: break-word;
}
.transcript-empty {
  padding: 24px 0;
  color: #909399;
  text-align: center;
}
@media (max-width: 768px) {
  .transcript-view__item {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .transcript-view__speaker {
    justify-self: start;
  }
}
</style>
