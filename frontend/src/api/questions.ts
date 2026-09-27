import { http } from './request'
import type {
  KnowledgePoint,
  PageResponse,
  Question,
  QuestionCreatePayload,
  QuestionListItem,
  QuestionType,
  Subject,
  Tag,
} from '@/types'

export interface QuestionQuery {
  page?: number
  page_size?: number
  question_type?: QuestionType | ''
  difficulty?: number
  knowledge_point_id?: number
  subject_id?: number
  keyword?: string
}

export function listQuestions(params: QuestionQuery) {
  return http<PageResponse<QuestionListItem>>({ url: '/questions', method: 'GET', params })
}

export function getQuestion(id: number) {
  return http<Question>({ url: `/questions/${id}`, method: 'GET' })
}

export function createQuestion(data: QuestionCreatePayload) {
  return http<Question>({ url: '/questions', method: 'POST', data })
}

export function updateQuestion(id: number, data: Partial<QuestionCreatePayload>) {
  return http<Question>({ url: `/questions/${id}`, method: 'PUT', data })
}

export function deleteQuestion(id: number) {
  return http<null>({ url: `/questions/${id}`, method: 'DELETE' })
}

export function listSubjects() {
  return http<Subject[]>({ url: '/questions/subjects', method: 'GET' })
}

export function createSubject(data: { name: string; code: string; description?: string }) {
  return http<Subject>({ url: '/questions/subjects', method: 'POST', data })
}

export function listKnowledgePoints(subjectId?: number) {
  return http<KnowledgePoint[]>({
    url: '/questions/knowledge-points',
    method: 'GET',
    params: subjectId ? { subject_id: subjectId } : undefined,
  })
}

export function listTags() {
  return http<Tag[]>({ url: '/questions/tags', method: 'GET' })
}
