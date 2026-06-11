<template>
  <el-dialog
    v-model="visible"
    :title="`保存远程登录态 - ${session?.label || ''}`"
    width="640px"
    destroy-on-close
    @closed="cookieContent = ''"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="step-alert"
      title="请先在当前设备完成登录，再按以下步骤复制 Cookie"
    />

    <ol class="steps">
      <li>在已登录的页面按 <kbd>F12</kbd> 打开开发者工具</li>
      <li>切换到「网络 / Network」面板，刷新页面</li>
      <li>
        点击任意请求到
        <code>{{ hostHint }}</code>
        的记录
      </li>
      <li>在「请求头 / Request Headers」中找到 <code>Cookie</code>，复制整行值（不含 Cookie: 前缀也可）</li>
      <li>粘贴到下方文本框，点击保存</li>
    </ol>

    <el-input
      v-model="cookieContent"
      type="textarea"
      :rows="8"
      placeholder="粘贴 Cookie 值，例如：sessionid=xxx; token=yyy; ..."
    />

    <p class="extra-tip">
      也支持粘贴 Cookie-Editor 等插件导出的 JSON 数组，或 Playwright 的 storage_state.json 内容。
    </p>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!cookieContent.trim()" @click="handleSave">
        保存远程登录态
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { importPlatformCookies, type PlatformSessionStatus } from '@/api/collection'

const emit = defineEmits<{
  saved: [session: PlatformSessionStatus]
}>()

const visible = ref(false)
const saving = ref(false)
const cookieContent = ref('')
const session = ref<PlatformSessionStatus | null>(null)

const hostHint = computed(() => {
  if (session.value?.platform === 'xiaohongshu') {
    return 'pgy.xiaohongshu.com / xiaohongshu.com'
  }
  return 'xingtu.cn / douyin.com'
})

function open(target: PlatformSessionStatus) {
  session.value = target
  cookieContent.value = ''
  visible.value = true
}

async function handleSave() {
  if (!session.value) return
  saving.value = true
  try {
    const res = await importPlatformCookies(session.value.platform, cookieContent.value.trim())
    ElMessage.success('远程登录态已保存')
    emit('saved', res.data)
    visible.value = false
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(msg || '保存失败，请检查 Cookie 是否完整')
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.step-alert {
  margin-bottom: 12px;
}

.steps {
  margin: 0 0 16px 20px;
  padding: 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.8;
}

.steps code,
.extra-tip code {
  background: #f5f7fa;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}

kbd {
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  padding: 0 4px;
  font-size: 12px;
}

.extra-tip {
  margin: 10px 0 0;
  font-size: 12px;
  color: #909399;
}
</style>
