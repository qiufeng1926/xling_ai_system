<template>
  <div class="page-card">
    <div class="filter-bar">
      <el-button type="primary" @click="openCreate">新建匹配</el-button>
      <el-button @click="loadData">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="list" stripe>
      <el-table-column prop="title" label="需求标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="(MATCH_STATUS_MAP[row.status]?.type as any) || 'info'">
            {{ MATCH_STATUS_MAP[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="匹配结果" width="100">
        <template #default="{ row }">{{ row.result_count ?? 0 }} 人</template>
      </el-table-column>
      <el-table-column label="已选中" width="90">
        <template #default="{ row }">{{ row.selected_count }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(INFLUENCER_ROUTES.matchDetail(row.id))">查看结果</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
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

    <el-dialog v-model="showDialog" title="新建智能匹配" width="640px" destroy-on-close>
      <el-form :model="form" label-width="110px">
        <el-form-item label="需求标题">
          <el-input v-model="form.title" placeholder="可选，留空自动生成" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="form.platform" placeholder="不限" clearable style="width: 100%">
            <el-option v-for="p in PLATFORM_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="粉丝区间">
          <div class="range-row">
            <el-input-number v-model="form.follower_min" :min="0" placeholder="下限" controls-position="right" />
            <span>—</span>
            <el-input-number v-model="form.follower_max" :min="0" placeholder="上限" controls-position="right" />
          </div>
        </el-form-item>
        <el-form-item label="必选标签">
          <el-select
            v-model="form.required_tag_ids"
            multiple
            collapse-tags
            filterable
            clearable
            placeholder="达人必须全部拥有"
            style="width: 100%"
          >
            <el-option-group v-for="g in tagOptions" :key="g.label" :label="g.label">
              <el-option v-for="t in g.options" :key="t.id" :label="t.name" :value="t.id" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="优先标签">
          <el-select
            v-model="form.preferred_tag_ids"
            multiple
            collapse-tags
            filterable
            clearable
            placeholder="命中越多分数越高"
            style="width: 100%"
          >
            <el-option-group v-for="g in tagOptions" :key="g.label" :label="g.label">
              <el-option v-for="t in g.options" :key="t.id" :label="t.name" :value="t.id" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="偏好机构">
          <el-select v-model="form.agency_id" placeholder="不限" clearable filterable style="width: 100%">
            <el-option v-for="a in agencyOptions" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="最低互动率">
          <el-input-number
            v-model="form.engagement_rate_min"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            placeholder="如 0.03"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="form.keyword" placeholder="昵称/ID 包含" clearable />
        </el-form-item>
        <el-form-item label="返回数量">
          <el-input-number v-model="form.limit" :min="1" :max="200" controls-position="right" />
        </el-form-item>
        <el-form-item label="其他">
          <el-checkbox v-model="form.must_have_contact">必须有联系方式</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">开始匹配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getAgencyOptions, type Agency } from '@/api/agencies'
import { PLATFORM_OPTIONS } from '@/api/influencer'
import {
  createMatchRequest,
  deleteMatchRequest,
  getMatchRequests,
  MATCH_STATUS_MAP,
  type MatchRequest,
} from '@/api/match'
import { getTags, type Tag } from '@/api/tags'
import { INFLUENCER_ROUTES } from '@/constants/routes'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const showDialog = ref(false)
const list = ref<MatchRequest[]>([])

const tagOptions = ref<{ label: string; options: Tag[] }[]>([])
const agencyOptions = ref<Agency[]>([])

const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const form = reactive({
  title: '',
  platform: undefined as string | undefined,
  follower_min: undefined as number | undefined,
  follower_max: undefined as number | undefined,
  required_tag_ids: [] as number[],
  preferred_tag_ids: [] as number[],
  agency_id: undefined as number | undefined,
  engagement_rate_min: undefined as number | undefined,
  keyword: '',
  must_have_contact: false,
  limit: 50,
})

function formatTime(value: string) {
  return value?.replace('T', ' ').slice(0, 19) || '-'
}

function resetForm() {
  form.title = ''
  form.platform = undefined
  form.follower_min = undefined
  form.follower_max = undefined
  form.required_tag_ids = []
  form.preferred_tag_ids = []
  form.agency_id = undefined
  form.engagement_rate_min = undefined
  form.keyword = ''
  form.must_have_contact = false
  form.limit = 50
}

function openCreate() {
  resetForm()
  showDialog.value = true
}

async function loadData() {
  loading.value = true
  try {
    const res = await getMatchRequests({
      page: pagination.page,
      page_size: pagination.page_size,
    })
    list.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    const requirements: Record<string, unknown> = { limit: form.limit }
    if (form.platform) requirements.platform = form.platform
    if (form.follower_min != null) requirements.follower_min = form.follower_min
    if (form.follower_max != null) requirements.follower_max = form.follower_max
    if (form.required_tag_ids.length) requirements.required_tag_ids = form.required_tag_ids
    if (form.preferred_tag_ids.length) requirements.preferred_tag_ids = form.preferred_tag_ids
    if (form.agency_id) requirements.agency_id = form.agency_id
    if (form.engagement_rate_min != null) requirements.engagement_rate_min = form.engagement_rate_min
    if (form.keyword.trim()) requirements.keyword = form.keyword.trim()
    if (form.must_have_contact) requirements.must_have_contact = true

    const res = await createMatchRequest({
      title: form.title.trim() || undefined,
      requirements: requirements as any,
    })
    ElMessage.success(res.message || '匹配完成')
    showDialog.value = false
    router.push(INFLUENCER_ROUTES.matchDetail(res.data.id))
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: { id: number; title: string | null }) {
  await ElMessageBox.confirm(`确认删除「${row.title || '匹配需求'}」？`, '提示', { type: 'warning' })
  await deleteMatchRequest(row.id)
  ElMessage.success('已删除')
  loadData()
}

async function loadOptions() {
  const [tagsRes, agencyRes] = await Promise.all([getTags(), getAgencyOptions()])
  const grouped: Record<string, Tag[]> = {}
  for (const tag of tagsRes.data) {
    const cat = tag.category || '其他'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(tag)
  }
  tagOptions.value = Object.entries(grouped).map(([label, options]) => ({ label, options }))
  agencyOptions.value = agencyRes.data
}

onMounted(async () => {
  await loadOptions()
  loadData()
})
</script>

<style scoped>
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.range-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
</style>
