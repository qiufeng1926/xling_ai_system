<template>
  <div class="wecom-mail page-card">
    <el-alert
      v-if="!config.configured"
      type="warning"
      :closable="false"
      show-icon
      title="企业微信邮箱未配置"
      class="wecom-mail__alert"
    >
      <template #default>
        请在 Portal 后端环境变量中配置 <code>WECOM_CORP_ID</code> 与
        <code>WECOM_CORP_SECRET</code>，并在
        <a href="https://developer.work.weixin.qq.com/document/path/97504" target="_blank" rel="noopener">
          企业微信管理后台
        </a>
        为自建应用开通「邮件」权限、配置应用邮箱。
      </template>
    </el-alert>

    <div class="wecom-mail__toolbar">
      <el-select v-model="days" style="width: 140px" @change="reloadInbox">
        <el-option label="最近 7 天" :value="7" />
        <el-option label="最近 14 天" :value="14" />
        <el-option label="最近 30 天" :value="30" />
      </el-select>
      <el-button :loading="listLoading" @click="reloadInbox">刷新收件箱</el-button>
      <el-button type="primary" :disabled="!config.configured" @click="openCompose">写邮件</el-button>
    </div>

    <div class="wecom-mail__layout">
      <el-card shadow="never" class="wecom-mail__list">
        <template #header>应用收件箱</template>
        <el-table
          v-loading="listLoading"
          :data="mailList"
          stripe
          highlight-current-row
          empty-text="暂无邮件"
          @row-click="handleSelectMail"
        >
          <el-table-column prop="mail_id" label="邮件 ID" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="handleSelectMail(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="hasMore" class="wecom-mail__more">
          <el-button :loading="listLoading" @click="loadMore">加载更多</el-button>
        </div>
      </el-card>

      <el-card shadow="never" class="wecom-mail__detail">
        <template #header>{{ detailTitle }}</template>
        <el-empty v-if="!selectedMailId" description="请选择一封邮件" />
        <div v-else v-loading="detailLoading" class="wecom-mail__detail-body">
          <dl class="wecom-mail__meta">
            <div><dt>主题</dt><dd>{{ detail.subject || '—' }}</dd></div>
            <div><dt>发件人</dt><dd>{{ detail.from_addr || '—' }}</dd></div>
            <div><dt>收件人</dt><dd>{{ detail.to_addr || '—' }}</dd></div>
            <div><dt>时间</dt><dd>{{ detail.date || '—' }}</dd></div>
          </dl>
          <el-divider />
          <div
            v-if="detail.body_html"
            class="wecom-mail__html"
            v-html="detail.body_html"
          />
          <pre v-else class="wecom-mail__text">{{ detail.body_text || '（无正文）' }}</pre>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="composeVisible" title="发送邮件" width="640px" destroy-on-close>
      <el-form :model="composeForm" label-width="100px">
        <el-form-item label="收件邮箱" required>
          <el-input
            v-model="composeForm.to_emails"
            type="textarea"
            :rows="2"
            placeholder="多个邮箱用逗号或换行分隔"
          />
        </el-form-item>
        <el-form-item label="收件 userid">
          <el-input
            v-model="composeForm.to_userids"
            placeholder="企业成员 userid，可与邮箱二选一或同时填写"
          />
        </el-form-item>
        <el-form-item label="主题" required>
          <el-input v-model="composeForm.subject" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="正文" required>
          <el-input v-model="composeForm.content" type="textarea" :rows="8" placeholder="支持 HTML" />
        </el-form-item>
        <el-form-item label="正文类型">
          <el-radio-group v-model="composeForm.content_type">
            <el-radio-button label="html">HTML</el-radio-button>
            <el-radio-button label="text">纯文本</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="composeVisible = false">取消</el-button>
        <el-button type="primary" :loading="sending" @click="handleSend">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getWeComMailConfig,
  getWeComMailDetail,
  listWeComInbox,
  sendWeComMail,
  type WeComMailDetail,
  type WeComMailListItem,
} from '@/api/wecomMail'

