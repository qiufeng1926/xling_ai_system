<template>
  <div v-loading="loading" class="page-card">
    <div class="header">
      <el-button @click="$router.back()">返回</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
    </div>

    <template v-if="form">
      <el-descriptions title="基础信息" :column="2" border>
        <el-descriptions-item label="昵称">{{ form.nickname || '-' }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ formatPlatform(form.platform) }}</el-descriptions-item>
        <el-descriptions-item label="达人ID">{{ form.platform_uid }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ formatSource(form.source) }}</el-descriptions-item>
        <el-descriptions-item label="所属机构">
          <el-select
            v-model="agencyId"
            clearable
            filterable
            placeholder="选择 MCN 机构"
            style="width: 100%"
            @change="handleAgencyChange"
          >
            <el-option v-for="a in agencyOptions" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-descriptions-item>
        <el-descriptions-item label="粉丝量">{{ formatFollowers(form.follower_count) }}</el-descriptions-item>
        <el-descriptions-item label="互动率">{{ form.engagement_rate ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="主页链接" :span="2">
          <a v-if="form.profile_url" :href="form.profile_url" target="_blank">{{ form.profile_url }}</a>
          <span v-else>-</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-divider />

      <h3>标签</h3>
      <div class="tag-section">
        <el-select
          v-model="selectedTagIds"
          multiple
          filterable
          placeholder="选择或搜索标签"
          style="width: 100%; max-width: 560px"
          @change="handleTagsChange"
        >
          <el-option-group v-for="group in tagOptions" :key="group.label" :label="group.label">
            <el-option v-for="tag in group.options" :key="tag.id" :label="tag.name" :value="tag.id" />
          </el-option-group>
        </el-select>
        <div class="tag-list">
          <el-tag
            v-for="tag in form.tags || []"
            :key="tag.id"
            closable
            style="margin: 4px 8px 4px 0"
            @close="removeTag(tag.id)"
          >
            {{ tag.name }}
          </el-tag>
        </div>
      </div>

      <el-divider />

      <h3>运营信息</h3>
      <el-form :model="profileForm" label-width="100px">
        <el-form-item label="合作政策">
          <el-input v-model="profileForm.cooperation_policy" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="内部备注">
          <el-input v-model="profileForm.internal_notes" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="拍摄风格">
          <el-select
            v-model="profileForm.shooting_style"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入后回车添加"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="人设特点">
          <el-select
            v-model="profileForm.persona_traits"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入后回车添加"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="联系方式">
          <el-input v-model="contactPhone" placeholder="手机号" style="width: 240px; margin-right: 12px" />
          <el-input v-model="contactWechat" placeholder="微信号" style="width: 240px" />
        </el-form-item>
      </el-form>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  formatFollowers,
  formatPlatform,
  formatSource,
  getInfluencer,
  updateInfluencer,
  type Influencer,
} from '@/api/influencer'
import { TAG_CATEGORY_MAP, getTags, setInfluencerTags, type Tag } from '@/api/tags'
import { getAgencyOptions, type Agency } from '@/api/agencies'

const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const form = ref<Influencer | null>(null)
const allTags = ref<Tag[]>([])
const agencyOptions = ref<Agency[]>([])
const selectedTagIds = ref<number[]>([])
const agencyId = ref<number | undefined>()

const tagOptions = computed(() => {
  const groups: Record<string, Tag[]> = {}
  for (const tag of allTags.value) {
    const cat = tag.category || 'other'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(tag)
  }
  return Object.entries(groups).map(([key, options]) => ({
    label: TAG_CATEGORY_MAP[key] || key,
    options,
  }))
})

const profileForm = reactive({
  cooperation_policy: '',
  internal_notes: '',
  shooting_style: [] as string[],
  persona_traits: [] as string[],
})

const contactPhone = ref('')
const contactWechat = ref('')

async function loadDetail() {
  loading.value = true
  try {
    const id = Number(route.params.id)
    const res = await getInfluencer(id)
    form.value = res.data
    selectedTagIds.value = (res.data.tags || []).map((t) => t.id)
    agencyId.value = res.data.agency_id || undefined

    const profile = res.data.profile
    profileForm.cooperation_policy = profile?.cooperation_policy || ''
    profileForm.internal_notes = profile?.internal_notes || ''
    profileForm.shooting_style = profile?.shooting_style || []
    profileForm.persona_traits = profile?.persona_traits || []
    contactPhone.value = (profile?.contact_info?.phone as string) || ''
    contactWechat.value = (profile?.contact_info?.wechat as string) || ''
  } finally {
    loading.value = false
  }
}

async function handleAgencyChange() {
  if (!form.value) return
  await updateInfluencer(form.value.id, { agency_id: agencyId.value ?? null })
  ElMessage.success('机构已更新')
  loadDetail()
}

async function handleTagsChange() {
  if (!form.value) return
  await setInfluencerTags(form.value.id, selectedTagIds.value)
  ElMessage.success('标签已更新')
  loadDetail()
}

async function removeTag(tagId: number) {
  selectedTagIds.value = selectedTagIds.value.filter((id) => id !== tagId)
  await handleTagsChange()
}

async function handleSave() {
  if (!form.value) return
  saving.value = true
  try {
    await updateInfluencer(form.value.id, {
      profile: {
        cooperation_policy: profileForm.cooperation_policy,
        internal_notes: profileForm.internal_notes,
        shooting_style: profileForm.shooting_style,
        persona_traits: profileForm.persona_traits,
        contact_info: {
          phone: contactPhone.value,
          wechat: contactWechat.value,
        },
      },
    })
    ElMessage.success('保存成功')
    loadDetail()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const [tagsRes, agencyRes] = await Promise.all([getTags(), getAgencyOptions()])
    allTags.value = tagsRes.data
    agencyOptions.value = agencyRes.data
  } catch {
    /* ignore */
  }
  loadDetail()
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

.tag-section {
  margin-bottom: 8px;
}

.tag-list {
  margin-top: 12px;
}
</style>
