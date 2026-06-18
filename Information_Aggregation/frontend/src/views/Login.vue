<template>
  <div class="login-page">
    <el-card class="login-card" shadow="hover">
      <h2>xlink</h2>
      <p class="subtitle">统一业务平台 · 登录或注册后使用</p>

      <div class="auth-tabs">
        <button type="button" class="auth-tab" :class="{ active: tab === 'login' }" @click="tab = 'login'">
          登录
        </button>
        <button
          v-if="allowRegister"
          type="button"
          class="auth-tab"
          :class="{ active: tab === 'register' }"
          @click="tab = 'register'"
        >
          注册
        </button>
      </div>

      <el-form
        v-if="tab === 'login'"
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input v-model="loginForm.username" placeholder="用户名" prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            prefix-icon="Lock"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="handleLogin">
          登录
        </el-button>
      </el-form>

      <el-form
        v-else
        ref="registerFormRef"
        :model="registerForm"
        :rules="registerRules"
        @submit.prevent="handleRegister"
      >
        <el-form-item prop="nickname">
          <el-input v-model="registerForm.nickname" placeholder="昵称（支持中文）" prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="username">
          <el-input v-model="registerForm.username" placeholder="用户名（登录用，至少 3 个字符）" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="registerForm.password"
            type="password"
            placeholder="密码（至少 8 位）"
            prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item prop="password_confirm">
          <el-input
            v-model="registerForm.password_confirm"
            type="password"
            placeholder="确认密码"
            prefix-icon="Lock"
            size="large"
            show-password
            @keyup.enter="handleRegister"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="handleRegister">
          注册
        </el-button>
      </el-form>

      <p v-if="tab === 'register'" class="hint">注册后为普通用户，模块权限可在平台内申请或由管理员下发</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { INFLUENCER_ROUTES } from '@/constants/routes'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()
const loading = ref(false)
const tab = ref<'login' | 'register'>('login')
const allowRegister = import.meta.env.VITE_ALLOW_REGISTER !== 'false'

const loginForm = reactive({
  username: '',
  password: '',
})

const registerForm = reactive({
  nickname: '',
  username: '',
  password: '',
  password_confirm: '',
})

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const registerRules: FormRules = {
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名至少 3 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  password_confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

async function handleLogin() {
  const valid = await loginFormRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await userStore.login(loginForm.username, loginForm.password)
    router.push(INFLUENCER_ROUTES.dashboard)
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  const valid = await registerFormRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await userStore.register({
      username: registerForm.username.trim(),
      nickname: registerForm.nickname.trim(),
      password: registerForm.password,
      password_confirm: registerForm.password_confirm,
    })
    ElMessage.success('注册成功')
    router.push(INFLUENCER_ROUTES.dashboard)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (route.query.tab === 'register' && allowRegister) {
    tab.value = 'register'
  }
})
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
  padding: 20px;
}

h2 {
  margin: 0 0 8px;
  text-align: center;
}

.subtitle {
  margin: 0 0 20px;
  text-align: center;
  color: #909399;
  font-size: 14px;
}

.auth-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.auth-tab {
  flex: 1;
  padding: 10px 0;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  color: #606266;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.auth-tab.active {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
}

.submit-btn {
  width: 100%;
}

.hint {
  margin: 16px 0 0;
  text-align: center;
  color: #909399;
  font-size: 12px;
}
</style>
