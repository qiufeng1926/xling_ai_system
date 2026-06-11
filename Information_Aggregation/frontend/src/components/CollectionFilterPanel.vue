<template>
  <div v-loading="loading" class="filter-panel">
    <el-collapse v-model="activeGroups">
      <el-collapse-item
        v-for="group in groups"
        :key="group.key"
        :title="group.label"
        :name="group.key"
      >
        <div v-for="field in group.fields" :key="field.key" class="filter-row">
          <div class="filter-label">{{ field.label }}</div>
          <div class="filter-content">
            <template v-if="field.type === 'single'">
              <el-check-tag
                v-for="opt in field.options"
                :key="opt.value || '__all__'"
                :checked="getSingle(field.key) === opt.value"
                class="filter-tag"
                @change="(checked: boolean) => setSingle(field.key, opt.value, checked)"
              >
                {{ opt.label }}
              </el-check-tag>
            </template>

            <template v-else-if="field.type === 'multi'">
              <el-check-tag
                v-for="opt in field.options || []"
                :key="opt.value"
                :checked="getMulti(field.key).includes(opt.value)"
                class="filter-tag"
                @change="(checked: boolean) => toggleMulti(field.key, opt.value, checked)"
              >
                {{ opt.label }}
              </el-check-tag>
            </template>

            <template v-else-if="field.type === 'number'">
              <el-input-number
                :model-value="getNumber(field.key)"
                :min="field.min ?? 0"
                :max="field.max"
                :step="field.step ?? 1"
                :placeholder="field.placeholder || '不限'"
                controls-position="right"
                class="number-input"
                @update:model-value="(v: number | undefined) => setNumber(field.key, v)"
              />
              <span v-if="field.unit" class="unit">{{ field.unit }}</span>
            </template>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import request, { type ApiResponse } from '@/api/request'
import type { CollectionFilters, FilterGroup } from '@/constants/collectionFilters'

const props = defineProps<{
  modelValue: CollectionFilters
  platform?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: CollectionFilters]
}>()

const loading = ref(false)
const groups = ref<FilterGroup[]>([])
const activeGroups = ref<string[]>(['cooperation', 'creator', 'metrics', 'cost', 'theme', 'task'])

function getSingle(key: string): string {
  return (props.modelValue as Record<string, string | undefined>)[key] || ''
}

function setSingle(key: string, value: string, checked: boolean) {
  const next = { ...props.modelValue, [key]: checked ? value : undefined }
  if (!value) delete (next as Record<string, unknown>)[key]
  emit('update:modelValue', next)
}

function getMulti(key: string): string[] {
  return (props.modelValue as Record<string, string[] | undefined>)[key] || []
}

function toggleMulti(key: string, value: string, checked: boolean) {
  const current = [...getMulti(key)]
  const next = checked ? [...current, value] : current.filter((v) => v !== value)
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: next.length ? next : undefined,
  })
}

function getNumber(key: string): number | undefined {
  return (props.modelValue as Record<string, number | undefined>)[key]
}

function setNumber(key: string, value: number | undefined) {
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: value,
  })
}

async function loadOptions() {
  loading.value = true
  try {
    const res = await request.get<any, ApiResponse<{ groups: FilterGroup[] }>>(
      '/collection/filter-options',
      { params: { platform: props.platform || 'douyin' } }
    )
    groups.value = res.data.groups
    activeGroups.value = groups.value.map((g) => g.key)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.platform,
  () => {
    loadOptions()
  }
)

onMounted(loadOptions)
</script>

<style scoped>
.filter-panel {
  max-height: 58vh;
  overflow-y: auto;
  padding-right: 4px;
}

.filter-row {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
  align-items: flex-start;
}

.filter-label {
  width: 88px;
  flex-shrink: 0;
  color: #606266;
  font-size: 13px;
  line-height: 28px;
}

.filter-content {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.filter-tag {
  margin: 0;
}

.number-input {
  width: 160px;
}

.unit {
  color: #909399;
  font-size: 12px;
}

:deep(.el-collapse-item__header) {
  font-weight: 600;
  color: #303133;
}

:deep(.el-check-tag) {
  font-weight: normal;
}
</style>
