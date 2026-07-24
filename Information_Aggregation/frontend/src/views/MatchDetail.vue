<template>
  <div class="page-card">
    <template v-if="detail">
      <div class="header-bar">
        <div>
          <h3>{{ detail.title || `匹配需求 #${detail.id}` }}</h3>
          <p class="meta">
            {{ formatTime(detail.created_at) }} · 共 {{ detail.result_count ?? 0 }} 条结果 · 已选
            {{ detail.selected_count }} 人
          </p>
        </div>
        <el-space>
          <el-button @click="$router.push(INFLUENCER_ROUTES.matchHistory)">返回历史</el-button>
          <el-button @click="$router.push(INFLUENCER_ROUTES.match)">商单筛库</el-button>
          <el-button :disabled="!selectedCount" @click="handleExport(true)">
            导出已选 ({{ selectedCount }})
          </el-button>
          <el-button type="primary" @click="handleExport(false)">导出全部</el-button>
        </el-space>
      </div>

      <el-card shadow="never" class="req-card">
        <template #header>匹配条件</template>
        <el-descriptions :column="3" size="small">
          <el-descriptions-item label="平台">
            {{ detail.requirements.platform ? formatPlatform(detail.requirements.platform) : '不限' }}
          </el-descriptions-item>
          <el-descriptions-item label="粉丝区间">
            {{ formatFollowerRange(detail.requirements) }}
          </el-descriptions-item>
          <el-descriptions-item label="最低互动率">
            {{
              detail.requirements.engagement_rate_min != null
                ? `${(detail.requirements.engagement_rate_min * 100).toFixed(1)}%`
                : '不限'
            }}
          </el-descriptions-item>
          <el-descriptions-item label="必选标签">{{ detail.requirements.required_tag_ids?.length || 0 }} 个</el-descriptions-item>
          <el-descriptions-item label="优先标签">{{ detail.requirements.preferred_tag_ids?.length || 0 }} 个</el-descriptions-item>
          <el-descriptions-item label="偏好机构">{{ detail.requirements.agency_id ? '已指定' : '不限' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <div class="toolbar">
        <el-checkbox v-model="showSelectedOnly" @change="reloadResults">只看已选</el-checkbox>
        <el-button
          type="primary"
          plain
          :disabled="!selectedCount"
          @click="clearSelection"
        >
          取消全部选中
        </el-button>
      </div>

      <el-table v-loading="loading" :data="results" stripe>
        <el-table-column label="选中" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="row.is_selected" @change="(val: boolean) => toggleSelect(row, val)" />
          </template>
        </el-table-column>
        <el-table-column label="排名" width="70" prop="rank_order" />
        <el-table-column label="匹配分" width="90">
          <template #default="{ row }">
            <el-tag type="success">{{ row.match_score }} 分</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="达人" min-width="180">
          <template #default="{ row }">
            <div class="influencer-cell" v-if="row.influencer">
              <el-avatar :size="36" :src="row.influencer.avatar_url || undefined">
                {{ row.influencer.nickname?.[0] || '达' }}
              </el-avatar>
              <div>
                <div>{{ row.influencer.nickname }}</div>
                <div class="sub">{{ formatPlatform(row.influencer.platform) }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="粉丝量" width="100">
          <template #default="{ row }">
            {{ formatFollowers(row.influencer?.follower_count || 0) }}
          </template>
        </el-table-column>
        <el-table-column label="机构" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.influencer?.agency_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="标签" min-width="140">
          <template #default="{ row }">
            <el-tag
              v-for="tag in row.influencer?.tags || []"
              :key="tag"
              size="small"
              style="margin-right: 4px"
            >
              {{ tag }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="匹配说明" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.reason?.summary || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openReason(row)">评分明细</el-button>
            <el-button link type="primary" @click="$router.push(INFLUENCER_ROUTES.influencerDetail(row.influencer_id))">
              详情
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
          @change="loadResults"
        />
      </div>
    </template>

    <el-drawer v-model="showReason" title="评分明细" size="420px">
      <template v-if="currentResult?.reason">
        <p class="reason-summary">{{ currentResult.reason.summary }}</p>
        <el-table :data="currentResult.reason.details" size="small" stripe>
          <el-table-column label="维度" width="100">
            <template #default="{ row }">{{ DIMENSION_LABELS[row.dimension] || row.dimension }}</template>
          </el-table-column>
          <el-table-column label="得分" width="90">
            <template #default="{ row }">{{ row.score }} / {{ row.max_score }}</template>
          </el-table-column>
          <el-table-column prop="note" label="说明" min-width="160" show-overflow-tooltip />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { formatFollowers, formatPlatform } from '@/api/influencer'
import {
  DIMENSION_LABELS,
  downloadMatchExport,
  getMatchRequest,
  getMatchResults,
  updateMatchSelection,
  type MatchRequestDetail,
  type MatchResult,
  type MatchRequirements,
} from '@/api/match'
import { INFLUENCER_ROUTES } from '@/constants/routes'

const route = useRoute()
const requestId = computed(() => Number(route.params.id))

const loading = ref(false)
const detail = ref<MatchRequestDetail | null>(null)
const results = ref<MatchResult[]>([])
const showSelectedOnly = ref(false)
const showReason = ref(false)
const currentResult = ref<MatchResult | null>(null)

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const selectedCount = computed(() => detail.value?.selected_count ?? 0)

function formatTime(value: string) {
  return value?.replace('T', ' ').slice(0, 19) || '-'
}

function formatFollowerRange(req: MatchRequirements) {
  const lo = req.follower_min
  const hi = req.follower_max
  if (lo == null && hi == null) return '不限'
  if (lo != null && hi != null) return `${formatFollowers(lo)} - ${formatFollowers(hi)}`
  if (lo != null) return `≥ ${formatFollowers(lo)}`
  return `≤ ${formatFollowers(hi!)}`
}

async function loadDetail() {
  const res = await getMatchRequest(requestId.value)
  detail.value = res.data
}

async function loadResults() {
  loading.value = true
  try {
    const res = await getMatchResults(requestId.value, {
      page: pagination.page,
      page_size: pagination.page_size,
      selected_only: showSelectedOnly.value,
    })
    results.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

function reloadResults() {
  pagination.page = 1
  loadResults()
}

async function toggleSelect(row: MatchResult, selected: boolean) {
  await updateMatchSelection(requestId.value, { result_ids: [row.id], selected })
  row.is_selected = selected
  await loadDetail()
}

async function clearSelection() {
  const ids = results.value.filter((r) => r.is_selected).map((r) => r.id)
  if (!ids.length) return
  await updateMatchSelection(requestId.value, { result_ids: ids, selected: false })
  ElMessage.success('已取消选中')
  await loadDetail()
  loadResults()
}

function openReason(row: MatchResult) {
  currentResult.value = row
  showReason.value = true
}

async function handleExport(selectedOnly: boolean) {
  try {
    await downloadMatchExport(requestId.value, selectedOnly)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

watch(
  () => route.params.id,
  async () => {
    pagination.page = 1
    await loadDetail()
    loadResults()
  }
)

onMounted(async () => {
  await loadDetail()
  loadResults()
})
</script>

<style scoped>
.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.header-bar h3 {
  margin: 0 0 4px;
}

.meta {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.req-card {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.influencer-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sub {
  font-size: 12px;
  color: #909399;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.reason-summary {
  margin: 0 0 12px;
  color: #606266;
}
</style>
