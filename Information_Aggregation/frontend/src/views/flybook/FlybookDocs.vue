<template>
  <div class="flybook-docs">
    <aside class="flybook-docs__sidebar">
      <div class="flybook-docs__sidebar-head">
        <div>
          <h2>云文档</h2>
          <p v-if="portalLabel" class="flybook-docs__account">
            xlink：{{ portalLabel }}
            <span v-if="bindStatus?.bound"> · 飞书：{{ bindStatus.feishu_name || '已绑定' }}</span>
          </p>
        </div>
        <div class="flybook-docs__head-actions">
          <el-dropdown trigger="click" :disabled="!bindStatus?.bound || creating || importing" @command="handleCreateCommand">
            <el-button type="primary" size="small" :loading="creating" :disabled="!bindStatus?.bound || importing">
              新建
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="item in createTypes"
                  :key="item.type"
                  :command="item.type"
                >
                  {{ item.label }}
                  <span v-if="!item.embed_editable" class="flybook-docs__ext-hint">（飞书页打开）</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button
            size="small"
            :loading="importing"
            :disabled="!bindStatus?.bound || creating"
            @click="triggerUpload"
          >
            上传
          </el-button>
          <input
            ref="fileInputRef"
            type="file"
            class="flybook-docs__file-input"
            :accept="uploadAccept"
            @change="handleFileInputChange"
          />
        </div>
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
          云文档按 xlink 账号隔离，请绑定<strong>您本人</strong>的飞书账号（当前：{{ portalLabel || '未登录' }}）。
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
          当前飞书绑定缺少云文档权限（如 drive:drive、docx:document、docs:document:import 等）。
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
            <span
              class="flybook-docs__file-icon"
              :class="`flybook-docs__file-icon--${file.type}`"
            >{{ fileIcon(file.type) }}</span>
            <span class="flybook-docs__file-name" :title="file.name">{{ file.name }}</span>
          </li>
        </ul>
        <el-empty v-else description="暂无云文档，可新建或上传本地文件" />
      </el-scrollbar>
    </aside>

    <section class="flybook-docs__editor">
      <div v-if="!selectedDocUrl" class="flybook-docs__placeholder">
        <p>从左侧选择文件，或新建云文档开始。</p>
        <p class="flybook-docs__hint">支持上传 Word / Excel / CSV / Markdown 等（≤20MB），导入后 docx 可内嵌编辑。</p>
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

    <el-dialog v-model="importDialogVisible" title="选择导入类型" width="420px" :close-on-click-modal="!importing">
      <p v-if="pendingImportFile" class="flybook-docs__import-name">
        文件：{{ pendingImportFile.name }}
      </p>
      <el-radio-group v-model="importTargetType">
        <el-radio v-for="t in importTargetOptions" :key="t" :value="t">
          {{ typeLabel(t) }}
        </el-radio>
      </el-radio-group>
      <template #footer>
        <el-button :disabled="importing" @click="cancelImportDialog">取消</el-button>
        <el-button type="primary" :loading="importing" @click="confirmImport">开始导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, Loading } from '@element-plus/icons-vue'
import {
  createFeishuFile,
  getDocsComponentAuth,
  getDocsCreateTypes,
  getFeishuBindStatus,
  getFlybookConfig,
  getFlybookErrorMessage,
  getImportFormats,
  importFeishuFile,
  isFeishuScopeMissingError,
  listDocsFiles,
  loadFeishuDocsSdk,
  startFeishuBind,
  suggestImportTarget,
  type FeishuBindStatus,
  type FeishuCreateType,
  type FeishuDriveFile,
  type FeishuFileCreated,
  type FeishuImportFormats,
} from '@/api/flybook'
import { FLYBOOK_ROUTES } from '@/constants/routes'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const portalLabel = computed(() => {
  const fromStatus = bindStatus.value?.portal_nickname || bindStatus.value?.portal_username
  if (fromStatus) return fromStatus
  return userStore.userInfo?.nickname || userStore.userInfo?.username || ''
})

const bindStatus = ref<FeishuBindStatus | null>(null)
const binding = ref(false)
const loadingList = ref(false)
const creating = ref(false)
const importing = ref(false)
const mounting = ref(false)
const files = ref<FeishuDriveFile[]>([])
const createTypes = ref<FeishuCreateType[]>([
  { type: 'docx', label: '文档', embed_editable: true },
  { type: 'sheet', label: '表格', embed_editable: false },
  { type: 'bitable', label: '多维表格', embed_editable: false },
  { type: 'slides', label: '幻灯片', embed_editable: false },
  { type: 'mindnote', label: '思维笔记', embed_editable: false },
])
const folderToken = ref('')
const docBaseUrl = ref('')
const sdkUrl = ref('')
const selectedToken = ref('')
const selectedDocUrl = ref('')
const needsDocsReauth = ref(false)
const mountRef = ref<HTMLElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const importFormats = ref<FeishuImportFormats | null>(null)
const importDialogVisible = ref(false)
const importTargetType = ref('')
const importTargetOptions = ref<string[]>([])
const pendingImportFile = ref<File | null>(null)

const uploadAccept = computed(() => {
  const targets = importFormats.value?.targets
  if (!targets?.length) return ''
  const exts = new Set<string>()
  for (const t of targets) {
    for (const ext of t.extensions) exts.add(ext)
  }
  return Array.from(exts)
    .map((ext) => `.${ext}`)
    .join(',')
})

let docSdk: { destroy?: () => void; start: () => Promise<void> } | null = null

