/** 后端统一响应结构 */
export interface APIResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface PageResponse<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export type Role = 'admin' | 'teacher' | 'student'

export interface User {
  id: number
  username: string
  email: string
  real_name: string
  role: Role
  status: number
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export type QuestionType =
  | 'single_choice'
  | 'multiple_choice'
  | 'judgment'
  | 'fill_blank'
  | 'short_answer'
  | 'programming'

export interface QuestionOption {
  id?: number
  content: string
  is_correct: number
  order_index: number
}

export interface QuestionListItem {
  id: number
  question_type: QuestionType
  content: string
  difficulty: number
  knowledge_point_id: number
  subject_id: number
}

export interface Question extends QuestionListItem {
  analysis: string
  discrimination: number
  created_at: string
  options: QuestionOption[]
  tags: Tag[]
}

export interface QuestionCreatePayload {
  question_type: QuestionType
  content: string
  analysis?: string
  difficulty: number
  knowledge_point_id: number
  subject_id: number
  options?: QuestionOption[]
  tag_ids?: number[]
}

export interface Subject {
  id: number
  name: string
  code: string
  description: string
}

export interface KnowledgePoint {
  id: number
  name: string
  parent_id: number | null
  subject_id: number
  children?: KnowledgePoint[]
}

export interface Tag {
  id: number
  name: string
  color: string
}

export type ExamStatus = 'draft' | 'published' | 'ended'
export type ExamType = 'formal' | 'practice' | 'mock'

export interface Exam {
  id: number
  title: string
  description: string
  subject_id: number
  exam_type: ExamType
  duration_minutes: number
  total_score: number
  pass_score: number
  start_time: string | null
  end_time: string | null
  is_random_order: number
  is_option_random: number
  allow_back: number
  anti_cheat_enabled: number
  require_booking: number
  max_attempts: number
  status: ExamStatus
  created_at: string
}

export interface ExamDetail extends Exam {
  question_count: number
}

export interface ExamCreatePayload {
  title: string
  description?: string
  subject_id: number
  exam_type?: ExamType
  duration_minutes: number
  total_score: number
  pass_score: number
  is_random_order?: number
  is_option_random?: number
  anti_cheat_enabled?: number
  require_booking?: number
  max_attempts?: number
}

export type SlotStatus = 'open' | 'closed'

export interface ExamSlot {
  id: number
  exam_id: number
  name: string
  start_time: string
  end_time: string
  capacity: number
  booked_count: number
  remaining: number
  status: SlotStatus
  created_at: string
}

export type SlotPayload = {
  name?: string
  start_time: string
  end_time: string
  capacity: number
  status?: SlotStatus
}

export type BookingStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'cancelled'
  | 'used'
  | 'missed'

export type BookingType = 'first' | 'retake'

export interface ExamBooking {
  id: number
  exam_id: number
  slot_id: number | null
  user_id: number
  username: string
  real_name: string
  attempt_no: number
  booking_type: BookingType
  status: BookingStatus
  apply_reason: string
  review_comment: string
  reviewer_id: number | null
  reviewed_at: string | null
  created_at: string
  slot_name: string
  slot_start: string | null
  slot_end: string | null
  exam_title: string
}

export interface ExamEligibility {
  exam_id: number
  require_booking: boolean
  can_start: boolean
  reason: string
  max_attempts: number
  used_attempts: number
  remaining_attempts: number
  has_passed: boolean
  booking: ExamBooking | null
}

export interface ExamQuestionBrief {
  exam_question_id: number
  question_id: number
  question_type: QuestionType
  content: string
  score: number
  options: Array<{ id: number; content: string; is_correct?: number }>
}

export interface SavedAnswer {
  question_id: number
  user_answer: string
  time_spent_seconds: number
  version: number
}

export interface ExamStartData {
  attempt_id: number
  exam_id: number
  title: string
  duration_minutes: number
  total_score: number
  start_time: string
  server_time: string
  deadline: string
  status: 'in_progress' | 'submitted' | 'graded'
  questions: ExamQuestionBrief[]
  answers: SavedAnswer[]
}

export interface AnswerSubmit {
  question_id: number
  user_answer: string
  time_spent_seconds: number
}

export interface AnswerSavePayload {
  question_id: number
  user_answer: string
  time_spent_seconds?: number
  base_version: number
}

export interface AutosaveConflict {
  question_id: number
  server_answer: string
  server_version: number
  client_answer: string
}

export interface AutosaveResult {
  attempt_id: number
  status: 'in_progress' | 'submitted' | 'graded'
  server_time: string
  deadline: string
  saved: Array<{
    question_id: number
    user_answer: string
    time_spent_seconds: number
    version: number
  }>
  versions: Record<string, number>
  conflicts: AutosaveConflict[]
}

export interface ExamAnswerResult {
  id: number
  question_id: number
  user_answer: string
  is_correct: number
  score: number
  time_spent_seconds: number
}

export interface ExamResult {
  attempt_id: number
  exam_id: number
  score: number
  total_score: number
  is_passed: boolean
  submit_time: string | null
  answers: ExamAnswerResult[]
  rank: number | null
  percentile: number | null
}

export interface Certificate {
  id: number
  certificate_no: string
  exam_id: number
  score: number
  issue_date: string
  is_valid: number
}

export interface ExamStats {
  exam_id: number
  attempt_count: number
  avg_score: number
  max_score: number
  min_score: number
  pass_rate: number
  distribution: Record<string, number>
  student_count: number
  pass_count: number
  booked_count: number
  attended_count: number
  attendance_rate: number
  absent_count: number
  first_attempt_count: number
  retake_attempt_count: number
  retake_pass_count: number
  retake_pass_rate: number
}

export interface LeaderboardItem {
  user_id: number
  username: string
  real_name: string
  score: number
  rank: number
  submit_time: string | null
}
