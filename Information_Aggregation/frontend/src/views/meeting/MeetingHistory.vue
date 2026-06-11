<template>
  <div class="meeting-history">
    <div class="meeting-history__header">
      <div>
        <h2>会议记录</h2>
        <p class="meeting-history__desc">查看实时转写、批量上传与协作会议的历史记录与 AI 总结。</p>
      </div>
      <el-button @click="router.push(MEETING_ROUTES.solo)">单人录制</el-button>
    </div>

    <el-card shadow="never" class="meeting-history__filter">
      <el-form inline @submit.prevent="handleSearch">
        <el-form-item label="开始日期">
          <el-date-picker
            v-model="startDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="不限"
            clearable
          />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker
            v-model="endDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="不限"
            clearable
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSearch">查询</el-button>
          <el-button @click="clearFilter">清除</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-loading="loading" shadow="never">
      <el-empty v-if="!loading && !meetings.length" description="暂无会议记录" />

      <div v-else class="meeting-history__list">
        <div
          v-for="item in meetings"
          :key="item.file_id"
          class="meeting-history__item"
          @click="goDetail(item.file_id)"
        >
          <div class="meeting-history__item-head">
            <div class="meeting-history__item-title">
              {{ displayName(item) }}
              <el-tag v-if="item.is_collaborative" size="small" type="primary">协作</el-tag>
              <el-tag v-if="item.meeting_type === 'realtime'" size="small">实时</el-tag>
              <el-tag v-else-if="item.meeting_type === 'batch'" size="small" type="info">批量</el-tag>
            </div>
            <span class="meeting-history__item-time">{{ formatTime(item.created_at) }}</span>
          </div>
          <div class="meeting-history__item-meta">
            <span v-if="item.transcript_length">文本 {{ item.transcript_length }} 字</span>
            <span v-if="item.has_summary">文字总结</span>
            <span v-if="item.has_visual_summary">图文速览</span>
            <span v-if="!item.has_summary && !item.has_visual_summary" class="muted">无总结</span>
          </div>
          <p class="meeting-history__item-preview">{{ previewText(item.preview) }}</p>
        </div>
      </div>

      <div v-if="total > pageSize" class="meeting-history__pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadData"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listMeetings, type MeetingListItem } from '@/api/meetings'
import { MEETING_ROUTES } from '@/constants/routes'

const router = useRouter()
const loading = ref(false)
const meetings = ref<MeetingListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const startDate = ref<string>()
const endDate = ref<string>()

function displayName(item: MeetingListItem) {
  return item.meeting_name || item.original_filename || '未命名会议'
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function previewText(text: string) {
  const trimmed = (text || '').trim()
  if (!trimmed) return '暂无预览'
  return trimmed.length > 150 ? `${trimmed.slice(0, 150)}…` : trimmed
}

function goDetail(fileId: string) {
  router.push(MEETING_ROUTES.recordDetail(fileId))
}

async function loadData() {
  loading.value = true
  try {
    const res = await listMeetings({
      start_date: startDate.value,
      end_date: endDate.value,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    if (!res.success) {
      throw new Error(res.error || '加载失败')
    }
    meetings.value = res.meetings || []
    total.value = res.total || 0
  } catch (err: any) {
    ElMessage.error(err?.message || '加载会议记录失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadData()
}

function clearFilter() {
  startDate.value = undefined
  endDate.value = undefined
  handleSearch()
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.meeting-history__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.meeting-history__desc {
  margin: 4px 0 0;
  color: #909399;
  font-size: 14px;
}
.meeting-history__filter {
  margin-bottom: 16px;
}
.meeting-history__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.meeting-history__item {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.meeting-history__item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.meeting-history__item-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 8px;
}
.meeting-history__item-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #409eff;
}
.meeting-history__item-time {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
}
.meeting-history__item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #606266;
  font-size: 13px;
  margin-bottom: 8px;
}
.meeting-history__item-meta .muted {
  color: #c0c4cc;
}
.meeting-history__item-preview {
  margin: 0;
  padding: 8px 10px;
  background: #f5f7fa;
  border-radius: 6px;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}
.meeting-history__pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
