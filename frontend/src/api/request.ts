import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import type { APIResponse } from '@/types'

const TOKEN_KEY = 'access_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

const request = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

request.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** 后端业务错误 */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

request.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    if (error.response?.status === 401) {
      clearToken()
      // 避免在登录页循环跳转
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    const detail = error.response?.data?.detail || error.message || '网络错误'
    return Promise.reject(new ApiError(detail, error.response?.status))
  },
)

/** 解包统一响应体 { code, message, data } */
export async function http<T>(config: AxiosRequestConfig): Promise<T> {
  const res = await request.request<APIResponse<T>>(config)
  const body = res.data
  if (body.code !== undefined && body.code !== 0) {
    throw new ApiError(body.message || '请求失败')
  }
  return body.data as T
}

export default request
