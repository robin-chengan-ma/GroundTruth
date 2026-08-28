import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import ApprovalView from '../views/ApprovalView.vue'
import InquiryView from '../views/InquiryView.vue'
import LoginView from '../views/LoginView.vue'
import ManualReviewView from '../views/ManualReviewView.vue'
import QuoteListView from '../views/QuoteListView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', redirect: '/inquiry' },
    { path: '/inquiry', name: 'inquiry', component: InquiryView },
    { path: '/quotes', name: 'quotes', component: QuoteListView },
    { path: '/approvals', name: 'approvals', component: ApprovalView, meta: { approver: true } },
    { path: '/reviews', name: 'reviews', component: ManualReviewView, meta: { admin: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()
  if (to.meta.public) return auth.isAuthenticated ? '/inquiry' : true
  if (!auth.isAuthenticated) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !auth.isAdmin) return '/inquiry'
  if (to.meta.approver && !auth.canApprove) return '/inquiry'
  return true
})

export default router
