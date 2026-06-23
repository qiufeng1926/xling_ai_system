<template>
  <div class="page-card">
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <el-statistic title="达人总数" :value="stats.influencerTotal" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="待审核" :value="stats.pendingReview">
          <template #suffix>
            <el-button link type="primary" @click="$router.push(INFLUENCER_ROUTES.review)">去审核</el-button>
          </template>
        </el-statistic>
      </el-col>
      <el-col :span="6">
        <el-statistic title="今日采集" :value="stats.todayCollected" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="任务成功率" :value="stats.successRate" suffix="%" />
      </el-col>
    </el-row>

    <el-divider />

    <CollectionSessionPanel v-if="showSessions" />

    <el-divider v-if="showSessions" />

    <el-alert
      v-if="stats.runningTaskId"
      type="warning"
      :closable="false"
      show-icon
      :title="`采集任务 #${stats.runningTaskId} 正在执行，队列中还有 ${stats.queuedTasks} 个任务等待`"
      style="margin-bottom: 16px"
    />

    <div class="welcome">
      <h3>欢迎使用 xlink · 达人信息管理</h3>
      <p>{{ welcomeText }}</p>
      <el-space wrap>
        <el-button type="primary" @click="$router.push(INFLUENCER_ROUTES.collection)">发起采集</el-button>
        <el-button type="success" @click="$router.push(INFLUENCER_ROUTES.review)">待审核列表</el-button>
        <el-button v-if="showAdminActions" type="warning" @click="$router.push(INFLUENCER_ROUTES.match)">智能匹配</el-button>
        <el-button @click="$router.push(INFLUENCER_ROUTES.influencers)">{{ influencerBtnLabel }}</el-button>
        <el-button v-if="showAdminActions" @click="$router.push(INFLUENCER_ROUTES.tags)">标签管理</el-button>
        <el-button v-if="showAdminActions" @click="$router.push(INFLUENCER_ROUTES.agencies)">MCN机构</el-button>
        <el-button v-if="showUserManage" @click="$router.push(INFLUENCER_ROUTES.users)">用户管理</el-button>
        <el-button v-if="showAccessReview" @click="$router.push(INFLUENCER_ROUTES.accessReview)">权限审核</el-button>
      </el-space>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'

defineOptions({ name: 'Dashboard' })
import CollectionSessionPanel from '@/components/CollectionSessionPanel.vue'
import { getCollectionStats } from '@/api/collection'
import { getInfluencers } from '@/api/influencer'
import { useUserStore } from '@/stores/user'
import { INFLUENCER_ROUTES } from '@/constants/routes'
import {
  canManageSessions,
  canManageUsers,
  canReviewAccess,
  canUseMatch,
  isUser,
} from '@/utils/permission'

const userStore = useUserStore()
const showSessions = computed(() => canManageSessions(userStore.userInfo?.role))
const showAdminActions = computed(() => canUseMatch(userStore.userInfo?.role))
const showUserManage = computed(() => canManageUsers(userStore.userInfo?.role))
const showAccessReview = computed(() => canReviewAccess(userStore.userInfo?.role))
const influencerBtnLabel = computed(() => (isUser(userStore.userInfo?.role) ? '我的达人' : '达人库'))
const welcomeText = computed(() =>
  isUser(userStore.userInfo?.role)
    ? '您可以使用自动采集、审核自己的采集结果，并在「我的达人」中查看已通过审核的达人。'
    : '采集前请在工作台配置星图 / 蒲公英登录态；管理员可在「权限审核」中审批普通用户的查阅申请。'
)

const stats = reactive({
  influencerTotal: 0,
  pendingReview: 0,
  todayCollected: 0,
  successRate: 100,
  runningTaskId: null as number | null,
  queuedTasks: 0,
})

async function loadStats() {
  const [influencers, collection] = await Promise.all([
    getInfluencers({ page: 1, page_size: 1 }),
    getCollectionStats(),
  ])
  stats.influencerTotal = influencers.data.total
  stats.pendingReview = collection.data.pending_review
  stats.todayCollected = collection.data.today_collected
  stats.successRate = collection.data.success_rate
  stats.runningTaskId = collection.data.running_task_id
  stats.queuedTasks = collection.data.queued_tasks
}

onMounted(async () => {
  await userStore.fetchUserInfo()
  loadStats()
})
</script>

<style scoped>
.stats-row {
  margin-bottom: 8px;
}

.welcome h3 {
  margin-top: 0;
}

.welcome p {
  color: #606266;
}
</style>
