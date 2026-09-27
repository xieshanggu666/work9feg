<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { reportScreenSwitch, startExam, submitExam } from '@/api/exams'
import type { AnswerSubmit, ExamStartData, QuestionType } from '@/types'

const route = useRoute()
const examId = Number(route.params.examId)
const router = useRouter()

const attempt = ref<ExamStartData | null>(null)
const loading = ref(true)
const loadError = ref('')
const submitting = ref(false)

const typeLabels: Record<QuestionType, string> = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  judgment: '判断题',
  fill_blank: '填空题',
  short_answer: '简答题',
  programming: '编程题',
}

// 答案：questionId -> 文本（多选逗号拼接）
const answers = reactive<Record<number, string>>({})
// 单题开始作答时间
const answerStart = new Map<number, number>()
// 单题累计用时（秒）
const answerSeconds = reactive<Record<number, number>>({})

function touchQuestion(qid: number) {
  if (!answerStart.has(qid)) answerStart.set(qid, Date.now())
}

function flushTime(qid: number) {
  const start = answerStart.get(qid)
  if (start) {
    answerSeconds[qid] = (answerSeconds[qid] || 0) + Math.floor((Date.now() - start) / 1000)
    answerStart.set(qid, Date.now())
  }
}

function onSingle(qid: number, value: string) {
  touchQuestion(qid)
  flushTime(qid)
  answers[qid] = value
}

function onText(qid: number, value: string) {
  touchQuestion(qid)
  answers[qid] = value
}

function onMulti(qid: number, value: string, checked: boolean) {
  touchQuestion(qid)
  flushTime(qid)
  const selected = new Set(
    (answers[qid] || '').split(',').map((s) => s.trim()).filter(Boolean),
  )
  if (checked) selected.add(value)
  else selected.delete(value)
  answers[qid] = Array.from(selected).join(',')
}

function isMultiChecked(qid: number, value: string) {
  return (answers[qid] || '').split(',').includes(value)
}

// ---- 倒计时 ----
const remainMs = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let endAt = 0

const timerText = computed(() => {
  const m = Math.floor(remainMs.value / 60000)
  const s = Math.floor((remainMs.value % 60000) / 1000)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

function startTimer() {
  if (!attempt.value) return
  endAt = Date.now() + attempt.value.duration_minutes * 60 * 1000
  remainMs.value = attempt.value.duration_minutes * 60 * 1000
  timer = setInterval(() => {
    remainMs.value = Math.max(0, endAt - Date.now())
    if (remainMs.value <= 0 && timer) {
      clearInterval(timer)
      timer = null
      window.alert('考试时间到，自动交卷')
      doSubmit(true)
    }
  }, 1000)
}

// ---- 防作弊：切屏检测 ----
const switchCount = ref(0)
const cheatTip = ref('')
let lastReportAt = 0

async function onScreenSwitch() {
  if (!attempt.value || submitting.value) return
  // 3 秒内只上报一次
  if (Date.now() - lastReportAt < 3000) return
  lastReportAt = Date.now()
  switchCount.value += 1
  try {
    const res = await reportScreenSwitch(attempt.value.attempt_id)
    switchCount.value = res.warning
    cheatTip.value = `检测到切屏（${res.warning} 次），多次切屏将强制交卷！`
    if (res.force_submit) {
      window.alert('检测到多次切屏，系统已强制交卷！')
      await doSubmit(true)
    }
  } catch {
    /* 网络错误忽略 */
  }
}

function onVisibilityChange() {
  if (document.hidden) onScreenSwitch()
}

// ---- 交卷 ----
async function doSubmit(force = false) {
  if (!attempt.value || submitting.value) return
  if (!force && !window.confirm('确定交卷？交卷后不可修改答案。')) return
  submitting.value = true
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  // 结算全部计时
  attempt.value.questions.forEach((q) => flushTime(q.question_id))

  const payload: AnswerSubmit[] = attempt.value.questions.map((q) => ({
    question_id: q.question_id,
    user_answer: answers[q.question_id] || '',
    time_spent_seconds: answerSeconds[q.question_id] || 0,
  }))

  try {
    const result = await submitExam(attempt.value.attempt_id, payload)
    sessionStorage.setItem(`result:${attempt.value.attempt_id}`, JSON.stringify(result))
    router.replace({ name: 'exam-result', params: { attemptId: attempt.value.attempt_id } })
  } catch (e) {
    submitting.value = false
    window.alert(e instanceof Error ? e.message : '交卷失败')
    startTimer()
  }
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('blur', onScreenSwitch)
  try {
    attempt.value = await startExam(examId)
    startTimer()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : '无法开始考试'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('blur', onScreenSwitch)
})
</script>

<template>
  <div v-if="loading" class="container"><div class="loading">正在进入考试...</div></div>

  <div v-else-if="loadError" class="login-body">
    <div class="login-card result-card">
      <h1>无法开始考试</h1>
      <div class="result-meta">{{ loadError }}</div>
      <RouterLink class="btn btn-primary" :to="{ name: 'exams' }">返回考试中心</RouterLink>
    </div>
  </div>

  <template v-else-if="attempt">
    <div class="exam-header">
      <div class="exam-title">{{ attempt.title }}</div>
      <div>
        <span v-if="cheatTip" class="cheat-tip">⚠️ {{ cheatTip }}</span>
        <span class="timer-text" :class="{ 'timer-danger': remainMs < 60000 }">
          剩余时间：{{ timerText }}
        </span>
      </div>
    </div>

    <main class="container exam-body">
      <div
        v-for="(q, idx) in attempt.questions"
        :key="q.question_id"
        class="card question-card"
      >
        <div class="question-head">
          <span class="badge badge-type">{{ idx + 1 }}. {{ typeLabels[q.question_type] }}</span>
          <span class="badge">{{ q.score }}分</span>
        </div>
        <div class="question-content">{{ q.content }}</div>

        <template v-if="q.question_type === 'single_choice' || q.question_type === 'judgment'">
          <label
            v-for="opt in q.options"
            :key="opt.id"
            class="option-row"
          >
            <input
              type="radio"
              :name="`q-${q.question_id}`"
              :value="String(opt.id)"
              :checked="answers[q.question_id] === String(opt.id)"
              @change="onSingle(q.question_id, String(opt.id))"
            />
            <span>{{ opt.content }}</span>
          </label>
        </template>

        <template v-else-if="q.question_type === 'multiple_choice'">
          <label
            v-for="opt in q.options"
            :key="opt.id"
            class="option-row"
          >
            <input
              type="checkbox"
              :value="String(opt.id)"
              :checked="isMultiChecked(q.question_id, String(opt.id))"
              @change="onMulti(q.question_id, String(opt.id), ($event.target as HTMLInputElement).checked)"
            />
            <span>{{ opt.content }}</span>
          </label>
        </template>

        <textarea
          v-else
          class="answer-textarea"
          :placeholder="q.question_type === 'programming' ? '请在此编写代码...' : '请输入答案...'"
          @focus="touchQuestion(q.question_id)"
          @input="onText(q.question_id, ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </div>
    </main>

    <div class="exam-footer">
      <button class="btn btn-primary" :disabled="submitting" @click="doSubmit()">
        {{ submitting ? '正在交卷...' : '交卷' }}
      </button>
    </div>
  </template>
</template>
