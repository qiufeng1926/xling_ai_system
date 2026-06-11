<template>
  <div class="meeting-room">
    <el-page-header @back="router.push('/meeting')">
      <template #content>
        {{ room?.meeting_name || '会议房间' }}
        <el-tag v-if="room" size="small" class="meeting-room__code">{{ room.room_code }}</el-tag>
      </template>
    </el-page-header>

    <el-skeleton v-if="loading" :rows="4" animated class="meeting-room__skeleton" />

    <template v-else-if="room">
      <div class="meeting-room__toolbar">
        <el-tag :type="statusTagType">{{ statusLabel(room.status) }}</el-tag>
        <span class="meeting-room__role">我的角色：{{ roleLabel(myRole) }}</span>
        <div class="meeting-room__toolbar-actions">
          <el-button
            v-if="myRole === 'host' && room.status === 'waiting'"
            type="primary"
            :loading="actionLoading"
            @click="handleStart"
          >
            开始会议
          </el-button>
          <el-button
            v-if="myRole === 'host' && room.status === 'live'"
            type="danger"
            :loading="actionLoading"
            @click="handleEnd"
          >
            结束会议
          </el-button>
          <el-button v-if="myRole === 'host'" @click="showInvite = true">邀请成员</el-button>
        </div>
      </div>

      <el-row :gutter="16" class="meeting-room__body">
        <el-col :span="8">
          <el-card shadow="never">
            <template #header>参与者</template>
            <el-empty v-if="!participants.length" description="暂无在线参与者" />
            <ul v-else class="meeting-room__participants">
              <li v-for="p in participants" :key="p.username">
                <strong>{{ p.nickname || p.username }}</strong>
                <el-tag size="small">{{ roleLabel(p.role) }}</el-tag>
                <el-tag v-if="p.is_recording" type="danger" size="small">录音中</el-tag>
              </li>
            </ul>
          </el-card>

          <el-card v-if="myRole === 'host' && invitations.length" shadow="never" class="meeting-room__invites">
            <template #header>邀请状态</template>
            <ul class="meeting-room__invites-list">
              <li v-for="inv in invitations" :key="inv.id">
                {{ inv.invitee_username }}
                <el-tag size="small">{{ inv.status }}</el-tag>
              </li>
            </ul>
          </el-card>
        </el-col>

        <el-col :span="16">
          <div class="meeting-room__embed-wrap">
            <iframe
              v-if="embedUrl"
              class="meeting-room__iframe"
              :src="embedUrl"
              title="会议录制"
              allow="microphone; autoplay"
            />
          </div>
        </el-col>
      </el-row>
    </template>

    <el-dialog v-model="showInvite" title="邀请成员" width="480px">
      <el-select
        v-model="inviteSelected"
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
      <div v-if="inviteSelected.length" class="meeting-room__invite-roles">
        <div v-for="u in inviteSelected" :key="u.username" class="meeting-room__role-row">
          <span>{{ u.nickname }}</span>
          <el-radio-group v-model="inviteRoles[u.username]" size="small">
            <el-radio-button value="recorder">录音员</el-radio-button>
            <el-radio-button value="viewer">观看者</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <template #footer>
        <el-button @click="showInvite = false">取消</el-button>
        <el-button type="primary" :loading="inviteLoading" @click="submitInvite">发送邀请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getRoom,
  inviteToRoom,
  joinRoom,
  startRoom,
  endRoom,
  type RoomInvitation,
  type RoomParticipant,
  type CollaborativeRoom,
} from '@/api/meetingRooms'
import { searchUsers, type UserSearchHit } from '@/api/users'

interface OnlineParticipant extends RoomParticipant {
  is_recording?: boolean
  online?: boolean
}

const route = useRoute()
const router = useRouter()
const roomCode = computed(() => String(route.params.roomCode || '').toUpperCase())

const loading = ref(true)
const actionLoading = ref(false)
const room = ref<CollaborativeRoom | null>(null)
const myRole = ref('viewer')
const participants = ref<OnlineParticipant[]>([])
const invitations = ref<RoomInvitation[]>([])

