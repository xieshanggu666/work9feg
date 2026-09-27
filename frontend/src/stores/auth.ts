import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as authApi from '@/api/auth'
import { clearToken, getToken, setToken } from '@/api/request'
import type { Role, User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string>(getToken())
  const loading = ref(false)

  const isLoggedIn = computed(() => !!token.value)
  const role = computed<Role | null>(() => user.value?.role ?? null)
  const canEdit = computed(() => role.value === 'admin' || role.value === 'teacher')

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const data = await authApi.login(username, password)
      token.value = data.access_token
      user.value = data.user
      setToken(data.access_token)
    } finally {
      loading.value = false
    }
  }

  async function fetchCurrentUser() {
    if (!token.value) return null
    try {
      user.value = await authApi.fetchMe()
    } catch {
      logout()
    }
    return user.value
  }

  function logout() {
    user.value = null
    token.value = ''
    clearToken()
  }

  return {
    user,
    token,
    loading,
    isLoggedIn,
    role,
    canEdit,
    login,
    logout,
    fetchCurrentUser,
  }
})
