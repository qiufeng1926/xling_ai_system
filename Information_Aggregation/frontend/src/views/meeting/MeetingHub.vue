<template>
  <div class="meeting-hub">
    <div class="meeting-hub__header">
      <div>
        <h2>协作会议</h2>
        <p class="meeting-hub__desc">创建多人会议、邀请同事录音或观看，转写自动合并。</p>
      </div>
      <div class="meeting-hub__actions">
        <el-button @click="router.push(MEETING_ROUTES.records)">会议记录</el-button>
        <el-button @click="router.push(MEETING_ROUTES.solo)">单人录制</el-button>
        <el-button type="primary" @click="router.push('/meeting/create')">创建会议</el-button>
      </div>
    </div>

    <el-card v-if="pending.length" class="meeting-hub__section" shadow="never">
      <template #header>待接受邀请</template>
      <el-table :data="pending" size="small">
        <el-table-column prop="room.meeting_name" label="会议名称" />
        <el-table-column prop="room.room_code" label="房间码" width="100" />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">{{ roleLabel(row.role) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="primary" link @click="acceptInvite(row.room.room_code)">接受</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>我发起的</template>
          <el-empty v-if="!hosted.length" description="暂无会议" />
          <el-table v-else :data="hosted" size="small" @row-click="goRoom">
            <el-table-column prop="meeting_name" label="会议名称" />
            <el-table-column prop="room_code" label="房间码" width="90" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.status === 'ending'" type="warning" size="small">
                  {{ statusLabel(row.status) }}
                </el-tag>
                <span v-else>{{ statusLabel(row.status) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" @click.stop>
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'ending'"
                  type="warning"
                  link
                  :loading="recoveringCode === row.room_code"
                  @click.stop="handleRecover(row)"
                >
                  恢复纪要
                </el-button>
                <el-button
                  v-else-if="row.status === 'completed'"
                  type="primary"
                  link
                  @click.stop="goRecord(row.file_id)"
                >
                  查看记录
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>我参与的</template>
          <el-empty v-if="!joined.length" description="暂无会议" />
          <el-table v-else :data="joined" size="small" @row-click="goRoom">
            <el-table-column prop="meeting_name" label="会议名称" />
            <el-table-column prop="room_code" label="房间码" width="90" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">{{ statusLabel(row.status) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  acceptInvitation,
  listMyRooms,
  recoverRoom,
  type CollaborativeRoom,
  type RoomInvitation,
} from '@/api/meetingRooms'

import { MEETING_ROUTES } from '@/constants/routes'

const router = useRouter()
const hosted = ref<CollaborativeRoom[]>([])
const joined = ref<CollaborativeRoom[]>([])
const pending = ref<Array<RoomInvitation & { room: CollaborativeRoom }>>([])
const recoveringCode = ref('')

function statusLabel(status: string) {
  const map: Record<string, string> = {
    waiting: '等待中',
    live: '进行中',
    ending: '结束中',
    completed: '已完成',
    cancelled: '已取消',
  }
  return map[status] || status
}

function roleLabel(role: string) {
  return role === 'recorder' ? '录音员' : role === 'viewer' ? '观看者' : role
}

function goRoom(row: CollaborativeRoom) {
  router.push(`/meeting/room/${row.room_code}`)
}

function goRecord(fileId: string) {
  router.push(MEETING_ROUTES.recordDetail(fileId))
}

async function handleRecover(row: CollaborativeRoom) {
  await ElMessageBox.confirm(
    `会议「${row.meeting_name}」结束处理未完成，是否从已保存转写恢复并生成纪要？可能需要 1–3 分钟。`,
    '恢复会议',
    { type: 'warning' }
  )
  recoveringCode.value = row.room_code
  try {
    const res = await recoverRoom(row.room_code)
    ElMessage.success(res.message || '恢复成功')
    await loadData()
    if (res.file_id) {
      await ElMessageBox.confirm('是否前往查看会议记录？', '恢复成功', {
        confirmButtonText: '查看记录',
        cancelButtonText: '稍后',
        type: 'success',
      }).then(() => goRecord(res.file_id)).catch(() => {})
    }
  } finally {
    recoveringCode.value = ''
  }
}

async function acceptInvite(roomCode: string) {
  await acceptInvitation(roomCode)
  ElMessage.success('已接受邀请')
  router.push(`/meeting/room/${roomCode}`)
}

async function loadData() {
  const res = await listMyRooms()
  hosted.value = res.hosted || []
  joined.value = res.joined || []
  pending.value = res.pending_invitations || []
}

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  loadData().catch((err) => {
    ElMessage.error(err?.message || '加载会议列表失败，请确认会议服务已启动')
  })
  pollTimer = setInterval(() => {
    loadData().catch(() => {})
  }, 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.meeting-hub__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}
.meeting-hub__desc {
  margin: 4px 0 0;
  color: #909399;
  font-size: 14px;
}
.meeting-hub__actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.meeting-hub__section {
  margin-bottom: 16px;
}
:deep(.el-table__row) {
  cursor: pointer;
}
</style>
