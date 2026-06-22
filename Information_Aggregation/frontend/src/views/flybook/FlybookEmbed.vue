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

      <el-alert type="info" :closable="false" show-icon title="为何不能内嵌？">
        <template #default>
          飞书只允许在字节/飞书自有域名下被嵌入。在 xlink 里用 iframe 加载会触发浏览器拦截，
          控制台会出现 <code>frame-ancestors</code> 相关报错，属于飞书安全策略，无法通过前端配置绕过。
        </template>
      </el-alert>

      <div class="flybook-page__actions">
        <el-button type="primary" size="large" @click="openFlybookWindow">
          打开飞书窗口
        </el-button>
        <el-button size="large" @click="openFlybookTab">在新标签页打开</el-button>
        <el-button v-if="windowOpen" size="large" link type="primary" @click="focusFlybookWindow">
          聚焦已打开的飞书窗口
        </el-button>
      </div>

      <p v-if="windowOpen" class="flybook-page__status">
        飞书已在独立窗口中运行，请切换到该窗口收发消息；关闭窗口后可再次点击上方按钮重新打开。
      </p>

      <p class="flybook-page__url">
        地址：<a :href="flybookUrl" target="_blank" rel="noopener noreferrer">{{ flybookUrl }}</a>
      </p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const DEFAULT_FLYBOOK_URL = 'https://gcnnna81ata3.feishu.cn/next/messenger'
const FLYBOOK_WINDOW_NAME = 'xlink-flybook-messenger'
const AUTO_OPEN_KEY = 'xlink_flybook_auto_opened'

const flybookUrl = computed(() => {
  const fromEnv =
    import.meta.env.VITE_FLYBOOK_URL?.trim() || import.meta.env.VITE_FEISHU_URL?.trim()
  return fromEnv || DEFAULT_FLYBOOK_URL
})

const windowOpen = ref(false)
let flybookWindow: Window | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

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

onMounted(() => {
  pollTimer = setInterval(syncWindowState, 1000)
  if (!sessionStorage.getItem(AUTO_OPEN_KEY)) {
    sessionStorage.setItem(AUTO_OPEN_KEY, '1')
    openFlybookWindow()
  }
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
