<template>
  <div class="wecom-approval page-card">
    <el-alert
      v-if="apiError"
      type="error"
      :closable="true"
      show-icon
      :title="apiError"
      class="wecom-approval__alert"
      @close="apiError = ''"
    />

    <el-alert
      v-if="!config.configured"
      type="warning"
      :closable="false"
      show-icon
      title="企业微信审批未配置"
      class="wecom-approval__alert"
    >
      <template #default>
        请在 Portal 后端配置 <code>WECOM_CORP_ID</code> 与 <code>WECOM_CORP_SECRET</code>，并在
        <a href="https://developer.work.weixin.qq.com/document/path/91854" target="_blank" rel="noopener">
          企业微信管理后台
        </a>
        将自建应用加入「审批 - 可调用接口的应用」，并在「审批 - API - 审批数据权限」中授权。
      </template>
    </el-alert>

    <div class="wecom-approval__toolbar">
      <el-select v-model="days" style="width: 120px" @change="reloadList">
        <el-option label="7 天" :value="7" />
        <el-option label="14 天" :value="14" />
        <el-option label="30 天" :value="30" />
      </el-select>
      <el-select v-model="spStatus" clearable placeholder="审批状态" style="width: 140px" @change="reloadList">
        <el-option label="审批中" value="1" />
        <el-option label="已通过" value="2" />
        <el-option label="已驳回" value="3" />
        <el-option label="已撤销" value="4" />
      </el-select>
      <el-input
        v-model="filterTemplateId"
        placeholder="模板 ID（可选）"
        clearable
        style="width: 260px"
        @keyup.enter="reloadList"
      />
      <el-input
        v-model="filterCreator"
        placeholder="申请人 userid（可选）"
        clearable
        style="width: 180px"
        @keyup.enter="reloadList"
      />
      <el-button :loading="listLoading" @click="reloadList">刷新列表</el-button>
      <el-button type="primary" :disabled="!config.configured" @click="openSubmit">提交审批</el-button>
    </div>

    <div class="wecom-approval__layout">
      <el-card shadow="never" class="wecom-approval__list">
        <template #header>审批单列表</template>
        <el-table
          v-loading="listLoading"
          :data="spList"
          stripe
          highlight-current-row
          empty-text="暂无审批单"
          @row-click="handleSelect"
        >
          <el-table-column prop="sp_no" label="审批编号" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.sp_status_label" :type="statusTagType(row.sp_status)" size="small">
                {{ row.sp_status_label }}
              </el-tag>
              <span v-else class="wecom-approval__muted">点击查看</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="72" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="handleSelect(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="hasMore" class="wecom-approval__more">
          <el-button :loading="listLoading" @click="loadMore">加载更多</el-button>
        </div>
      </el-card>

      <el-card shadow="never" class="wecom-approval__detail">
        <template #header>{{ detailTitle }}</template>
        <el-empty v-if="!selectedSpNo" description="请选择一条审批单" />
        <div v-else v-loading="detailLoading" class="wecom-approval__detail-body">
          <dl class="wecom-approval__meta">
            <div><dt>编号</dt><dd>{{ detail.sp_no }}</dd></div>
            <div><dt>模板</dt><dd>{{ detail.sp_name || '—' }}</dd></div>
            <div><dt>状态</dt><dd>{{ detail.sp_status_label || '—' }}</dd></div>
            <div><dt>申请人</dt><dd>{{ detail.applyer?.userid || '—' }}</dd></div>
            <div><dt>提交时间</dt><dd>{{ formatTime(detail.apply_time) }}</dd></div>
          </dl>
          <el-divider content-position="left">表单内容</el-divider>
          <div v-if="applyContents.length" class="wecom-approval__fields">
            <div v-for="(item, idx) in applyContents" :key="idx" class="wecom-approval__field">
              <span class="wecom-approval__field-label">{{ fieldTitle(item) }}</span>
              <span class="wecom-approval__field-value">{{ fieldValue(item) }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无表单字段" :image-size="64" />
        </div>
      </el-card>
    </div>

    <el-dialog v-model="submitVisible" title="提交审批" width="720px" destroy-on-close>
      <el-form :model="submitForm" label-width="120px">
        <el-form-item label="模板 ID" required>
          <el-input v-model="submitForm.template_id" placeholder="审批模板 ID">
            <template #append>
              <el-button :loading="templateLoading" @click="loadTemplate">加载模板</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="申请人 userid" required>
          <el-input v-model="submitForm.creator_userid" placeholder="企业成员 userid" />
        </el-form-item>
        <el-form-item label="审批流程">
          <el-radio-group v-model="submitForm.use_template_approver">
            <el-radio-button :label="1">使用模板后台流程</el-radio-button>
            <el-radio-button :label="0">接口指定审批人</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="templateControls.length" label="表单字段">
          <div class="wecom-approval__submit-fields">
            <el-form-item
              v-for="ctrl in templateControls"
              :key="ctrl.id"
              :label="ctrl.title"
              label-width="100px"
              class="wecom-approval__submit-field"
            >
              <el-input
                v-if="ctrl.control === 'Text'"
                v-model="ctrl.value"
                :placeholder="ctrl.placeholder || '请输入'"
              />
              <el-input
                v-else-if="ctrl.control === 'Textarea'"
                v-model="ctrl.value"
                type="textarea"
                :rows="3"
                :placeholder="ctrl.placeholder || '请输入'"
              />
              <el-input v-else disabled placeholder="该控件类型请使用 JSON 模式" />
            </el-form-item>
          </div>
        </el-form-item>
        <el-form-item label="摘要（最多3行）">
          <el-input v-model="submitForm.summary_line1" placeholder="第 1 行摘要" maxlength="20" show-word-limit />
          <el-input
            v-model="submitForm.summary_line2"
            placeholder="第 2 行摘要（可选）"
            maxlength="20"
            show-word-limit
            style="margin-top: 8px"
          />
        </el-form-item>
        <el-form-item v-if="submitForm.use_template_approver === 0" label="process JSON">
          <el-input
            v-model="submitForm.process_json"
            type="textarea"
            :rows="4"
            placeholder='{"node_list":[{"type":1,"apv_rel":1,"userid":["userid1"]}]}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getWeComApprovalConfig,
  getWeComApprovalDetail,
  getWeComApprovalTemplate,
  listWeComApprovals,
  submitWeComApproval,
  type WeComApprovalDetail,
  type WeComApprovalListItem,
} from '@/api/wecomApproval'

