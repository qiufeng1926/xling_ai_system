import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { AUTH_ROUTES } from '@/constants/routes'

const FIELD_LABELS: Record<string, string> = {
  username: '用户名',
  password: '密码',
  nickname: '昵称',
  role: '角色',
}

function formatApiError(detail: unknown): string {
  if (!detail) return '请求失败'
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          const loc = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : ''
          const label = typeof loc === 'string' ? FIELD_LABELS[loc] || loc : ''
          const msg = String(item.msg)
          if (msg.includes('at least 3 characters')) return `${label || '用户名'}至少 3 个字符`
          if (msg.includes('at least 8 characters')) return `${label || '密码'}至少 8 位`
          return label ? `${label}：${msg}` : msg
        }
        return '请求参数错误'
      })
      .join('；')
  }
  return '请求失败'
}

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => {
    const res = response.data
    if (res.code !== 0) {
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    return res
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      router.push(AUTH_ROUTES.login)
    }
    if (!error.config?.silent) {
      ElMessage.error(formatApiError(error.response?.data?.detail) || error.message || '网络错误')
    }
    return Promise.reject(error)
  }
)

export default request

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
