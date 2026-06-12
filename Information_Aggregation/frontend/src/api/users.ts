import request, { type ApiResponse, type PageResult } from './request'

export interface ManagedUser {
  id: number
  username: string
  nickname: string | null
  role: string
  status: number
  view_library: boolean
  view_all_meetings: boolean
  view_root_meetings: boolean
  view_all_root_meetings: boolean
  download_meetings: boolean
  approve_meeting_download: boolean
  approve_meeting_view: boolean
  permissions?: Record<string, boolean>
  created_at: string
}

export function getUsers(params: { page?: number; page_size?: number }) {
  return request.get<any, ApiResponse<PageResult<ManagedUser>>>('/users', { params })
}

export function createUser(data: {
  username: string
  password: string
  nickname?: string
  role: string
}) {
  return request.post<any, ApiResponse<ManagedUser>>('/users', data)
}

export function updateUser(
  userId: number,
  data: Partial<{
    nickname: string
    role: string
    status: number
    view_library: boolean
    view_all_meetings: boolean
    view_root_meetings: boolean
    view_all_root_meetings: boolean
    download_meetings: boolean
    approve_meeting_download: boolean
    approve_meeting_view: boolean
    password: string
  }>
) {
  return request.put<any, ApiResponse<ManagedUser>>(`/users/${userId}`, data)
}

export function deleteUser(userId: number) {
  return request.delete<any, ApiResponse<null>>(`/users/${userId}`)
}

export interface UserSearchHit {
  id: number
  username: string
  nickname: string
}

export function searchUsers(keyword: string, limit = 10) {
  return request.get<any, ApiResponse<UserSearchHit[]>>('/users/search', {
    params: { keyword, limit },
  })
}