interface TemplateControlField {
  control: string
  id: string
  title: string
  placeholder: string
  require: boolean
  value: string
}

const config = reactive({
  configured: false,
  corp_id: null as string | null,
  default_template_id: null as string | null,
})

const days = ref(7)
const spStatus = ref<string>('')
const filterTemplateId = ref('')
const filterCreator = ref('')
const listLoading = ref(false)
const detailLoading = ref(false)
const templateLoading = ref(false)
const submitting = ref(false)
const apiError = ref('')
const spList = ref<WeComApprovalListItem[]>([])
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const selectedSpNo = ref('')
const detail = reactive<WeComApprovalDetail>({ sp_no: '' })

const submitVisible = ref(false)
const templateControls = ref<TemplateControlField[]>([])
const submitForm = reactive({
  template_id: '',
  creator_userid: '',
  use_template_approver: 1,
  summary_line1: '',
  summary_line2: '',
  process_json: '',
})

const detailTitle = computed(() =>
  selectedSpNo.value ? detail.sp_name || '审批详情' : '审批详情'
)

const applyContents = computed(() => detail.apply_data?.contents || [])

function statusTagType(status?: number | null) {
  if (status === 2) return 'success'
  if (status === 3) return 'danger'
  if (status === 1) return 'warning'
  return 'info'
}

function formatTime(ts?: number | null) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString()
}

function fieldTitle(item: Record<string, unknown>) {
  const titles = item.title as Array<{ text?: string }> | undefined
  return titles?.[0]?.text || item.id || '字段'
}

function fieldValue(item: Record<string, unknown>) {
  const value = (item.value || {}) as Record<string, unknown>
  if (typeof value.text === 'string' && value.text) return value.text
  if (typeof value.new_number === 'string' && value.new_number) return value.new_number
  if (typeof value.new_money === 'string' && value.new_money) return value.new_money
  return JSON.stringify(value)
}

async function loadConfig() {
  const res = await getWeComApprovalConfig()
  config.configured = res.data.configured
  config.corp_id = res.data.corp_id
  config.default_template_id = res.data.default_template_id
  if (config.default_template_id) {
    filterTemplateId.value = config.default_template_id
    submitForm.template_id = config.default_template_id
  }
}

async function reloadList() {
  if (!config.configured) return
  listLoading.value = true
  apiError.value = ''
  try {
    const res = await listWeComApprovals({
      days: days.value,
      sp_status: spStatus.value || undefined,
      template_id: filterTemplateId.value || undefined,
      creator: filterCreator.value || undefined,
      size: 50,
    })
    spList.value = res.data.sp_list || []
    nextCursor.value = res.data.next_cursor
    hasMore.value = !!res.data.has_more
    selectedSpNo.value = ''
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    apiError.value = typeof detail === 'string' ? detail : '加载审批列表失败'
    spList.value = []
  } finally {
    listLoading.value = false
  }
}

async function loadMore() {
  if (!nextCursor.value) return
  listLoading.value = true
  try {
    const res = await listWeComApprovals({
      days: days.value,
      sp_status: spStatus.value || undefined,
      template_id: filterTemplateId.value || undefined,
      creator: filterCreator.value || undefined,
      cursor: nextCursor.value,
      size: 50,
    })
    spList.value = [...spList.value, ...(res.data.sp_list || [])]
    nextCursor.value = res.data.next_cursor
    hasMore.value = !!res.data.has_more
  } finally {
    listLoading.value = false
  }
}

