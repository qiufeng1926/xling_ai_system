<template>
  <div class="meeting-history">
    <div class="meeting-history__header">
      <div>
        <h2>会议记录</h2>
        <p class="meeting-history__desc">
          所有人可查看会议列表。浏览/下载他人会议需勾选后逐条向管理员申请；自己录制或参与的协作会议默认可浏览，自己录制的会议默认可下载。
        </p>
      </div>
      <div class="meeting-history__header-actions">
        <el-button
          v-if="viewSelectableCount > 0"
          type="primary"
          :disabled="!selectedViewIds.length"
          :loading="applyingView"
          @click="handleBatchApplyView"
        >
          申请浏览{{ selectedViewIds.length ? ` (${selectedViewIds.length})` : '' }}
        </el-button>
        <el-button
          v-if="downloadSelectableCount > 0"
          :disabled="!selectedDownloadIds.length"
          :loading="applyingDownload"
          @click="handleBatchApplyDownload"
        >
          申请下载{{ selectedDownloadIds.length ? ` (${selectedDownloadIds.length})` : '' }}
        </el-button>
        <el-button @click="router.push(MEETING_ROUTES.solo)">单人录制</el-button>
      </div>
    </div>

    <el-card shadow="never" class="meeting-history__filter">
      <el-form inline @submit.prevent="handleSearch">
        <el-form-item label="开始日期">
          <el-date-picker v-model="startDate" type="date" value-format="YYYY-MM-DD" placeholder="不限" clearable />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="endDate" type="date" value-format="YYYY-MM-DD" placeholder="不限" clearable />
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
          :class="{
            'meeting-history__item--locked': item.can_access === false,
            'meeting-history__item--selected':
              selectedViewIds.includes(item.file_id) || selectedDownloadIds.includes(item.file_id),
          }"
          @click="goDetail(item)"
        >
          <div class="meeting-history__checks" @click.stop>
            <el-checkbox
              v-if="isViewSelectable(item)"
              :model-value="selectedViewIds.includes(item.file_id)"
              @change="(val: boolean) => toggleViewSelect(item.file_id, val)"
            >
              浏览
            </el-checkbox>
            <el-checkbox
              v-if="isDownloadSelectable(item)"
              :model-value="selectedDownloadIds.includes(item.file_id)"
              @change="(val: boolean) => toggleDownloadSelect(item.file_id, val)"
            >
              下载
            </el-checkbox>
          </div>
          <div class="meeting-history__item-body">
            <div class="meeting-history__item-head">
              <div class="meeting-history__item-title">
                {{ displayName(item) }}
                <el-tag v-if="item.is_collaborative" size="small" type="primary">协作</el-tag>
                <el-tag v-if="item.meeting_type === 'realtime'" size="small">实时</el-tag>
                <el-tag v-else-if="item.meeting_type === 'batch'" size="small" type="info">批量</el-tag>
                <el-tag v-if="item.access_request_status === 'pending'" size="small" type="warning">浏览申请中</el-tag>
                <el-tag v-else-if="item.can_access === false" size="small" type="warning">需申请浏览</el-tag>
                <el-tag v-if="item.download_request_status === 'pending'" size="small" type="info">下载申请中</el-tag>
                <el-tag v-else-if="item.can_access && item.can_download === false" size="small" type="info">需申请下载</el-tag>
              </div>
              <span class="meeting-history__item-time">{{ formatTime(item.created_at) }}</span>
            </div>
            <div class="meeting-history__item-meta">
              <span v-if="item.transcript_length">文本 {{ item.transcript_length }} 字</span>
              <span v-if="item.has_summary">文字总结</span>
              <span v-if="item.has_visual_summary">图文速览</span>
              <span v-if="!item.has_summary && !item.has_visual_summary" class="muted">无总结</span>
            </div>
            <p class="meeting-history__item-preview">{{ previewMessage(item) }}</p>
          </div>
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
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  applyMeetingDownloadAccess,
  applyMeetingViewAccess,
  listMeetings,
  type MeetingListItem,
} from '@/api/meetings'
import { MEETING_ROUTES } from '@/constants/routes'

const router = useRouter()
const loading = ref(false)
const applyingView = ref(false)
const applyingDownload = ref(false)
const meetings = ref<MeetingListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const startDate = ref<string>()
const endDate = ref<string>()
const selectedViewIds = ref<string[]>([])
const selectedDownloadIds = ref<string[]>([])

const viewSelectableCount = computed(() => meetings.value.filter(isViewSelectable).length)
const downloadSelectableCount = computed(() => meetings.value.filter(isDownloadSelectable).length)

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

function isViewSelectable(item: MeetingListItem) {
  return item.can_access === false && item.access_request_status !== 'pending'
}

function isDownloadSelectable(item: MeetingListItem) {
  return (
    item.can_access === true &&
    item.can_download === false &&
    item.download_request_status !== 'pending'
  )
}

