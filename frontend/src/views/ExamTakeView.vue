<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue'
import {
  autosaveAnswers, getAttemptResult, reportScreenSwitch, startExam, submitExam,
} from '@/api/exams'
import { getToken } from '@/api/request'
import type {
  AnswerSavePayload, AutosaveConflict, ExamStartData, QuestionType,
} from '@/types'

const route = useRoute()
const examId = Number(route.params.examId)
const router = useRouter()

const attempt = ref<ExamStartData | null>(null)
const loading = ref(true)
const loadError = ref('')
const submitting = ref(false)
const saveState = ref<'idle' | 'saving' | 'error'>('idle')

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
// 与服务端同步过的答案版本（乐观锁基准）
const versions = reactive<Record<number, number>>({})
// 单题开始作答时间 / 累计用时（秒）
const answerStart = new Map<number, number>()
const answerSeconds = reactive<Record<number, number>>({})

// 待保存（脏）题目，以及当前未解决冲突的题目
const dirty = new Set<number>()
const conflictSet = new Set<number>()
const conflicts = reactive<AutosaveConflict[]>([])

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
  scheduleSave()
}

function onSingle(qid: number, value: string) {
  touchQuestion(qid)
  flushTime(qid)
  answers[qid] = value
  markDirty(qid)
}

function onText(qid: number, value: string) {
  touchQuestion(qid)
  answers[qid] = value
  markDirty(qid)
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

// ---- 倒计时（以服务端时钟为准，本机时钟不准也不影响） ----
const remainMs = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let periodicSaver: ReturnType<typeof setInterval> | null = null
// 服务端时间与本机时间的偏移：serverNow = Date.now() + clockOffset
let clockOffset = 0

const timerText = computed(() => {
  const m = Math.floor(remainMs.value / 60000)
  const s = Math.floor((remainMs.value % 60000) / 1000)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

function syncClock(serverTime: string | Date) {
  clockOffset = new Date(serverTime).getTime() - Date.now()
}

function serverNow() {
  return Date.now() + clockOffset
}

function startTimer() {
  if (!attempt.value || timer) return
  const tick = () => {
    const rest = new Date(attempt.value!.deadline).getTime() - serverNow()
    remainMs.value = Math.max(0, rest)
    if (remainMs.value <= 0 && timer) {
      clearInterval(timer)
      timer = null
      onTimeUp()
    }
  }
  tick()
  timer = setInterval(tick, 1000)
}

// ---- 自动保存 ----
let saveTimer: ReturnType<typeof setTimeout> | null = null
let saveInFlight = false

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    void flushSaves()
  }, 1200)
}

function buildSavePayload(): AnswerSavePayload[] {
  if (!attempt.value) return []
  return attempt.value.questions
    .filter((q) => dirty.has(q.question_id) && !conflictSet.has(q.question_id))
    .map((q) => ({
      question_id: q.question_id,
      user_answer: answers[q.question_id] || '',
      time_spent_seconds: answerSeconds[q.question_id] || 0,
      base_version: versions[q.question_id] || 0,
    }))
}

function applyAutosaveResult(res: Awaited<ReturnType<typeof autosaveAnswers>>) {
  syncClock(res.server_time)
  if (attempt.value) {
    attempt.value.deadline = res.deadline
    attempt.value.status = res.status
  }

  for (const s of res.saved) {
    versions[s.question_id] = s.version
    // 保存期间本地没有再改动，才清除脏标记；否则保留待下一次保存
    if ((answers[s.question_id] || '') === s.user_answer) {
      dirty.delete(s.question_id)
    }
  }

  for (const c of res.conflicts) {
    if (conflictSet.has(c.question_id)) continue
    conflictSet.add(c.question_id)
    conflicts.push(c)
    dirty.delete(c.question_id)
  }
}