async function handleSelect(row: WeComApprovalListItem) {
  selectedSpNo.value = row.sp_no
  detailLoading.value = true
  try {
    const res = await getWeComApprovalDetail(row.sp_no)
    Object.assign(detail, res.data)
    const idx = spList.value.findIndex((item) => item.sp_no === row.sp_no)
    if (idx >= 0) {
      spList.value[idx] = {
        ...spList.value[idx],
        sp_name: res.data.sp_name,
        sp_status: res.data.sp_status,
        sp_status_label: res.data.sp_status_label,
        applyer_userid: (res.data.applyer as { userid?: string } | undefined)?.userid,
      }
    }
  } finally {
    detailLoading.value = false
  }
}

function openSubmit() {
  submitForm.template_id = filterTemplateId.value || config.default_template_id || ''
  submitForm.creator_userid = ''
  submitForm.use_template_approver = 1
  submitForm.summary_line1 = ''
  submitForm.summary_line2 = ''
  submitForm.process_json = ''
  templateControls.value = []
  submitVisible.value = true
}

async function loadTemplate() {
  const templateId = submitForm.template_id.trim()
  if (!templateId) {
    ElMessage.warning('请先填写模板 ID')
    return
  }
  templateLoading.value = true
  try {
    const res = await getWeComApprovalTemplate(templateId)
    const controls = res.data.template_content?.controls || []
    templateControls.value = controls
      .map((item) => {
        const prop = item.property || {}
        const control = prop.control || ''
        const id = prop.id || ''
        if (!control || !id) return null
        if (!['Text', 'Textarea'].includes(control)) return null
        return {
          control,
          id,
          title: prop.title?.[0]?.text || id,
          placeholder: prop.placeholder?.[0]?.text || '',
          require: prop.require === 1,
          value: '',
        } satisfies TemplateControlField
      })
      .filter(Boolean) as TemplateControlField[]
    if (!templateControls.value.length) {
      ElMessage.info('该模板暂无 Text/Textarea 控件，请确认模板或联系管理员扩展 JSON 提交')
    }
  } finally {
    templateLoading.value = false
  }
}

async function handleSubmit() {
  if (!submitForm.template_id.trim() || !submitForm.creator_userid.trim()) {
    ElMessage.warning('请填写模板 ID 与申请人 userid')
    return
  }
  const contents = templateControls.value
    .filter((ctrl) => ctrl.value.trim() || ctrl.require)
    .map((ctrl) => ({
      control: ctrl.control,
      id: ctrl.id,
      value: { text: ctrl.value },
    }))
  if (!contents.length) {
    ElMessage.warning('请加载模板并填写至少一个表单字段')
    return
  }
  let process: Record<string, unknown> | undefined
  if (submitForm.use_template_approver === 0) {
    if (!submitForm.process_json.trim()) {
      ElMessage.warning('请填写 process JSON')
      return
    }
    try {
      process = JSON.parse(submitForm.process_json)
    } catch {
      ElMessage.error('process JSON 格式不正确')
      return
    }
  }
  submitting.value = true
  try {
    const summary_lines = [submitForm.summary_line1, submitForm.summary_line2].filter((s) => s.trim())
    const res = await submitWeComApproval({
      template_id: submitForm.template_id.trim(),
      creator_userid: submitForm.creator_userid.trim(),
      use_template_approver: submitForm.use_template_approver,
      contents,
      summary_lines,
      process,
    })
    ElMessage.success(`审批已提交：${res.data.sp_no}`)
    submitVisible.value = false
    await reloadList()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  if (config.configured) {
    await reloadList()
  }
})
</script>

<style scoped>
.wecom-approval__alert {
  margin-bottom: 16px;
}

.wecom-approval__toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.wecom-approval__layout {
  display: grid;
  grid-template-columns: minmax(320px, 420px) 1fr;
  gap: 16px;
  min-height: 520px;
}

@media (max-width: 960px) {
  .wecom-approval__layout {
    grid-template-columns: 1fr;
  }
}

.wecom-approval__list,
.wecom-approval__detail {
  min-height: 480px;
}

.wecom-approval__more {
  margin-top: 12px;
  text-align: center;
}

.wecom-approval__meta {
  margin: 0;
}

.wecom-approval__meta div {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  margin-bottom: 8px;
}

.wecom-approval__meta dt {
  color: #909399;
  font-size: 13px;
}

.wecom-approval__meta dd {
  margin: 0;
  word-break: break-all;
}

.wecom-approval__fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wecom-approval__field {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px;
  font-size: 14px;
}

.wecom-approval__field-label {
  color: #606266;
}

.wecom-approval__field-value {
  word-break: break-word;
}

.wecom-approval__submit-fields {
  width: 100%;
}

.wecom-approval__submit-field {
  margin-bottom: 8px;
}

.wecom-approval__muted {
  color: #909399;
  font-size: 12px;
}
</style>