const config = reactive({ configured: false, corp_id: null as string | null })
const days = ref(7)
const listLoading = ref(false)
const detailLoading = ref(false)
const sending = ref(false)
const mailList = ref<WeComMailListItem[]>([])
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const selectedMailId = ref('')
const detail = reactive<WeComMailDetail>({
  mail_id: '',
  subject: '',
  from_addr: '',
  to_addr: '',
  date: '',
  body_text: '',
  body_html: '',
})

const composeVisible = ref(false)
const composeForm = reactive({
  to_emails: '',
  to_userids: '',
  subject: '',
  content: '',
  content_type: 'html' as 'html' | 'text',
})

const detailTitle = computed(() =>
  selectedMailId.value ? detail.subject || '邮件详情' : '邮件详情'
)

function splitList(raw: string) {
  return raw
    .split(/[,;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function loadConfig() {
  const res = await getWeComMailConfig()
  config.configured = res.data.configured
  config.corp_id = res.data.corp_id
}

async function reloadInbox() {
  if (!config.configured) return
  listLoading.value = true
  try {
    const res = await listWeComInbox({ days: days.value, limit: 50 })
    mailList.value = res.data.mail_list || []
    nextCursor.value = res.data.next_cursor
    hasMore.value = !!res.data.has_more
    selectedMailId.value = ''
  } finally {
    listLoading.value = false
  }
}

async function loadMore() {
  if (!nextCursor.value) return
  listLoading.value = true
  try {
    const res = await listWeComInbox({
      days: days.value,
      limit: 50,
      cursor: nextCursor.value,
    })
    mailList.value = [...mailList.value, ...(res.data.mail_list || [])]
    nextCursor.value = res.data.next_cursor
    hasMore.value = !!res.data.has_more
  } finally {
    listLoading.value = false
  }
}

async function handleSelectMail(row: WeComMailListItem) {
  selectedMailId.value = row.mail_id
  detailLoading.value = true
  try {
    const res = await getWeComMailDetail(row.mail_id)
    Object.assign(detail, res.data)
  } finally {
    detailLoading.value = false
  }
}

function openCompose() {
  composeForm.to_emails = ''
  composeForm.to_userids = ''
  composeForm.subject = ''
  composeForm.content = ''
  composeForm.content_type = 'html'
  composeVisible.value = true
}

async function handleSend() {
  const to_emails = splitList(composeForm.to_emails)
  const to_userids = splitList(composeForm.to_userids)
  if (!to_emails.length && !to_userids.length) {
    ElMessage.warning('请填写收件邮箱或 userid')
    return
  }
  if (!composeForm.subject.trim() || !composeForm.content.trim()) {
    ElMessage.warning('请填写主题和正文')
    return
  }
  sending.value = true
  try {
    await sendWeComMail({
      to_emails,
      to_userids,
      subject: composeForm.subject.trim(),
      content: composeForm.content,
      content_type: composeForm.content_type,
    })
    ElMessage.success('邮件已发送')
    composeVisible.value = false
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  if (config.configured) {
    await reloadInbox()
  }
})
</script>

<style scoped>
.wecom-mail__alert {
  margin-bottom: 16px;
}

.wecom-mail__toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.wecom-mail__layout {
  display: grid;
  grid-template-columns: minmax(280px, 380px) 1fr;
  gap: 16px;
  min-height: 520px;
}

@media (max-width: 960px) {
  .wecom-mail__layout {
    grid-template-columns: 1fr;
  }
}

.wecom-mail__list,
.wecom-mail__detail {
  min-height: 480px;
}

.wecom-mail__more {
  margin-top: 12px;
  text-align: center;
}

.wecom-mail__meta {
  margin: 0;
}

.wecom-mail__meta div {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  margin-bottom: 8px;
}

.wecom-mail__meta dt {
  color: #909399;
  font-size: 13px;
}

.wecom-mail__meta dd {
  margin: 0;
  word-break: break-all;
}

.wecom-mail__html {
  line-height: 1.6;
  overflow: auto;
}

.wecom-mail__text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: inherit;
  line-height: 1.6;
}
</style>
