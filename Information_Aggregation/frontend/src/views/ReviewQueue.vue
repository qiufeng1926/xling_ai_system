<template>
  <div class="page-card">
    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <el-tab-pane label="待审核" name="pending" />
      <el-tab-pane label="已通过" name="approved" />
      <el-tab-pane label="已拒绝" name="rejected" />
    </el-tabs>

    <div class="filter-bar">
      <el-select
        v-model="taskId"
        placeholder="筛选任务"
        clearable
        style="width: 200px"
        @visible-change="onTaskSelectVisible"
        @change="handleSearch"
      >
        <el-option v-for="t in tasks" :key="t.id" :label="`${t.keyword} (#${t.id})`" :value="t.id" />
      </el-select>
      <el-button type="primary" @click="handleSearch">搜索</el-button>
      <el-button :loading="refreshing" @click="loadData({ silent: false })">刷新</el-button>
      <div style="flex: 1"></div>
      <template v-if="activeTab === 'pending'">
        <el-button type="success" :disabled="!selectedIds.length || actionLoading" :loading="actionLoading" @click="handleBatchApprove">
          批量通过 ({{ selectedIds.length }})
        </el-button>
        <el-button type="danger" :disabled="!selectedIds.length || actionLoading" :loading="actionLoading" @click="handleBatchReject">
          批量拒绝
        </el-button>
      </template>
    </div>

    <div class="table-scroll">
      <el-table
        v-loading="loading"
        :data="list"
        row-key="id"
        stripe
        @selection-change="handleSelectionChange"
      >
      <el-table-column v-if="activeTab === 'pending'" type="selection" width="50" />
      <el-table-column label="头像" width="70">
        <template #default="{ row }">
          <el-avatar :size="40" :src="row.avatar_url || undefined">
            {{ row.nickname?.[0] || '达' }}
          </el-avatar>
        </template>
      </el-table-column>
      <el-table-column prop="nickname" label="昵称" min-width="140">
        <template #default="{ row }">
          <span>{{ row.nickname }}</span>
          <el-tag v-if="row.in_library" size="small" type="warning" style="margin-left: 6px">库内已有</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="平台" width="80">
        <template #default="{ row }">{{ formatPlatform(row.platform) }}</template>
      </el-table-column>
      <el-table-column label="粉丝量" width="100">
        <template #default="{ row }">{{ formatFollowers(row.follower_count) }}</template>
      </el-table-column>
      <el-table-column label="达人类型" width="100" show-overflow-tooltip>
        <template #default="{ row }">{{ row.creator_type || '-' }}</template>
      </el-table-column>
      <el-table-column label="预期播放" width="100">
        <template #default="{ row }">
          {{ formatFollowers(row.expected_play_count ?? row.avg_views) }}
        </template>
      </el-table-column>
      <el-table-column label="匹配度" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.match_score != null" type="success">{{ row.match_score }}分</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="互动率" width="90">
        <template #default="{ row }">
          {{ row.engagement_rate != null ? `${(row.engagement_rate * 100).toFixed(2)}%` : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="完播率" width="90">
        <template #default="{ row }">
          {{ formatRate(row.completion_rate) }}
        </template>
      </el-table-column>
      <el-table-column label="成交率" width="90">
        <template #default="{ row }">
          {{ formatRate(row.deal_rate) }}
        </template>
      </el-table-column>
      <el-table-column label="MCN机构" width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ row.mcn_name || '-' }}</template>
      </el-table-column>
      <el-table-column label="标签" min-width="140">
        <template #default="{ row }">
          <el-tag v-for="tag in row.matched_tags || []" :key="tag" size="small" style="margin-right: 4px">
            {{ tag }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          <template v-if="activeTab === 'pending'">
            <el-button link type="success" :loading="actionLoading" @click="handleApprove([row.id])">通过</el-button>
            <el-button link type="danger" :loading="actionLoading" @click="handleReject([row.id])">拒绝</el-button>
          </template>
        </template>
      </el-table-column>
      </el-table>
    </div>

    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        layout="total, prev, pager, next"
        @current-change="() => loadData({ silent: list.length > 0 })"
        @size-change="() => loadData({ silent: list.length > 0 })"
      />
    </div>

    <el-drawer v-model="showDrawer" title="达人详情" size="480px">
      <template v-if="currentItem">
        <div class="detail-header">
          <el-avatar :size="56" :src="currentItem.avatar_url || undefined">
            {{ currentItem.nickname?.[0] || '达' }}
          </el-avatar>
          <div>
            <h3>{{ currentItem.nickname }}</h3>
            <p>{{ formatPlatform(currentItem.platform) }} · UID {{ currentItem.platform_uid }}</p>
          </div>
        </div>

        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="粉丝量">{{ formatFollowers(currentItem.follower_count) }}</el-descriptions-item>
          <el-descriptions-item label="达人类型">
            {{ currentItem.creator_type || parsedData.creator_type || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="预期播放量">
            {{ formatFollowers(currentItem.expected_play_count ?? currentItem.avg_views) }}
          </el-descriptions-item>
          <el-descriptions-item label="互动率">
            {{
              currentItem.engagement_rate != null
                ? `${(currentItem.engagement_rate * 100).toFixed(2)}%`
                : '-'
            }}
          </el-descriptions-item>
          <el-descriptions-item label="完播率">
            {{ formatRate(currentItem.completion_rate ?? (parsedData.completion_rate as number | undefined)) }}
          </el-descriptions-item>
          <el-descriptions-item label="成交率">
            {{ formatRate(currentItem.deal_rate ?? (parsedData.deal_rate as number | undefined)) }}
          </el-descriptions-item>
          <el-descriptions-item label="平均播放" v-if="currentItem.avg_views">
            {{ formatFollowers(currentItem.avg_views) }}
          </el-descriptions-item>
          <el-descriptions-item label="匹配度">{{ currentItem.match_score }} 分</el-descriptions-item>
          <el-descriptions-item label="库内状态">
            <el-tag :type="currentItem.in_library ? 'warning' : 'success'">
              {{ currentItem.in_library ? '已存在于达人库' : '新达人' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="抖音号">
            {{ currentItem.short_id || parsedData.short_id || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="城市">
            {{ currentItem.city || parsedData.city || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="性别">
            {{ formatGender(parsedData.gender) }}
          </el-descriptions-item>
          <el-descriptions-item label="MCN机构">
            {{ currentItem.mcn_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="联系方式">
            <span v-if="currentItem.contact_phone || currentItem.contact_wechat">
              {{ currentItem.contact_phone ? `电话 ${currentItem.contact_phone}` : '' }}
              {{ currentItem.contact_wechat ? `微信 ${currentItem.contact_wechat}` : '' }}
            </span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="视频风格">
            <el-tag
              v-for="style in currentItem.content_styles || []"
              :key="style"
              size="small"
              style="margin-right: 4px"
            >
              {{ style }}
            </el-tag>
            <span v-if="!(currentItem.content_styles || []).length">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="主页链接">
            <a
              v-if="profileLink"
              :href="profileLink"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ profileLink }}
            </a>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="标签">
            <el-tag v-for="tag in currentItem.matched_tags || []" :key="tag" size="small" style="margin-right: 4px">
              {{ tag }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="activeTab === 'pending'" class="drawer-actions">
          <el-button type="success" :loading="actionLoading" @click="handleApprove([currentItem.id])">通过并入库</el-button>
          <el-button type="danger" :loading="actionLoading" @click="handleReject([currentItem.id])">拒绝</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

defineOptions({ name: 'ReviewQueue' })
import {
  approveCollected,
  formatFollowers,
  formatPlatform,
  getCollectionTasks,
  getPendingReview,
  getReviewedItems,
  rejectCollected,
  type CollectedInfluencer,
  type CollectionTask,
} from '@/api/collection'

const route = useRoute()
const loading = ref(false)
const refreshing = ref(false)
const actionLoading = ref(false)
const tasksLoaded = ref(false)
const list = ref<CollectedInfluencer[]>([])
const tasks = ref<CollectionTask[]>([])
const selectedIds = ref<number[]>([])
const activeTab = ref<'pending' | 'approved' | 'rejected'>('pending')
const taskId = ref<number | undefined>(
  route.query.task_id ? Number(route.query.task_id) : undefined
)

const showDrawer = ref(false)
const currentItem = ref<CollectedInfluencer | null>(null)

const parsedData = computed(() => {
  const extra = currentItem.value?.extra_data as Record<string, unknown> | undefined
  return (extra?.parsed as Record<string, string>) || {}
})

const profileLink = computed(() => {
  const item = currentItem.value
  if (!item) return ''
  if (item.platform === 'douyin') {
    return (
      item.xingtu_homepage ||
      item.profile_url ||
      item.douyin_homepage ||
      (parsedData.value.xingtu_homepage as string) ||
      (parsedData.value.profile_url as string) ||
      ''
    )
  }
  return (
    item.profile_url ||
    item.xhs_homepage ||
    item.pgy_homepage ||
    item.douyin_homepage ||
    item.xingtu_homepage ||
    (parsedData.value.profile_url as string) ||
    ''
  )
})

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

function formatGender(value: string | undefined) {
  if (!value) return '-'
  if (value === '1') return '男'
  if (value === '2') return '女'
  return value
}

function formatRate(value: number | null | undefined) {
  if (value == null) return '-'
  return `${(value * 100).toFixed(2)}%`
}

function handleSelectionChange(rows: CollectedInfluencer[]) {
  selectedIds.value = rows.map((r) => r.id)
}

function openDetail(row: CollectedInfluencer) {
  currentItem.value = row
  showDrawer.value = true
}

async function loadTasks() {
  const res = await getCollectionTasks({ page: 1, page_size: 100 })
  tasks.value = res.data.items
  tasksLoaded.value = true
}

async function onTaskSelectVisible(visible: boolean) {
  if (!visible || tasksLoaded.value) return
  try {
    await loadTasks()
  } catch {
    /* ignore */
  }
}

async function loadData(options: { silent?: boolean } = {}) {
  const silent = options.silent ?? list.value.length > 0
  if (!silent) loading.value = true
  else refreshing.value = true
  try {
    const params = {
      task_id: taskId.value,
      page: pagination.page,
      page_size: pagination.page_size,
    }
    const res =
      activeTab.value === 'pending'
        ? await getPendingReview(params)
        : await getReviewedItems({ ...params, review_status: activeTab.value })
    list.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadData()
}

function handleTabChange() {
  selectedIds.value = []
  pagination.page = 1
  loadData()
}

async function handleApprove(ids: number[]) {
  actionLoading.value = true
  try {
    const res = await approveCollected(ids)
    ElMessage.success(`已通过 ${res.data.approved} 条，已自动打标并关联机构`)
    showDrawer.value = false
    selectedIds.value = []
    list.value = list.value.filter((item) => !ids.includes(item.id))
    loadData({ silent: true })
  } finally {
    actionLoading.value = false
  }
}

async function handleReject(ids: number[]) {
  await ElMessageBox.confirm('确认拒绝所选达人？', '提示', { type: 'warning' })
  actionLoading.value = true
  try {
    const res = await rejectCollected(ids)
    ElMessage.success(`已拒绝 ${res.data.rejected} 条`)
    showDrawer.value = false
    selectedIds.value = []
    list.value = list.value.filter((item) => !ids.includes(item.id))
    loadData({ silent: true })
  } finally {
    actionLoading.value = false
  }
}

function handleBatchApprove() {
  handleApprove(selectedIds.value)
}

function handleBatchReject() {
  handleReject(selectedIds.value)
}

watch(
  () => route.query.task_id,
  (val) => {
    taskId.value = val ? Number(val) : undefined
    loadData()
  }
)

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.detail-header {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}

.detail-header h3 {
  margin: 0 0 4px;
}

.detail-header p {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.drawer-actions {
  margin-top: 20px;
  display: flex;
  gap: 12px;
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
}
</style>
