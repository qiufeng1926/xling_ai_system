<template>
  <div class="page-card">
    <div class="filter-bar">
      <el-input v-model="filters.keyword" placeholder="搜索机构名称/联系人" clearable style="width: 220px" />
      <el-select v-model="filters.platform" placeholder="平台" clearable style="width: 140px">
        <el-option v-for="p in AGENCY_PLATFORM_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
      </el-select>
      <el-button type="primary" @click="handleSearch">搜索</el-button>
      <el-button @click="handleReset">重置</el-button>
      <div style="flex: 1"></div>
      <el-button type="primary" @click="openCreate">新建机构</el-button>
    </div>

    <el-table v-loading="loading" :data="list" stripe>
      <el-table-column prop="name" label="机构名称" min-width="160" />
      <el-table-column label="平台" width="100">
        <template #default="{ row }">{{ formatAgencyPlatform(row.platform) }}</template>
      </el-table-column>
      <el-table-column prop="contact_person" label="联系人" width="110" />
      <el-table-column prop="contact_phone" label="电话" width="130" />
      <el-table-column prop="influencer_count" label="达人数" width="90" />
      <el-table-column label="平均粉丝" width="110">
        <template #default="{ row }">{{ formatFollowers(row.avg_follower_count || 0) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(INFLUENCER_ROUTES.agencyDetail(row.id))">详情</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
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

    <el-dialog v-model="showDialog" :title="editing ? '编辑机构' : '新建机构'" width="560px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="机构名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="form.platform" clearable style="width: 100%">
            <el-option v-for="p in AGENCY_PLATFORM_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="form.contact_person" />
        </el-form-item>
        <el-form-item label="电话">
          <el-input v-model="form.contact_phone" />
        </el-form-item>
        <el-form-item label="微信">
          <el-input v-model="form.contact_wechat" />
        </el-form-item>
        <el-form-item label="合作政策">
          <el-input v-model="form.policy_notes" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  AGENCY_PLATFORM_OPTIONS,
  createAgency,
  deleteAgency,
  formatAgencyPlatform,
  formatFollowers,
  getAgencies,
  updateAgency,
  type Agency,
} from '@/api/agencies'
import { INFLUENCER_ROUTES } from '@/constants/routes'

const loading = ref(false)
const saving = ref(false)
const showDialog = ref(false)
const editing = ref<Agency | null>(null)
const list = ref<Agency[]>([])

const filters = reactive({ keyword: '', platform: '' })
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const form = reactive({
  name: '',
  platform: '',
  contact_person: '',
  contact_phone: '',
  contact_wechat: '',
  policy_notes: '',
})

function resetForm() {
  form.name = ''
  form.platform = ''
  form.contact_person = ''
  form.contact_phone = ''
  form.contact_wechat = ''
  form.policy_notes = ''
  editing.value = null
}

async function loadData() {
  loading.value = true
  try {
    const res = await getAgencies({
      page: pagination.page,
      page_size: pagination.page_size,
      keyword: filters.keyword || undefined,
      platform: filters.platform || undefined,
    })
    list.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadData()
}

function handleReset() {
  filters.keyword = ''
  filters.platform = ''
  handleSearch()
}

function openCreate() {
  resetForm()
  showDialog.value = true
}

function openEdit(row: Agency) {
  editing.value = row
  form.name = row.name
  form.platform = row.platform || ''
  form.contact_person = row.contact_person || ''
  form.contact_phone = row.contact_phone || ''
  form.contact_wechat = row.contact_wechat || ''
  form.policy_notes = row.policy_notes || ''
  showDialog.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入机构名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      platform: form.platform || null,
      contact_person: form.contact_person || null,
      contact_phone: form.contact_phone || null,
      contact_wechat: form.contact_wechat || null,
      policy_notes: form.policy_notes || null,
    }
    if (editing.value) {
      await updateAgency(editing.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createAgency(payload)
      ElMessage.success('创建成功')
    }
    showDialog.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: Agency) {
  await ElMessageBox.confirm(`确认删除机构「${row.name}」？旗下达人将解除关联。`, '提示', {
    type: 'warning',
  })
  await deleteAgency(row.id)
  ElMessage.success('删除成功')
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