function previewMessage(item: MeetingListItem) {
  if (item.can_access === false) {
    if (item.access_request_status === 'pending') {
      return '已提交浏览申请，请等待超级管理员审批'
    }
    return '暂无浏览权限，可勾选「浏览」后申请'
  }
  if (item.can_download === false) {
    if (item.download_request_status === 'pending') {
      return '已提交下载申请，请等待管理员审批'
    }
    return previewText(item.preview) + '（可勾选「下载」申请导出权限）'
  }
  return previewText(item.preview)
}

function toggleViewSelect(fileId: string, checked: boolean) {
  if (checked) {
    if (!selectedViewIds.value.includes(fileId)) {
      selectedViewIds.value = [...selectedViewIds.value, fileId]
    }
  } else {
    selectedViewIds.value = selectedViewIds.value.filter((id) => id !== fileId)
  }
}

function toggleDownloadSelect(fileId: string, checked: boolean) {
  if (checked) {
    if (!selectedDownloadIds.value.includes(fileId)) {
      selectedDownloadIds.value = [...selectedDownloadIds.value, fileId]
    }
  } else {
    selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => id !== fileId)
  }
}

async function submitViewApply(fileIds: string[], reason?: string) {
  applyingView.value = true
  try {
    const res = await applyMeetingViewAccess(fileIds, reason)
    const skippedTip = res.skipped?.length ? `，${res.skipped.length} 条已跳过` : ''
    ElMessage.success(`${res.message || '申请已提交'}${skippedTip}`)
    selectedViewIds.value = selectedViewIds.value.filter((id) => !fileIds.includes(id))
    await loadData()
  } catch (err: any) {
    ElMessage.error(err?.message || '提交浏览申请失败')
  } finally {
    applyingView.value = false
  }
}

async function submitDownloadApply(fileIds: string[], reason?: string) {
  applyingDownload.value = true
  try {
    const res = await applyMeetingDownloadAccess(fileIds, reason)
    const skippedTip = res.skipped?.length ? `，${res.skipped.length} 条已跳过` : ''
    ElMessage.success(`${res.message || '申请已提交'}${skippedTip}`)
    selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => !fileIds.includes(id))
    await loadData()
  } catch (err: any) {
    ElMessage.error(err?.message || '提交下载申请失败')
  } finally {
    applyingDownload.value = false
  }
}

async function handleBatchApplyView() {
  if (!selectedViewIds.value.length) {
    ElMessage.warning('请先勾选需要申请浏览的会议')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `将为 ${selectedViewIds.value.length} 条会议分别提交浏览申请`,
      '批量申请浏览',
      {
        confirmButtonText: '提交申请',
        cancelButtonText: '取消',
        inputPlaceholder: '申请理由（可选）',
        inputType: 'textarea',
      }
    )
    await submitViewApply([...selectedViewIds.value], value || undefined)
  } catch {
    /* cancelled */
  }
}

async function handleBatchApplyDownload() {
  if (!selectedDownloadIds.value.length) {
    ElMessage.warning('请先勾选需要申请下载的会议')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `将为 ${selectedDownloadIds.value.length} 条会议分别提交下载申请`,
      '批量申请下载',
      {
        confirmButtonText: '提交申请',
        cancelButtonText: '取消',
        inputPlaceholder: '申请理由（可选）',
        inputType: 'textarea',
      }
    )
    await submitDownloadApply([...selectedDownloadIds.value], value || undefined)
  } catch {
    /* cancelled */
  }
}

async function applySingleView(item: MeetingListItem) {
  try {
    const { value } = await ElMessageBox.prompt(
      `申请浏览会议「${displayName(item)}」`,
      '申请浏览',
      {
        confirmButtonText: '提交申请',
        cancelButtonText: '取消',
        inputPlaceholder: '申请理由（可选）',
        inputType: 'textarea',
      }
    )
    await submitViewApply([item.file_id], value || undefined)
  } catch {
    /* cancelled */
  }
}

function goDetail(item: MeetingListItem) {
  if (item.can_access === false) {
    if (item.access_request_status === 'pending') {
      ElMessage.info('该会议浏览申请审批中，请耐心等待')
      return
    }
    applySingleView(item)
    return
  }
  router.push(MEETING_ROUTES.recordDetail(item.file_id))
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
    const visibleIds = new Set(meetings.value.map((item) => item.file_id))
    selectedViewIds.value = selectedViewIds.value.filter((id) => visibleIds.has(id))
    selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => visibleIds.has(id))
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

onMounted(loadData)
</script>

<style scoped>
.meeting-history__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.meeting-history__header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.meeting-history__checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
  min-width: 72px;
}
.meeting-history__item-body {
  flex: 1;
  min-width: 0;
}
.meeting-history__item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.meeting-history__item--locked {
  opacity: 0.96;
}
.meeting-history__item--locked .meeting-history__item-title {
  color: #909399;
}
.meeting-history__item--selected {
  border-color: #409eff;
  background: #f5f9ff;
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
