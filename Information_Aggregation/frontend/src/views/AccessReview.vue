<template>
  <div class="page-card">
    <el-card v-if="applyTypes.length" shadow="never" class="section">
      <template #header>申请平台权限</template>
      <p class="tip">所有模块的权限均在 xling 平台统一申请与审批，审批通过后重新登录生效。</p>
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
          <el-button type="primary" @click="handleApply">提交申请</el-button>
        </el-form-item>
      </el-form>
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
            <el-select v-model="typeFilter" clearable placeholder="申请类型" style="width: 180px" @change="loadData">
              <el-option
                v-for="(label, key) in REQUEST_TYPE_LABELS"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
            <el-radio-group v-model="statusFilter" size="small" @change="loadData">
              <el-radio-button label="pending">待审核</el-radio-button>
              <el-radio-button label="approved">已通过</el-radio-button>
              <el-radio-button label="rejected">已拒绝</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="list" stripe>
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
        <el-table-column v-if="statusFilter !== 'pending'" label="审批人" width="130">
          <template #default="{ row }">
            {{ row.reviewer_username || row.reviewer_nickname || '—' }}
          </template>
        </el-table-column>
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
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAccessRequests,
  getApplicableRequestTypes,
  getPermissionSettings,
  REQUEST_TYPE_LABELS,
  reviewAccessRequest,
  submitAccessRequest,
  updatePermissionSettings,
  type AccessRequest,
  type RequestTypeOption,
} from '@/api/permissions'
import { useUserStore } from '@/stores/user'
import { canReviewAccess } from '@/utils/permission'

const userStore = useUserStore()
const loading = ref(false)
const list = ref<AccessRequest[]>([])
const statusFilter = ref('pending')
const typeFilter = ref<string | undefined>()
const applyReason = ref('')
const applyType = ref('')
const applyTypes = ref<RequestTypeOption[]>([])
const settings = ref({ block_upper_role_tasks: true })

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

async function loadData() {
  loading.value = true
  try {
    const res = await getAccessRequests({
      status: statusFilter.value,
      request_type: typeFilter.value,
      page: 1,
      page_size: 50,
    })
    list.value = res.data.items
  } finally {
    loading.value = false
  }
}

async function handleApply() {
  if (!applyType.value) {
    ElMessage.warning('请选择申请类型')
    return
  }
  await submitAccessRequest(applyType.value, applyReason.value || undefined)
  ElMessage.success('申请已提交，审批通过后请重新登录')
  applyReason.value = ''
  await loadApplyTypes()
}

async function handleReview(row: AccessRequest, approve: boolean) {
  const applicant = row.username || row.nickname || `用户#${row.user_id}`
  const typeLabel = row.request_type_label || REQUEST_TYPE_LABELS[row.request_type] || row.request_type
  const action = approve ? '通过' : '拒绝'
  try {
    await ElMessageBox.confirm(
      `确定${action}用户「${applicant}」的「${typeLabel}」申请？`,
      '权限审批',
      { type: approve ? 'success' : 'warning', confirmButtonText: action, cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await reviewAccessRequest(row.id, approve)
  ElMessage.success(approve ? '已通过' : '已拒绝')
  loadData()
}

async function saveSettings() {
  await updatePermissionSettings(settings.value.block_upper_role_tasks)
  ElMessage.success('策略已更新')
}

onMounted(async () => {
  await userStore.fetchUserInfo()
  await loadApplyTypes()
  if (canReview.value) {
    loadSettings()
    loadData()
  }
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
}

.filters {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
