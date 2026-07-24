<template>
  <div class="page-card">
    <div class="header-bar">
      <div>
        <h3>表单匹配历史</h3>
        <p class="meta">
          旧版表单智能匹配的只读记录（API 仍保留导出）。新商单请走「商单筛库」对话。
        </p>
      </div>
      <el-space>
        <el-button type="primary" @click="$router.push(INFLUENCER_ROUTES.match)">
          返回商单筛库
        </el-button>
      </el-space>
    </div>

    <el-table v-loading="loading" :data="items" stripe>
      <el-table-column label="ID" prop="id" width="80" />
      <el-table-column label="标题" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.title || `匹配需求 #${row.id}` }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="(MATCH_STATUS_MAP[row.status]?.type as any) || 'info'" size="small">
            {{ MATCH_STATUS_MAP[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结果数" width="90" prop="result_count" />
      <el-table-column label="已选" width="80" prop="selected_count" />
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(INFLUENCER_ROUTES.matchDetail(row.id))">
            查看
          </el-button>
          <el-button link type="primary" @click="onExport(row.id)">导出</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        layout="total, prev, pager, next"
        @change="loadList"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  MATCH_STATUS_MAP,
  downloadMatchExport,
  getMatchRequests,
  type MatchRequest,
} from '@/api/match'
import { INFLUENCER_ROUTES } from '@/constants/routes'

const loading = ref(false)
const items = ref<MatchRequest[]>([])
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

function formatTime(value: string) {
  return value?.replace('T', ' ').slice(0, 19) || '-'
}

async function loadList() {
  loading.value = true
  try {
    const res = await getMatchRequests({
      page: pagination.page,
      page_size: pagination.page_size,
    })
    items.value = res.data.items || []
    pagination.total = res.data.total || 0
  } finally {
    loading.value = false
  }
}

async function onExport(id: number) {
  try {
    await downloadMatchExport(id, false)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

onMounted(loadList)
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
  max-width: 520px;
  line-height: 1.5;
}
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
