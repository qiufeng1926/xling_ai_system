<template>
  <div class="page-card">
    <div class="filter-bar">
      <el-button type="primary" @click="showCreate = true">发起采集</el-button>
      <el-button @click="loadData">刷新</el-button>
      <div style="flex: 1"></div>
      <el-button type="success" @click="$router.push(INFLUENCER_ROUTES.review)">待审核列表</el-button>
    </div>

    <el-table v-loading="loading" :data="list" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="任务名称" min-width="160" />
      <el-table-column label="平台" width="90">
        <template #default="{ row }">{{ formatPlatform(row.platform) }}</template>
      </el-table-column>
      <el-table-column prop="keyword" label="关键词" width="120" />
      <el-table-column label="筛选条件" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="filter-summary">{{ (row.filter_summary || ['不限']).join(' · ') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="(TASK_STATUS_MAP[row.status]?.type as any) || 'info'">
            {{ TASK_STATUS_MAP[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="错误信息" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.error_message" class="error-msg">{{ row.error_message }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="result_count" label="采集数" width="80" />
      <el-table-column prop="approved_count" label="已通过" width="80" />
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
          <el-button
            link
            type="primary"
            :disabled="row.status === 'running'"
            @click="goReview(row.id)"
          >
            审核
          </el-button>
          <el-button
            link
            type="warning"
            :disabled="row.status === 'running'"
            @click="handleRetry(row.id)"
          >
            重试
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        layout="total, prev, pager, next"
        @change="loadData"
      />
    </div>

    <el-dialog v-model="showCreate" title="发起采集任务" width="860px" top="4vh" destroy-on-close>
      <el-form :model="form" label-width="72px" class="create-form">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="平台" required>
              <el-select v-model="form.platform" style="width: 100%" @change="onPlatformChange">
                <el-option
                  v-for="item in COLLECTION_PLATFORM_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="关键词" required>
              <el-input v-model="form.keyword" placeholder="例如：吃播、美妆、探店" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="section-title">筛选条件（默认不限）</div>
      <CollectionFilterPanel v-model="filterForm" :platform="form.platform" />

      <div class="env-info">
        <p class="tip">
          当前平台登录态：
          <el-tag size="small" :type="playwrightReady ? 'success' : 'danger'">
            {{ playwrightReady ? '就绪' : '未就绪' }}
          </el-tag>
          <el-button link type="primary" style="margin-left: 8px" @click="goConfigureSession">
            前往工作台配置
          </el-button>
        </p>
        <p v-if="envHint" class="warn tip">{{ envHint }}</p>
        <p class="tip">
          Playwright 将自动在{{ form.platform === 'xiaohongshu' ? '蒲公英' : '星图' }}页面应用所选筛选，结果进入待审核列表。
        </p>
      </div>
      <template #footer>
        <el-button @click="resetCreateForm">重置筛选</el-button>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">开始采集</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showDetail" title="采集任务详情" size="520px">
      <div v-if="detailLoading" v-loading="true" style="height: 120px" />
      <template v-else-if="taskDetail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="任务 ID">{{ taskDetail.id }}</el-descriptions-item>
          <el-descriptions-item label="关键词">{{ taskDetail.keyword }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="(TASK_STATUS_MAP[taskDetail.status]?.type as any) || 'info'">
              {{ TASK_STATUS_MAP[taskDetail.status]?.label || taskDetail.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="采集数">{{ taskDetail.result_count }}</el-descriptions-item>
          <el-descriptions-item label="已通过">{{ taskDetail.approved_count }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(taskDetail.duration_seconds) }}</el-descriptions-item>
          <el-descriptions-item v-if="taskDetail.retry_count" label="重试次数">
            {{ taskDetail.retry_count }}
          </el-descriptions-item>
          <el-descriptions-item v-if="taskDetail.queue_position" label="队列位置">
            第 {{ taskDetail.queue_position }} 位
          </el-descriptions-item>
          <el-descriptions-item label="筛选条件">
            <el-tag
              v-for="item in taskDetail.filter_summary || ['不限']"
              :key="item"
              size="small"
              style="margin: 2px 4px 2px 0"
            >
              {{ item }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="taskDetail.error_message" label="错误信息">
            <span class="error-msg">{{ taskDetail.error_message }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <h4 v-if="taskDetail.sample_items?.length" class="detail-subtitle">采集样本（Top {{ taskDetail.sample_items.length }}）</h4>
        <el-table v-if="taskDetail.sample_items?.length" :data="taskDetail.sample_items" size="small" stripe>
          <el-table-column prop="nickname" label="昵称" />
          <el-table-column label="粉丝" width="90">
            <template #default="{ row }">{{ formatFollowers(row.follower_count) }}</template>
          </el-table-column>
          <el-table-column prop="match_score" label="匹配度" width="80" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  COLLECTION_PLATFORM_OPTIONS,
  TASK_STATUS_MAP,
  createCollectionTask,
  formatDuration,
  formatFollowers,
  formatPlatform,
  getCollectionTaskDetail,
  getCollectionTasks,
  retryCollectionTask,
  type CollectionTask,
  type CollectionTaskDetail,
} from '@/api/collection'
import request, { type ApiResponse } from '@/api/request'
import { INFLUENCER_ROUTES } from '@/constants/routes'
import CollectionFilterPanel from '@/components/CollectionFilterPanel.vue'
import {
  buildFiltersPayload,
  createEmptyFilters,
  type CollectionFilters,
} from '@/constants/collectionFilters'

const playwrightReady = ref(false)
const envHint = ref('')

const showDetail = ref(false)
const detailLoading = ref(false)
const taskDetail = ref<CollectionTaskDetail | null>(null)

const router = useRouter()
const loading = ref(false)
const creating = ref(false)
const showCreate = ref(false)
const list = ref<CollectionTask[]>([])
let timer: ReturnType<typeof setInterval> | null = null

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const form = reactive({
  platform: 'douyin',
  keyword: '',
})

const filterForm = ref<CollectionFilters>(createEmptyFilters())

function resetCreateForm() {
  form.keyword = ''
  filterForm.value = createEmptyFilters()
}

function onPlatformChange() {
  filterForm.value = createEmptyFilters()
  loadCollectorConfig()
}

function formatTime(value: string) {
  return value?.replace('T', ' ').slice(0, 19)
}

function goConfigureSession() {
  showCreate.value = false
  router.push(INFLUENCER_ROUTES.dashboard)
}

async function loadCollectorConfig() {
  try {
    const res = await request.get<
      any,
      ApiResponse<{
        ready: boolean
        hint: string
      }>
    >('/collection/config', { params: { platform: form.platform } })
    playwrightReady.value = !!res.data.ready
    envHint.value = res.data.hint || ''
  } catch {
    playwrightReady.value = false
    envHint.value = '无法获取环境状态，请在工作台配置登录态'
  }
}

async function loadData() {
  loading.value = true
  try {
    const res = await getCollectionTasks({ page: pagination.page, page_size: pagination.page_size })
    list.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!form.keyword.trim()) {
    ElMessage.warning('请输入关键词')
    return
  }
  if (!playwrightReady.value) {
    ElMessage.warning('当前平台登录态未就绪，请先在工作台配置')
    return
  }
  creating.value = true
  try {
    await createCollectionTask({
      platform: form.platform,
      keyword: form.keyword.trim(),
      filters: buildFiltersPayload(filterForm.value),
    })
    ElMessage.success('采集任务已启动')
    showCreate.value = false
    resetCreateForm()
    loadData()
  } finally {
    creating.value = false
  }
}

function goReview(taskId: number) {
  router.push({ path: INFLUENCER_ROUTES.review, query: { task_id: String(taskId) } })
}

async function handleRetry(taskId: number) {
  await retryCollectionTask(taskId)
  ElMessage.success('任务已重新加入队列')
  loadData()
}

async function openDetail(taskId: number) {
  showDetail.value = true
  detailLoading.value = true
  taskDetail.value = null
  try {
    const res = await getCollectionTaskDetail(taskId)
    taskDetail.value = res.data
  } finally {
    detailLoading.value = false
  }
}

watch(showCreate, (open) => {
  if (open) loadCollectorConfig()
})

onMounted(() => {
  loadCollectorConfig()
  loadData()
  timer = setInterval(loadData, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.tip {
  color: #909399;
  font-size: 13px;
  margin: 0 0 8px;
}

.warn {
  color: #e6a23c;
  margin-left: 0;
}

.python-path {
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}

.error-msg {
  color: #f56c6c;
  font-size: 12px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 8px 0 12px;
}

.create-form {
  margin-bottom: 4px;
}

.env-info {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}

.filter-summary {
  font-size: 12px;
  color: #606266;
}

.detail-subtitle {
  margin: 20px 0 12px;
  font-size: 14px;
}
</style>
