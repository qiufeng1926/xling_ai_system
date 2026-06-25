<template>
  <el-container class="layout-container">
    <el-aside width="240px" class="layout-aside">
      <div class="logo">xlink</div>
      <el-menu
        :default-active="activeMenu"
        :default-openeds="defaultOpeneds"
        router
        background-color="#001529"
        text-color="#fff"
        active-text-color="#409eff"
      >
        <el-sub-menu index="module-influencer">
          <template #title>
            <el-icon><DataAnalysis /></el-icon>
            <span>达人信息管理</span>
          </template>
          <el-menu-item :index="INFLUENCER_ROUTES.dashboard">
            <el-icon><Odometer /></el-icon>
            <span>工作台</span>
          </el-menu-item>
          <el-menu-item :index="INFLUENCER_ROUTES.collection">
            <el-icon><Search /></el-icon>
            <span>自动采集</span>
          </el-menu-item>
          <el-menu-item :index="INFLUENCER_ROUTES.review">
            <el-icon><Checked /></el-icon>
            <span>待审核</span>
          </el-menu-item>
          <el-menu-item :index="INFLUENCER_ROUTES.influencers">
            <el-icon><User /></el-icon>
            <span>{{ influencerMenuLabel }}</span>
          </el-menu-item>
          <el-menu-item v-if="showAdminMenus" :index="INFLUENCER_ROUTES.tags">
            <el-icon><CollectionTag /></el-icon>
            <span>标签管理</span>
          </el-menu-item>
          <el-menu-item v-if="showAdminMenus" :index="INFLUENCER_ROUTES.agencies">
            <el-icon><OfficeBuilding /></el-icon>
            <span>MCN机构</span>
          </el-menu-item>
          <el-menu-item v-if="showAdminMenus" :index="INFLUENCER_ROUTES.match">
            <el-icon><Connection /></el-icon>
            <span>智能匹配</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="!isOffboardingPending" index="module-meeting">
          <template #title>
            <el-icon><Microphone /></el-icon>
            <span>会议 AI</span>
          </template>
          <el-menu-item :index="MEETING_ROUTES.home">
            <el-icon><VideoCamera /></el-icon>
            <span class="menu-item-with-badge">
              协作会议
              <el-badge v-if="pendingInviteCount > 0" :value="pendingInviteCount" class="menu-badge" />
            </span>
          </el-menu-item>
          <el-menu-item :index="MEETING_ROUTES.solo">
            <el-icon><Microphone /></el-icon>
            <span>单人录制</span>
          </el-menu-item>
          <el-menu-item :index="MEETING_ROUTES.records">
            <el-icon><Document /></el-icon>
            <span>会议记录</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-flybook">
          <template #title>
            <el-icon><ChatDotRound /></el-icon>
            <span>飞书</span>
          </template>
          <el-menu-item :index="FLYBOOK_ROUTES.messenger">
            <el-icon><ChatDotRound /></el-icon>
            <span>飞书消息</span>
          </el-menu-item>
          <el-menu-item :index="FLYBOOK_ROUTES.docs">
            <el-icon><Document /></el-icon>
            <span>云文档</span>
          </el-menu-item>
          <el-menu-item :index="FLYBOOK_ROUTES.docLibrary">
            <el-icon><FolderOpened /></el-icon>
            <span>文档库</span>
          </el-menu-item>
          <el-menu-item :index="FLYBOOK_ROUTES.minutesAi">
            <el-icon><Microphone /></el-icon>
            <span>妙纪 AI</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="showAdminMenus" index="module-qywechat">
          <template #title>
            <el-icon><Comment /></el-icon>
            <span>企微</span>
          </template>
          <el-menu-item :index="QYWECHAT_ROUTES.mail">
            <el-icon><Message /></el-icon>
            <span>企微邮箱</span>
          </el-menu-item>
          <el-menu-item :index="QYWECHAT_ROUTES.approval">
            <el-icon><Stamp /></el-icon>
            <span>企微审批</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-platform">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>平台管理</span>
          </template>
          <el-menu-item v-if="showUserManage" :index="INFLUENCER_ROUTES.users">
            <el-icon><UserFilled /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item v-if="showUserManage" :index="INFLUENCER_ROUTES.offboardingManage">
            <el-icon><Switch /></el-icon>
            <span>离职交接</span>
          </el-menu-item>
          <el-menu-item
            v-if="showOffboardingApply"
            :index="INFLUENCER_ROUTES.offboardingApply"
          >
            <el-icon><DocumentRemove /></el-icon>
            <span>离职申请</span>
          </el-menu-item>
          <el-menu-item v-if="showHandoverMenu" :index="INFLUENCER_ROUTES.offboardingHandover">
            <el-icon><CircleCheck /></el-icon>
            <span class="menu-item-with-badge">
              交接文档
              <el-badge v-if="handoverTaskCount > 0" :value="handoverTaskCount" class="menu-badge" />
            </span>
          </el-menu-item>
          <el-menu-item v-if="showAccessReview" :index="INFLUENCER_ROUTES.accessReview">
            <el-icon><Stamp /></el-icon>
            <span class="menu-item-with-badge">
              {{ accessMenuLabel }}
              <el-badge
                v-if="accessBadgeCount > 0"
                :value="accessBadgeCount"
                class="menu-badge"
              />
            </span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="layout-header">
        <div class="header-title">{{ currentTitle }}</div>
        <div class="header-right">
          <el-button
            v-if="pendingAccessReviewCount > 0"
            type="warning"
            link
            @click="router.push(INFLUENCER_ROUTES.accessReview)"
          >
            {{ pendingAccessReviewCount }} 条权限申请待审批
          </el-button>
          <el-button
            v-if="myPendingAccessCount > 0"
            type="warning"
            link
            @click="router.push(INFLUENCER_ROUTES.accessReview)"
          >
            您有 {{ myPendingAccessCount }} 条权限申请待审核
          </el-button>
          <el-button
            v-if="pendingInviteCount > 0 && !isOffboardingPending"
            type="primary"
            link
            @click="router.push(MEETING_ROUTES.home)"
          >
            {{ pendingInviteCount }} 条会议邀请待处理
          </el-button>
          <el-tag v-if="roleLabel" size="small" type="info">{{ roleLabel }}</el-tag>
          <span class="username">{{ userStore.userInfo?.nickname || userStore.userInfo?.username }}</span>
          <el-button link type="primary" @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="layout-main">
        <router-view v-slot="{ Component }">
          <keep-alive :include="['Dashboard', 'CollectionTasks', 'ReviewQueue', 'InfluencerList']">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { listMyRooms } from '@/api/meetingRooms'
