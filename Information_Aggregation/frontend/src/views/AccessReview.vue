<template>
  <div class="page-card">
    <el-card v-if="applyTypes.length" shadow="never" class="section">
      <template #header>申请平台权限</template>
      <p class="tip">所有模块的权限均在 xling 平台统一申请与审批，审批通过后请重新登录生效。</p>
      <el-form label-width="120px">
        <el-form-item label="申请类型">
          <el-select v-model="applyType" style="width: 100%">
            <el-option
              v-for="item in applyTypes"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="申请理由">
          <el-input v-model="applyReason" type="textarea" :rows="3" placeholder="可选" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="applying" @click="handleApply">提交申请</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="header-row">
          <span>我的申请记录</span>
          <el-tag v-if="stats.my_pending > 0" type="warning" size="small">
            {{ stats.my_pending }} 条待审核
          </el-tag>
        </div>
      </template>
      <el-table v-loading="myLoading" :data="myRequests" stripe empty-text="暂无申请记录">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="类型" width="180">
          <template #default="{ row }">
            {{ row.request_type_label || REQUEST_TYPE_LABELS[row.request_type] || row.request_type }}
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="申请理由" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="申请时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="审批人" width="120">
          <template #default="{ row }">
            {{ row.reviewer_nickname || row.reviewer_username || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="reviewed_at" label="审批时间" width="170">
          <template #default="{ row }">{{ row.reviewed_at ? formatTime(row.reviewed_at) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="review_note" label="审批备注" min-width="140" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card v-if="canReview" shadow="never" class="section">
      <template #header>权限策略</template>
      <el-form inline>
        <el-form-item label="屏蔽上级任务">
          <el-switch
            v-model="settings.block_upper_role_tasks"
            active-text="普通用户不可查看管理员及以上任务"
            @change="saveSettings"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="canReview" shadow="never" class="section">
      <template #header>
        <div class="header-row">
          <span>权限申请审批</span>
          <div class="filters">
            <el-tag v-if="stats.pending_for_review > 0" type="danger" size="small">
              {{ stats.pending_for_review }} 条待处理
            </el-tag>
            <el-select
              v-model="typeFilter"
              clearable
              placeholder="申请类型"
              style="width: 180px"
              @change="loadReviewData"
            >
              <el-option
                v-for="(label, key) in REQUEST_TYPE_LABELS"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
            <el-radio-group v-model="statusFilter" size="small" @change="loadReviewData">
              <el-radio-button label="pending">待审核</el-radio-button>
              <el-radio-button label="approved">已通过</el-radio-button>
              <el-radio-button label="rejected">已拒绝</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <el-table v-loading="reviewLoading" :data="reviewList" stripe empty-text="暂无审批记录">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="类型" width="180">
          <template #default="{ row }">
            {{ row.request_type_label || REQUEST_TYPE_LABELS[row.request_type] || row.request_type }}
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" width="130">
          <template #default="{ row }">{{ row.username || '—' }}</template>
        </el-table-column>
        <el-table-column prop="nickname" label="昵称" width="120">
          <template #default="{ row }">{{ row.nickname || '—' }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="申请理由" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="申请时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="审批人" width="120">
          <template #default="{ row }">
            {{ row.reviewer_nickname || row.reviewer_username || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="reviewed_at" label="审批时间" width="170">
          <template #default="{ row }">{{ row.reviewed_at ? formatTime(row.reviewed_at) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="review_note" label="审批备注" min-width="140" show-overflow-tooltip />
        <el-table-column v-if="statusFilter === 'pending'" label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" @click="handleReview(row, true)">通过</el-button>
            <el-button link type="danger" @click="handleReview(row, false)">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import {
  getAccessRequestStats,
  getAccessRequests,
  getApplicableRequestTypes,
  getPermissionSettings,
  REQUEST_TYPE_LABELS,
  reviewAccessRequest,
  submitAccessRequest,
  updatePermissionSettings,
  type AccessRequest,
  type AccessRequestStats,
  type RequestTypeOption,
} from '@/api/permissions'
import { useUserStore } from '@/stores/user'
import { canReviewAccess } from '@/utils/permission'

const NOTIFY_KEY = 'xling_perm_result_notified'

const userStore = useUserStore()
const applying = ref(false)
const myLoading = ref(false)
const reviewLoading = ref(false)
const myRequests = ref<AccessRequest[]>([])
const reviewList = ref<AccessRequest[]>([])
const statusFilter = ref('pending')
const typeFilter = ref<string | undefined>()
const applyReason = ref('')
const applyType = ref('')
const applyTypes = ref<RequestTypeOption[]>([])
const settings = ref({ block_upper_role_tasks: true })
const stats = ref<AccessRequestStats>({
  my_pending: 0,
  my_total: 0,
  pending_for_review: 0,
  can_review: false,
})

const canReview = computed(() => canReviewAccess(userStore.userInfo?.role))

function formatTime(v: string) {
  return v?.replace('T', ' ').slice(0, 19)
}

function statusLabel(s: string) {
  return { pending: '待审核', approved: '已通过', rejected: '已拒绝' }[s] || s
}

function statusType(s: string) {
  return ({ pending: 'warning', approved: 'success', rejected: 'info' } as const)[s] || 'info'
}

function loadNotifiedIds(): Set<number> {
  try {
    const raw = sessionStorage.getItem(NOTIFY_KEY)
    return new Set(raw ? JSON.parse(raw) : [])
  } catch {
    return new Set()
  }
}

function saveNotifiedIds(ids: Set<number>) {
  sessionStorage.setItem(NOTIFY_KEY, JSON.stringify([...ids].slice(-100)))
}

function notifyReviewResults(items: AccessRequest[]) {
  const notified = loadNotifiedIds()
  for (const row of items) {
    if (row.status === 'pending' || notified.has(row.id)) continue
    const typeLabel =
      row.request_type_label || REQUEST_TYPE_LABELS[row.request_type] || row.request_type
    const result = row.status === 'approved' ? '已通过' : '已拒绝'
    ElNotification({
      title: '权限申请已有结果',
      message: `您的「${typeLabel}」申请${result}${row.review_note ? `：${row.review_note}` : ''}`,
      type: row.status === 'approved' ? 'success' : 'warning',
      duration: 8000,
    })
    notified.add(row.id)
  }
  saveNotifiedIds(notified)
}

function notifyPendingForReviewer(count: number) {
  if (!canReview.value || count <= 0) return
  ElNotification({
    title: '权限申请待审批',
    message: `您有 ${count} 条权限申请待处理，请及时审批。`,
    type: 'warning',
    duration: 6000,
  })
}

async function loadStats() {
  const res = await getAccessRequestStats()
  stats.value = res.data
  return res.data
}

async function loadSettings() {
  const res = await getPermissionSettings()
  settings.value = res.data
}

async function loadApplyTypes() {
  const res = await getApplicableRequestTypes()
  applyTypes.value = res.data
  if (res.data.length && !applyType.value) {
    applyType.value = res.data[0].value
  }
}

async function loadMyRequests() {
  myLoading.value = true
  try {
    const res = await getAccessRequests({
      scope: 'mine',
      page: 1,
      page_size: 50,
    })
    myRequests.value = res.data.items
    notifyReviewResults(res.data.items)
  } finally {
    myLoading.value = false
  }
}

async function loadReviewData() {
  if (!canReview.value) return
  reviewLoading.value = true
  try {
    const res = await getAccessRequests({
      scope: 'review',
      status: statusFilter.value,
      request_type: typeFilter.value,
      page: 1,
      page_size: 50,
    })
    reviewList.value = res.data.items
  } finally {
    reviewLoading.value = false
  }
}

async function refreshAll(notifyReviewer = false) {
  const data = await loadStats()
  await loadMyRequests()
  if (canReview.value) {
    await loadReviewData()
    if (notifyReviewer && data.pending_for_review > 0) {
      notifyPendingForReviewer(data.pending_for_review)
    }
  }
}

async function handleApply() {
  if (!applyType.value) {
    ElMessage.warning('请选择申请类型')
    return
  }
  applying.value = true
  try {
    await submitAccessRequest(applyType.value, applyReason.value || undefined)
    ElMessage.success('申请已提交，请留意「我的申请记录」与消息提醒')
    applyReason.value = ''
    await loadApplyTypes()
    await refreshAll(false)
    ElNotification({
      title: '申请已提交',
      message: '管理员审批后将在此页面通知您，审批通过后请重新登录。',
      type: 'info',
      duration: 6000,
    })
  } finally {
    applying.value = false
  }
}

async function handleReview(row: AccessRequest, approve: boolean) {
  const applicant = row.username || row.nickname || `用户#${row.user_id}`
  const typeLabel = row.request_type_label || REQUEST_TYPE_LABELS[row.request_type] || row.request_type
  const action = approve ? '通过' : '拒绝'
  let reviewNote: string | undefined
  try {
    const { value } = await ElMessageBox.prompt(
      `确定${action}用户「${applicant}」的「${typeLabel}」申请？`,
      '权限审批',
      {
        type: approve ? 'success' : 'warning',
        confirmButtonText: action,
        cancelButtonText: '取消',
        inputPlaceholder: '审批备注（可选）',
        inputValue: '',
      }
    )
    reviewNote = value || undefined
  } catch {
    return
  }
  await reviewAccessRequest(row.id, approve, reviewNote)
  ElMessage.success(approve ? '已通过，申请人将在「我的申请记录」中看到结果' : '已拒绝')
  await refreshAll(false)
}

async function saveSettings() {
  await updatePermissionSettings(settings.value.block_upper_role_tasks)
  ElMessage.success('策略已更新')
}

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await userStore.fetchUserInfo()
  await loadApplyTypes()
  if (canReview.value) {
    await loadSettings()
  }
  await refreshAll(true)
  pollTimer = setInterval(() => {
    refreshAll(false).catch(() => {})
  }, 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.section {
  margin-bottom: 16px;
}

.tip {
  color: #606266;
  font-size: 13px;
  margin: 0 0 12px;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.filters {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
