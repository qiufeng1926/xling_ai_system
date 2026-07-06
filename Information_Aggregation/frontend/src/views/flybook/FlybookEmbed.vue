<template>
  <div class="flybook-page">
    <el-card shadow="never" class="flybook-page__card">
      <div class="flybook-page__hero">
        <div class="flybook-page__icon">飞</div>
        <div>
          <h2 class="flybook-page__title">飞书消息</h2>
          <p class="flybook-page__desc">
            飞书官方限制了网页被第三方系统 iframe 嵌入（CSP <code>frame-ancestors</code>），
            因此无法在 xlink 页面内直接显示飞书界面，需通过独立窗口使用。
          </p>
        </div>
      </div>

      <el-alert type="info" :closable="false" show-icon class="flybook-page__account-tip">
        <template #title>个人绑定说明</template>
        <template #default>
          飞书绑定按 <strong>xlink 账号</strong> 隔离：当前登录
          <strong>{{ portalLabel }}</strong>
          需单独绑定自己的飞书账号。不同 xlink 用户互不影响；同一飞书账号不能绑定多个 xlink 用户。
        </template>
      </el-alert>

      <el-alert
        v-if="bindStatus?.bound"
        type="success"
        :closable="false"
        show-icon
        :title="`已绑定飞书：${bindStatus.feishu_name || '飞书用户'}`"
      >
        <template #default>
          此绑定仅属于 xlink 账号「{{ portalLabel }}」。打开飞书窗口时将使用该飞书身份。
        </template>
      </el-alert>

      <el-alert
        v-else
        type="warning"
        :closable="false"
        show-icon
        title="尚未绑定飞书账号"
      >
        <template #default>
          请使用<strong>您本人</strong>的飞书账号完成授权，绑定后将与 xlink 账号「{{ portalLabel }}」一一对应。
        </template>
      </el-alert>

      <el-alert type="info" :closable="false" show-icon title="为何不能内嵌？" class="flybook-page__tip">
        <template #default>
          飞书只允许在字节/飞书自有域名下被嵌入。在 xlink 里用 iframe 加载会触发浏览器拦截，
          控制台会出现 <code>frame-ancestors</code> 相关报错，属于飞书安全策略，无法通过前端配置绕过。
        </template>
      </el-alert>

      <div class="flybook-page__actions">
        <el-button
          v-if="!bindStatus?.bound"
          type="primary"
          size="large"
          :loading="binding"
          @click="handleBindAndOpen"
        >
          绑定飞书并打开
        </el-button>
        <template v-else>
          <el-button type="primary" size="large" @click="openFlybookWindow">
            打开飞书窗口
          </el-button>
          <el-button size="large" :loading="binding" @click="handleRebind">
            重新绑定
          </el-button>
          <el-button size="large" :loading="unbinding" @click="handleUnbind">
            解除绑定
          </el-button>
        </template>
        <el-button size="large" @click="openFlybookTab">在新标签页打开</el-button>
        <el-button v-if="windowOpen" size="large" link type="primary" @click="focusFlybookWindow">
          聚焦已打开的飞书窗口
        </el-button>
      </div>

      <p v-if="windowOpen" class="flybook-page__status">
        飞书已在独立窗口中运行，请切换到该窗口收发消息。
      </p>

      <p class="flybook-page__url">
        地址：<a :href="flybookUrl" target="_blank" rel="noopener noreferrer">{{ flybookUrl }}</a>
      </p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getFeishuBindStatus,
  startFeishuBind,
  unbindFeishu,
  type FeishuBindStatus,
} from '@/api/flybook'
import { FLYBOOK_ROUTES } from '@/constants/routes'
import { useUserStore } from '@/stores/user'

const DEFAULT_FLYBOOK_URL = 'https://gcnnna81ata3.feishu.cn/next/messenger'
const FLYBOOK_WINDOW_NAME = 'xlink-flybook-messenger'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const portalLabel = computed(() => {
  const fromStatus = bindStatus.value?.portal_nickname || bindStatus.value?.portal_username
  if (fromStatus) return fromStatus
  return userStore.userInfo?.nickname || userStore.userInfo?.username || '当前用户'
})

const flybookUrl = computed(() => {
  const fromEnv =
    import.meta.env.VITE_FLYBOOK_URL?.trim() || import.meta.env.VITE_FEISHU_URL?.trim()
  return fromEnv || DEFAULT_FLYBOOK_URL
})

const bindStatus = ref<FeishuBindStatus | null>(null)
const binding = ref(false)
const unbinding = ref(false)
const windowOpen = ref(false)
let flybookWindow: Window | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

