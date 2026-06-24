<template>
  <div class="page-card">
    <h2 class="page-title">离职交接申请</h2>
    <p class="hint">
      提交申请后，在超级管理员完成交接前，您仅可使用本页面相关功能，其他系统功能将暂时不可用。
    </p>

    <el-alert v-if="pending" :type="pending.error_message ? 'error' : 'warning'" show-icon :closable="false" class="status-alert">
      <template #title>
        申请处理中（{{ statusLabel(pending.status) }}）
      </template>
      提交时间：{{ formatTime(pending.created_at) }}
      <span v-if="pending.reason"> · 原因：{{ pending.reason }}</span>
      <div v-if="pending.error_message" class="error-msg">
        上次交接失败：{{ pending.error_message }}。请联系超级管理员重试或取消申请。
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { applyOffboarding, getMyOffboarding, type OffboardingRecord } from '@/api/offboarding'

const pending = ref<OffboardingRecord | null>(null)
const submitting = ref(false)
const form = reactive({ reason: '', last_work_day: '' as string | undefined })

function formatTime(v: string) {
  return v?.replace('T', ' ').slice(0, 19)
}

function statusLabel(s: string) {
  return { pending: '待超管处理', processing: '交接中', completed: '已完成', cancelled: '已取消', failed: '失败' }[s] || s
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
.status-alert {
  margin-top: 12px;
}
.apply-form {
  max-width: 560px;
  margin-top: 16px;
}
.error-msg {
  margin-top: 8px;
  line-height: 1.5;
}
</style>