async function flushSaves(force = false) {
  if (!attempt.value || saveInFlight) return
  if (!force && submitting.value) return
  if (attempt.value.status === 'graded') {
    gotoResult(attempt.value.attempt_id)
    return
  }
  const payload = buildSavePayload()
  if (payload.length === 0) return

  // 快照发送内容，用于响应回来时判断期间是否又被编辑
  const snapshot = new Map(payload.map((p) => [p.question_id, p.user_answer]))
  saveInFlight = true
  saveState.value = 'saving'
  try {
    const res = await autosaveAnswers(attempt.value.attempt_id, payload)
    for (const [qid, val] of snapshot) {
      if ((answers[qid] || '') !== val) dirty.add(qid)
    }
    applyAutosaveResult(res)
    saveState.value = 'idle'
    if (res.status === 'graded') {
      gotoResult(res.attempt_id)
      return
    }
  } catch {
    saveState.value = 'error'
    // 失败的题目保留脏标记，下次定时保存/交卷时重试
  } finally {
    saveInFlight = false
  }
}

// 页面关闭/切后台：尽力把答案发出去（keepalive 不阻塞卸载）
function saveOnUnload() {
  if (!attempt.value || attempt.value.status === 'graded') return
  const payload = buildSavePayload()
  if (!payload.length) return
  try {
    void fetch(`/api/attempts/${attempt.value.attempt_id}/autosave`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ answers: payload }),
      keepalive: true,
    })
  } catch {
    /* 浏览器不支持时忽略，周期保存已尽量覆盖 */
  }
}

// ---- 多端冲突处理 ----
function adoptServerAnswer(c: AutosaveConflict) {
  answers[c.question_id] = c.server_answer
  versions[c.question_id] = c.server_version
  conflictSet.delete(c.question_id)
  const idx = conflicts.findIndex((x) => x.question_id === c.question_id)
  if (idx >= 0) conflicts.splice(idx, 1)
  // 与服务端一致，无需再保存
  dirty.delete(c.question_id)
}

async function keepMyAnswer(c: AutosaveConflict) {
  // 以服务端最新版本为基准重新保存我的答案（强制覆盖）
  versions[c.question_id] = c.server_version
  conflictSet.delete(c.question_id)
  const idx = conflicts.findIndex((x) => x.question_id === c.question_id)
  if (idx >= 0) conflicts.splice(idx, 1)
  dirty.add(c.question_id)
  await flushSaves()
}

// ---- 防作弊：切屏检测 ----
const cheatTip = ref('')
let lastReportAt = 0

