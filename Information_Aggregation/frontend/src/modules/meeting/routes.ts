import type { RouteRecordRaw } from 'vue-router'

export const meetingRoutes: RouteRecordRaw[] = [
  {
    path: '',
    name: 'MeetingHub',
    component: () => import('@/views/meeting/MeetingHub.vue'),
    meta: { title: '协作会议', module: 'meeting' },
  },
  {
    path: 'create',
    name: 'MeetingCreate',
    component: () => import('@/views/meeting/MeetingCreate.vue'),
    meta: { title: '创建会议', module: 'meeting' },
  },
  {
    path: 'room/:roomCode',
    name: 'MeetingRoom',
    component: () => import('@/views/meeting/MeetingRoom.vue'),
    meta: { title: '会议房间', module: 'meeting' },
  },
  {
    path: 'solo',
    name: 'MeetingSolo',
    component: () => import('@/views/MeetingEmbed.vue'),
    meta: { title: '单人录制', module: 'meeting' },
  },
  {
    path: 'records',
    name: 'MeetingHistory',
    component: () => import('@/views/meeting/MeetingHistory.vue'),
    meta: { title: '会议记录', module: 'meeting' },
  },
  {
    path: 'records/:fileId',
    name: 'MeetingRecordDetail',
    component: () => import('@/views/meeting/MeetingRecordDetail.vue'),
    meta: { title: '会议详情', module: 'meeting' },
  },
]
