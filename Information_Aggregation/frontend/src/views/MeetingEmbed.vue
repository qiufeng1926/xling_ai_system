<template>

  <div class="meeting-embed">

    <el-empty v-if="!userStore.token" description="请先在 xlink 平台登录后再使用会议 AI">

      <el-button type="primary" @click="goLogin">去登录</el-button>

    </el-empty>

    <template v-else>

      <div v-if="loading" class="meeting-embed__loading">

        <el-icon class="is-loading" :size="28"><Loading /></el-icon>

        <span>正在加载会议 AI…</span>

      </div>

      <el-alert

        v-if="loadError"

        type="warning"

        :closable="false"

        show-icon

        title="会议服务未就绪"

        description="请确认 meeting_ai 后端已启动（默认端口 8001），且 JWT_SECRET 与达人后端 SECRET_KEY 一致。"

      />

      <iframe

        v-show="!loadError"

        :key="userStore.token"

        ref="frameRef"

        class="meeting-embed__frame"

        :src="meetingAppUrl"

        title="会议 AI"

        allow="microphone; autoplay"

        @load="onFrameLoad"

      />

    </template>

  </div>

</template>



<script setup lang="ts">

import { computed, ref, watch } from 'vue'

import { useRouter } from 'vue-router'

import { Loading } from '@element-plus/icons-vue'

import { useUserStore } from '@/stores/user'

import { AUTH_ROUTES } from '@/constants/routes'



const router = useRouter()

const userStore = useUserStore()

const loading = ref(true)

const loadError = ref(false)

const frameRef = ref<HTMLIFrameElement | null>(null)



const meetingAppUrl = computed(() => {

  const base = import.meta.env.VITE_MEETING_APP_PATH || '/meeting-app/'

  const sep = base.includes('?') ? '&' : '?'

  return `${base}${sep}embedded=1&v=20260630`

})



function onFrameLoad() {

  loading.value = false

  try {

    const doc = frameRef.value?.contentDocument

    if (doc?.body?.innerText) {

      loadError.value = false

    }

  } catch {

    // 同源 iframe

  }

}



function goLogin() {

  router.push(AUTH_ROUTES.login)

}



watch(

  () => userStore.token,

  () => {

    loading.value = true

    loadError.value = false

  }

)



setTimeout(() => {

  if (loading.value) {

    loading.value = false

  }

}, 15000)

</script>



<style scoped>

.meeting-embed {

  position: relative;

  height: calc(100vh - 120px);

  min-height: 480px;

  background: #fff;

  border-radius: 8px;

  overflow: hidden;

}



.meeting-embed__frame {

  width: 100%;

  height: 100%;

  border: none;

  display: block;

}



.meeting-embed__loading {

  position: absolute;

  inset: 0;

  z-index: 1;

  display: flex;

  flex-direction: column;

  align-items: center;

  justify-content: center;

  gap: 12px;

  color: #909399;

  background: #fff;

}

</style>