import { getAccessRequestStats } from '@/api/permissions'
import { getMeetingViewRequestStats } from '@/api/meetings'
import { getFeishuDocumentAccessStats } from '@/api/feishuDocuments'
import { getHandoverArchive, getMyHandoverTasks } from '@/api/offboarding'
import { useUserNotifications } from '@/composables/useUserNotifications'
import {
  ROLE_LABELS,
  canManageUsers,
  canReviewAccess,
  canReviewMeetingDownload,
  canReviewMeetingView,
  canUseMatch,
  isSuperAdmin,
  isUser,
  normalizeRole,
} from '@/utils/permission'
import { AUTH_ROUTES, FLYBOOK_ROUTES, INFLUENCER_ROUTES, MEETING_ROUTES, QYWECHAT_ROUTES } from '@/constants/routes'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/influencer/influencers')) return INFLUENCER_ROUTES.influencers
  if (path.startsWith('/influencer/collection')) return INFLUENCER_ROUTES.collection
  if (path.startsWith('/influencer/review')) return INFLUENCER_ROUTES.review
  if (path.startsWith('/influencer/tags')) return INFLUENCER_ROUTES.tags
  if (path.startsWith('/influencer/match')) return INFLUENCER_ROUTES.match
  if (path.startsWith('/influencer/agencies')) return INFLUENCER_ROUTES.agencies
  if (path.startsWith('/influencer/users')) return INFLUENCER_ROUTES.users
  if (path.startsWith('/influencer/offboarding-manage')) return INFLUENCER_ROUTES.offboardingManage
  if (path.startsWith('/influencer/offboarding-handover')) return INFLUENCER_ROUTES.offboardingHandover
  if (path.startsWith('/influencer/offboarding-apply')) return INFLUENCER_ROUTES.offboardingApply
  if (path.startsWith('/influencer/access-review')) return INFLUENCER_ROUTES.accessReview
  if (path.startsWith('/meeting/solo')) return MEETING_ROUTES.solo
  if (path.startsWith('/meeting/records')) return MEETING_ROUTES.records
  if (path.startsWith('/meeting/create')) return MEETING_ROUTES.create
  if (path.startsWith('/meeting/room')) return MEETING_ROUTES.home
  if (path.startsWith('/meeting')) return MEETING_ROUTES.home
  if (path.startsWith('/flybook/minutes-ai')) return FLYBOOK_ROUTES.minutesAi
  if (path.startsWith('/flybook/doc-library')) return FLYBOOK_ROUTES.docLibrary
  if (path.startsWith('/flybook/docs')) return FLYBOOK_ROUTES.docs
  if (path.startsWith('/flybook') || path.startsWith('/feishu')) return FLYBOOK_ROUTES.messenger
  if (path.startsWith('/qywechat/mail') || path.startsWith('/wecom/mail')) return QYWECHAT_ROUTES.mail
  if (path.startsWith('/qywechat/approval') || path.startsWith('/wecom/approval')) return QYWECHAT_ROUTES.approval
  if (path.startsWith('/qywechat') || path.startsWith('/wecom')) return QYWECHAT_ROUTES.mail
  if (path.startsWith('/influencer/dashboard')) return INFLUENCER_ROUTES.dashboard
  return path
})

const defaultOpeneds = computed(() => {
  if (route.path.startsWith('/meeting')) {
    return ['module-meeting']
  }
  if (route.path.startsWith('/qywechat') || route.path.startsWith('/wecom')) {
    return ['module-qywechat']
  }
  if (route.path.startsWith('/flybook') || route.path.startsWith('/feishu')) {
    return ['module-flybook']
  }
  if (route.path.startsWith('/influencer/users') || route.path.startsWith('/influencer/access-review') || route.path.startsWith('/influencer/offboarding')) {
    return ['module-platform']
  }
  return ['module-influencer']
})

