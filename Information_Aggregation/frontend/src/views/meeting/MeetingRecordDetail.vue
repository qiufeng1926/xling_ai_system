<template>
  <div v-loading="loading" class="meeting-detail">
    <div class="meeting-detail__toolbar">
      <el-button @click="router.push(MEETING_ROUTES.records)">← 返回列表</el-button>
      <div class="meeting-detail__actions">
        <el-button
          v-if="canDownload"
          :loading="exportingSummary"
          :disabled="!detail?.summary"
          @click="handleExportSummary"
        >
          导出 Word
        </el-button>
        <el-button
          v-if="canDownload"
          :loading="exportingVisual"
          :disabled="!detail?.summary_visual"
          @click="handleExportVisual"
        >
          下载图文
        </el-button>
        <el-button
          v-if="canDelete"
          type="danger"
          :loading="deleting"
          @click="handleDelete"
        >
          删除
        </el-button>
      </div>
    </div>

    <el-empty
      v-if="permissionDenied && !isSuperAdminUser"
      description="无权查看该会议内容"
    >
      <p class="meeting-detail__denied-tip">
        您只能浏览自己录制或参与的协作会议。查看他人会议请在会议记录列表中勾选并申请浏览权限。
      </p>
      <el-button type="primary" @click="router.push(MEETING_ROUTES.records)">返回会议记录</el-button>
    </el-empty>

    <template v-else-if="detail">
      <section class="meeting-detail__hero">
        <div>
          <h1 class="meeting-detail__title">{{ pageTitle }}</h1>
          <div class="meeting-detail__tags">
            <el-tag v-if="formattedCreatedAt" size="small" effect="plain">{{ formattedCreatedAt }}</el-tag>
            <el-tag v-if="detail.transcript_length" size="small" type="info" effect="plain">
              转写 {{ detail.transcript_length }} 字
            </el-tag>
            <el-tag v-if="detail.summary" size="small" type="success" effect="plain">已生成速览</el-tag>
          </div>
        </div>
      </section>

      <el-card shadow="never" class="meeting-detail__panel">
        <el-tabs v-model="activeTab" class="meeting-detail__tabs">
          <el-tab-pane v-if="detail.summary" label="智能速览" name="summary">
            <el-scrollbar max-height="620px">
              <MeetingSummaryView :summary="detail.summary" />
            </el-scrollbar>
          </el-tab-pane>

          <el-tab-pane label="转写原文" name="transcript">
            <el-scrollbar max-height="620px">
              <MeetingTranscriptView :transcript="detail.transcript" />
            </el-scrollbar>
          </el-tab-pane>

          <el-tab-pane
            v-if="detail.summary_visual"
            label="图文速览"
            name="visual"
          >
            <el-scrollbar max-height="620px">
              <MeetingVisualSummary
                :visual="detail.summary_visual"
                :status="detail.summary_visual_status"
              />
            </el-scrollbar>
          </el-tab-pane>
        </el-tabs>

        <p class="meeting-detail__disclaimer">内容由 AI 根据转写整理，如有出入以转写原文为准。</p>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteMeetingRecord,
  exportMeetingSummaryDocx,
  exportMeetingVisual,
  getMeetingDetail,
  type MeetingDetail,
} from '@/api/meetings'
import MeetingSummaryView from '@/components/MeetingSummaryView.vue'
import MeetingTranscriptView from '@/components/MeetingTranscriptView.vue'
import MeetingVisualSummary from '@/components/MeetingVisualSummary.vue'
import { MEETING_ROUTES } from '@/constants/routes'
import { parseSummary } from '@/utils/meetingContent'
import { useUserStore } from '@/stores/user'
import { isSuperAdmin } from '@/utils/permission'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const permissionDenied = ref(false)
const deleting = ref(false)
const exportingSummary = ref(false)
const exportingVisual = ref(false)
const detail = ref<MeetingDetail | null>(null)
const activeTab = ref('summary')

const fileId = computed(() => String(route.params.fileId || ''))

const pageTitle = computed(() => {
  const fromApi = detail.value?.meeting_name?.trim()
  if (fromApi) return fromApi
  const topic = parseSummary(detail.value?.summary || '').meta.topic
  return topic || '会议详情'
})

const formattedCreatedAt = computed(() => {
  const raw = detail.value?.created_at
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
})

const canDownload = computed(() => {
  if (isSuperAdmin(userStore.userInfo?.role)) return true
  if (detail.value?.can_download) return true
  return !!userStore.userInfo?.permissions?.download_meetings
})

const isSuperAdminUser = computed(() => isSuperAdmin(userStore.userInfo?.role))

const canDelete = computed(() => isSuperAdmin(userStore.userInfo?.role))

async function loadDetail() {
  loading.value = true
  permissionDenied.value = false
  try {
    const res = await getMeetingDetail(fileId.value)
    if (!res.success) {
      if (res.error?.includes('无权') && !isSuperAdminUser.value) {
        permissionDenied.value = true
        return
      }
      if (res.error?.includes('无权') && isSuperAdminUser.value) {
        throw new Error('暂无浏览权限（隐身超管等特殊会议）')
      }
      throw new Error(res.error || '加载失败')
    }
    detail.value = res
    activeTab.value = res.summary ? 'summary' : 'transcript'
  } catch (err: any) {
    ElMessage.error(err?.message || '加载会议详情失败')
    if (!permissionDenied.value) {
      router.push(MEETING_ROUTES.records)
    }
  } finally {
    loading.value = false
  }
}

async function handleExportSummary() {
  exportingSummary.value = true
  try {
    await exportMeetingSummaryDocx(fileId.value)
    ElMessage.success('导出成功')
  } catch (err: any) {
    ElMessage.error(err?.message || '导出失败')
  } finally {
    exportingSummary.value = false
  }
}

async function handleExportVisual() {
  exportingVisual.value = true
  try {
    await exportMeetingVisual(fileId.value, 'html')
    ElMessage.success('导出成功')
  } catch (err: any) {
    ElMessage.error(err?.message || '导出失败')
  } finally {
    exportingVisual.value = false
  }
}

async function handleDelete() {
  await ElMessageBox.confirm('确定删除该会议记录？此操作不可恢复。', '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  deleting.value = true
  try {
    await deleteMeetingRecord(fileId.value)
    ElMessage.success('已删除')
    router.push(MEETING_ROUTES.records)
  } catch (err: any) {
    ElMessage.error(err?.message || '删除失败')
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  if (!userStore.userInfo) {
    await userStore.fetchUserInfo().catch(() => {})
  }
  loadDetail()
})
</script>

<style scoped>
.meeting-detail {
  max-width: 980px;
  margin: 0 auto;
}
.meeting-detail__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.meeting-detail__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.meeting-detail__hero {
  margin-bottom: 16px;
}
.meeting-detail__title {
  margin: 0 0 10px;
  color: #1f2d3d;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.35;
}
.meeting-detail__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.meeting-detail__panel {
  border-radius: 12px;
}
.meeting-detail__tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.meeting-detail__disclaimer {
  margin: 12px 0 0;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
  color: #909399;
  font-size: 12px;
}
.meeting-detail__denied-tip {
  margin: 0 0 16px;
  max-width: 420px;
  color: #606266;
  font-size: 14px;
  line-height: 1.6;
}
</style>
