<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listCertificates } from '@/api/grades'
import type { Certificate } from '@/types'

const certs = ref<Certificate[]>([])
const loading = ref(true)
const errorMsg = ref('')

async function load() {
  loading.value = true
  try {
    certs.value = await listCertificates()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <h2>🏅 我的证书</h2>

  <div v-if="loading" class="loading">加载中...</div>

  <div v-else class="card">
    <template v-if="certs.length">
      <div v-for="c in certs" :key="c.id" class="cert-item" style="font-size: 14px; padding: 14px">
        🏅 证书编号：{{ c.certificate_no }}
        <div style="margin-top: 4px">
          考试 #{{ c.exam_id }} · 成绩 {{ c.score }} 分 ·
          签发于 {{ new Date(c.issue_date).toLocaleDateString() }}
        </div>
      </div>
    </template>
    <div v-else class="empty">
      暂未获得证书，通过考试后系统会自动发放。
    </div>
  </div>
</template>
