<template>
  <div class="page-card">
    <el-card v-if="applyTypes.length" shadow="never" class="section">
      <template #header>申请平台权限</template>
      <p class="tip">所有模块的权限均在 xlink 平台统一申请与审批，审批通过后请重新登录生效。</p>
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
            <el-tag v-if="portalPendingForReview > 0" type="danger" size="small">
              {{ portalPendingForReview }} 条待处理
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
        <el-table-column v-if="isSuperAdminUser" label="管理" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDeletePortalRequest(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="canReviewMeetingViewPerm" shadow="never" class="section">
      <template #header>
        <div class="header-row">
          <span>会议浏览申请审批</span>
          <div class="filters">
            <el-tag v-if="meetingViewPendingCount > 0" type="danger" size="small">
              {{ meetingViewPendingCount }} 条待处理
            </el-tag>
            <el-radio-group v-model="meetingViewStatusFilter" size="small" @change="loadMeetingViewReviewData">
              <el-radio-button label="pending">待审核</el-radio-button>
              <el-radio-button label="approved">已通过</el-radio-button>
              <el-radio-button label="rejected">已拒绝</el-radio-button>
            </el-radio-group>
            <el-button
              size="small"
              type="success"
              :disabled="!selectedViewRequests.length"
              @click="handleBatchMeetingReview('view', true)"
            >
              批量通过 ({{ selectedViewRequests.length }})
            </el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="!selectedViewRequests.length"
              @click="handleBatchMeetingReview('view', false)"
            >
              批量拒绝
            </el-button>
          </div>
        </div>
      </template>
      <p class="tip">用户按单条会议申请浏览权限，通过后仅可查看对应会议内容。</p>
      <el-table
        v-loading="meetingViewReviewLoading"
        :data="meetingViewReviewList"
        stripe
        empty-text="暂无会议浏览申请"
        @selection-change="(rows: MeetingPermissionRequest[]) => (selectedViewRequests = rows)"
      >
        <el-table-column v-if="meetingViewStatusFilter === 'pending'" type="selection" width="48" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="meeting_name" label="会议" min-width="180" show-overflow-tooltip />
        <el-table-column prop="username" label="用户名" width="130" />
        <el-table-column prop="nickname" label="昵称" width="120" />
        <el-table-column prop="reason" label="申请理由" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="申请时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at || '') }}</template>
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
        <el-table-column v-if="meetingViewStatusFilter === 'pending'" label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" @click="handleMeetingReview('view', row, true)">通过</el-button>
            <el-button link type="danger" @click="handleMeetingReview('view', row, false)">拒绝</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="isSuperAdminUser" label="管理" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDeleteMeetingRequest('view', row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="canReviewMeetingDownloadPerm" shadow="never" class="section">
      <template #header>
        <div class="header-row">
          <span>会议下载申请审批</span>
          <div class="filters">
            <el-tag v-if="meetingDownloadPendingCount > 0" type="danger" size="small">
              {{ meetingDownloadPendingCount }} 条待处理
            </el-tag>
            <el-radio-group v-model="meetingDownloadStatusFilter" size="small" @change="loadMeetingDownloadReviewData">
              <el-radio-button label="pending">待审核</el-radio-button>
              <el-radio-button label="approved">已通过</el-radio-button>
              <el-radio-button label="rejected">已拒绝</el-radio-button>
            </el-radio-group>
            <el-button
              size="small"
              type="success"
              :disabled="!selectedDownloadRequests.length"
              @click="handleBatchMeetingReview('download', true)"
            >
              批量通过 ({{ selectedDownloadRequests.length }})
            </el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="!selectedDownloadRequests.length"
              @click="handleBatchMeetingReview('download', false)"
            >
              批量拒绝
            </el-button>
          </div>
        </div>
      </template>
      <p class="tip">用户须先获得会议浏览权限方可申请下载；通过后仅可导出对应会议。</p>
      <el-table
        v-loading="meetingDownloadReviewLoading"
        :data="meetingDownloadReviewList"
        stripe
        empty-text="暂无会议下载申请"
        @selection-change="(rows: MeetingPermissionRequest[]) => (selectedDownloadRequests = rows)"
      >
        <el-table-column v-if="meetingDownloadStatusFilter === 'pending'" type="selection" width="48" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="meeting_name" label="会议" min-width="180" show-overflow-tooltip />
        <el-table-column prop="username" label="用户名" width="130" />
        <el-table-column prop="nickname" label="昵称" width="120" />
        <el-table-column prop="reason" label="申请理由" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="申请时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at || '') }}</template>
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
        <el-table-column v-if="meetingDownloadStatusFilter === 'pending'" label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" @click="handleMeetingReview('download', row, true)">通过</el-button>
            <el-button link type="danger" @click="handleMeetingReview('download', row, false)">拒绝</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="isSuperAdminUser" label="管理" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDeleteMeetingRequest('download', row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="canReviewMeetingViewPerm" shadow="never" class="section">
      <template #header>
        <div class="header-row">
          <span>文档浏览申请审批</span>
          <el-tag v-if="docViewPendingCount > 0" type="danger" size="small">
            {{ docViewPendingCount }} 条待处理
          </el-tag>
        </div>
      </template>
      <p class="tip">用户按单篇文档申请浏览权限，规则与会议记录浏览一致（复用 view_all_meetings 等权限）。</p>
      <el-table
        v-loading="docViewReviewLoading"
        :data="docViewReviewList"
        stripe
        empty-text="暂无文档浏览申请"
      >
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="document_title" label="文档" min-width="180" show-overflow-tooltip />
        <el-table-column prop="username" label="用户名" width="130" />
        <el-table-column prop="nickname" label="昵称" width="120" />
        <el-table-column prop="reason" label="申请理由" min-width="160" show-overflow-tooltip />
        <el-table-column prop="created_at" label="申请时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at || '') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" @click="handleDocumentReview('view', row, true)">通过</el-button>
            <el-button link type="danger" @click="handleDocumentReview('view', row, false)">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="canReviewMeetingDownloadPerm" shadow="never" class="section">
      <template #header>
        <div class="header-row">
          <span>文档下载申请审批</span>
          <el-tag v-if="docDownloadPendingCount > 0" type="danger" size="small">
            {{ docDownloadPendingCount }} 条待处理
          </el-tag>
        </div>
      </template>
      <p class="tip">用户须先获得文档浏览权限方可申请下载；规则与会议记录下载一致。</p>
      <el-table
        v-loading="docDownloadReviewLoading"
        :data="docDownloadReviewList"
        stripe
        empty-text="暂无文档下载申请"
      >
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="document_title" label="文档" min-width="180" show-overflow-tooltip />
        <el-table-column prop="username" label="用户名" width="130" />
        <el-table-column prop="nickname" label="昵称" width="120" />
        <el-table-column prop="reason" label="申请理由" min-width="160" show-overflow-tooltip />
        <el-table-column prop="created_at" label="申请时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at || '') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" @click="handleDocumentReview('download', row, true)">通过</el-button>
            <el-button link type="danger" @click="handleDocumentReview('download', row, false)">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { useNotificationListener } from '@/composables/useUserNotifications'
import {
  getAccessRequestStats,
  getAccessRequests,
  getApplicableRequestTypes,
  getPermissionSettings,
  deleteAccessRequest,
  REQUEST_TYPE_LABELS,
  reviewAccessRequest,
  submitAccessRequest,
  updatePermissionSettings,
  type AccessRequest,
  type AccessRequestStats,
  type RequestTypeOption,
} from '@/api/permissions'
import {
  batchReviewMeetingPermissionRequests,
  deleteMeetingDownloadRequestRecord,
  deleteMeetingViewRequestRecord,
  getMeetingViewRequestStats,
  getMyMeetingDownloadRequests,
  getMyMeetingViewRequests,
  getPendingMeetingDownloadRequests,
  getPendingMeetingViewRequests,
  reviewMeetingDownloadRequest,
  reviewMeetingViewRequest,
  type MeetingPermissionRequest,
} from '@/api/meetings'
import {
  getFeishuDocumentAccessStats,
  getPendingFeishuDocumentDownloadRequests,
  getPendingFeishuDocumentViewRequests,
  reviewFeishuDocumentDownloadRequest,
  reviewFeishuDocumentViewRequest,
  type FeishuDocumentAccessRequest,
} from '@/api/feishuDocuments'
import { useUserStore } from '@/stores/user'
import { canReviewAccess, canReviewMeetingDownload, canReviewMeetingView, isSuperAdmin } from '@/utils/permission'

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
const portalPendingForReview = ref(0)

const canReview = computed(() => canReviewAccess(userStore.userInfo?.role))
const isSuperAdminUser = computed(() => isSuperAdmin(userStore.userInfo?.role))
const canReviewMeetingDownloadPerm = computed(() =>
  canReviewMeetingDownload(userStore.userInfo?.role, userStore.userInfo?.permissions)
)
const canReviewMeetingViewPerm = computed(() =>
  canReviewMeetingView(userStore.userInfo?.role, userStore.userInfo?.permissions)
)

const meetingViewReviewLoading = ref(false)
const meetingDownloadReviewLoading = ref(false)
const meetingViewReviewList = ref<MeetingPermissionRequest[]>([])
const meetingDownloadReviewList = ref<MeetingPermissionRequest[]>([])
const meetingViewPendingCount = ref(0)
const meetingDownloadPendingCount = ref(0)
const meetingViewStatusFilter = ref('pending')
const meetingDownloadStatusFilter = ref('pending')
const selectedViewRequests = ref<MeetingPermissionRequest[]>([])
const selectedDownloadRequests = ref<MeetingPermissionRequest[]>([])

const docViewReviewLoading = ref(false)
const docDownloadReviewLoading = ref(false)
const docViewReviewList = ref<FeishuDocumentAccessRequest[]>([])
const docDownloadReviewList = ref<FeishuDocumentAccessRequest[]>([])
const docViewPendingCount = ref(0)
const docDownloadPendingCount = ref(0)

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
    if (row.status === 'pending') continue
    const notifyKey =
      row.request_type === 'view_meeting'
        ? row.id + 1000000
        : row.request_type === 'download_meeting'
          ? row.id + 3000000
          : row.id
    if (notified.has(notifyKey)) continue
    const typeLabel =
      row.request_type_label || REQUEST_TYPE_LABELS[row.request_type] || row.request_type
    const result = row.status === 'approved' ? '已通过' : '已拒绝'
    ElNotification({
      title: '权限申请已有结果',
      message: `您的「${typeLabel}」申请${result}${row.review_note ? `：${row.review_note}` : ''}`,
      type: row.status === 'approved' ? 'success' : 'warning',
      duration: 8000,
    })
    notified.add(notifyKey)
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
  const base = { ...res.data }
  portalPendingForReview.value = base.pending_for_review || 0
  let totalPending = portalPendingForReview.value
  let myPending = base.my_pending || 0

  try {
    const meetingStats = await getMeetingViewRequestStats()
    myPending += meetingStats.my_pending || 0
    meetingViewPendingCount.value = meetingStats.view?.pending_for_review ?? 0
    meetingDownloadPendingCount.value = meetingStats.download?.pending_for_review ?? 0
    if (
      canReview.value ||
      canReviewMeetingViewPerm.value ||
      canReviewMeetingDownloadPerm.value
    ) {
      totalPending += meetingStats.pending_for_review || 0
    }
  } catch {
    meetingViewPendingCount.value = 0
    meetingDownloadPendingCount.value = 0
  }
  try {
    const docStats = await getFeishuDocumentAccessStats()
    myPending += docStats.data.my_pending || 0
    if (
      canReview.value ||
      canReviewMeetingViewPerm.value ||
      canReviewMeetingDownloadPerm.value
    ) {
      totalPending += docStats.data.pending_for_review || 0
    }
  } catch {
    /* flybook/doc mirror optional */
  }

  stats.value = {
    ...base,
    my_pending: myPending,
    pending_for_review: totalPending,
  }
  return stats.value
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

async function loadMyRequests(silent = false) {
  if (!silent) myLoading.value = true
  try {
    const res = await getAccessRequests({
      scope: 'mine',
      page: 1,
      page_size: 50,
    })
    let meetingItems: AccessRequest[] = []
    try {
      const [viewRes, downloadRes] = await Promise.all([
        getMyMeetingViewRequests(),
        getMyMeetingDownloadRequests(),
      ])
      const mapRow = (row: MeetingPermissionRequest, prefix: string): AccessRequest => ({
        id: row.id,
        user_id: row.user_id,
        request_type: prefix === 'view' ? 'view_meeting' : 'download_meeting',
        request_type_label: `${prefix === 'view' ? '浏览' : '下载'}会议：${row.meeting_name || row.file_id}`,
        status: row.status,
        reason: row.reason,
        reviewer_id: row.reviewer_id,
        review_note: row.review_note,
        created_at: row.created_at || '',
        reviewed_at: row.reviewed_at,
        username: row.username,
        nickname: row.nickname,
        reviewer_username: row.reviewer_username,
        reviewer_nickname: row.reviewer_nickname,
      })
      meetingItems = [
        ...(viewRes.requests || []).map((r) => mapRow(r, 'view')),
        ...(downloadRes.requests || []).map((r) => mapRow(r, 'download')),
      ]
    } catch {
      meetingItems = []
    }
    myRequests.value = [...res.data.items, ...meetingItems].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    notifyReviewResults(myRequests.value)
  } finally {
    if (!silent) myLoading.value = false
  }
}

async function loadMeetingViewReviewData(silent = false) {
  if (!canReviewMeetingViewPerm.value) return
  if (!silent) meetingViewReviewLoading.value = true
  try {
    const res = await getPendingMeetingViewRequests(meetingViewStatusFilter.value)
    meetingViewReviewList.value = res.requests || []
    selectedViewRequests.value = []
  } finally {
    if (!silent) meetingViewReviewLoading.value = false
  }
}

async function loadMeetingDownloadReviewData(silent = false) {
  if (!canReviewMeetingDownloadPerm.value) return
  if (!silent) meetingDownloadReviewLoading.value = true
  try {
    const res = await getPendingMeetingDownloadRequests(meetingDownloadStatusFilter.value)
    meetingDownloadReviewList.value = res.requests || []
    selectedDownloadRequests.value = []
  } finally {
    if (!silent) meetingDownloadReviewLoading.value = false
  }
}

async function loadDocViewReviewData(silent = false) {
  if (!canReviewMeetingViewPerm.value) return
  if (!silent) docViewReviewLoading.value = true
  try {
    const res = await getPendingFeishuDocumentViewRequests()
    docViewReviewList.value = res.data.requests || []
    docViewPendingCount.value = docViewReviewList.value.length
  } finally {
    if (!silent) docViewReviewLoading.value = false
  }
}

async function loadDocDownloadReviewData(silent = false) {
  if (!canReviewMeetingDownloadPerm.value) return
  if (!silent) docDownloadReviewLoading.value = true
  try {
    const res = await getPendingFeishuDocumentDownloadRequests()
    docDownloadReviewList.value = res.data.requests || []
    docDownloadPendingCount.value = docDownloadReviewList.value.length
  } finally {
    if (!silent) docDownloadReviewLoading.value = false
  }
}

async function loadReviewData(silent = false) {
  if (!canReview.value) return
  if (!silent) reviewLoading.value = true
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
    if (!silent) reviewLoading.value = false
  }
}

async function refreshAll(notifyReviewer = false, silent = false) {
  if (!silent) {
    await userStore.fetchUserInfo()
  }
  const data = await loadStats()
  await loadMyRequests(silent)
  if (canReview.value) {
    await loadReviewData(silent)
    if (notifyReviewer && data.pending_for_review > 0) {
      notifyPendingForReviewer(data.pending_for_review)
    }
  }
  if (canReviewMeetingViewPerm.value) {
    await loadMeetingViewReviewData(silent)
  }
  if (canReviewMeetingDownloadPerm.value) {
    await loadMeetingDownloadReviewData(silent)
  }
  if (canReviewMeetingViewPerm.value) {
    await loadDocViewReviewData(silent)
  }
  if (canReviewMeetingDownloadPerm.value) {
    await loadDocDownloadReviewData(silent)
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
  if (row.request_type === 'view_meeting') {
    await handleMeetingReview('view', { id: row.id, meeting_name: row.request_type_label, username: row.username, nickname: row.nickname, user_id: row.user_id, file_id: '' }, approve)
    return
  }
  if (row.request_type === 'download_meeting') {
    await handleMeetingReview('download', { id: row.id, meeting_name: row.request_type_label, username: row.username, nickname: row.nickname, user_id: row.user_id, file_id: '' }, approve)
    return
  }
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

async function handleMeetingReview(
  kind: 'view' | 'download',
  row: MeetingPermissionRequest,
  approve: boolean
) {
  const applicant = row.username || row.nickname || `用户#${row.user_id}`
  const meetingName = row.meeting_name || row.file_id
  const action = approve ? '通过' : '拒绝'
  const title = kind === 'view' ? '会议浏览审批' : '会议下载审批'
  let reviewNote: string | undefined
  try {
    const { value } = await ElMessageBox.prompt(
      `确定${action}用户「${applicant}」${kind === 'view' ? '浏览' : '下载'}会议「${meetingName}」的申请？`,
      title,
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
  if (kind === 'view') {
    await reviewMeetingViewRequest(row.id, approve, reviewNote)
  } else {
    await reviewMeetingDownloadRequest(row.id, approve, reviewNote)
  }
  ElMessage.success(approve ? '已通过' : '已拒绝')
  await refreshAll(false)
}

async function handleDocumentReview(
  kind: 'view' | 'download',
  row: FeishuDocumentAccessRequest,
  approve: boolean
) {
  const applicant = row.username || row.nickname || '用户'
  const docName = row.document_title || row.doc_id
  const action = approve ? '通过' : '拒绝'
  const title = kind === 'view' ? '文档浏览审批' : '文档下载审批'
  let reviewNote: string | undefined
  try {
    const { value } = await ElMessageBox.prompt(
      `确定${action}用户「${applicant}」${kind === 'view' ? '浏览' : '下载'}文档「${docName}」的申请？`,
      title,
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
  if (kind === 'view') {
    await reviewFeishuDocumentViewRequest(row.id, approve, reviewNote)
  } else {
    await reviewFeishuDocumentDownloadRequest(row.id, approve, reviewNote)
  }
  ElMessage.success(approve ? '已通过' : '已拒绝')
  await refreshAll(false)
}

async function handleBatchMeetingReview(kind: 'view' | 'download', approve: boolean) {
  const rows = kind === 'view' ? selectedViewRequests.value : selectedDownloadRequests.value
  if (!rows.length) {
    ElMessage.warning('请先勾选要审批的申请')
    return
  }
  const action = approve ? '通过' : '拒绝'
  const title = kind === 'view' ? '批量审批会议浏览' : '批量审批会议下载'
  let reviewNote: string | undefined
  try {
    const { value } = await ElMessageBox.prompt(
      `确定${action} ${rows.length} 条${kind === 'view' ? '浏览' : '下载'}申请？`,
      title,
      {
        type: approve ? 'success' : 'warning',
        confirmButtonText: action,
        cancelButtonText: '取消',
        inputPlaceholder: '审批备注（可选，将应用于全部）',
        inputValue: '',
      }
    )
    reviewNote = value || undefined
  } catch {
    return
  }
  const res = await batchReviewMeetingPermissionRequests(
    kind,
    rows.map((r) => r.id),
    approve,
    reviewNote
  )
  const errTip = res.errors?.length ? `，${res.errors.length} 条失败` : ''
  ElMessage.success(`${res.message || '批量审批完成'}${errTip}`)
  await refreshAll(false)
}

async function handleDeletePortalRequest(row: AccessRequest) {
  if (row.request_type === 'view_meeting' || row.request_type === 'download_meeting') {
    await handleDeleteMeetingRequest(
      row.request_type === 'view_meeting' ? 'view' : 'download',
      { id: row.id, meeting_name: row.request_type_label, username: row.username, nickname: row.nickname, user_id: row.user_id, file_id: '' }
    )
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定永久删除该条「${row.request_type_label || REQUEST_TYPE_LABELS[row.request_type] || row.request_type}」申请记录？此操作不可恢复。`,
      '删除申请记录',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await deleteAccessRequest(row.id)
  ElMessage.success('申请记录已删除')
  await refreshAll(false)
}

async function handleDeleteMeetingRequest(kind: 'view' | 'download', row: MeetingPermissionRequest) {
  const applicant = row.username || row.nickname || `用户#${row.user_id}`
  const meetingName = row.meeting_name || row.file_id
  try {
    await ElMessageBox.confirm(
      `确定永久删除用户「${applicant}」${kind === 'view' ? '浏览' : '下载'}会议「${meetingName}」的申请记录？此操作不可恢复。`,
      '删除申请记录',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  if (kind === 'view') {
    await deleteMeetingViewRequestRecord(row.id)
  } else {
    await deleteMeetingDownloadRequestRecord(row.id)
  }
  ElMessage.success('申请记录已删除')
  await refreshAll(false)
}

async function saveSettings() {
  await updatePermissionSettings(settings.value.block_upper_role_tasks)
  ElMessage.success('策略已更新')
}

onMounted(async () => {
  await userStore.fetchUserInfo()
  await loadApplyTypes()
  if (canReview.value) {
    await loadSettings()
  }
  await refreshAll(true)
})

useNotificationListener(() => refreshAll(false, true))
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
