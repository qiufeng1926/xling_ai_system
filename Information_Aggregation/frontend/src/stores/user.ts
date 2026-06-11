import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMe, login as loginApi, register as registerApi, type UserInfo } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfo | null>(null)

  async function login(username: string, password: string) {
    const res = await loginApi(username, password)
    token.value = res.data.access_token
    localStorage.setItem('token', token.value)
    await fetchUserInfo()
  }

  async function register(data: {
    username: string
    nickname: string
    password: string
    password_confirm: string
  }) {
    const res = await registerApi(data)
    token.value = res.data.access_token
    localStorage.setItem('token', token.value)
    await fetchUserInfo()
  }

  async function fetchUserInfo() {
    if (!token.value) return
    const res = await getMe()
    userInfo.value = res.data
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('authToken')
  }

  return { token, userInfo, login, register, fetchUserInfo, logout }
})
