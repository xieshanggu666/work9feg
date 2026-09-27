import { http } from './request'
import type { Certificate, ExamStats, LeaderboardItem } from '@/types'

export function getExamStats(examId: number) {
  return http<ExamStats>({ url: `/grades/stats/${examId}`, method: 'GET' })
}

export function getLeaderboard(examId: number, limit = 20) {
  return http<LeaderboardItem[]>({
    url: `/grades/leaderboard/${examId}`,
    method: 'GET',
    params: { limit },
  })
}

export function listCertificates() {
  return http<Certificate[]>({ url: '/grades/certificates', method: 'GET' })
}

export function generateCertificate(examId: number) {
  return http<Certificate>({ url: `/grades/certificates/${examId}/generate`, method: 'POST' })
}
