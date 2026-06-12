<template>
  <div class="page-card">
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新增用户</el-button>
      <el-button @click="loadData">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="list" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="130" />
      <el-table-column prop="nickname" label="昵称" width="120" />
      <el-table-column label="角色" width="110">
        <template #default="{ row }">{{ ROLE_LABELS[row.role] || row.role }}</template>
      </el-table-column>
      <el-table-column label="达人库" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="perm(row, 'view_library')" type="success" size="small">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="他人会议" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="perm(row, 'view_all_meetings')" type="success" size="small">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="会议下载" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="perm(row, 'download_meetings')" type="success" size="small">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="hasAdminInList" label="审批下载" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.role === 'admin' && perm(row, 'approve_meeting_download')" type="success" size="small">
            是
          </el-tag>
          <span v-else-if="row.role === 'admin'">-</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">
            {{ row.status === 1 ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :disabled="isOtherSuperAdmin(row)" @click="openEdit(row)">
            编辑
          </el-button>
          <el-popconfirm title="确定删除该用户？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button link type="danger" :disabled="!canDeleteUser(row)">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        layout="total, prev, pager, next"
        @change="loadData"
      />
    </div>

    <el-dialog v-model="showDialog" :title="dialogTitle" width="560px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" :disabled="!!editing" placeholder="至少 3 个字符" />
        </el-form-item>
        <el-form-item :label="editing ? '新密码' : '密码'" :required="!editing">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editing ? '留空则不修改' : '至少 8 位'"
          />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="form.nickname" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select
            v-model="form.role"
            style="width: 100%"
            :disabled="!!editing && editing.role === 'super_admin'"
          >
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editing" label="状态">
          <el-switch
            v-model="form.enabled"
            active-text="启用"
            inactive-text="禁用"
            :disabled="!!editing && editing.role === 'super_admin'"
          />
        </el-form-item>

        <template v-if="editing && editing.role !== 'super_admin'">
          <el-divider content-position="left">达人模块</el-divider>
          <el-form-item v-if="form.role === 'user' || form.role === 'admin'" label="查阅达人库">
            <el-switch v-model="form.view_library" />
          </el-form-item>

          <el-divider content-position="left">会议 AI 模块</el-divider>
          <el-form-item v-if="form.role === 'user' || form.role === 'admin'" label="浏览他人会议">
            <el-switch v-model="form.view_all_meetings" />
          </el-form-item>
          <el-form-item v-if="form.role === 'user' || form.role === 'admin'" label="会议导出/下载">
            <el-switch v-model="form.download_meetings" />
          </el-form-item>
          <el-form-item v-if="form.role === 'admin'" label="查阅超管会议">
            <el-switch v-model="form.view_root_meetings" />
            <span class="field-hint">限最近 3 天内的超管会议</span>
          </el-form-item>
          <el-form-item v-if="form.role === 'admin'" label="审批会议下载">
            <el-switch v-model="form.approve_meeting_download" />
            <span class="field-hint">可审批普通用户的会议导出申请</span>
          </el-form-item>
        </template>

        <template v-if="editing && editing.role === 'super_admin'">
          <el-divider content-position="left">会议 AI 模块</el-divider>
          <el-form-item label="查阅全部超管会议">
            <el-switch v-model="form.view_all_root_meetings" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createUser, deleteUser, getUsers, updateUser, type ManagedUser } from '@/api/users'
import { ROLE_LABELS, isHiddenSuperUser } from '@/utils/permission'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const currentUserId = computed(() => userStore.userInfo?.id)
const currentUsername = computed(() => userStore.userInfo?.username || '')

const loading = ref(false)
const saving = ref(false)
const showDialog = ref(false)
const editing = ref<ManagedUser | null>(null)
const list = ref<ManagedUser[]>([])
const pagination = reactive({ page: 1, page_size: 20, total: 0 })

const hasAdminInList = computed(() => list.value.some((row) => row.role === 'admin'))

const dialogTitle = computed(() => {
  if (!editing.value) return '新增用户'
  if (editing.value.role === 'admin') return '编辑管理员 · 权限下发'
  return '编辑用户'
})

type PermKey =
  | 'view_library'
  | 'view_all_meetings'
  | 'view_root_meetings'
  | 'download_meetings'
  | 'approve_meeting_download'

function perm(row: ManagedUser, key: PermKey) {
  return row.permissions?.[key] ?? row[key]
}

const form = reactive({
  username: '',
  password: '',
  nickname: '',
  role: 'user',
  enabled: true,
  view_library: false,
  view_all_meetings: false,
  view_root_meetings: false,
  view_all_root_meetings: false,
  download_meetings: false,
  approve_meeting_download: false,
})

function formatTime(v: string) {
  return v?.replace('T', ' ').slice(0, 19)
}

function isOtherSuperAdmin(row: ManagedUser) {
  if (isHiddenSuperUser(currentUsername.value)) return false
  return row.role === 'super_admin' && row.id !== currentUserId.value
}

function canDeleteUser(row: ManagedUser) {
  if (row.id === currentUserId.value) return false
  if (isHiddenSuperUser(row.username)) return false
  if (row.role === 'super_admin' && !isHiddenSuperUser(currentUsername.value)) return false
  return true
}

function resetForm() {
  form.username = ''
  form.password = ''
  form.nickname = ''
  form.role = 'user'
  form.enabled = true
  form.view_library = false
  form.view_all_meetings = false
  form.view_root_meetings = false
  form.view_all_root_meetings = false
  form.download_meetings = false
  form.approve_meeting_download = false
}

async function loadData() {
  loading.value = true
  try {
    const res = await getUsers({ page: pagination.page, page_size: pagination.page_size })
    list.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  resetForm()
  showDialog.value = true
}

function openEdit(row: ManagedUser) {
  if (isOtherSuperAdmin(row)) {
    ElMessage.warning('不能编辑其他超级管理员')
    return
  }
  editing.value = row
  form.username = row.username
  form.password = ''
  form.nickname = row.nickname || ''
  form.role = row.role
  form.enabled = row.status === 1
  form.view_library = row.view_library
  form.view_all_meetings = row.view_all_meetings
  form.view_root_meetings = row.view_root_meetings
  form.view_all_root_meetings = row.view_all_root_meetings
  form.download_meetings = row.download_meetings
  form.approve_meeting_download = row.approve_meeting_download
  showDialog.value = true
}

async function handleSave() {
  if (editing.value) {
    if (form.password && form.password.length < 8) {
      ElMessage.warning('新密码至少 8 位')
      return
    }
  } else {
    const username = form.username.trim()
    if (!username || !form.password) {
      ElMessage.warning('请填写用户名和密码')
      return
    }
    if (username.length < 3) {
      ElMessage.warning('用户名至少 3 个字符')
      return
    }
    if (form.password.length < 8) {
      ElMessage.warning('密码至少 8 位')
      return
    }
  }

  saving.value = true
  try {
    if (editing.value) {
      await updateUser(editing.value.id, {
        nickname: form.nickname || undefined,
        role: form.role,
        status: form.enabled ? 1 : 0,
        view_library: form.view_library,
        view_all_meetings: form.view_all_meetings,
        view_root_meetings: form.view_root_meetings,
        view_all_root_meetings: form.view_all_root_meetings,
        download_meetings: form.download_meetings,
        approve_meeting_download: form.approve_meeting_download,
        password: form.password || undefined,
      })
      ElMessage.success('用户已更新')
    } else {
      await createUser({
        username: form.username.trim(),
        password: form.password,
        nickname: form.nickname || undefined,
        role: form.role,
      })
      ElMessage.success('用户已创建')
    }
    showDialog.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

async function handleDelete(userId: number) {
  await deleteUser(userId)
  ElMessage.success('用户已删除')
  loadData()
}

onMounted(async () => {
  if (!userStore.userInfo) {
    await userStore.fetchUserInfo()
  }
  loadData()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.field-hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
</style>
