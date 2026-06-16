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
      <el-card shadow="never" class="meeting-detail__section">
        <template #header>转写文本</template>
        <el-scrollbar max-height="420px">
          <pre class="meeting-detail__transcript">{{ detail.transcript || '暂无转写内容' }}</pre>
        </el-scrollbar>
      </el-card>

      <el-card
        v-if="detail.summary || detail.summary_visual"
        shadow="never"
        class="meeting-detail__section"
      >
        <template #header>
          <div class="meeting-detail__summary-head">
            <span>AI 智能速览</span>
            <el-radio-group v-model="summaryTab" size="small">
              <el-radio-button value="markdown">文字速览</el-radio-button>
              <el-radio-button value="visual" :disabled="!detail.summary_visual">图文速览</el-radio-button>
            </el-radio-group>
          </div>
        </template>

        <el-scrollbar v-if="summaryTab === 'markdown'" max-height="520px">
          <pre class="meeting-detail__summary">{{ detail.summary || '暂无文字速览' }}</pre>
        </el-scrollbar>
        <MeetingVisualSummary
          v-else
          :visual="detail.summary_visual"
          :status="detail.summary_visual_status"
        />
        <p class="meeting-detail__disclaimer">图文内容由 AI 根据转写整理，如有出入以转写原文为准。</p>
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
import MeetingVisualSummary from '@/components/MeetingVisualSummary.vue'
import { MEETING_ROUTES } from '@/constants/routes'
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
const summaryTab = ref<'markdown' | 'visual'>('markdown')

const fileId = computed(() => String(route.params.fileId || ''))

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
    summaryTab.value = res.summary ? 'markdown' : 'visual'
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
.meeting-detail__section {
  margin-bottom: 16px;
}
.meeting-detail__summary-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.meeting-detail__transcript,
.meeting-detail__summary {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
  font-family: inherit;
  color: #303133;
}
.meeting-detail__disclaimer {
  margin: 12px 0 0;
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
