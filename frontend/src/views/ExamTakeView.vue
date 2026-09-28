<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getAttemptResult,
  reportScreenSwitch,
  saveAnswers,
  saveAnswersBeacon,
  startExam,
  submitExam,
} from '@/api/exams'
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
// 每题已与服务端同步的版本号（多端冲突检测的 base_version）
const answerVersions = new Map<number, number>()
// 有本地修改、尚未成功保存的题目
const dirty = new Set<number>()
// 多端冲突提示
const conflictTip = ref('')
// 自动保存状态：'' / saving / saved / error
const saveStatus = ref('')
let saveStatusTimer: ReturnType<typeof setTimeout> | null = null

function flashSaveStatus(status: string) {
  saveStatus.value = status
  if (saveStatusTimer) clearTimeout(saveStatusTimer)
  if (status === 'saved') {
    saveStatusTimer = setTimeout(() => { saveStatus.value = '' }, 1500)
  }
}

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

function markDirty(qid: number) {
  dirty.add(qid)
  conflictTip.value = ''
}

function onSingle(qid: number, value: string) {
  touchQuestion(qid)
  flushTime(qid)
  if (answers[qid] !== value) {
    answers[qid] = value
    markDirty(qid)
  }
}

function onText(qid: number, value: string) {
  touchQuestion(qid)
  if (answers[qid] !== value) {
    answers[qid] = value
    markDirty(qid)
  }
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
  markDirty(qid)
}

function isMultiChecked(qid: number, value: string) {
  return (answers[qid] || '').split(',').includes(value)
}

// ---- 服务端时间基准（校准客户端时钟偏移） ----
const clockOffsetMs = ref(0)
function syncClock(serverTime: string | null) {
  if (serverTime) {
    clockOffsetMs.value = new Date(serverTime).getTime() - Date.now()
  }
}
function serverNow() {
  return Date.now() + clockOffsetMs.value
}

// ---- 倒计时：以服务端 deadline 为准，刷新后按剩余时间恢复 ----
const remainMs = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let deadlineAt = 0

const timerText = computed(() => {
  const m = Math.floor(remainMs.value / 60000)
  const s = Math.floor((remainMs.value % 60000) / 1000)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

function startTimer() {
  if (!attempt.value?.deadline) return
  deadlineAt = new Date(attempt.value.deadline).getTime()
  remainMs.value = Math.max(0, deadlineAt - serverNow())
  timer = setInterval(() => {
    remainMs.value = Math.max(0, deadlineAt - serverNow())
    if (remainMs.value <= 0 && timer) {
      clearInterval(timer)
      timer = null
      void doSubmit('timeout')
    }
  }, 1000)
}

// ---- 自动保存 ----
let saveTimer: ReturnType<typeof setInterval> | null = null
let saveInFlight = false

function buildPayload(qids: number[]): AnswerSubmit[] {
  if (!attempt.value) return []
  return qids.map((qid) => {
    flushTime(qid)
    return {
      question_id: qid,
      user_answer: answers[qid] || '',
      time_spent_seconds: answerSeconds[qid] || 0,
      base_version: answerVersions.get(qid) || 0,
    }
  })
}

async function flushSave(showConflict = true) {
  if (!attempt.value || submitting.value || saveInFlight || dirty.size === 0) return
  const qids = Array.from(dirty)
  saveInFlight = true
  flashSaveStatus('saving')
  try {
    const res = await saveAnswers(attempt.value.attempt_id, buildPayload(qids))
    // 保存成功，记录每题版本
    qids.forEach((qid) => {
      answerVersions.set(qid, res.answer_version)
      dirty.delete(qid)
    })
    attempt.value.answer_version = res.answer_version
    flashSaveStatus('saved')
    // 多端冲突：加载服务端版本并提示用户核对（server-wins，不静默覆盖）
    if (showConflict && res.conflicts.length) {
      res.conflicts.forEach((c) => {
        answers[c.question_id] = c.server_answer
        answerVersions.set(c.question_id, c.server_version)
      })
      conflictTip.value =
        `检测到 ${res.conflicts.length} 题在其它设备上被修改，已为你加载最新答案，请核对。`
    }
  } catch (e) {
    // 409：服务端已到时自动交卷
    const status = (e as { status?: number })?.status
    if (status === 409) {
      await goToResult(true)
      return
    }
    // 其它网络错误：保留 dirty，下个周期重试
    flashSaveStatus('error')
  } finally {
    saveInFlight = false
  }
}

function flushSaveBeacon() {
  if (!attempt.value || dirty.size === 0) return
  saveAnswersBeacon(attempt.value.attempt_id, buildPayload(Array.from(dirty)))
  dirty.clear()
}

// ---- 防作弊：切屏检测（同时触发一次保存） ----
const switchCount = ref(0)
const cheatTip = ref('')
let lastReportAt = 0

async function onScreenSwitch() {
  if (!attempt.value || submitting.value) return
  // 切后台时优先保存一次答案
  void flushSave(false)
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
      await doSubmit('forced')
    }
  } catch {
    /* 网络错误忽略 */
  }
}

