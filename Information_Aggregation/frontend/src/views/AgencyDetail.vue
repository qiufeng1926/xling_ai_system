<template>
  <div v-loading="loading" class="page-card">
    <div class="header">
      <el-button @click="$router.push(INFLUENCER_ROUTES.agencies)">返回列表</el-button>
      <el-button type="primary" @click="openEdit">编辑机构</el-button>
    </div>

    <template v-if="agency">
      <el-descriptions title="机构信息" :column="2" border>
        <el-descriptions-item label="机构名称">{{ agency.name }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ formatAgencyPlatform(agency.platform) }}</el-descriptions-item>
        <el-descriptions-item label="联系人">{{ agency.contact_person || '-' }}</el-descriptions-item>
        <el-descriptions-item label="电话">{{ agency.contact_phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="微信">{{ agency.contact_wechat || '-' }}</el-descriptions-item>
        <el-descriptions-item label="达人数">{{ agency.influencer_count || 0 }}</el-descriptions-item>
        <el-descriptions-item label="平均粉丝">
          {{ formatFollowers(agency.avg_follower_count || 0) }}
        </el-descriptions-item>
        <el-descriptions-item label="粉丝总量">
          {{ formatFollowers(agency.total_followers || 0) }}
        </el-descriptions-item>
        <el-descriptions-item label="合作政策" :span="2">
          {{ agency.policy_notes || '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-divider />

      <h3>旗下达人</h3>
      <el-table :data="influencers" stripe>
        <el-table-column prop="nickname" label="昵称" min-width="140" />
        <el-table-column label="平台" width="90">
          <template #default="{ row }">{{ formatPlatform(row.platform) }}</template>
        </el-table-column>
        <el-table-column prop="platform_uid" label="达人ID" min-width="140" />
        <el-table-column label="粉丝量" width="110">
          <template #default="{ row }">{{ formatFollowers(row.follower_count) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(INFLUENCER_ROUTES.influencerDetail(row.id))">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          layout="total, prev, pager, next"
          @change="loadInfluencers"
        />
      </div>
    </template>

    <el-dialog v-model="showDialog" title="编辑机构" width="560px">
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
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  AGENCY_PLATFORM_OPTIONS,
  formatAgencyPlatform,
  formatFollowers,
  getAgency,
  getAgencyInfluencers,
  updateAgency,
  type Agency,
  type AgencyInfluencer,
} from '@/api/agencies'
import { formatPlatform } from '@/api/influencer'
import { INFLUENCER_ROUTES } from '@/constants/routes'

const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const showDialog = ref(false)
const agency = ref<Agency | null>(null)
const influencers = ref<AgencyInfluencer[]>([])
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const form = reactive({
  name: '',
  platform: '',
  contact_person: '',
  contact_phone: '',
  contact_wechat: '',
  policy_notes: '',
})

const agencyId = Number(route.params.id)

async function loadAgency() {
  loading.value = true
  try {
    const res = await getAgency(agencyId)
    agency.value = res.data
  } finally {
    loading.value = false
  }
}

async function loadInfluencers() {
  const res = await getAgencyInfluencers(agencyId, {
    page: pagination.page,
    page_size: pagination.page_size,
  })
  influencers.value = res.data.items
  pagination.total = res.data.total
}

function openEdit() {
  if (!agency.value) return
  form.name = agency.value.name
  form.platform = agency.value.platform || ''
  form.contact_person = agency.value.contact_person || ''
  form.contact_phone = agency.value.contact_phone || ''
  form.contact_wechat = agency.value.contact_wechat || ''
  form.policy_notes = agency.value.policy_notes || ''
  showDialog.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入机构名称')
    return
  }
  saving.value = true
  try {
    await updateAgency(agencyId, {
      name: form.name.trim(),
      platform: form.platform || null,
      contact_person: form.contact_person || null,
      contact_phone: form.contact_phone || null,
      contact_wechat: form.contact_wechat || null,
      policy_notes: form.policy_notes || null,
    })
    ElMessage.success('保存成功')
    showDialog.value = false
    loadAgency()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadAgency()
  loadInfluencers()
})
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}

h3 {
  margin: 0 0 16px;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
