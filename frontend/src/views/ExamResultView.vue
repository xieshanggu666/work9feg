<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getAttemptResult } from '@/api/exams'
import { listCertificates } from '@/api/grades'
import type { Certificate, ExamResult } from '@/types'

const route = useRoute()
const attemptId = Number(route.params.attemptId)

const result = ref<ExamResult | null>(null)
const certs = ref<Certificate[]>([])
const loading = ref(true)
const loadError = ref('')

onMounted(async () => {
  // 优先使用交卷时写入的缓存（含本次排名等），没有则向服务端查询（支持刷新/重连）
  const cached = sessionStorage.getItem(`result:${attemptId}`)
  if (cached) {
    result.value = JSON.parse(cached) as ExamResult
    sessionStorage.removeItem(`result:${attemptId}`)
    loading.value = false
  } else {
    try {
      result.value = await getAttemptResult(attemptId)
    } catch (e) {
      loadError.value = e instanceof Error ? e.message : '暂时无法获取成绩'
    } finally {
      loading.value = false
    }
  }
  // 证书信息在有/无缓存时都可补充展示
  try {
    certs.value = await listCertificates()
  } catch {
    certs.value = []
  }
})
</script>

<template>
  <div class="login-body">
    <div class="login-card result-card">
      <h1>📄 考试结果</h1>

      <div v-if="loading" class="loading">正在获取成绩...</div>

      <template v-else-if="result">
        <div
          class="result-score"
          :style="{ color: result.is_passed ? '#2e7d32' : '#e74c3c' }"
        >
          {{ result.is_passed ? '🎉 恭喜通过！' : '很遗憾，未通过' }}
        </div>
        <div class="result-meta">
          <span v-if="result.submit_type === 'timeout'" class="badge badge-type">到时自动交卷</span>
          <span v-else-if="result.submit_type === 'forced'" class="badge badge-type">强制交卷</span>
          <span v-if="result.already" class="muted">（重复提交已忽略，按首次交卷计分）</span>
        </div>
        <div class="result-score">{{ result.score }} / {{ result.total_score }} 分</div>
        <div class="result-meta">
          <span v-if="result.rank">排名：第 {{ result.rank }} 名</span>
          <span v-if="result.percentile !== null && result.percentile !== undefined">
            ｜超过 {{ result.percentile.toFixed(1) }}% 的考生
          </span>
        </div>
        <div class="result-meta">
          答对 {{ result.answers.filter((a) => a.is_correct === 1).length }} 题 /
          共 {{ result.answers.length }} 题
        </div>
      </template>

      <template v-else>
        <div class="result-meta">{{ loadError || '考试尚未完成交卷' }}</div>
      </template>

      <h3 style="margin-top: 18px">我的证书（{{ certs.length }} 张）</h3>
      <template v-if="certs.length">
        <div v-for="c in certs" :key="c.id" class="cert-item">
          🏅 {{ c.certificate_no }}（考试 #{{ c.exam_id }}，{{ c.score }} 分）
        </div>
      </template>
      <div v-else class="muted">暂未获得证书（通过考试后自动生成）</div>

      <div class="modal-actions" style="justify-content: center">
        <RouterLink class="btn btn-primary" :to="{ name: 'dashboard' }">返回仪表盘</RouterLink>
        <RouterLink class="btn" :to="{ name: 'exams' }">考试中心</RouterLink>
      </div>
    </div>
  </div>
</template>