function fileIcon(type: string) {
  if (type === 'docx' || type === 'doc') return '文'
  if (type === 'sheet') return '表'
  if (type === 'bitable') return '库'
  if (type === 'slides') return '演'
  if (type === 'mindnote') return '脑'
  if (type === 'file') return '件'
  return '档'
}

function typeLabel(type: string) {
  return createTypes.value.find((t) => t.type === type)?.label || type
}

function isEmbedEditable(type: string) {
  return type === 'docx' || type === 'doc'
}

function buildDocUrl(file: FeishuDriveFile): string {
  if (file.url) return file.url
  const base = docBaseUrl.value.replace(/\/$/, '')
  const paths: Record<string, string> = {
    docx: 'docx',
    doc: 'docx',
    sheet: 'sheets',
    bitable: 'base',
    slides: 'slides',
    mindnote: 'mindnote',
    file: 'file',
  }
  const path = paths[file.type] || file.type
  return `${base}/${path}/${file.token}`
}

function openInFeishu(url: string, label: string) {
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) {
    ElMessage.success(`已在飞书打开${label}`)
  } else {
    ElMessage.warning('浏览器拦截了弹窗，请允许本站打开新窗口')
  }
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
  const url = buildDocUrl(file)
  selectedToken.value = file.token

  if (!isEmbedEditable(file.type)) {
    selectedDocUrl.value = ''
    await destroyEditor()
    openInFeishu(url, typeLabel(file.type))
    return
  }

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
    files.value = res.files || []
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

async function openCreatedFile(created: FeishuFileCreated) {
  const file: FeishuDriveFile = {
    token: created.token,
    name: created.title || '未命名',
    type: created.type,
    url: created.url,
    embed_editable: created.embed_editable,
  }
  files.value = [file, ...files.value.filter((f) => f.token !== file.token)]
  await openDocument(file)
}

function triggerUpload() {
  if (needsDocsReauth.value || !bindStatus.value?.docs_authorized) {
    ElMessage.warning('请先重新授权云文档权限')
    return
  }
  fileInputRef.value?.click()
}

function resetFileInput() {
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function cancelImportDialog() {
  if (importing.value) return
  importDialogVisible.value = false
  pendingImportFile.value = null
  resetFileInput()
}

async function runImport(file: File, targetType: string) {
  importing.value = true
  try {
    const created = await importFeishuFile(file, targetType, { folderToken: folderToken.value })
    if (created.import_warnings?.length) {
      ElMessage.warning(`导入完成：${created.import_warnings.join('；')}`)
    } else {
      ElMessage.success('导入成功')
    }
    await openCreatedFile(created)
  } catch (err) {
    if (isFeishuScopeMissingError(err)) {
      needsDocsReauth.value = true
    } else {
      ElMessage.error(getFlybookErrorMessage(err, '导入失败'))
    }
  } finally {
    importing.value = false
    pendingImportFile.value = null
    importDialogVisible.value = false
    resetFileInput()
  }
}

async function handleFileInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const maxBytes = importFormats.value?.max_size_bytes ?? 20 * 1024 * 1024
  if (file.size > maxBytes) {
    ElMessage.error(`文件超过 ${Math.floor(maxBytes / (1024 * 1024))}MB 上限`)
    resetFileInput()
    return
  }

  try {
    const suggest = await suggestImportTarget(file.name)
    if (!suggest.targets.length) {
      ElMessage.error('不支持的文件格式')
      resetFileInput()
      return
    }
    if (suggest.targets.length === 1 || suggest.default_target) {
      await runImport(file, suggest.default_target || suggest.targets[0])
      return
    }
    pendingImportFile.value = file
    importTargetOptions.value = suggest.targets
    importTargetType.value = suggest.targets[0]
    importDialogVisible.value = true
  } catch (err) {
    ElMessage.error(getFlybookErrorMessage(err, '无法识别导入类型'))
    resetFileInput()
  }
}

async function confirmImport() {
  if (!pendingImportFile.value || !importTargetType.value) return
  await runImport(pendingImportFile.value, importTargetType.value)
}

async function handleCreateCommand(fileType: string) {
  if (needsDocsReauth.value || !bindStatus.value?.docs_authorized) {
    ElMessage.warning('请先重新授权云文档权限')
    return
  }
  const label = typeLabel(fileType)
  creating.value = true
  try {
    const created = await createFeishuFile(
      fileType,
      `xlink ${label} ${new Date().toLocaleString('zh-CN')}`,
      folderToken.value
    )
    await openCreatedFile(created)
    ElMessage.success(`${label}已创建`)
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
    try {
      const typesRes = await getDocsCreateTypes()
      if (typesRes.types?.length) {
        createTypes.value = typesRes.types
      }
    } catch {
      /* 使用默认 createTypes */
    }
    try {
      importFormats.value = await getImportFormats()
    } catch {
      /* 使用默认 accept / 大小限制 */
    }
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
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #ebeef5;
  gap: 12px;
}

.flybook-docs__head-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
}

.flybook-docs__file-input {
  display: none;
}

.flybook-docs__import-name {
  margin: 0 0 12px;
  font-size: 13px;
  color: #606266;
  word-break: break-all;
}

.flybook-docs__sidebar-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.flybook-docs__account {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
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

.flybook-docs__file-icon--sheet { background: #34c724; }
.flybook-docs__file-icon--bitable { background: #7b61ff; }
.flybook-docs__file-icon--slides { background: #ff8800; }
.flybook-docs__file-icon--mindnote { background: #14c0ff; }
.flybook-docs__file-icon--file { background: #8f959e; }

.flybook-docs__ext-hint {
  margin-left: 4px;
  font-size: 12px;
  color: #909399;
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
