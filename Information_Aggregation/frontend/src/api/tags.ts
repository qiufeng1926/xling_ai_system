import request, { type ApiResponse } from './request'

export interface Tag {
  id: number
  name: string
  category: string | null
  parent_id: number | null
  level: number
  influencer_count?: number
  children?: Tag[]
}

export const TAG_CATEGORY_MAP: Record<string, string> = {
  content: '内容类',
  style: '风格类',
  business: '商业类',
  source: '来源类',
}

export function getTags(params?: { category?: string; tree?: boolean }) {
  return request.get<any, ApiResponse<Tag[]>>('/tags', { params })
}

export function getTagCategories() {
  return request.get<any, ApiResponse<Record<string, string>>>('/tags/categories')
}

export function createTag(data: {
  name: string
  category?: string
  parent_id?: number | null
  level?: number
}) {
  return request.post<any, ApiResponse<Tag>>('/tags', data)
}

export function updateTag(
  id: number,
  data: Partial<{ name: string; category: string; parent_id: number | null; level: number }>
) {
  return request.put<any, ApiResponse<Tag>>(`/tags/${id}`, data)
}

export function deleteTag(id: number) {
  return request.delete<any, ApiResponse<null>>(`/tags/${id}`)
}

export function attachInfluencerTags(
  influencerId: number,
  data: { tag_ids?: number[]; tag_names?: string[] }
) {
  return request.post<any, ApiResponse<{ attached: number }>>(
    `/tags/influencers/${influencerId}/attach`,
    data
  )
}

export function setInfluencerTags(influencerId: number, tagIds: number[]) {
  return request.put<any, ApiResponse<null>>(`/tags/influencers/${influencerId}`, {
    tag_ids: tagIds,
  })
}

export function detachInfluencerTag(influencerId: number, tagId: number) {
  return request.delete<any, ApiResponse<null>>(`/tags/influencers/${influencerId}/${tagId}`)
}

export function formatTagCategory(category: string | null) {
  if (!category) return '未分类'
  return TAG_CATEGORY_MAP[category] || category
}

export function categoryTagType(category: string | null) {
  const map: Record<string, string> = {
    content: '',
    style: 'success',
    business: 'warning',
    source: 'info',
  }
  return map[category || ''] || 'info'
}