async function onScreenSwitch() {
  if (!attempt.value || submitting.value || attempt.value.status === 'graded') return
  // 切走前先保存一次答案
  void flushSaves()
  // 3 秒内只上报一次
  if (Date.now() - lastReportAt < 3000) return
  lastReportAt = Date.now()
  try {
    const res = await reportScreenSwitch(attempt.value.attempt_id)
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
  if (document.hidden) {
    void flushSaves()
    onScreenSwitch()
  } else {
    // 重新回到页面（可能刚从断网/休眠恢复）：立刻补存并重新校准时钟
    void flushSaves()
  }
}

function onOnline() {
  saveState.value = 'idle'
  void flushSaves()
}

// ---- 到时自动交卷 ----
let timeUpHandled = false
async function onTimeUp() {
  if (timeUpHandled) return
  timeUpHandled = true
  window.alert('考试时间到，系统将按已保存的答案自动交卷')
  await doSubmit(true)
}

// ---- 交卷（幂等：同一 attempt 固定一个幂等令牌） ----
function idempotencyKey(attemptId: number) {
  const key = `submit-key:${attemptId}`
  let v = sessionStorage.getItem(key)
  if (!v) {
    v = `sub_${attemptId}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
    sessionStorage.setItem(key, v)
  }
  return v
}

async function doSubmit(force = false) {
  if (!attempt.value || submitting.value) return
  if (!force && !window.confirm('确定交卷？交卷后不可修改答案。')) return
  submitting.value = true
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  // 结算全部计时，最后再保存一次，尽量让服务端拿到最新答案
  attempt.value.questions.forEach((q) => flushTime(q.question_id))
  attempt.value.questions.forEach((q) => dirty.add(q.question_id))
  try {
    await flushSaves(true)
  } catch {
    /* 交卷请求体仍会携带全部答案 */
  }

  const payload = attempt.value.questions.map((q) => ({
    question_id: q.question_id,
    user_answer: answers[q.question_id] || '',
    time_spent_seconds: answerSeconds[q.question_id] || 0,
  }))

  const attemptId = attempt.value.attempt_id
  const requestSubmit = () =>
    submitExam(attemptId, payload, idempotencyKey(attemptId))

  try {
    const result = await requestSubmit()
    sessionStorage.setItem(`result:${attemptId}`, JSON.stringify(result))
    gotoResult(attemptId)
  } catch {
    // 网络失败也不丢成绩：服务端到时会按已保存答案自动交卷，改为轮询结果
    await pollResult(attemptId)
  }
}

async function pollResult(attemptId: number) {
  for (let i = 0; i < 30; i += 1) {
    await new Promise((r) => setTimeout(r, 3000))
    try {
      const result = await getAttemptResult(attemptId)
      sessionStorage.setItem(`result:${attemptId}`, JSON.stringify(result))
      gotoResult(attemptId)
      return
    } catch {
      /* 服务端可能正在自动交卷，继续轮询 */
    }
  }
  submitting.value = false
  saveState.value = 'error'
  window.alert('交卷确认中，系统将按已保存答案处理，稍后可在考试记录中查看成绩')
  startTimer()
}

function gotoResult(attemptId: number) {
  router.replace({ name: 'exam-result', params: { attemptId } })
}

// ---- 进入 / 恢复 ----
function restoreSession(data: ExamStartData) {
  attempt.value = data
  syncClock(data.server_time)
  // 恢复已保存答案、版本与单题用时
  for (const a of data.answers) {
    answers[a.question_id] = a.user_answer
    versions[a.question_id] = a.version
    answerSeconds[a.question_id] = a.time_spent_seconds
  }
  startTimer()
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('blur', onScreenSwitch)
  window.addEventListener('pagehide', saveOnUnload)
  window.addEventListener('online', onOnline)
  try {
    const data = await startExam(examId)
    if (data.status === 'graded') {
      // 已交卷（可能是在其它端交的，或服务端到时自动交的）-> 直接看结果
      gotoResult(data.attempt_id)
      return
    }
    loading.value = false
    restoreSession(data)
    // 周期性兜底保存
    periodicSaver = setInterval(() => {
      void flushSaves()
    }, 15000)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : '无法开始考试'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (periodicSaver) clearInterval(periodicSaver)
  if (saveTimer) clearTimeout(saveTimer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('blur', onScreenSwitch)
  window.removeEventListener('pagehide', saveOnUnload)
  window.removeEventListener('online', onOnline)
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
      <div class="exam-header-right">
        <span v-if="conflicts.length" class="conflict-tip">
          ⚠️ 检测到 {{ conflicts.length }} 道题在其它设备被修改
        </span>
        <span v-else-if="saveState === 'saving'" class="save-hint">保存中...</span>
        <span v-else-if="saveState === 'error'" class="save-hint save-hint-error">
          保存失败，将自动重试
        </span>
        <span v-if="cheatTip" class="cheat-tip">⚠️ {{ cheatTip }}</span>
        <span class="timer-text" :class="{ 'timer-danger': remainMs < 60000 }">
          剩余时间：{{ timerText }}
        </span>
      </div>
    </div>

    <!-- 多端修改冲突条 -->
    <div v-if="conflicts.length" class="container conflict-bar-wrap">
      <div
        v-for="c in conflicts"
        :key="c.question_id"
        class="conflict-bar card"
      >
        <div>
          第 {{ attempt.questions.findIndex((q) => q.question_id === c.question_id) + 1 }} 题
          在其它设备上有不同答案。请选择保留哪一端：
        </div>
        <div class="conflict-answers">
          <span class="conflict-side">本机：{{ c.client_answer || '（空）' }}</span>
          <span class="conflict-side conflict-side-server">
            其它设备：{{ c.server_answer || '（空）' }}
          </span>
        </div>
        <div class="conflict-actions">
          <button class="btn btn-primary btn-sm" @click="keepMyAnswer(c)">保留我的答案</button>
          <button class="btn btn-sm" @click="adoptServerAnswer(c)">采用其它设备的答案</button>
        </div>
      </div>
    </div>

    <main class="container exam-body">
      <div
        v-for="(q, idx) in attempt.questions"
        :key="q.question_id"
        class="card question-card"
        :class="{ 'question-conflict': conflictSet.has(q.question_id) }"
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
          :value="answers[q.question_id] || ''"
          @focus="touchQuestion(q.question_id)"
          @blur="flushTime(q.question_id)"
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