async function loadBindStatus() {
  try {
    const res = await getFeishuBindStatus()
    bindStatus.value = res.data
  } catch {
    bindStatus.value = null
  }
}

function openFlybookWindow() {
  const features = [
    'width=1280',
    'height=860',
    'left=120',
    'top=60',
    'menubar=no',
    'toolbar=no',
    'location=yes',
    'status=no',
    'resizable=yes',
    'scrollbars=yes',
  ].join(',')

  if (flybookWindow && !flybookWindow.closed) {
    flybookWindow.focus()
    flybookWindow.location.href = flybookUrl.value
  } else {
    flybookWindow = window.open(flybookUrl.value, FLYBOOK_WINDOW_NAME, features)
  }
  windowOpen.value = !!(flybookWindow && !flybookWindow.closed)
}

function focusFlybookWindow() {
  if (flybookWindow && !flybookWindow.closed) {
    flybookWindow.focus()
  } else {
    openFlybookWindow()
  }
}

function openFlybookTab() {
  window.open(flybookUrl.value, '_blank', 'noopener,noreferrer')
}

function syncWindowState() {
  windowOpen.value = !!(flybookWindow && !flybookWindow.closed)
}

async function redirectToFeishuBind() {
  binding.value = true
  try {
    const url = await startFeishuBind(FLYBOOK_ROUTES.home)
    window.location.href = url
  } finally {
    binding.value = false
  }
}

async function handleBindAndOpen() {
  await redirectToFeishuBind()
}

async function handleRebind() {
  await redirectToFeishuBind()
}

async function handleUnbind() {
  try {
    await ElMessageBox.confirm(
      `确定解除 xlink 账号「${portalLabel.value}」与飞书的绑定？其他 xlink 用户的绑定不受影响。`,
      '解除飞书绑定',
      { type: 'warning', confirmButtonText: '解除绑定', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  unbinding.value = true
  try {
    await unbindFeishu()
    bindStatus.value = {
      bound: false,
      feishu_name: null,
      token_valid: false,
      docs_authorized: false,
    }
    ElMessage.success('已解除飞书绑定')
  } finally {
    unbinding.value = false
  }
}

function handleBindQuery() {
  const bind = String(route.query.bind || '')
  const bindError = String(route.query.bind_error || '')

  if (bind === 'success') {
    ElMessage.success('飞书绑定成功')
    void loadBindStatus().then(() => openFlybookWindow())
  } else if (bindError) {
    const messages: Record<string, string> = {
      access_denied: '您已取消飞书授权',
      invalid_state: '绑定状态无效或已过期，请重试',
      missing_code: '飞书未返回授权码',
      feishu_api_error: '飞书接口调用失败',
      bind_failed: '绑定失败，请查看 flybook/portal 日志或重启门户后端',
      already_bound: '绑定失败，该飞书账号已绑定其他 xlink 用户',
      invalid_service_key: '服务密钥不一致，请检查 FLYBOOK_INTERNAL_KEY',
      missing_user: '无法识别绑定用户，请重新登录后再试',
    }
    ElMessage.error(messages[bindError] || '飞书绑定失败')
  }

  if (bind || bindError) {
    router.replace({ path: FLYBOOK_ROUTES.messenger })
  }
}

onMounted(() => {
  pollTimer = setInterval(syncWindowState, 1000)
  void loadBindStatus()
  handleBindQuery()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.flybook-page {
  min-height: calc(100vh - 120px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 24px 16px;
}

.flybook-page__card {
  width: min(720px, 100%);
}

.flybook-page__hero {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}

.flybook-page__icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: linear-gradient(135deg, #3370ff, #1456f0);
  color: #fff;
  font-size: 28px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.flybook-page__title {
  margin: 0 0 8px;
  font-size: 22px;
  color: #303133;
}

.flybook-page__desc {
  margin: 0;
  color: #606266;
  line-height: 1.6;
  font-size: 14px;
}

.flybook-page__tip {
  margin-top: 12px;
}

.flybook-page__account-tip {
  margin-bottom: 12px;
}

.flybook-page__desc code,
:deep(.el-alert__description code) {
  padding: 1px 6px;
  border-radius: 4px;
  background: #f4f4f5;
  font-size: 12px;
}

.flybook-page__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 24px 0 12px;
}

.flybook-page__status {
  margin: 0 0 12px;
  color: #67c23a;
  font-size: 14px;
}

.flybook-page__url {
  margin: 16px 0 0;
  font-size: 13px;
  color: #909399;
  word-break: break-all;
}

.flybook-page__url a {
  color: #409eff;
}
</style>
