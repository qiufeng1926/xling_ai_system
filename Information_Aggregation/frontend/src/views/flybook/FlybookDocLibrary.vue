<template>
  <div class="doc-library">
    <div class="doc-library__header">
      <div>
        <h2>文档库</h2>
        <p class="doc-library__desc">
          <template v-if="isSuperAdminUser">
            超级管理员可浏览与下载全部文档快照，无需申请权限。
          </template>
          <template v-else>
            所有人可查看文档列表。浏览/下载他人文档需勾选后向管理员申请；自己的文档默认可浏览与下载。
          </template>
        </p>
      </div>
      <div v-if="!isSuperAdminUser" class="doc-library__header-actions">
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
        <el-button @click="router.push(FLYBOOK_ROUTES.docs)">云文档编辑</el-button>
      </div>
    </div>

    <el-card shadow="never" class="doc-library__filter">
      <el-form inline @submit.prevent="handleSearch">
        <el-form-item label="关键词">
          <el-input v-model="keyword" placeholder="标题或 token" clearable style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSearch">查询</el-button>
          <el-button @click="clearFilter">清除</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-loading="loading" shadow="never">
      <el-empty v-if="!loading && !documents.length" description="暂无文档镜像，请在云文档中新建或导入" />

      <div v-else class="doc-library__list">
        <div
          v-for="item in documents"
          :key="item.doc_id"
          class="doc-library__item"
          :class="{
            'doc-library__item--locked': item.can_access === false,
            'doc-library__item--selected':
              selectedViewIds.includes(item.doc_id) || selectedDownloadIds.includes(item.doc_id),
          }"
          @click="openDocument(item)"
        >
          <div class="doc-library__checks" @click.stop>
            <el-checkbox
              v-if="!isSuperAdminUser && isViewSelectable(item)"
              :model-value="selectedViewIds.includes(item.doc_id)"
              @change="(val: boolean) => toggleViewSelect(item.doc_id, val)"
            >
              浏览
            </el-checkbox>
            <el-checkbox
              v-if="!isSuperAdminUser && isDownloadSelectable(item)"
              :model-value="selectedDownloadIds.includes(item.doc_id)"
              @change="(val: boolean) => toggleDownloadSelect(item.doc_id, val)"
            >
              下载
            </el-checkbox>
          </div>
          <div class="doc-library__item-body">
            <div class="doc-library__item-head">
              <div class="doc-library__item-title">
                {{ item.title || '未命名文档' }}
                <el-tag size="small" type="info">{{ typeLabel(item.feishu_type) }}</el-tag>
                <el-tag v-if="!isSuperAdminUser && item.access_request_status === 'pending'" size="small" type="warning">
                  浏览申请中
                </el-tag>
                <el-tag v-else-if="!isSuperAdminUser && item.can_access === false" size="small" type="warning">
                  需申请浏览
                </el-tag>
                <el-tag v-if="!isSuperAdminUser && item.download_request_status === 'pending'" size="small" type="info">
                  下载申请中
                </el-tag>
                <el-tag
                  v-else-if="!isSuperAdminUser && item.can_access && item.can_download === false"
                  size="small"
                  type="info"
                >
                  需申请下载
                </el-tag>
              </div>
              <span class="doc-library__item-time">{{ formatTime(item.synced_at) }}</span>
            </div>
            <div class="doc-library__item-meta">
              <span>所有者：{{ item.owner_nickname || item.owner_username || '-' }}</span>
              <span v-if="item.has_snapshot">已同步快照</span>
              <span v-else class="muted">未同步正文</span>
            </div>
            <p class="doc-library__item-preview">{{ previewMessage(item) }}</p>
          </div>
        </div>
      </div>

      <div v-if="total > pageSize" class="doc-library__pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadData"
        />
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" :title="detail?.title || '文档详情'" width="720px" destroy-on-close>
      <div v-loading="detailLoading" class="doc-library__detail">
        <div v-if="detail" class="doc-library__detail-meta">
          <span>类型：{{ typeLabel(detail.feishu_type) }}</span>
          <span>同步：{{ formatTime(detail.synced_at) }}</span>
          <el-link v-if="detail.feishu_url" :href="detail.feishu_url" target="_blank" type="primary">
            在飞书打开
          </el-link>
        </div>
        <pre v-if="detail?.content" class="doc-library__detail-content">{{ detail.content }}</pre>
        <el-empty v-else :description="emptyDetailHint" />
      </div>
      <template #footer>
        <el-button
          v-if="detail?.can_sync"
          type="primary"
          :loading="syncing"
          @click="handleSyncDetail"
        >
          从飞书同步
        </el-button>
        <el-button v-if="detail?.can_download && detail?.content" @click="downloadContent">下载正文</el-button>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  applyFeishuDocumentDownloadAccess,
  applyFeishuDocumentViewAccess,
  getFeishuDocument,
  listFeishuDocuments,
  syncFeishuDocument,
  type FeishuDocumentDetail,
  type FeishuDocumentListItem,
} from '@/api/feishuDocuments'
import { FLYBOOK_ROUTES } from '@/constants/routes'
import { useUserStore } from '@/stores/user'
import { isSuperAdmin } from '@/utils/permission'

