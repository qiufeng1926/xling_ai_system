import axios from 'axios'
import { ElMessage } from 'element-plus'

const meetingRequest = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

meetingRequest.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

meetingRequest.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error.response?.data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : error.response?.status === 401
          ? '会议服务认证失败，请确认 meeting_ai 与门户 JWT_SECRET 一致'
          : error.message || '会议服务请求失败'
    if (!error.config?.silent) {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  }
)

export default meetingRequest

export interface CollaborativeRoom {
  id: number
  room_code: string
  file_id: string
  host_username: string
  meeting_name: string
  status: string
  created_at?: string
  started_at?: string
  ended_at?: string
  merged_transcript?: string
}

export interface RoomParticipant {
  username: string
  nickname: string
  role: string
  joined_at?: string
  left_at?: string
}

export interface RoomInvitation {
  id: number
  invitee_username: string
  role: string
  status: string
  invited_by: string
}

export interface RoomState {
  success: boolean
  room: CollaborativeRoom
  my_role: string
  participants: RoomParticipant[]
  invitations: RoomInvitation[]
}

export function createRoom(meetingName: string) {
  return meetingRequest.post<{ success: boolean; room: CollaborativeRoom; my_role: string }>(
    '/meetings/rooms',
    { meeting_name: meetingName }
  )
}

export function listMyRooms(config?: { silent?: boolean }) {
  return meetingRequest.get<{
    success: boolean
    hosted: CollaborativeRoom[]
    joined: CollaborativeRoom[]
    pending_invitations: Array<RoomInvitation & { room: CollaborativeRoom }>
  }>('/meetings/rooms/mine', { silent: config?.silent } as object)
}

export function getRoom(roomCode: string) {
  return meetingRequest.get<RoomState>(`/meetings/rooms/${encodeURIComponent(roomCode)}`)
}

export function inviteToRoom(
  roomCode: string,
  invitees: Array<{ username: string; role: 'recorder' | 'viewer' }>
) {
  return meetingRequest.post(`/meetings/rooms/${encodeURIComponent(roomCode)}/invite`, { invitees })
}

export function acceptInvitation(roomCode: string) {
  return meetingRequest.post<RoomState>(`/meetings/rooms/${encodeURIComponent(roomCode)}/accept`)
}

export function joinRoom(roomCode: string) {
  return meetingRequest.post<RoomState>(`/meetings/rooms/${encodeURIComponent(roomCode)}/join`)
}

export function startRoom(roomCode: string) {
  return meetingRequest.post(`/meetings/rooms/${encodeURIComponent(roomCode)}/start`)
}

export function endRoom(roomCode: string) {
  return meetingRequest.post(`/meetings/rooms/${encodeURIComponent(roomCode)}/end`, null, {
    timeout: 180000,
  })
}

export interface RecoverRoomResult {
  success: boolean
  room: CollaborativeRoom
  file_id: string
  transcript_length?: number
  message?: string
}

/** 恢复卡在「结束中」的协作会议（合并转写并生成纪要，耗时较长） */
export function recoverRoom(roomCode: string) {
  return meetingRequest.post<RecoverRoomResult>(
    `/meetings/rooms/${encodeURIComponent(roomCode)}/recover`,
    null,
    { timeout: 180000 }
  )
}
