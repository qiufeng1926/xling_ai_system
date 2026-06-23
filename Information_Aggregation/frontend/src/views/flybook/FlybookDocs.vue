<template>
  <div class="flybook-docs">
    <aside class="flybook-docs__sidebar">
      <div class="flybook-docs__sidebar-head">
        <h2>云文档</h2>
        <el-button
          type="primary"
          size="small"
          :loading="creating"
          :disabled="!bindStatus?.bound"
          @click="handleCreateDoc"
        >
          新建
        </el-button>
      </div>

      <el-alert
        v-if="!bindStatus?.bound"
        type="warning"
        :closable="false"
        show-icon
        title="尚未绑定飞书"
        class="flybook-docs__bind-alert"
      >
        <template #default>
          云文档需先绑定飞书账号并授权文档权限。
          <el-button link type="primary" :loading="binding" @click="handleBind">
            去绑定
          </el-button>
        </template>
      </el-alert>

      <el-alert
        v-else-if="needsDocsReauth"
        type="warning"
        :closable="false"
        show-icon
        title="需要重新授权云文档权限"
        class="flybook-docs__bind-alert"
      >
        <template #default>
          当前飞书绑定仅有消息权限，缺少云文档所需的 drive:drive、docx:document 等权限。
          请点击下方按钮重新授权（不会解除账号绑定关系）。
          <div class="flybook-docs__rebind-row">
            <el-button type="primary" size="small" :loading="binding" @click="handleBind">
              重新授权云文档
            </el-button>
          </div>
        </template>
      </el-alert>

      <el-skeleton v-if="loadingList" :rows="6" animated />
      <el-scrollbar v-else class="flybook-docs__list-wrap">
        <ul v-if="files.length" class="flybook-docs__list">
          <li
            v-for="file in files"
            :key="file.token"
            :class="{ active: selectedToken === file.token }"
            @click="openDocument(file)"
          >
            <span class="flybook-docs__file-icon">{{ fileIcon(file.type) }}</span>
            <span class="flybook-docs__file-name" :title="file.name">{{ file.name }}</span>
          </li>
        </ul>
        <el-empty v-else description="暂无文档，点击右上角新建" />
      </el-scrollbar>
    </aside>

    <section class="flybook-docs__editor">
      <div v-if="!selectedDocUrl" class="flybook-docs__placeholder">
        <p>从左侧选择文档，或新建一篇云文档开始编辑。</p>
        <p v-if="bindStatus?.bound && !bindStatus.token_valid" class="flybook-docs__hint">
          飞书授权可能已过期，请前往
          <router-link :to="FLYBOOK_ROUTES.messenger">飞书消息</router-link>
          重新绑定。
        </p>
      </div>
      <div v-else-if="mounting" class="flybook-docs__loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在加载编辑器…</span>
      </div>
      <div ref="mountRef" class="flybook-docs__mount" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import {
  createFeishuDoc,
  getDocsComponentAuth,
  getFeishuBindStatus,
  getFlybookConfig,
  isFeishuScopeMissingError,
  listDocsFiles,
  loadFeishuDocsSdk,
  startFeishuBind,
  type FeishuBindStatus,
  type FeishuDriveFile,
} from '@/api/flybook'
import { FLYBOOK_ROUTES } from '@/constants/routes'

const route = useRoute()
const router = useRouter()

const bindStatus = ref<FeishuBindStatus | null>(null)
const binding = ref(false)
const loadingList = ref(false)
const creating = ref(false)
const mounting = ref(false)
const files = ref<FeishuDriveFile[]>([])
const folderToken = ref('')
const docBaseUrl = ref('')
const sdkUrl = ref('')
const selectedToken = ref('')
const selectedDocUrl = ref('')
const needsDocsReauth = ref(false)
const mountRef = ref<HTMLElement | null>(null)

let docSdk: { destroy?: () => void; start: () => Promise<void> } | null = null

function fileIcon(type: string) {
  if (type === 'docx' || type === 'doc') return '文'
  if (type === 'sheet') return '表'
  if (type === 'bitable') return '库'
  return '档'
}

function buildDocUrl(file: FeishuDriveFile): string {
  if (file.url) return file.url
  const base = docBaseUrl.value.replace(/\/$/, '')
  if (file.type === 'docx' || file.type === 'doc') {
    return `${base}/docx/${file.token}`
  }
  return `${base}/${file.type}/${file.token}`
}

async function destroyEditor() {
  if (docSdk?.destroy) {
    try {
      docSdk.destroy()
    } catch {
      /* ignore */
    }
  }
  docSdk = null
  if (mountRef.value) {
    mountRef.value.innerHTML = ''
  }
}

