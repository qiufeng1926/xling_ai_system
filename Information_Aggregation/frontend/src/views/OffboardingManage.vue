<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 160px" @change="load">
        <el-option label="待指定交接人" value="pending" />
        <el-option label="待上传文档" value="awaiting_documents" />
        <el-option label="待交接人确认" value="awaiting_handover_confirm" />
        <el-option label="待最终批准" value="awaiting_final_approval" />
        <el-option label="已完成" value="completed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="list" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="离职员工" min-width="140">
        <template #default="{ row }">
          {{ row.user_nickname || row.user_username }}
          <span class="sub">@{{ row.user_username }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对接人" min-width="120">
        <template #default="{ row }">
          <span v-if="row.handover_username">{{ row.handover_nickname || row.handover_username }}</span>
          <span v-else class="muted">待指定</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_message" label="失败原因" min-width="160" show-overflow-tooltip />
      <el-table-column label="提交时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="交接文档" min-width="120">
        <template #default="{ row }">
          <el-button
            v-if="hasDocuments(row)"
            link
            type="primary"
            @click="showDetail(row)"
          >
            {{ row.documents?.length || 0 }} 个文件
          </el-button>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'pending'" link type="primary" @click="openAssign(row)">
            指定交接人
          </el-button>
          <el-button
            v-if="row.status === 'awaiting_final_approval' || row.status === 'failed'"
            link
            type="primary"
            @click="handleApprove(row.id)"
          >
            {{ row.error_message ? '重试批准' : '批准离职' }}
          </el-button>
          <el-button v-if="hasDocuments(row)" link type="primary" @click="showDetail(row)">
            查看文档
          </el-button>
          <el-button v-else-if="isActiveRecord(row.status)" link type="primary" @click="showDetail(row)">
            详情
          </el-button>
          <el-popconfirm
            v-if="isActiveRecord(row.status)"
            title="确定取消该申请？"
            @confirm="handleCancel(row.id)"
          >
            <template #reference>
              <el-button link type="danger">取消</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        layout="total, prev, pager, next"
        @change="load"
      />
    </div>

    <el-dialog v-model="assignVisible" title="指定交接人" width="480px">
      <p>员工：<strong>{{ assigning?.user_nickname || assigning?.user_username }}</strong></p>
      <p class="dialog-hint">指定后，员工需上传交接文档，再由交接人确认，最后由您批准离职。</p>
      <el-form label-width="100px">
        <el-form-item label="对接人员" required>
          <el-select
            v-model="handoverUserId"
            filterable
            remote
            :remote-method="searchHandover"
            :loading="searchLoading"
            placeholder="搜索在职用户"
            style="width: 100%"
          >
            <el-option
              v-for="u in handoverOptions"
              :key="u.id"
              :label="`${u.nickname} (@${u.username})`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="assigningLoading" @click="handleAssign">确认指定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="交接文档" width="600px">
      <template v-if="detailRow">
        <p>离职员工：{{ detailRow.user_nickname || detailRow.user_username }} (@{{ detailRow.user_username }})</p>
        <p v-if="detailRow.handover_username">
          交接人：{{ detailRow.handover_nickname || detailRow.handover_username }} (@{{ detailRow.handover_username }})
        </p>
        <p>状态：{{ statusLabel(detailRow.status) }}</p>
        <p v-if="detailRow.applicant_note">员工说明：{{ detailRow.applicant_note }}</p>
        <p v-if="detailRow.handover_confirm_note">交接人备注：{{ detailRow.handover_confirm_note }}</p>
        <el-table v-if="detailRow.documents?.length" :data="detailRow.documents" size="small">
          <el-table-column prop="filename" label="文档">
            <template #default="{ row }">
              <el-button link type="primary" @click="downloadDoc(row.id, row.filename)">{{ row.filename }}</el-button>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="90">
            <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无交接文档" />
        <pre v-if="detailRow.content_snapshot" class="snapshot">{{ JSON.stringify(detailRow.content_snapshot, null, 2) }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  approveOffboarding,
  assignHandover,
  cancelOffboarding,
  downloadOffboardingDocument,
  getOffboarding,
  listOffboarding,
  OFFBOARDING_STATUS_LABELS,
  type OffboardingRecord,
} from '@/api/offboarding'
import { searchUsers, type UserSearchHit } from '@/api/users'

const loading = ref(false)
const list = ref<OffboardingRecord[]>([])
const statusFilter = ref('pending')
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const assignVisible = ref(false)
const assigning = ref<OffboardingRecord | null>(null)
const handoverUserId = ref<number | null>(null)
const handoverOptions = ref<UserSearchHit[]>([])
const searchLoading = ref(false)
const assigningLoading = ref(false)

const detailVisible = ref(false)
const detailRow = ref<OffboardingRecord | null>(null)

function formatTime(v: string) {
  return v?.replace('T', ' ').slice(0, 19)
}

function formatSize(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function statusLabel(s: string) {
  return OFFBOARDING_STATUS_LABELS[s] || s
}

function statusType(s: string) {
  return (
    {
      pending: 'warning',
      awaiting_documents: 'warning',
      awaiting_handover_confirm: '',
      awaiting_final_approval: 'success',
      processing: '',
      completed: 'success',
      cancelled: 'info',
      failed: 'danger',
    } as const
  )[s] || 'info'
}

function isActiveRecord(status: string) {
  return !['completed', 'cancelled'].includes(status)
}

function hasDocuments(row: OffboardingRecord) {
  return Boolean(row.documents_submitted_at || row.documents?.length)
}

async function load() {
  loading.value = true
  try {
    const res = await listOffboarding({
      page: pagination.page,
      page_size: pagination.page_size,
      status: statusFilter.value || undefined,
    })
    list.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

function openAssign(row: OffboardingRecord) {
  assigning.value = row
  handoverUserId.value = null
  handoverOptions.value = []
  assignVisible.value = true
}

async function searchHandover(keyword: string) {
  if (!keyword.trim()) return
  searchLoading.value = true
  try {
    const res = await searchUsers(keyword, 15)
    handoverOptions.value = (res.data || []).filter((u) => u.id !== assigning.value?.user_id)
  } finally {
    searchLoading.value = false
  }
}

async function handleAssign() {
  if (!assigning.value || !handoverUserId.value) {
    ElMessage.warning('请选择对接人员')
    return
  }
  assigningLoading.value = true
  try {
    await assignHandover(assigning.value.id, handoverUserId.value)
    ElMessage.success('已指定交接人，等待员工上传文档')
    assignVisible.value = false
    load()
  } finally {
    assigningLoading.value = false
  }
}

async function handleApprove(id: number) {
  await ElMessageBox.confirm('将执行资源转移与账号封存，是否批准离职？', '最终批准')
  await approveOffboarding(id)
  ElMessage.success('离职交接已完成')
  load()
}

async function handleCancel(id: number) {
  await cancelOffboarding(id)
  ElMessage.success('已取消')
  load()
}

async function showDetail(row: OffboardingRecord) {
  detailVisible.value = true
  detailRow.value = row
  try {
    const res = await getOffboarding(row.id)
    detailRow.value = res.data
  } catch {
    /* 回退使用列表数据 */
  }
}

async function downloadDoc(docId: number, filename: string) {
  try {
    await downloadOffboardingDocument(docId, filename)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.sub {
  color: #909399;
  font-size: 12px;
}
.muted {
  color: #c0c4cc;
}
.dialog-hint {
  color: #909399;
  font-size: 13px;
  margin-bottom: 12px;
}
.snapshot {
  max-height: 300px;
  overflow: auto;
  font-size: 12px;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  margin-top: 12px;
}
</style>
