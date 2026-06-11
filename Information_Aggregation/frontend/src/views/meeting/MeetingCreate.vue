<template>
  <div class="meeting-create">
    <el-page-header @back="router.push('/meeting')">
      <template #content>创建协作会议</template>
    </el-page-header>

    <el-form class="meeting-create__form" label-width="100px" @submit.prevent="submit">
      <el-form-item label="会议名称" required>
        <el-input v-model="meetingName" placeholder="请输入会议名称" maxlength="255" />
      </el-form-item>

      <el-form-item label="邀请成员">
        <el-select
          v-model="selectedUsers"
          multiple
          filterable
          remote
          reserve-keyword
          placeholder="搜索用户名或昵称"
          :remote-method="searchRemoteUsers"
          :loading="searchLoading"
          value-key="username"
          style="width: 100%"
        >
          <el-option
            v-for="u in searchResults"
            :key="u.username"
            :label="`${u.nickname} (${u.username})`"
            :value="u"
          />
        </el-select>
      </el-form-item>

      <el-form-item v-if="selectedUsers.length" label="角色">
        <div class="meeting-create__roles">
          <div v-for="u in selectedUsers" :key="u.username" class="meeting-create__role-row">
            <span>{{ u.nickname }} ({{ u.username }})</span>
            <el-radio-group v-model="roles[u.username]" size="small">
              <el-radio-button value="recorder">录音员</el-radio-button>
              <el-radio-button value="viewer">观看者</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">创建并进入</el-button>
        <el-button @click="router.push('/meeting')">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createRoom, inviteToRoom } from '@/api/meetingRooms'
import { searchUsers, type UserSearchHit } from '@/api/users'

const router = useRouter()
const meetingName = ref('')
const selectedUsers = ref<UserSearchHit[]>([])
const searchResults = ref<UserSearchHit[]>([])
const searchLoading = ref(false)
const submitting = ref(false)
const roles = reactive<Record<string, 'recorder' | 'viewer'>>({})

async function searchRemoteUsers(keyword: string) {
  if (!keyword.trim()) {
    searchResults.value = []
    return
  }
  searchLoading.value = true
  try {
    const res = await searchUsers(keyword.trim(), 15)
    searchResults.value = res.data || []
    for (const u of searchResults.value) {
      if (!roles[u.username]) roles[u.username] = 'recorder'
    }
  } finally {
    searchLoading.value = false
  }
}

async function submit() {
  const name = meetingName.value.trim()
  if (!name) {
    ElMessage.warning('请填写会议名称')
    return
  }
  submitting.value = true
  try {
    const created = await createRoom(name)
    const roomCode = created.room.room_code
    if (selectedUsers.value.length) {
      await inviteToRoom(
        roomCode,
        selectedUsers.value.map((u) => ({
          username: u.username,
          role: roles[u.username] || 'recorder',
        }))
      )
    }
    ElMessage.success('会议已创建')
    router.push(`/meeting/room/${roomCode}`)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.meeting-create {
  max-width: 720px;
}
.meeting-create__form {
  margin-top: 24px;
}
.meeting-create__roles {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}
.meeting-create__role-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
</style>