const router = useRouter()
const userStore = useUserStore()
const isSuperAdminUser = computed(() => isSuperAdmin(userStore.userInfo?.role))

const loading = ref(false)
const applyingView = ref(false)
const applyingDownload = ref(false)
const documents = ref<FeishuDocumentListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const selectedViewIds = ref<string[]>([])
const selectedDownloadIds = ref<string[]>([])

const detailVisible = ref(false)
const detailLoading = ref(false)
const syncing = ref(false)
const detail = ref<FeishuDocumentDetail | null>(null)
const currentDocId = ref('')

const emptyDetailHint = computed(() => {
  const t = detail.value?.feishu_type
  if (t === 'slides' || t === 'mindnote') {
    return '幻灯片/思维笔记暂不支持正文快照，请使用「在飞书打开」查看'
  }
  if (detail.value?.can_sync) {
    return '暂无正文快照，请点击「从飞书同步」拉取最新内容'
  }
  return '暂无正文快照，请联系文档所有者同步'
})

const viewSelectableCount = computed(() => documents.value.filter(isViewSelectable).length)
const downloadSelectableCount = computed(() => documents.value.filter(isDownloadSelectable).length)

const TYPE_LABELS: Record<string, string> = {
  docx: '文档',
  doc: '文档',
  sheet: '表格',
  bitable: '多维表格',
  slides: '幻灯片',
  mindnote: '思维笔记',
}

function typeLabel(type: string) {
  return TYPE_LABELS[type] || type || '文档'
}

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function previewText(text: string) {
  const trimmed = (text || '').trim()
  if (!trimmed) return '暂无预览'
  return trimmed.length > 150 ? `${trimmed.slice(0, 150)}…` : trimmed
}

function isViewSelectable(item: FeishuDocumentListItem) {
  return item.can_access === false && item.access_request_status !== 'pending'
}

function isDownloadSelectable(item: FeishuDocumentListItem) {
  return (
    item.can_access === true &&
    item.can_download === false &&
    item.download_request_status !== 'pending'
  )
}

function previewMessage(item: FeishuDocumentListItem) {
  if (isSuperAdminUser.value) {
    if (item.can_access === false) {
      return '暂无浏览权限（隐身超管等特殊文档）'
    }
    return previewText(item.preview)
  }
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
    return `${previewText(item.preview)}（可勾选「下载」申请导出权限）`
  }
  return previewText(item.preview)
}

function toggleViewSelect(docId: string, checked: boolean) {
  if (checked) {
    if (!selectedViewIds.value.includes(docId)) {
      selectedViewIds.value = [...selectedViewIds.value, docId]
    }
  } else {
    selectedViewIds.value = selectedViewIds.value.filter((id) => id !== docId)
  }
}

function toggleDownloadSelect(docId: string, checked: boolean) {
  if (checked) {
    if (!selectedDownloadIds.value.includes(docId)) {
      selectedDownloadIds.value = [...selectedDownloadIds.value, docId]
    }
  } else {
    selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => id !== docId)
  }
}

async function submitViewApply(docIds: string[], reason?: string) {
  applyingView.value = true
  try {
    const res = await applyFeishuDocumentViewAccess(docIds, reason)
    const skippedTip = res.data.skipped?.length ? `，${res.data.skipped.length} 条已跳过` : ''
    ElMessage.success(`已提交 ${res.data.created} 条浏览申请${skippedTip}`)
    selectedViewIds.value = selectedViewIds.value.filter((id) => !docIds.includes(id))
    await loadData()
  } catch (err: any) {
    ElMessage.error(err?.message || '提交浏览申请失败')
  } finally {
    applyingView.value = false
  }
}

