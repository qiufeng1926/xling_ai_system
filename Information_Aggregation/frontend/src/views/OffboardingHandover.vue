<template>
  <div class="page-card">
    <h2 class="page-title">交接文档</h2>
    <p class="hint">查阅员工提交的交接文档；待确认任务处理完成后，可在「归档查阅」中随时再次下载。</p>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="待确认" name="pending">
        <el-empty v-if="!pendingLoading && !pendingList.length" description="暂无待确认的交接任务" />
        <el-table v-else v-loading="pendingLoading" :data="pendingList" stripe>
          <el-table-column label="离职员工" min-width="140">
            <template #default="{ row }">
              {{ row.user_nickname || row.user_username }}
              <span class="sub">@{{ row.user_username }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="applicant_note" label="员工说明" min-width="160" show-overflow-tooltip />
          <el-table-column label="提交时间" width="170">
            <template #default="{ row }">{{ formatTime(row.documents_submitted_at || row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="文档" min-width="200">
            <template #default="{ row }">
              <div v-for="d in row.documents || []" :key="d.id" class="doc-row">
                <el-button link type="primary" @click="downloadDoc(d.id, d.filename)">{{ d.filename }}</el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openConfirm(row)">确认交接</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="归档查阅" name="archive">
        <el-empty v-if="!archiveLoading && !archiveList.length" description="暂无已存档的交接记录" />
        <el-table v-else v-loading="archiveLoading" :data="archiveList" stripe>
          <el-table-column label="离职员工" min-width="140">
            <template #default="{ row }">
              {{ row.user_nickname || row.user_username }}
              <span class="sub">@{{ row.user_username }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="applicant_note" label="员工说明" min-width="140" show-overflow-tooltip />
          <el-table-column label="提交时间" width="170">
            <template #default="{ row }">{{ formatTime(row.documents_submitted_at || row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="交接文档" min-width="220">
            <template #default="{ row }">
              <div v-for="d in row.documents || []" :key="d.id" class="doc-row">
                <el-button link type="primary" @click="downloadDoc(d.id, d.filename)">{{ d.filename }}</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="confirmVisible" title="确认交接完成" width="480px">
      <p v-if="confirming">
        确认已收到 <strong>{{ confirming.user_nickname || confirming.user_username }}</strong> 的交接文档？
      </p>
      <el-form label-width="80px">
        <el-form-item label="备注">
          <el-input v-model="confirmNote" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="confirmingLoading" @click="handleConfirm">确认完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  confirmHandover,
  downloadOffboardingDocument,
  getHandoverArchive,
  getMyHandoverTasks,
  OFFBOARDING_STATUS_LABELS,
  type OffboardingRecord,
} from '@/api/offboarding'

const activeTab = ref('pending')
const pendingLoading = ref(false)
const archiveLoading = ref(false)
const pendingList = ref<OffboardingRecord[]>([])
const archiveList = ref<OffboardingRecord[]>([])
const confirmVisible = ref(false)
const confirming = ref<OffboardingRecord | null>(null)
const confirmNote = ref('')
const confirmingLoading = ref(false)

function formatTime(v: string) {
  return v?.replace('T', ' ').slice(0, 19)
}

function statusLabel(s: string) {
  return OFFBOARDING_STATUS_LABELS[s] || s
}

function statusType(s: string) {
  return (
    {
      awaiting_handover_confirm: 'warning',
      awaiting_final_approval: '',
      processing: '',
      completed: 'success',
      failed: 'danger',
    } as const
  )[s] || 'info'
}

async function loadPending() {
  pendingLoading.value = true
  try {
    const res = await getMyHandoverTasks()
    pendingList.value = res.data || []
  } finally {
    pendingLoading.value = false
  }
}

async function loadArchive() {
  archiveLoading.value = true
  try {
    const res = await getHandoverArchive()
    archiveList.value = res.data || []
  } finally {
    archiveLoading.value = false
  }
}

function onTabChange(name: string | number) {
  if (name === 'archive' && !archiveList.value.length) {
    loadArchive()
  }
}

function openConfirm(row: OffboardingRecord) {
  confirming.value = row
  confirmNote.value = ''
  confirmVisible.value = true
}

async function handleConfirm() {
  if (!confirming.value) return
  await ElMessageBox.confirm('确认后将提交超管进行最终批准，是否继续？', '确认')
  confirmingLoading.value = true
  try {
    await confirmHandover(confirming.value.id, confirmNote.value || undefined)
    ElMessage.success('交接已确认')
    confirmVisible.value = false
    await Promise.all([loadPending(), loadArchive()])
    activeTab.value = 'archive'
  } finally {
    confirmingLoading.value = false
  }
}

async function downloadDoc(docId: number, filename: string) {
  try {
    await downloadOffboardingDocument(docId, filename)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

onMounted(() => {
  loadPending()
  loadArchive()
})
</script>

<style scoped>
.page-title {
  margin: 0 0 8px;
}
.hint {
  color: #909399;
  margin-bottom: 20px;
}
.sub {
  color: #909399;
  font-size: 12px;
}
.doc-row + .doc-row {
  margin-top: 4px;
}
</style>