const currentTitle = computed(() => {
  if (route.path.startsWith('/influencer/influencers') && isUser(userStore.userInfo?.role)) {
    return '我的达人'
  }
  return (route.meta.title as string) || 'xlink'
})

const role = computed(() => normalizeRole(userStore.userInfo?.role))
const roleLabel = computed(() => ROLE_LABELS[role.value] || role.value)
const showAdminMenus = computed(() => canUseMatch(role.value))
const showUserManage = computed(() => canManageUsers(role.value))
const showOffboardingApply = computed(
  () => !isSuperAdmin(userStore.userInfo?.role) && userStore.userInfo?.account_status !== 'offboarded'
)
const isOffboardingPending = computed(() => userStore.userInfo?.account_status === 'offboarding')
const showAccessReview = computed(
  () => canReviewAccess(role.value) || isUser(userStore.userInfo?.role)
)
const accessMenuLabel = computed(() => (isUser(userStore.userInfo?.role) ? '权限申请' : '权限审核'))
const influencerMenuLabel = computed(() => (isUser(userStore.userInfo?.role) ? '我的达人' : '达人库'))

const pendingInviteCount = ref(0)
const pendingAccessReviewCount = ref(0)
const myPendingAccessCount = ref(0)
const handoverTaskCount = ref(0)
const handoverArchiveCount = ref(0)
const showHandoverMenu = computed(
  () => showUserManage.value || handoverTaskCount.value > 0 || handoverArchiveCount.value > 0
)

const accessBadgeCount = computed(() => {
  if (canReviewAccess(role.value)) return pendingAccessReviewCount.value
  return myPendingAccessCount.value
})

async function refreshPendingInvites() {
  if (!userStore.token) {
    pendingInviteCount.value = 0
    return
  }
  try {
    const res = await listMyRooms()
    pendingInviteCount.value = res.pending_invitations?.length || 0
  } catch {
    // meeting 服务不可用时静默忽略
  }
}

async function refreshAccessRequestStats() {
  if (!userStore.token) {
    pendingAccessReviewCount.value = 0
    myPendingAccessCount.value = 0
    return
  }
  try {
    const res = await getAccessRequestStats()
    pendingAccessReviewCount.value = res.data.pending_for_review || 0
    myPendingAccessCount.value = res.data.my_pending || 0
    try {
      const meetingStats = await getMeetingViewRequestStats()
      myPendingAccessCount.value += meetingStats.my_pending || 0
      if (
        canReviewAccess(userStore.userInfo?.role) ||
        canReviewMeetingView(userStore.userInfo?.role, userStore.userInfo?.permissions) ||
        canReviewMeetingDownload(userStore.userInfo?.role, userStore.userInfo?.permissions)
      ) {
        pendingAccessReviewCount.value += meetingStats.pending_for_review || 0
      }
    } catch {
      // meeting 服务不可用时静默忽略
    }
    try {
      const docStats = await getFeishuDocumentAccessStats()
      myPendingAccessCount.value += docStats.data.my_pending || 0
      if (
        canReviewAccess(userStore.userInfo?.role) ||
        canReviewMeetingView(userStore.userInfo?.role, userStore.userInfo?.permissions) ||
        canReviewMeetingDownload(userStore.userInfo?.role, userStore.userInfo?.permissions)
      ) {
        pendingAccessReviewCount.value += docStats.data.pending_for_review || 0
      }
    } catch {
      // 飞书文档服务不可用时静默忽略
    }
  } catch {
    pendingAccessReviewCount.value = 0
    myPendingAccessCount.value = 0
  }
}

async function refreshHandoverTasks() {
  if (!userStore.token || isOffboardingPending.value) {
    handoverTaskCount.value = 0
    handoverArchiveCount.value = 0
    return
  }
  try {
    const [pendingRes, archiveRes] = await Promise.all([getMyHandoverTasks(), getHandoverArchive()])
    handoverTaskCount.value = pendingRes.data?.length || 0
    handoverArchiveCount.value = archiveRes.data?.length || 0
  } catch {
    handoverTaskCount.value = 0
    handoverArchiveCount.value = 0
  }
}

onMounted(() => {
  userStore.fetchUserInfo()
  refreshPendingInvites()
  refreshAccessRequestStats()
  refreshHandoverTasks()
})

useUserNotifications(async () => {
  await Promise.all([refreshPendingInvites(), refreshAccessRequestStats(), refreshHandoverTasks()])
})

function handleLogout() {
  userStore.logout()
  router.push(AUTH_ROUTES.login)
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}

.layout-aside {
  background: #001529;
}

.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.08em;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.username {
  color: #606266;
}

.menu-item-with-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.menu-badge :deep(.el-badge__content) {
  border: none;
}

.layout-main {
  background: #f5f7fa;
}

:deep(.el-sub-menu__title),
:deep(.el-menu-item) {
  height: 46px;
  line-height: 46px;
}
</style>
