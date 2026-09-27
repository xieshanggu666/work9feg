<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/request'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const form = reactive({ username: '', password: '' })
const errorMsg = ref('')

async function handleSubmit() {
  errorMsg.value = ''
  try {
    await auth.login(form.username.trim(), form.password)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e) {
    errorMsg.value = e instanceof ApiError ? e.message : '登录失败'
  }
}
</script>

<template>
  <div class="login-body">
    <div class="login-card">
      <div class="login-logo">
        <div class="logo-icon">📝</div>
        <h1>在线考试与题库系统</h1>
        <div class="login-subtitle">登录您的账号以继续</div>
      </div>
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="form.username" type="text" required placeholder="admin / teacher / student" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" required placeholder="123456" />
        </div>
        <button type="submit" class="btn btn-primary btn-block" :disabled="auth.loading">
          {{ auth.loading ? '登录中...' : '登 录' }}
        </button>
        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
      </form>
      <div class="login-tip">示例账号：admin/123456、teacher/123456、student/123456</div>
    </div>
  </div>
</template>
