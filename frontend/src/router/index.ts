import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import ApprovalView from '../views/ApprovalView.vue'
import InquiryView from '../views/InquiryView.vue'
import LoginView from '../views/LoginView.vue'
import ManualReviewView from '../views/ManualReviewView.vue'
import PurchaseRequestListView from '../views/PurchaseRequestListView.vue'
import { canAccess, firstAccessiblePath } from '../navigation'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'home', component: { template: '<span />' } },
    {
      path: '/inquiry',
      name: 'inquiry',
      component: InquiryView,
      meta: { permissions: ['purchase_request.create'] },
    },
    {
      path: '/purchase-requests',
      name: 'purchase-requests',
      component: PurchaseRequestListView,
      meta: { permissions: ['purchase_request.read_own'] },
    },
    {
      path: '/purchase-requests/:id',
      name: 'purchase-request-detail',
      component: PurchaseRequestListView,
      meta: { permissions: ['purchase_request.read_own'] },
    },
    {
      path: '/approvals',
      name: 'approvals',
      component: ApprovalView,
      meta: { permissions: ['approval.read_all'] },
    },
    {
      path: '/reviews',
      name: 'reviews',
      component: ManualReviewView,
      meta: { permissions: ['manual_review.decide'] },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()
  const fallback = firstAccessiblePath(auth.user?.permissions ?? [])
  if (to.meta.public) return auth.isAuthenticated ? (fallback ?? false) : true
  if (!auth.isAuthenticated) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'home') return fallback ?? false
  if (!canAccess(auth.user?.permissions ?? [], to.meta.permissions)) return fallback ?? false
  return true
})

export default router
