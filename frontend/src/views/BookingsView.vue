<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { listExams } from '@/api/exams'
import {
  applyBooking, cancelBooking, createSlot, deleteSlot, listBookings,
  listMyBookings, listSlots, reviewBooking, updateSlot,
} from '@/api/bookings'
import { useAuthStore } from '@/stores/auth'
import type {
  BookingStatus, Exam, ExamBooking, ExamSlot,
} from '@/types'

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')
const isStudent = computed(() => auth.role === 'student')

const exams = ref<Exam[]>([])
const selectedExamId = ref<number>(0)
const loading = ref(false)

const statusText: Record<BookingStatus, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
  cancelled: '已取消',
  used: '已考试',
  missed: '缺考',
}

function fmt(t: string | null): string {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ============ 学生端 ============
const myBookings = ref<ExamBooking[]>([])
const slots = ref<ExamSlot[]>([])
const applyForm = reactive<{ exam_id: number; slot_id: number; reason: string }>({
  exam_id: 0, slot_id: 0, reason: '',
})
const applyError = ref('')
const applying = ref(false)

async function loadStudent() {
  loading.value = true
  try {
    ;[myBookings.value, exams.value] = await Promise.all([
      listMyBookings(),
      listExams({ page: 1, page_size: 100, status: 'published' }).then((p) => p.items),
    ])
    applyForm.exam_id = exams.value[0]?.id ?? 0
    await onSelectExam()
  } finally {
    loading.value = false
  }
}

async function onSelectExam() {
  applyForm.slot_id = 0
  slots.value = []
  if (!applyForm.exam_id) return
  slots.value = await listSlots(applyForm.exam_id)
}

async function submitApply() {
  if (!applyForm.slot_id) {
    applyError.value = '请选择预约时段'
    return
  }
  applying.value = true
  applyError.value = ''
  try {
    await applyBooking(applyForm.slot_id, applyForm.reason.trim())
    applyForm.reason = ''
    applyForm.slot_id = 0
    await loadStudent()
  } catch (e) {
    applyError.value = e instanceof Error ? e.message : '申请失败'
  } finally {
    applying.value = false
  }
}

async function onCancel(b: ExamBooking) {
  if (!window.confirm('确定取消该预约？取消后名额将被释放。')) return
  await cancelBooking(b.id)
  await loadStudent()
}

// ============ 教师/管理员端：审核 ============
const reviewList = ref<ExamBooking[]>([])
const reviewTotal = ref(0)
const reviewStatus = ref<BookingStatus | ''>('pending')
const reviewPage = ref(1)
const pageSize = 10
const reviewComment = reactive<Record<number, string>>({})

async function loadReview() {
  if (!selectedExamId.value) return
  const page = await listBookings({
    exam_id: selectedExamId.value,
    status: reviewStatus.value || undefined,
    page: reviewPage.value,
    page_size: pageSize,
  })
  reviewList.value = page.items
  reviewTotal.value = page.total
}

const totalPages = computed(() => Math.max(1, Math.ceil(reviewTotal.value / pageSize)))

async function onReview(b: ExamBooking, approved: boolean) {
  const verb = approved ? '通过' : '驳回'
  if (!window.confirm(`确定${verb}该预约申请？`)) return
  try {
    await reviewBooking(b.id, approved, reviewComment[b.id] || '')
    await loadReview()
  } catch (e) {
    window.alert(e instanceof Error ? e.message : '审核失败')
  }
}

// ============ 管理员端：时段名额 ============
const slotList = ref<ExamSlot[]>([])
const slotModalVisible = ref(false)
const editingSlot = ref<ExamSlot | null>(null)
const slotForm = reactive({ name: '', start_time: '', end_time: '', capacity: 30 })
const slotSaving = ref(false)
const slotError = ref('')

async function loadSlots() {
  if (!selectedExamId.value) return
  slotList.value = await listSlots(selectedExamId.value)
}

function openCreateSlot() {
  editingSlot.value = null
  slotForm.name = ''
  slotForm.start_time = toLocalInput(new Date())
  const end = new Date()
  end.setDate(end.getDate() + 7)
  slotForm.end_time = toLocalInput(end)
  slotForm.capacity = 30
  slotError.value = ''
  slotModalVisible.value = true
}

function openEditSlot(s: ExamSlot) {
  editingSlot.value = s
  slotForm.name = s.name
  slotForm.start_time = toLocalInput(new Date(s.start_time))
  slotForm.end_time = toLocalInput(new Date(s.end_time))
  slotForm.capacity = s.capacity
  slotError.value = ''
  slotModalVisible.value = true
}

async function submitSlot() {
  slotError.value = ''
  if (!slotForm.start_time || !slotForm.end_time) {
    slotError.value = '请填写完整的开始与结束时间'
    return
  }
  if (new Date(slotForm.end_time) <= new Date(slotForm.start_time)) {
    slotError.value = '结束时间必须晚于开始时间'
    return
  }
  slotSaving.value = true
  try {
    const payload = {
      name: slotForm.name.trim(),
      start_time: new Date(slotForm.start_time).toISOString(),
      end_time: new Date(slotForm.end_time).toISOString(),
      capacity: slotForm.capacity,
    }
    if (editingSlot.value) {
      await updateSlot(editingSlot.value.id, payload)
    } else {
      await createSlot(selectedExamId.value, payload)
    }
    slotModalVisible.value = false
    await loadSlots()
  } catch (e) {
    slotError.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    slotSaving.value = false
  }
}

async function toggleSlotStatus(s: ExamSlot) {
  const next = s.status === 'open' ? 'closed' : 'open'
  await updateSlot(s.id, { status: next })
  await loadSlots()
}

async function onDeleteSlot(s: ExamSlot) {
  if (!window.confirm(`确定删除时段「${s.name}」？`)) return
  try {
    await deleteSlot(s.id)
    await loadSlots()
  } catch (e) {
    window.alert(e instanceof Error ? e.message : '删除失败')
  }
}

// ============ 管理端考试切换与加载 ============
async function loadAdminExams() {
  const page = await listExams({ page: 1, page_size: 100 })
  exams.value = page.items
  selectedExamId.value = page.items[0]?.id ?? 0
}

watch(selectedExamId, async () => {
  reviewPage.value = 1
  await Promise.all([loadReview(), loadSlots()])
})

watch([reviewStatus, reviewPage], () => {
  if (isStudent.value) return
  loadReview()
})

onMounted(async () => {
  if (isStudent.value) {
    await loadStudent()
  } else {
    await loadAdminExams()
  }
})
</script>

<template>
  <h2>📅 考试预约与补考</h2>

  <!-- ================= 学生端 ================= -->
  <template v-if="isStudent">
    <div v-if="loading" class="loading">加载中...</div>
    <template v-else>
      <div class="card" style="margin-bottom: 16px">
        <h3 style="margin-top: 0">申请预约 / 补考</h3>
        <div class="form-row">
          <label>选择考试</label>
          <select v-model.number="applyForm.exam_id" @change="onSelectExam">
            <option v-for="e in exams" :key="e.id" :value="e.id">
              #{{ e.id }} {{ e.title }}
              （最多 {{ e.max_attempts }} 次{{ e.require_booking ? '·需预约' : '·免预约' }}）
            </option>
          </select>
        </div>
        <div class="form-row" v-if="slots.length">
          <label>选择时段</label>
          <select v-model.number="applyForm.slot_id">
            <option :value="0" disabled>请选择时段</option>
            <option v-for="s in slots" :key="s.id" :value="s.id"
                    :disabled="s.status !== 'open' || (s.capacity > 0 && s.remaining <= 0)">
              {{ s.name || '未命名批次' }} · {{ fmt(s.start_time) }} ~ {{ fmt(s.end_time) }}
              · 剩余 {{ s.capacity === 0 ? '不限' : `${s.remaining}/${s.capacity}` }}
              {{ s.status !== 'open' ? '·已关闭' : '' }}
            </option>
          </select>
        </div>
        <div v-else-if="applyForm.exam_id" class="muted">该考试暂无可预约时段，请等待管理员配置。</div>
        <div class="form-row">
          <label>申请说明</label>
          <input v-model="applyForm.reason" type="text"
                 placeholder="补考请填写原因，首考可留空" />
        </div>
        <div v-if="applyError" class="error-msg">{{ applyError }}</div>
        <button class="btn btn-primary" :disabled="applying || !applyForm.exam_id" @click="submitApply">
          {{ applying ? '提交中...' : '提交申请' }}
        </button>
      </div>

      <div class="card">
        <h3 style="margin-top: 0">我的预约</h3>
        <table class="table">
          <thead>
            <tr>
              <th>考试</th><th>时段</th><th>类型</th><th>场次</th>
              <th>状态</th><th>审核意见</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in myBookings" :key="b.id">
              <td>{{ b.exam_title || `考试#${b.exam_id}` }}</td>
              <td>{{ b.slot_name || '-' }}<br /><span class="muted">{{ fmt(b.slot_start) }}</span></td>
              <td>{{ b.booking_type === 'first' ? '首考' : '补考' }}</td>
              <td>第 {{ b.attempt_no }} 次</td>
              <td><span class="badge" :class="`badge-booking-${b.status}`">{{ statusText[b.status] }}</span></td>
              <td>{{ b.review_comment || '-' }}</td>
              <td>
                <button v-if="['pending', 'approved'].includes(b.status)"
                        class="btn btn-sm btn-danger" @click="onCancel(b)">取消</button>
                <span v-else class="muted">-</span>
              </td>
            </tr>
            <tr v-if="!myBookings.length" class="empty-row">
              <td colspan="7">暂无预约记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </template>

  <!-- ================= 教师 / 管理员端 ================= -->
  <template v-else>
    <div class="toolbar">
      <label>考试：</label>
      <select v-model.number="selectedExamId">
        <option v-for="e in exams" :key="e.id" :value="e.id">
          #{{ e.id }} {{ e.title }}（{{ e.require_booking ? '需预约' : '免预约' }} · 最多 {{ e.max_attempts }} 次）
        </option>
      </select>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <h3 style="margin-top: 0">预约审核</h3>
      <div class="toolbar" style="margin-bottom: 8px">
        <button v-for="t in (['pending', 'approved', 'rejected', 'used', 'missed', ''] as const)"
                :key="t" class="btn btn-sm"
                :class="{ 'btn-primary': reviewStatus === t }"
                @click="reviewStatus = t; reviewPage = 1">
          {{ t === '' ? '全部' : statusText[t] }}
        </button>
      </div>
      <table class="table">
        <thead>
          <tr>
            <th>学生</th><th>类型</th><th>场次</th><th>时段</th>
            <th>申请说明</th><th>状态</th><th>审核意见</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in reviewList" :key="b.id">
            <td>{{ b.real_name }}（{{ b.username }}）</td>
            <td>{{ b.booking_type === 'first' ? '首考' : '补考' }}</td>
            <td>第 {{ b.attempt_no }} 次</td>
            <td>{{ b.slot_name || '-' }}<br /><span class="muted">{{ fmt(b.slot_start) }}</span></td>
            <td>{{ b.apply_reason || '-' }}</td>
            <td><span class="badge" :class="`badge-booking-${b.status}`">{{ statusText[b.status] }}</span></td>
            <td>
              <input v-if="b.status === 'pending'" v-model="reviewComment[b.id]"
                     type="text" placeholder="审核意见（可选）" style="width: 140px" />
              <span v-else>{{ b.review_comment || '-' }}</span>
            </td>
            <td>
              <template v-if="b.status === 'pending'">
                <button class="btn btn-sm btn-primary" @click="onReview(b, true)">通过</button>
                <button class="btn btn-sm btn-danger" @click="onReview(b, false)">驳回</button>
              </template>
              <button v-else-if="b.status === 'approved'"
                      class="btn btn-sm btn-danger" @click="cancelBooking(b.id).then(loadReview)">
                取消预约
              </button>
              <span v-else class="muted">-</span>
            </td>
          </tr>
          <tr v-if="!reviewList.length" class="empty-row">
            <td colspan="8">暂无预约记录</td>
          </tr>
        </tbody>
      </table>
      <div v-if="totalPages > 1" class="pager">
        <button class="btn btn-sm" :disabled="reviewPage <= 1" @click="reviewPage -= 1">上一页</button>
        <span>第 {{ reviewPage }} / {{ totalPages }} 页（共 {{ reviewTotal }} 条）</span>
        <button class="btn btn-sm" :disabled="reviewPage >= totalPages" @click="reviewPage += 1">下一页</button>
      </div>
    </div>

    <!-- 管理员配置时段名额 -->
    <div v-if="isAdmin" class="card">
      <div class="toolbar">
        <h3 style="margin: 0">时段与名额配置</h3>
        <span class="spacer"></span>
        <button class="btn btn-primary btn-sm" @click="openCreateSlot">+ 新增时段</button>
      </div>
      <table class="table">
        <thead>
          <tr>
            <th>批次</th><th>开始时间</th><th>结束时间</th>
            <th>名额</th><th>已约</th><th>剩余</th><th>状态</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in slotList" :key="s.id">
            <td>{{ s.name || '未命名批次' }}</td>
            <td>{{ fmt(s.start_time) }}</td>
            <td>{{ fmt(s.end_time) }}</td>
            <td>{{ s.capacity === 0 ? '不限' : s.capacity }}</td>
            <td>{{ s.booked_count }}</td>
            <td>{{ s.capacity === 0 ? '不限' : s.remaining }}</td>
            <td>
              <span class="badge" :class="s.status === 'open' ? 'badge-published' : 'badge-ended'">
                {{ s.status === 'open' ? '开放中' : '已关闭' }}
              </span>
            </td>
            <td>
              <button class="btn btn-sm" @click="openEditSlot(s)">编辑</button>
              <button class="btn btn-sm" @click="toggleSlotStatus(s)">
                {{ s.status === 'open' ? '关闭' : '开放' }}
              </button>
              <button class="btn btn-sm btn-danger" @click="onDeleteSlot(s)">删除</button>
            </td>
          </tr>
          <tr v-if="!slotList.length" class="empty-row">
            <td colspan="8">暂未配置时段</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 时段编辑弹窗 -->
    <div v-if="slotModalVisible" class="modal-mask" @click.self="slotModalVisible = false">
      <div class="modal-content">
        <h3>{{ editingSlot ? '编辑时段' : '新增时段' }}</h3>
        <div class="form-group">
          <label>批次名称</label>
          <input v-model="slotForm.name" type="text" placeholder="如：第一批次" />
        </div>
        <div class="form-group">
          <label>开始时间</label>
          <input v-model="slotForm.start_time" type="datetime-local" />
        </div>
        <div class="form-group">
          <label>结束时间</label>
          <input v-model="slotForm.end_time" type="datetime-local" />
        </div>
        <div class="form-group">
          <label>名额（0 表示不限）</label>
          <input v-model.number="slotForm.capacity" type="number" min="0" />
        </div>
        <div v-if="slotError" class="error-msg">{{ slotError }}</div>
        <div class="modal-actions">
          <button class="btn btn-primary" :disabled="slotSaving" @click="submitSlot">
            {{ slotSaving ? '保存中...' : '保存' }}
          </button>
          <button class="btn" @click="slotModalVisible = false">取消</button>
        </div>
      </div>
    </div>
  </template>
</template>

<style scoped>
.form-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.form-row label {
  width: 70px;
  color: #666;
  font-size: 14px;
}
.form-row select,
.form-row input {
  flex: 1;
  padding: 7px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
}
.muted {
  color: #999;
  font-size: 12px;
}
.pager {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 10px;
  font-size: 13px;
  color: #666;
}
.badge-booking-pending { background: #fff3e0; color: #e65100; }
.badge-booking-approved { background: #e8f5e9; color: #2e7d32; }
.badge-booking-rejected { background: #fce4ec; color: #c62828; }
.badge-booking-cancelled { background: #eceff1; color: #607d8b; }
.badge-booking-used { background: #e3f2fd; color: #1565c0; }
.badge-booking-missed { background: #f3e5f5; color: #7b1fa2; }
</style>