function onVisibilityChange() {
  if (document.hidden) void onScreenSwitch()
}

function onBeforeUnload() {
  flushSaveBeacon()
}

// ---- 恢复服务端已保存答案 ----
function restoreSaved() {
  if (!attempt.value) return
  syncClock(attempt.value.server_time)
  for (const a of attempt.value.answers) {
    answers[a.question_id] = a.user_answer
    answerSeconds[a.question_id] = a.time_spent_seconds
    answerVersions.set(a.question_id, a.version)
  }
  dirty.clear()
}

async function goToResult(skipCache = false) {
  if (!attempt.value) return
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  if (saveTimer) {
    clearInterval(saveTimer)
    saveTimer = null
  }
  let result = null
  try {
    result = await getAttemptResult(attempt.value.attempt_id)
    sessionStorage.setItem(
      `result:${attempt.value.attempt_id}`,
      JSON.stringify(result),
    )
  } catch {
    /* 结果稍后可在结果页自行拉取 */
  }
  router.replace({
    name: 'exam-result',
    params: { attemptId: attempt.value.attempt_id },
    query: skipCache && !result ? { timeout: '1' } : {},
  })
}

// ---- 交卷 ----
async function doSubmit(kind: 'manual' | 'timeout' | 'forced' = 'manual') {
  if (!attempt.value || submitting.value) return
  if (kind === 'manual' && !window.confirm('确定交卷？交卷后不可修改答案。')) return
  submitting.value = true
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  if (saveTimer) {
    clearInterval(saveTimer)
    saveTimer = null
  }

  // 先把未落库的答案保存掉（超时情况下也尽量带上最后修改）
  await flushSave(false)

  attempt.value.questions.forEach((q) => flushTime(q.question_id))
  const payload: AnswerSubmit[] = attempt.value.questions.map((q) => ({
    question_id: q.question_id,
    user_answer: answers[q.question_id] || '',
    time_spent_seconds: answerSeconds[q.question_id] || 0,
    base_version: answerVersions.get(q.question_id) || 0,
  }))

  try {
    const result = await submitExam(attempt.value.attempt_id, payload, kind)
    sessionStorage.setItem(`result:${attempt.value.attempt_id}`, JSON.stringify(result))
    router.replace({ name: 'exam-result', params: { attemptId: attempt.value.attempt_id } })
  } catch (e) {
    // 若已被服务端自动交卷/并发交卷，直接进入结果页
    const status = (e as { status?: number })?.status
    if (status === 409) {
      await goToResult(true)
      return
    }
    submitting.value = false
    window.alert(e instanceof Error ? e.message : '交卷失败')
    if (kind === 'manual') startTimer()
  }
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('blur', onScreenSwitch)
  window.addEventListener('pagehide', onBeforeUnload)
  try {
    const data = await startExam(examId)
    // 服务端已到时自动交卷（重连场景）
    if (data.status === 'graded') {
      attempt.value = data
      await goToResult()
      return
    }
    attempt.value = data
    restoreSaved()
    startTimer()
    // 周期性自动保存
    saveTimer = setInterval(() => void flushSave(), 10000)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : '无法开始考试'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  // 组件销毁（路由跳转）时尽力保存，但不再触发页面跳转
  if (dirty.size) flushSaveBeacon()
  if (timer) clearInterval(timer)
  if (saveTimer) clearInterval(saveTimer)
  if (saveStatusTimer) clearTimeout(saveStatusTimer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('blur', onScreenSwitch)
  window.removeEventListener('pagehide', onBeforeUnload)
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
        <span class="muted" style="margin-right: 10px; font-size: 13px">
          <template v-if="saveStatus === 'saving'">💾 保存中...</template>
          <template v-else-if="saveStatus === 'saved'">✅ 已自动保存</template>
          <template v-else-if="saveStatus === 'error'">⚠️ 保存失败，将重试</template>
        </span>
        <span v-if="conflictTip" class="cheat-tip" style="background:#fdf0d5">🔄 {{ conflictTip }}</span>
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
          :value="answers[q.question_id] || ''"
          :placeholder="q.question_type === 'programming' ? '请在此编写代码...' : '请输入答案...'"
          @focus="touchQuestion(q.question_id)"
          @input="onText(q.question_id, ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </div>
    </main>

    <div class="exam-footer">
      <button class="btn btn-primary" :disabled="submitting" @click="doSubmit('manual')">
        {{ submitting ? '正在交卷...' : '交卷' }}
      </button>
    </div>
  </template>
</template>
