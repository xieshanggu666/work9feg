import { http } from './request'
import type {
  ExamBooking,
  ExamEligibility,
  ExamSlot,
  PageResponse,
  SlotPayload,
} from '@/types'

// ---------- 时段（管理员） ----------
export function listSlots(examId: number) {
  return http<ExamSlot[]>({ url: `/exams/${examId}/slots`, method: 'GET' })
}

export function createSlot(examId: number, data: SlotPayload) {
  return http<ExamSlot>({ url: `/exams/${examId}/slots`, method: 'POST', data })
}

export function updateSlot(slotId: number, data: Partial<SlotPayload>) {
  return http<ExamSlot>({ url: `/slots/${slotId}`, method: 'PUT', data })
}

export function deleteSlot(slotId: number) {
  return http<null>({ url: `/slots/${slotId}`, method: 'DELETE' })
}

// ---------- 开考资格 ----------
export function getEligibility(examId: number) {
  return http<ExamEligibility>({ url: `/exams/${examId}/eligibility`, method: 'GET' })
}

// ---------- 预约（学生） ----------
export function applyBooking(slotId: number, applyReason = '') {
  return http<ExamBooking>({
    url: '/bookings',
    method: 'POST',
    data: { slot_id: slotId, apply_reason: applyReason },
  })
}

export function listMyBookings(examId?: number) {
  return http<ExamBooking[]>({
    url: '/bookings/my',
    method: 'GET',
    params: examId ? { exam_id: examId } : undefined,
  })
}

export function cancelBooking(bookingId: number) {
  return http<ExamBooking>({ url: `/bookings/${bookingId}/cancel`, method: 'POST' })
}

// ---------- 审核（教师 / 管理员） ----------
export interface BookingQuery {
  exam_id?: number
  status?: string
  slot_id?: number
  page?: number
  page_size?: number
}

export function listBookings(params: BookingQuery) {
  return http<PageResponse<ExamBooking>>({ url: '/bookings', method: 'GET', params })
}

export function reviewBooking(bookingId: number, approved: boolean, reviewComment = '') {
  return http<ExamBooking>({
    url: `/bookings/${bookingId}/review`,
    method: 'POST',
    data: { approved, review_comment: reviewComment },
  })
}
