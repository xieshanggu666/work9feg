import { http, getToken } from './request'
import type {
  Exam,
  ExamCreatePayload,
  ExamDetail,
  ExamStartData,
  ExamResult,
  AnswerSaveResult,
  AnswerSubmit,
  PageResponse,
  ExamStatus,
} from '@/types'

export interface ExamQuery {
  page?: number
  page_size?: number
  status?: ExamStatus | ''
  subject_id?: number
}

export function listExams(params: ExamQuery) {
  return http<PageResponse<Exam>>({ url: '/exams', method: 'GET', params })
}

export function getExam(id: number) {
  return http<ExamDetail>({ url: `/exams/${id}`, method: 'GET' })
}

export function createExam(data: ExamCreatePayload) {
  return http<Exam>({ url: '/exams', method: 'POST', data })
}

export function updateExam(id: number, data: Partial<ExamCreatePayload> & { status?: ExamStatus }) {
  return http<Exam>({ url: `/exams/${id}`, method: 'PUT', data })
}

export function deleteExam(id: number) {
  return http<null>({ url: `/exams/${id}`, method: 'DELETE' })
}

export function startExam(examId: number) {
  return http<ExamStartData>({ url: `/attempts/${examId}/start`, method: 'POST' })
}

export function saveAnswers(attemptId: number, answers: AnswerSubmit[]) {
  return http<AnswerSaveResult>({
    url: `/attempts/${attemptId}/answers`,
    method: 'PUT',
    data: { answers },
  })
}

/** 页面关闭/刷新时用 keepalive 做最后一次兜底保存（不等待响应） */
export function saveAnswersBeacon(attemptId: number, answers: AnswerSubmit[]) {
  try {
    void fetch(`/api/attempts/${attemptId}/answers`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ answers }),
      keepalive: true,
    })
  } catch {
    /* 页面卸载阶段失败可忽略，周期性保存已覆盖大多数情况 */
  }
}

export function getAttemptResult(attemptId: number) {
  return http<ExamResult>({ url: `/attempts/${attemptId}/result`, method: 'GET' })
}

export function submitExam(attemptId: number, answers: AnswerSubmit[], submitType = 'manual') {
  return http<ExamResult>({
    url: `/attempts/${attemptId}/submit`,
    method: 'POST',
    data: { answers, submit_type: submitType },
  })
}

export function reportScreenSwitch(attemptId: number) {
  return http<{ warning: number; force_submit: boolean }>({
    url: `/attempts/${attemptId}/screen-switch`,
    method: 'POST',
  })
}
