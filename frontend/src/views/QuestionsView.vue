<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  createQuestion,
  deleteQuestion,
  listQuestions,
  listSubjects,
  type QuestionQuery,
} from '@/api/questions'
import { useAuthStore } from '@/stores/auth'
import type { QuestionListItem, QuestionOption, QuestionType, Subject } from '@/types'

const auth = useAuthStore()

const PAGE_SIZE = 10
const page = ref(1)
const total = ref(0)
const items = ref<QuestionListItem[]>([])
const subjects = ref<Subject[]>([])
const loading = ref(false)

const filters = reactive<{ question_type: QuestionType | ''; keyword: string }>({
  question_type: '',
  keyword: '',
})

const typeOptions: Array<{ value: QuestionType; label: string }> = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multiple_choice', label: '多选题' },
  { value: 'judgment', label: '判断题' },
  { value: 'fill_blank', label: '填空题' },
  { value: 'short_answer', label: '简答题' },
  { value: 'programming', label: '编程题' },
]

function typeLabel(t: QuestionType) {
  return typeOptions.find((o) => o.value === t)?.label || t
}

const modalVisible = ref(false)
const saving = ref(false)
const modalError = ref('')
const form = reactive({
  question_type: 'single_choice' as QuestionType,
  content: '',
  difficulty: 3,
  knowledge_point_id: 1,
  subject_id: 1,
  analysis: '',
  optionsText: '选项A@1\n选项B@0\n选项C@0\n选项D@0',
})

function resetForm() {
  form.question_type = 'single_choice'
  form.content = ''
  form.difficulty = 3
  form.knowledge_point_id = 1
  form.subject_id = subjects.value[0]?.id || 1
  form.analysis = ''
  form.optionsText = '选项A@1\n选项B@0\n选项C@0\n选项D@0'
  modalError.value = ''
}

const totalPages = () => Math.max(1, Math.ceil(total.value / PAGE_SIZE))

async function load(target?: number) {
  if (target !== undefined) {
    if (target < 1 || target > totalPages()) return
    page.value = target
  }
  loading.value = true
  try {
    const params: QuestionQuery = { page: page.value, page_size: PAGE_SIZE }
    if (filters.question_type) params.question_type = filters.question_type
    if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
    const data = await listQuestions(params)
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function openModal() {
  resetForm()
  modalVisible.value = true
}

async function submitQuestion() {
  if (!form.content.trim()) {
    modalError.value = '请填写题目内容'
    return
  }
  // 选项文本解析：每行 “内容@是否正确0/1”
  const options: QuestionOption[] = form.optionsText
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, i) => {
      const [content, flag] = line.split('@')
      return { content: content.trim(), is_correct: Number(flag) || 0, order_index: i }
    })

  saving.value = true
  modalError.value = ''
  try {
    await createQuestion({
      question_type: form.question_type,
      content: form.content.trim(),
      difficulty: form.difficulty,
      knowledge_point_id: form.knowledge_point_id,
      subject_id: form.subject_id,
      analysis: form.analysis,
      options,
    })
    modalVisible.value = false
    await load()
  } catch (e) {
    modalError.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function removeQuestion(id: number) {
  if (!window.confirm('确定删除该题目？')) return
  await deleteQuestion(id)
  await load(Math.min(page.value, totalPages()))
}

onMounted(async () => {
  subjects.value = await listSubjects()
  if (subjects.value.length) form.subject_id = subjects.value[0].id
  await load()
})
</script>

<template>
  <h2>📚 题库管理</h2>

  <div class="toolbar">
    <select v-model="filters.question_type">
      <option value="">全部题型</option>
      <option v-for="t in typeOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
    </select>
    <input v-model="filters.keyword" type="text" placeholder="搜索题目内容" @keyup.enter="load(1)" />
    <button class="btn btn-primary" @click="load(1)">搜索</button>
    <span class="spacer"></span>
    <button v-if="auth.canEdit" class="btn" @click="openModal">+ 新增题目</button>
  </div>

  <table class="table">
    <thead>
      <tr>
        <th>ID</th><th>题型</th><th>题目</th><th>难度</th><th v-if="auth.canEdit">操作</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="q in items" :key="q.id">
        <td>{{ q.id }}</td>
        <td>{{ typeLabel(q.question_type) }}</td>
        <td>{{ q.content.slice(0, 40) }}</td>
        <td>{{ '★'.repeat(q.difficulty) }}{{ '☆'.repeat(5 - q.difficulty) }}</td>
        <td v-if="auth.canEdit">
          <button class="btn btn-sm btn-danger" @click="removeQuestion(q.id)">删除</button>
        </td>
      </tr>
      <tr v-if="!loading && !items.length" class="empty-row">
        <td :colspan="auth.canEdit ? 5 : 4">暂无题目</td>
      </tr>
    </tbody>
  </table>

  <div class="pagination">
    <button class="btn btn-sm" :disabled="page <= 1" @click="load(page - 1)">上一页</button>
    <span>{{ page }}/{{ totalPages() }}（共 {{ total }} 题）</span>
    <button class="btn btn-sm" :disabled="page >= totalPages()" @click="load(page + 1)">下一页</button>
  </div>

  <div v-if="modalVisible" class="modal-mask" @click.self="modalVisible = false">
    <div class="modal-content">
      <h3>新增题目</h3>
      <div class="form-group">
        <label>题型</label>
        <select v-model="form.question_type">
          <option v-for="t in typeOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>科目</label>
        <select v-model.number="form.subject_id">
          <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>题目内容</label>
        <textarea v-model="form.content" rows="3"></textarea>
      </div>
      <div class="form-group">
        <label>难度 (1-5)</label>
        <input v-model.number="form.difficulty" type="number" min="1" max="5" />
      </div>
      <div class="form-group">
        <label>知识点ID</label>
        <input v-model.number="form.knowledge_point_id" type="number" />
      </div>
      <div class="form-group">
        <label>答案解析 / 关键词（多个以 | 分隔）</label>
        <textarea v-model="form.analysis" rows="2" placeholder="填空标准答案或简答关键词用|分隔"></textarea>
      </div>
      <div class="form-group">
        <label>选项（每行一个，格式：内容@是否正确0/1；填空/简答/编程可留空）</label>
        <textarea v-model="form.optionsText" rows="4"></textarea>
      </div>
      <div v-if="modalError" class="error-msg">{{ modalError }}</div>
      <div class="modal-actions">
        <button class="btn btn-primary" :disabled="saving" @click="submitQuestion">
          {{ saving ? '保存中...' : '保存' }}
        </button>
        <button class="btn" @click="modalVisible = false">取消</button>
      </div>
    </div>
  </div>
</template>
