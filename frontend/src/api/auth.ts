import { http } from './request'
import type { TokenResponse, User } from '@/types'

export function login(username: string, password: string) {
  return http<TokenResponse>({
    url: '/auth/login',
    method: 'POST',
    data: { username, password },
  })
}

export function register(username: string, password: string) {
  return http<User>({
    url: '/auth/register',
    method: 'POST',
    data: { username, password },
  })
}

export function fetchMe() {
  return http<User>({ url: '/users/me', method: 'GET' })
}
