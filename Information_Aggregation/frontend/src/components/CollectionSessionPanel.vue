<template>
  <div v-loading="loading" class="session-panel">
    <div class="panel-header">
      <h4>采集平台登录态</h4>
      <el-button link type="primary" :loading="loading" @click="loadSessions">刷新</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="global-hint"
      :title="`${accessModeLabel(accessMode)}：${accessModeHint(accessMode)}`"
    />

    <el-row :gutter="16">
      <el-col v-for="session in sessions" :key="session.platform" :span="12">
        <el-card shadow="never" class="session-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">{{ session.label }}</span>
              <el-tag :type="sessionTagType(session)" size="small">
                {{ sessionStatusLabel(session) }}
              </el-tag>
            </div>
          </template>

          <el-descriptions :column="1" size="small" class="session-desc">
            <el-descriptions-item label="Playwright">
              {{ session.playwright_installed ? '已安装' : '未安装' }}
            </el-descriptions-item>
            <el-descriptions-item label="Chromium">
              {{ session.chromium_ready ? '已就绪' : '未就绪' }}
            </el-descriptions-item>
            <el-descriptions-item label="Cookie 数">
              {{ session.storage_configured ? session.cookie_count : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="更新时间">
              {{ formatTime(session.storage_updated_at) }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="session.login_warning"
            type="warning"
            :closable="false"
            show-icon
            class="session-alert"
            :title="session.login_warning"
          />
          <el-alert
            v-else-if="session.hint"
            type="warning"
            :closable="false"
            show-icon
            class="session-alert"
            :title="session.hint"
          />
          <el-alert
            v-if="session.login_in_progress && serverBrowserMode"
            type="success"
            :closable="false"
            show-icon
            class="session-alert"
            title="浏览器已在后端电脑打开，请完成登录后点击「保存登录态」"
          />

          <!-- 远程/穿透 -->
          <div v-if="!serverBrowserMode" class="session-actions">
            <el-button type="primary" @click="openLoginOnClient(session)">
              ① 在当前设备打开登录页
            </el-button>
            <el-button type="success" @click="openImportDialog(session)">
              ② 保存远程登录态
            </el-button>
          </div>

          <!-- 本机 localhost -->
          <div v-if="serverBrowserMode" class="session-actions">
            <el-button
              type="primary"
              :loading="actionLoading[session.platform] === 'start'"
              :disabled="!!session.login_in_progress"
              @click="handleStartLogin(session.platform)"
            >
              本机弹出浏览器登录
            </el-button>
            <el-button
              type="success"
              :loading="actionLoading[session.platform] === 'save'"
              :disabled="!session.login_in_progress"
              @click="handleSaveLogin(session.platform)"
            >
              保存登录态
            </el-button>
            <el-button
              :loading="actionLoading[session.platform] === 'cancel'"
              :disabled="!session.login_in_progress"
              @click="handleCancelLogin(session.platform)"
            >
              取消
            </el-button>
          </div>

          <div v-if="serverBrowserMode" class="session-actions secondary">
            <el-button link type="primary" @click="openImportDialog(session)">
              从 Cookie 导入登录态
            </el-button>
            <el-button link type="primary" @click="openLoginOnClient(session)">
              在当前设备打开登录页
            </el-button>
          </div>

          <div class="session-actions secondary">
            <el-upload
              :show-file-list="false"
              accept=".json,application/json"
              :http-request="(opt) => handleUpload(session.platform, opt)"
            >
              <el-button :loading="actionLoading[session.platform] === 'upload'">
                上传登录态文件
              </el-button>
            </el-upload>
            <el-popconfirm title="确定清除该平台登录态？" @confirm="handleDelete(session.platform)">
              <template #reference>
                <el-button
                  type="danger"
                  link
                  :loading="actionLoading[session.platform] === 'delete'"
                  :disabled="!session.storage_configured"
                >
                  清除登录态
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <RemoteSessionImportDialog ref="importDialogRef" @saved="applySession" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import {
  cancelPlatformLogin,
  deletePlatformSession,
  getCollectionSessions,
  savePlatformLogin,
  startPlatformLogin,
  uploadPlatformSession,
  type PlatformSessionStatus,
} from '@/api/collection'
import RemoteSessionImportDialog from '@/components/RemoteSessionImportDialog.vue'
import {
  accessModeHint,
  accessModeLabel,
  canUseServerBrowser,
  getAccessMode,
} from '@/utils/accessMode'

const loading = ref(false)
const sessions = ref<PlatformSessionStatus[]>([])
const actionLoading = reactive<Record<string, string>>({})
const importDialogRef = ref<InstanceType<typeof RemoteSessionImportDialog> | null>(null)

const accessMode = computed(() => getAccessMode())
const serverBrowserMode = computed(() => canUseServerBrowser())

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

function sessionStatusLabel(session: PlatformSessionStatus) {
  if (session.login_in_progress) return '登录中'
  if (session.ready) return '就绪'
  if (session.storage_configured) return '已配置'
  return '未配置'
}

function sessionTagType(session: PlatformSessionStatus) {
  if (session.login_in_progress) return 'warning'
  if (session.ready) return 'success'
  if (session.storage_configured) return ''
  return 'danger'
}

function openLoginOnClient(session: PlatformSessionStatus) {
  const opened = window.open(session.login_url, '_blank', 'noopener,noreferrer')
  if (!opened) {
    ElMessage.warning('浏览器拦截了弹窗，请允许弹窗后重试')
    return
  }
  ElMessage.success('已在当前设备打开登录页，登录完成后请保存远程登录态')
}

function openImportDialog(session: PlatformSessionStatus) {
  importDialogRef.value?.open(session)
}

async function loadSessions() {
  loading.value = true
  try {
    const res = await getCollectionSessions()
    sessions.value = res.data
  } finally {
    loading.value = false
  }
}

function setAction(platform: string, action: string) {
  actionLoading[platform] = action
}

function clearAction(platform: string) {
  delete actionLoading[platform]
}

function applySession(updated: PlatformSessionStatus) {
  const idx = sessions.value.findIndex((s) => s.platform === updated.platform)
  if (idx >= 0) {
    sessions.value[idx] = updated
  }
}

async function handleStartLogin(platform: string) {
  setAction(platform, 'start')
  try {
    const res = await startPlatformLogin(platform)
    applySession(res.data)
    ElMessage.success('浏览器已在后端电脑打开，请完成登录后保存')
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(msg || '无法打开登录浏览器')
  } finally {
    clearAction(platform)
  }
}

async function handleSaveLogin(platform: string) {
  setAction(platform, 'save')
  try {
    const res = await savePlatformLogin(platform)
    applySession(res.data)
    ElMessage.success('登录态已保存')
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(msg || '保存失败')
  } finally {
    clearAction(platform)
  }
}

async function handleCancelLogin(platform: string) {
  setAction(platform, 'cancel')
  try {
    const res = await cancelPlatformLogin(platform)
    applySession(res.data)
    ElMessage.info('已取消登录流程')
  } finally {
    clearAction(platform)
  }
}

async function handleUpload(platform: string, options: UploadRequestOptions) {
  const file = options.file as File
  setAction(platform, 'upload')
  try {
    const res = await uploadPlatformSession(platform, file)
    applySession(res.data)
    ElMessage.success('登录态文件已上传')
    options.onSuccess?.(res)
  } catch (e) {
    options.onError?.(e as Error)
    ElMessage.error('上传失败，请确认文件格式正确')
  } finally {
    clearAction(platform)
  }
}

async function handleDelete(platform: string) {
  setAction(platform, 'delete')
  try {
    const res = await deletePlatformSession(platform)
    applySession(res.data)
    ElMessage.success('登录态已清除')
  } finally {
    clearAction(platform)
  }
}

onMounted(loadSessions)

defineExpose({ refresh: loadSessions })
</script>

<style scoped>
.session-panel {
  margin-top: 8px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.global-hint {
  margin-bottom: 16px;
}

.session-card {
  margin-bottom: 16px;
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
}

.session-desc {
  margin-bottom: 8px;
}

.session-alert {
  margin: 8px 0 12px;
}

.session-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.session-actions.secondary {
  align-items: center;
}
</style>
