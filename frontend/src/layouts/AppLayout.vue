<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (!auth.user) auth.fetchCurrentUser()
})

function handleLogout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <nav class="topbar">
    <div class="brand">📝 在线考试与题库系统</div>
    <div class="nav-links">
      <RouterLink :to="{ name: 'dashboard' }">📊 <span>仪表盘</span></RouterLink>
      <RouterLink :to="{ name: 'questions' }">📚 <span>题库管理</span></RouterLink>
      <RouterLink :to="{ name: 'exams' }">📝 <span>考试中心</span></RouterLink>
      <RouterLink :to="{ name: 'bookings' }">📅 <span>考试预约</span></RouterLink>
      <RouterLink :to="{ name: 'certificates' }">🏅 <span>我的证书</span></RouterLink>
      <span v-if="auth.user" class="nav-user">
        👤 {{ auth.user.real_name }}（{{ auth.user.role }}）
      </span>
      <button type="button" @click="handleLogout">退出登录</button>
    </div>
  </nav>
  <main class="container">
    <RouterView />
  </main>
</template>
