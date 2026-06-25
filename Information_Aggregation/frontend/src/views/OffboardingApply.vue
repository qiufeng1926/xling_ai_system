<template>
  <div class="page-card">
    <h2 class="page-title">离职交接申请</h2>
    <p class="hint">
      提交申请后，在超级管理员完成最终批准前，您仅可使用本页面相关功能。
    </p>

    <el-steps v-if="pending" :active="stepActive" finish-status="success" align-center class="steps">
      <el-step title="提交申请" />
      <el-step title="指定交接人" />
      <el-step title="上传交接文档" />
      <el-step title="交接人确认" />
      <el-step title="超管批准" />
    </el-steps>

    <el-alert
      v-if="pending && pending.status !== 'awaiting_documents'"
      :type="pending.error_message ? 'error' : 'info'"
      show-icon
      :closable="false"
      class="status-alert"
    >
      <template #title>当前进度：{{ statusLabel(pending.status) }}</template>
      <div v-if="pending.handover_nickname">交接人：{{ pending.handover_nickname }} (@{{ pending.handover_username }})</div>
      <div v-if="pending.error_message" class="error-msg">失败原因：{{ pending.error_message }}</div>
    </el-alert>

    <template v-if="pending?.status === 'awaiting_documents'">
      <el-alert type="warning" show-icon :closable="false" class="status-alert">
        <template #title>请上传交接文档</template>
        超管已指定交接人：<strong>{{ pending.handover_nickname || pending.handover_username }}</strong>。
        请上传工作交接文档后提交。
      </el-alert>
      <el-form label-width="100px" class="apply-form">
        <el-form-item label="交接说明">
          <el-input v-model="docNote" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="交接文档" required>
          <el-upload
            v-model:file-list="fileList"
            :auto-upload="false"
            multiple
            :limit="10"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.zip,.png,.jpg,.jpeg"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <div class="upload-tip">支持 PDF/Office/文本/图片/ZIP，单文件不超过 20MB，最多 10 个</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmitDocs">提交交接文档</el-button>
        </el-form-item>
      </el-form>
    </template>

    <el-alert
      v-else-if="pending"
      :type="pending.error_message ? 'error' : 'warning'"
      show-icon
      :closable="false"
      class="status-alert"
    >
      <template #title>申请处理中（{{ statusLabel(pending.status) }}）</template>
      提交时间：{{ formatTime(pending.created_at) }}
      <span v-if="pending.reason"> · 原因：{{ pending.reason }}</span>
      <div v-if="pending.documents?.length" class="doc-list">
        已上传文档：
        <el-button
          v-for="d in pending.documents"
          :key="d.id"
          link
          type="primary"
          @click="downloadDoc(d.id, d.filename)"
        >
          {{ d.filename }}
        </el-button>
      </div>
    </el-alert>

    <el-form v-else label-width="100px" class="apply-form">
      <el-form-item label="离职原因">
        <el-input v-model="form.reason" type="textarea" :rows="3" maxlength="500" show-word-limit />
      </el-form-item>
      <el-form-item label="最后工作日">
        <el-date-picker v-model="form.last_work_day" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="handleApply">提交申请</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import {
  applyOffboarding,
  downloadOffboardingDocument,
  getMyOffboarding,
  OFFBOARDING_STATUS_LABELS,
  submitOffboardingDocuments,
  type OffboardingRecord,
} from '@/api/offboarding'

const pending = ref<OffboardingRecord | null>(null)
const submitting = ref(false)
const form = reactive({ reason: '', last_work_day: '' as string | undefined })
const docNote = ref('')
const fileList = ref<UploadUserFile[]>([])

const stepActive = computed(() => {
  if (!pending.value) return 0
  const map: Record<string, number> = {
    pending: 1,
    awaiting_documents: 2,
    awaiting_handover_confirm: 3,
    awaiting_final_approval: 4,
    processing: 4,
    failed: 4,
    completed: 5,
  }
  return map[pending.value.status] ?? 1
})

function formatTime(v: string) {
  return v?.replace('T', ' ').slice(0, 19)
}

function statusLabel(s: string) {
  return OFFBOARDING_STATUS_LABELS[s] || s
}

async function load() {
  const res = await getMyOffboarding()
  pending.value = res.data
}

async function handleApply() {
  await ElMessageBox.confirm('确定提交离职交接申请？提交后将限制其他功能的使用。', '确认')
  submitting.value = true
  try {
    const res = await applyOffboarding({
      reason: form.reason || undefined,
      last_work_day: form.last_work_day || undefined,
    })
    pending.value = res.data
    ElMessage.success('申请已提交')
  } finally {
    submitting.value = false
  }
}

async function handleSubmitDocs() {
  const files = fileList.value.map((f) => f.raw).filter(Boolean) as File[]
  if (!files.length) {
    ElMessage.warning('请至少选择一个文件')
    return
  }
  await ElMessageBox.confirm('确定提交交接文档？提交后将由交接人确认。', '确认')
  submitting.value = true
  try {
    const res = await submitOffboardingDocuments(pending.value!.id, files, docNote.value || undefined)
    pending.value = res.data
    fileList.value = []
    ElMessage.success('交接文档已提交')
  } finally {
    submitting.value = false
  }
}

async function downloadDoc(docId: number, filename: string) {
  try {
    await downloadOffboardingDocument(docId, filename)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-title {
  margin: 0 0 8px;
}
.hint {
  color: #909399;
  margin-bottom: 20px;
}
.steps {
  margin-bottom: 24px;
}
.status-alert {
  margin-top: 12px;
}
.apply-form {
  max-width: 560px;
  margin-top: 16px;
}
.error-msg,
.doc-list {
  margin-top: 8px;
  line-height: 1.5;
}
.upload-tip {
  color: #909399;
  font-size: 12px;
}
</style>