const showInvite = ref(false)
const inviteSelected = ref<UserSearchHit[]>([])
const searchResults = ref<UserSearchHit[]>([])
const searchLoading = ref(false)
const inviteLoading = ref(false)
const inviteRoles = reactive<Record<string, 'recorder' | 'viewer'>>({})

const embedUrl = computed(() => {
  if (!room.value || !myRole.value) return ''
  const base = import.meta.env.VITE_MEETING_APP_PATH || '/meeting-app/'
  const sep = base.includes('?') ? '&' : '?'
  const params = new URLSearchParams({
    embedded: '1',
    collab: '1',
    room_code: room.value.room_code,
    role: myRole.value,
    meeting_name: room.value.meeting_name,
  })
  return `${base}${sep}${params.toString()}`
})

const statusTagType = computed(() => {
  const s = room.value?.status
  if (s === 'live') return 'success'
  if (s === 'waiting') return 'info'
  if (s === 'completed') return ''
  return 'warning'
})

function statusLabel(status: string) {
  const map: Record<string, string> = {
    waiting: '等待中',
    live: '进行中',
    ending: '结束中',
    completed: '已完成',
  }
  return map[status] || status
}

function roleLabel(role: string) {
  const map: Record<string, string> = {
    host: '主持人',
    recorder: '录音员',
    viewer: '观看者',
  }
  return map[role] || role
}

async function loadRoom() {
  loading.value = true
  try {
    const joinRes = await joinRoom(roomCode.value)
    room.value = joinRes.room
    myRole.value = joinRes.my_role || 'viewer'
    participants.value = joinRes.participants || []
    invitations.value = joinRes.invitations || []
  } catch (err: unknown) {
    try {
      const res = await getRoom(roomCode.value)
      room.value = res.room
      myRole.value = res.my_role || 'viewer'
      participants.value = res.participants || []
      invitations.value = res.invitations || []
    } catch {
      const msg = err instanceof Error ? err.message : '无法进入会议'
      ElMessage.error(msg)
    }
  } finally {
    loading.value = false
  }
}

async function handleStart() {
  actionLoading.value = true
  try {
    await startRoom(roomCode.value)
    ElMessage.success('会议已开始')
    await loadRoom()
  } finally {
    actionLoading.value = false
  }
}

async function handleEnd() {
  await ElMessageBox.confirm('确定结束会议？将合并所有录音并生成纪要。', '结束会议', {
    type: 'warning',
  })
  actionLoading.value = true
  try {
    await endRoom(roomCode.value)
    ElMessage.success('会议已结束')
    await loadRoom()
  } finally {
    actionLoading.value = false
  }
}

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
      if (!inviteRoles[u.username]) inviteRoles[u.username] = 'recorder'
    }
  } finally {
    searchLoading.value = false
  }
}

async function submitInvite() {
  if (!inviteSelected.value.length) {
    ElMessage.warning('请选择要邀请的用户')
    return
  }
  inviteLoading.value = true
  try {
    await inviteToRoom(
      roomCode.value,
      inviteSelected.value.map((u) => ({
        username: u.username,
        role: inviteRoles[u.username] || 'recorder',
      }))
    )
    ElMessage.success('邀请已发送')
    showInvite.value = false
    inviteSelected.value = []
    await loadRoom()
  } finally {
    inviteLoading.value = false
  }
}

onMounted(() => {
  loadRoom().catch(() => {})
})
</script>

<style scoped>
.meeting-room__code {
  margin-left: 8px;
  vertical-align: middle;
}
.meeting-room__skeleton {
  margin-top: 24px;
}
.meeting-room__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0 16px;
  flex-wrap: wrap;
}
.meeting-room__role {
  color: #606266;
  font-size: 14px;
}
.meeting-room__toolbar-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.meeting-room__body {
  margin-top: 0;
}
.meeting-room__participants,
.meeting-room__invites-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.meeting-room__participants li,
.meeting-room__invites-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #ebeef5;
}
.meeting-room__invites {
  margin-top: 12px;
}
.meeting-room__embed-wrap {
  height: calc(100vh - 220px);
  min-height: 480px;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
}
.meeting-room__iframe {
  width: 100%;
  height: 100%;
  border: none;
}
.meeting-room__invite-roles {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.meeting-room__role-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