async function submitDownloadApply(docIds: string[], reason?: string) {
  applyingDownload.value = true
  try {
    const res = await applyFeishuDocumentDownloadAccess(docIds, reason)
    const skippedTip = res.data.skipped?.length ? `，${res.data.skipped.length} 条已跳过` : ''
    ElMessage.success(`已提交 ${res.data.created} 条下载申请${skippedTip}`)
    selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => !docIds.includes(id))
    await loadData()
  } catch (err: any) {
    ElMessage.error(err?.message || '提交下载申请失败')
  } finally {
    applyingDownload.value = false
  }
}

async function handleBatchApplyView() {
  if (!selectedViewIds.value.length) {
    ElMessage.warning('请先勾选需要申请浏览的文档')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `将为 ${selectedViewIds.value.length} 篇文档分别提交浏览申请`,
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
    ElMessage.warning('请先勾选需要申请下载的文档')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `将为 ${selectedDownloadIds.value.length} 篇文档分别提交下载申请`,
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

async function applySingleView(item: FeishuDocumentListItem) {
  try {
    const { value } = await ElMessageBox.prompt(
      `申请浏览文档「${item.title || '未命名文档'}」`,
      '申请浏览',
      {
        confirmButtonText: '提交申请',
        cancelButtonText: '取消',
        inputPlaceholder: '申请理由（可选）',
        inputType: 'textarea',
      }
    )
    await submitViewApply([item.doc_id], value || undefined)
  } catch {
    /* cancelled */
  }
}

async function openDocument(item: FeishuDocumentListItem) {
  if (!isSuperAdminUser.value && item.can_access === false) {
    if (item.access_request_status === 'pending') {
      ElMessage.info('该文档浏览申请审批中，请耐心等待')
      return
    }
    applySingleView(item)
    return
  }

  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  currentDocId.value = item.doc_id
  try {
    const res = await getFeishuDocument(item.doc_id)
    detail.value = res.data
  } catch (err: any) {
    ElMessage.error(err?.message || '加载文档详情失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function handleSyncDetail() {
  if (!currentDocId.value) return
  syncing.value = true
  try {
    await syncFeishuDocument(currentDocId.value)
    const res = await getFeishuDocument(currentDocId.value)
    detail.value = res.data
    ElMessage.success('同步完成')
    await loadData()
  } catch (err: any) {
    ElMessage.error(err?.message || '同步失败')
  } finally {
    syncing.value = false
  }
}

function downloadContent() {
  if (!detail.value?.content) return
  const blob = new Blob([detail.value.content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${detail.value.title || 'document'}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

async function loadData() {
  loading.value = true
  try {
    const res = await listFeishuDocuments({
      query: keyword.value.trim() || undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    documents.value = res.data.items || []
    total.value = res.data.total || 0
    const visibleIds = new Set(documents.value.map((item) => item.doc_id))
    selectedViewIds.value = selectedViewIds.value.filter((id) => visibleIds.has(id))
    selectedDownloadIds.value = selectedDownloadIds.value.filter((id) => visibleIds.has(id))
  } catch (err: any) {
    ElMessage.error(err?.message || '加载文档库失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadData()
}

function clearFilter() {
  keyword.value = ''
  handleSearch()
}

onMounted(loadData)
</script>

<style scoped>
.doc-library__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.doc-library__header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.doc-library__desc {
  margin: 4px 0 0;
  color: #909399;
  font-size: 14px;
}
.doc-library__filter {
  margin-bottom: 16px;
}
.doc-library__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.doc-library__item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.doc-library__checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
  min-width: 72px;
}
.doc-library__item-body {
  flex: 1;
  min-width: 0;
}
.doc-library__item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.doc-library__item--locked {
  opacity: 0.96;
}
.doc-library__item--locked .doc-library__item-title {
  color: #909399;
}
.doc-library__item--selected {
  border-color: #409eff;
  background: #f5f9ff;
}
.doc-library__item-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 8px;
}
.doc-library__item-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #409eff;
}
.doc-library__item-time {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
}
.doc-library__item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #606266;
  font-size: 13px;
  margin-bottom: 8px;
}
.doc-library__item-meta .muted {
  color: #c0c4cc;
}
.doc-library__item-preview {
  margin: 0;
  padding: 8px 10px;
  background: #f5f7fa;
  border-radius: 6px;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}
.doc-library__pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.doc-library__detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
  color: #606266;
  font-size: 13px;
}
.doc-library__detail-content {
  max-height: 480px;
  overflow: auto;
  margin: 0;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
}
</style>
