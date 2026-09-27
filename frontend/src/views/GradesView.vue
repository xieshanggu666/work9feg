<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getExamStats, getLeaderboard } from '@/api/grades'
import { useAuthStore } from '@/stores/auth'
import type { ExamStats, LeaderboardItem } from '@/types'

const route = useRoute()
const examId = Number(route.params.examId)
const auth = useAuthStore()

const stats = ref<ExamStats | null>(null)
const leaderboard = ref<LeaderboardItem[]>([])
const loading = ref(true)
const errorMsg = ref('')

onMounted(async () => {
  try {
    // 排行榜无需特殊权限；统计接口需要登录
    const [s, board] = await Promise.all([
      getExamStats(examId),
      getLeaderboard(examId, 20),
    ])
    stats.value = s
    leaderboard.value = board
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '暂无统计数据（可能还没有考生提交）'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <h2>📈 成绩统计 - 考试 #{{ examId }}</h2>

  <div v-if="loading" class="loading">加载中...</div>

  <template v-else>
    <div v-if="errorMsg" class="card">
      <div class="muted">{{ errorMsg }}</div>
    </div>

    <template v-if="stats">
      <div class="card-grid">
        <div class="card stat-card">
          <div class="stat-num">{{ stats.attempt_count }}</div>
          <div class="stat-label">参考人次</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.avg_score.toFixed(1) }}</div>
          <div class="stat-label">平均分</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.max_score }}</div>
          <div class="stat-label">最高分</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.pass_rate.toFixed(1) }}%</div>
          <div class="stat-label">及格率</div>
        </div>
      </div>

      <div class="card-grid">
        <div class="card stat-card">
          <div class="stat-num">{{ stats.student_count }}</div>
          <div class="stat-label">参考人数（去重）</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.pass_count }}</div>
          <div class="stat-label">通过人数</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.booked_count }}</div>
          <div class="stat-label">有效预约</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.absent_count }}</div>
          <div class="stat-label">缺考</div>
        </div>
      </div>

      <div class="card" style="margin-bottom: 16px">
        <h3 style="margin-top: 0">预约与补考</h3>
        <div class="dist-grid">
          <div class="dist-bar">到考率：{{ stats.attendance_rate.toFixed(1) }}%</div>
          <div class="dist-bar">首考人次：{{ stats.first_attempt_count }}</div>
          <div class="dist-bar">补考人次：{{ stats.retake_attempt_count }}</div>
          <div class="dist-bar">补考通过：{{ stats.retake_pass_count }}（{{ stats.retake_pass_rate.toFixed(1) }}%）</div>
        </div>
      </div>

      <div class="card" style="margin-bottom: 16px">
        <h3 style="margin-top: 0">分数分布</h3>
        <div class="dist-grid">
          <div
            v-for="(count, range) in stats.distribution"
            :key="range"
            class="dist-bar"
          >{{ range }} 分：{{ count }} 人</div>
        </div>
      </div>
    </template>

    <div class="card">
      <h3 style="margin-top: 0">🏆 排行榜</h3>
      <div v-if="leaderboard.length">
        <div
          v-for="item in leaderboard"
          :key="item.user_id"
          class="ranking-row"
          :class="{ me: auth.user?.id === item.user_id }"
        >
          <span>第 {{ item.rank }} 名 · {{ item.real_name }}（{{ item.username }}）</span>
          <span>{{ item.score }} 分</span>
        </div>
      </div>
      <div v-else class="empty">暂无排名数据</div>
    </div>
  </template>
</template>
