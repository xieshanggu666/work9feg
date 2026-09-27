import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '仪表盘' },
      },
      {
        path: 'questions',
        name: 'questions',
        component: () => import('@/views/QuestionsView.vue'),
        meta: { title: '题库管理' },
      },
      {
        path: 'exams',
        name: 'exams',
        component: () => import('@/views/ExamsView.vue'),
        meta: { title: '考试中心' },
      },
      {
        path: 'bookings',
        name: 'bookings',
        component: () => import('@/views/BookingsView.vue'),
        meta: { title: '考试预约与补考' },
      },
      {
        path: 'grades/:examId',
        name: 'grades',
        component: () => import('@/views/GradesView.vue'),
        meta: { title: '成绩统计' },
      },
      {
        path: 'certificates',
        name: 'certificates',
        component: () => import('@/views/CertificatesView.vue'),
        meta: { title: '我的证书' },
      },
    ],
  },
  {
    path: '/exam/:examId/take',
    name: 'exam-take',
    component: () => import('@/views/ExamTakeView.vue'),
    meta: { title: '答题中' },
  },
  {
    path: '/result/:attemptId',
    name: 'exam-result',
    component: () => import('@/views/ExamResultView.vue'),
    meta: { title: '考试结果' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (auth.isLoggedIn && to.name === 'login') return { name: 'dashboard' }
    return true
  }
  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (!auth.user) {
    const u = await auth.fetchCurrentUser()
    if (!u) return { name: 'login' }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${(to.meta.title as string) || ''} - 在线考试系统`
})

export default router
