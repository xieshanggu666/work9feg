import { http } from './request'
import type {
  Exam,
  ExamCreatePayload,
  ExamDetail,
  ExamStartData,
  ExamResult,
  AnswerSubmit,
  AnswerSavePayload,
  AutosaveResult,
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

export function resumeAttempt(attemptId: number) {
  return http<ExamStartData>({ url: `/attempts/${attemptId}/resume`, method: 'GET' })
}

export function autosaveAnswers(attemptId: number, answers: AnswerSavePayload[]) {
  return http<AutosaveResult>({
    url: `/attempts/${attemptId}/autosave`,
    method: 'POST',
    data: { answers },
    timeout: 10000,
  })
}

export function submitExam(attemptId: number, answers: AnswerSubmit[], idempotencyKey?: string) {
  return http<ExamResult>({
    url: `/attempts/${attemptId}/submit`,
    method: 'POST',
    data: { answers, idempotency_key: idempotencyKey },
    timeout: 20000,
  })
}

export function getAttemptResult(attemptId: number) {
  return http<ExamResult>({ url: `/attempts/${attemptId}/result`, method: 'GET' })
}

export function reportScreenSwitch(attemptId: number) {
  return http<{ warning: number; force_submit: boolean }>({
    url: `/attempts/${attemptId}/screen-switch`,
    method: 'POST',
  })
}
