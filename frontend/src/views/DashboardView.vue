<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { listExams } from '@/api/exams'
import { listCertificates } from '@/api/grades'
import type { Certificate, Exam } from '@/types'

const exams = ref<Exam[]>([])
const total = ref(0)
const certs = ref<Certificate[]>([])
const loading = ref(true)

const statusText: Record<string, string> = {
  draft: '未发布',
  published: '进行中',
  ended: '已结束',
}

onMounted(async () => {
  try {
    const [examPage, certList] = await Promise.all([
      listExams({ page: 1, page_size: 100 }),
      listCertificates(),
    ])
    exams.value = examPage.items
    total.value = examPage.total
    certs.value = certList
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <h2>📊 仪表盘</h2>

  <div class="card-grid">
    <div class="card stat-card">
      <div class="stat-num">{{ total }}</div>
      <div class="stat-label">考试总数</div>
    </div>
    <div class="card stat-card">
      <div class="stat-num">{{ exams.filter((e) => e.status === 'published').length }}</div>
      <div class="stat-label">进行中考试</div>
    </div>
    <div class="card stat-card">
      <div class="stat-num">{{ exams.filter((e) => e.status === 'ended').length }}</div>
      <div class="stat-label">已结束考试</div>
    </div>
    <div class="card stat-card">
      <div class="stat-num">{{ certs.length }}</div>
      <div class="stat-label">我的证书</div>
    </div>
  </div>

  <h3>考试列表</h3>
  <table v-if="!loading" class="table">
    <thead>
      <tr>
        <th>ID</th><th>考试名称</th><th>时长</th><th>状态</th><th>操作</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="e in exams" :key="e.id">
        <td>{{ e.id }}</td>
        <td>{{ e.title }}</td>
        <td>{{ e.duration_minutes }} 分钟</td>
        <td><span class="badge" :class="`badge-${e.status}`">{{ statusText[e.status] || e.status }}</span></td>
        <td>
          <RouterLink
            v-if="e.status === 'published'"
            class="btn btn-sm btn-primary"
            :to="{ name: 'exam-take', params: { examId: e.id } }"
          >开始考试</RouterLink>
          <RouterLink
            v-else
            class="btn btn-sm"
            :to="{ name: 'grades', params: { examId: e.id } }"
          >查看统计</RouterLink>
        </td>
      </tr>
      <tr v-if="!exams.length" class="empty-row">
        <td colspan="5">暂无考试</td>
      </tr>
    </tbody>
  </table>
  <div v-else class="loading">加载中...</div>
</template>
