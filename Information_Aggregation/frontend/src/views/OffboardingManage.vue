<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 140px" @change="load">
        <el-option label="待处理" value="pending" />
        <el-option label="已完成" value="completed" />
        <el-option label="已取消" value="cancelled" />
        <el-option label="失败" value="failed" />
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
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_message" label="失败原因" min-width="180" show-overflow-tooltip />
      <el-table-column prop="reason" label="原因" min-width="160" show-overflow-tooltip />
      <el-table-column label="提交时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <template v-if="isActiveRecord(row.status)">
            <el-button link type="primary" @click="openComplete(row)">
              {{ row.status === 'pending' && !row.error_message ? '完成交接' : '重试交接' }}
            </el-button>
            <el-popconfirm title="确定取消该申请？取消后员工账号将恢复正常。" @confirm="handleCancel(row.id)">
              <template #reference>
                <el-button link type="danger">取消</el-button>
              </template>
            </el-popconfirm>
          </template>
          <el-button v-else link type="primary" @click="showDetail(row)">查看清单</el-button>
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

    <el-dialog v-model="completeVisible" title="完成离职交接" width="480px">
      <p>员工：<strong>{{ completing?.user_nickname || completing?.user_username }}</strong></p>
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
        <el-button @click="completeVisible = false">取消</el-button>
        <el-button type="primary" :loading="completingLoading" @click="handleComplete">确认交接</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="交接清单" width="560px">
      <pre v-if="detailSnapshot" class="snapshot">{{ JSON.stringify(detailSnapshot, null, 2) }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  cancelOffboarding,
  completeOffboarding,
  listOffboarding,
  type OffboardingRecord,
} from '@/api/offboarding'
import { searchUsers, type UserSearchHit } from '@/api/users'

const loading = ref(false)
const list = ref<OffboardingRecord[]>([])
const statusFilter = ref('pending')
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const completeVisible = ref(false)
const completing = ref<OffboardingRecord | null>(null)
const handoverUserId = ref<number | null>(null)
const handoverOptions = ref<UserSearchHit[]>([])
const searchLoading = ref(false)
const completingLoading = ref(false)

const detailVisible = ref(false)
const detailSnapshot = ref<Record<string, unknown> | null>(null)

function formatTime(v: string) {
  return v?.replace('T', ' ').slice(0, 19)
}

function statusLabel(s: string) {
  return { pending: '待处理', processing: '交接中', completed: '已完成', cancelled: '已取消', failed: '失败' }[s] || s
}

function statusType(s: string) {
  return ({ pending: 'warning', processing: '', completed: 'success', cancelled: 'info', failed: 'danger' } as const)[s] || 'info'
}

function isActiveRecord(status: string) {
  return status === 'pending' || status === 'processing' || status === 'failed'
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

function openComplete(row: OffboardingRecord) {
  completing.value = row
  handoverUserId.value = row.handover_user_id ?? null
  handoverOptions.value = row.handover_user_id && row.handover_username
    ? [{ id: row.handover_user_id, username: row.handover_username, nickname: row.handover_nickname || row.handover_username }]
    : []
  completeVisible.value = true
}

async function searchHandover(keyword: string) {
  if (!keyword.trim()) return
  searchLoading.value = true
  try {
    const res = await searchUsers(keyword, 15)
    handoverOptions.value = (res.data || []).filter((u) => u.id !== completing.value?.user_id)
  } finally {
    searchLoading.value = false
  }
}

async function handleComplete() {
  if (!completing.value || !handoverUserId.value) {
    ElMessage.warning('请选择对接人员')
    return
  }
  await ElMessageBox.confirm('将镜像飞书文档、转移全部资源并封存账号，是否继续？', '确认交接')
  completingLoading.value = true
  try {
    await completeOffboarding(completing.value.id, handoverUserId.value)
    ElMessage.success('交接已完成')
    completeVisible.value = false
    load()
  } finally {
    completingLoading.value = false
  }
}

async function handleCancel(id: number) {
  await cancelOffboarding(id)
  ElMessage.success('已取消')
  load()
}

function showDetail(row: OffboardingRecord) {
  detailSnapshot.value = row.content_snapshot
  detailVisible.value = true
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
.snapshot {
  max-height: 400px;
  overflow: auto;
  font-size: 12px;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
}
</style>