async function mountEditor(docUrl: string) {
  if (!window.DocComponentSdk) {
    throw new Error('飞书云文档 SDK 未就绪')
  }
  await destroyEditor()
  mounting.value = true
  try {
    await nextTick()
    const mountEl = mountRef.value
    if (!mountEl) {
      throw new Error('编辑器容器未就绪，请重试')
    }
    const signUrl = `${window.location.origin}${window.location.pathname}`
    const auth = await getDocsComponentAuth(signUrl)
    docSdk = new window.DocComponentSdk({
      src: docUrl,
      mount: mountEl,
      size: {
        width: '100%',
        height: 'calc(100vh - 120px)',
        minHeight: '500px',
      },
      auth,
    })
    await docSdk.start()
  } finally {
    mounting.value = false
  }
}

async function openDocument(file: FeishuDriveFile) {
  if (file.type !== 'docx' && file.type !== 'doc') {
    ElMessage.info('当前仅支持在云文档组件中打开 docx 文档')
    return
  }
  const url = buildDocUrl(file)
  selectedToken.value = file.token
  selectedDocUrl.value = url
  await nextTick()
  try {
    await mountEditor(url)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '打开文档失败')
  }
}

async function loadFiles() {
  if (!bindStatus.value?.bound) {
    files.value = []
    return
  }
  if (!bindStatus.value.docs_authorized) {
    needsDocsReauth.value = true
    files.value = []
    return
  }
  loadingList.value = true
  try {
    const res = await listDocsFiles({ folder_token: folderToken.value })
    files.value = (res.files || []).filter((f) => f.type === 'docx' || f.type === 'doc')
    needsDocsReauth.value = false
  } catch (err) {
    files.value = []
    if (isFeishuScopeMissingError(err)) {
      needsDocsReauth.value = true
    }
  } finally {
    loadingList.value = false
  }
}

async function handleCreateDoc() {
  if (needsDocsReauth.value || !bindStatus.value?.docs_authorized) {
    ElMessage.warning('请先重新授权云文档权限')
    return
  }
  creating.value = true
  try {
    const doc = await createFeishuDoc(`xlink 文档 ${new Date().toLocaleString('zh-CN')}`, folderToken.value)
    const url = doc.url || `${docBaseUrl.value.replace(/\/$/, '')}/docx/${doc.document_id}`
    const file: FeishuDriveFile = {
      token: doc.document_id,
      name: doc.title || '未命名文档',
      type: 'docx',
      url,
    }
    files.value = [file, ...files.value]
    await openDocument(file)
    ElMessage.success('文档已创建')
  } catch (err) {
    if (isFeishuScopeMissingError(err)) {
      needsDocsReauth.value = true
    }
  } finally {
    creating.value = false
  }
}

async function handleBind() {
  binding.value = true
  try {
    const url = await startFeishuBind(FLYBOOK_ROUTES.docs)
    window.location.href = url
  } finally {
    binding.value = false
  }
}

function handleBindQuery() {
  const bind = String(route.query.bind || '')
  const bindError = String(route.query.bind_error || '')
  if (bind === 'success') {
    ElMessage.success('飞书绑定成功，正在加载文档列表')
    void initPage()
  } else if (bindError) {
    ElMessage.error('飞书绑定失败，请重试')
  }
  if (bind || bindError) {
    router.replace({ path: FLYBOOK_ROUTES.docs })
  }
}

async function initPage() {
  try {
    const statusRes = await getFeishuBindStatus()
    bindStatus.value = statusRes.data
  } catch {
    bindStatus.value = null
  }

  try {
    const cfg = await getFlybookConfig()
    docBaseUrl.value = cfg.doc_base_url
    sdkUrl.value = cfg.docs_component_sdk_url
    await loadFeishuDocsSdk(cfg.docs_component_sdk_url)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载飞书配置失败')
    return
  }

  if (bindStatus.value?.bound) {
    needsDocsReauth.value = !bindStatus.value.docs_authorized
    await loadFiles()
  }
}

onMounted(() => {
  handleBindQuery()
  if (!route.query.bind && !route.query.bind_error) {
    void initPage()
  }
})

onBeforeUnmount(() => {
  void destroyEditor()
})
</script>

<style scoped>
.flybook-docs {
  display: flex;
  gap: 0;
  min-height: calc(100vh - 120px);
  margin: -12px -16px;
  background: #f5f7fa;
}

.flybook-docs__sidebar {
  width: 280px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 120px);
}

.flybook-docs__sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #ebeef5;
}

.flybook-docs__sidebar-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.flybook-docs__bind-alert {
  margin: 12px;
}

.flybook-docs__rebind-row {
  margin-top: 8px;
}

.flybook-docs__list-wrap {
  flex: 1;
  padding: 8px 0;
}

.flybook-docs__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.flybook-docs__list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.flybook-docs__list li:hover,
.flybook-docs__list li.active {
  background: #ecf5ff;
}

.flybook-docs__file-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #3370ff;
  color: #fff;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.flybook-docs__file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: #303133;
}

.flybook-docs__editor {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  position: relative;
}

.flybook-docs__placeholder,
.flybook-docs__loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  gap: 8px;
  z-index: 1;
  pointer-events: none;
}

.flybook-docs__hint {
  font-size: 13px;
}

.flybook-docs__mount {
  flex: 1;
  width: 100%;
  height: calc(100vh - 120px);
  min-height: 500px;
}
</style>
