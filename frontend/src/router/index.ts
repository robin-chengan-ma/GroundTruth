import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import ApprovalView from '../views/ApprovalView.vue'
import AuditDashboardView from '../views/AuditDashboardView.vue'
import AuditLogListView from '../views/AuditLogListView.vue'
import AwardDecisionListView from '../views/AwardDecisionListView.vue'
import GoodsReceiptListView from '../views/GoodsReceiptListView.vue'
import InquiryView from '../views/InquiryView.vue'
import InspectionVarianceListView from '../views/InspectionVarianceListView.vue'
import InventoryView from '../views/InventoryView.vue'
import LoginView from '../views/LoginView.vue'
import ManualReviewView from '../views/ManualReviewView.vue'
import ProductListView from '../views/ProductListView.vue'
import PurchaseOrderListView from '../views/PurchaseOrderListView.vue'
import PurchaseRequestListView from '../views/PurchaseRequestListView.vue'
import PurchaseSuggestionListView from '../views/PurchaseSuggestionListView.vue'
import RfqListView from '../views/RfqListView.vue'
import SupplierListView from '../views/SupplierListView.vue'
import SupplierProductListView from '../views/SupplierProductListView.vue'
import SupplierQuoteListView from '../views/SupplierQuoteListView.vue'
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
    {
      path: '/suppliers',
      name: 'suppliers',
      component: SupplierListView,
      meta: { permissions: ['master_data.read'] },
    },
    {
      path: '/products',
      name: 'products',
      component: ProductListView,
      meta: { permissions: ['master_data.read'] },
    },
    {
      path: '/supplier-products',
      name: 'supplier-products',
      component: SupplierProductListView,
      meta: { permissions: ['master_data.read'] },
    },
    {
      path: '/rfqs',
      name: 'rfqs',
      component: RfqListView,
      meta: { anyPermissions: ['rfq.manage', 'audit.read'] },
    },
    {
      path: '/supplier-quotes',
      name: 'supplier-quotes',
      component: SupplierQuoteListView,
      meta: { anyPermissions: ['supplier_quote.manage', 'audit.read'] },
    },
    {
      path: '/award-decisions',
      name: 'award-decisions',
      component: AwardDecisionListView,
      meta: { anyPermissions: ['award.recommend', 'audit.read'] },
    },
    {
      path: '/purchase-orders',
      name: 'purchase-orders',
      component: PurchaseOrderListView,
      meta: { anyPermissions: ['purchase_order.manage', 'audit.read'] },
    },
    {
      path: '/goods-receipts',
      name: 'goods-receipts',
      component: GoodsReceiptListView,
      meta: { anyPermissions: ['receipt.record', 'inspection.decide', 'audit.read'] },
    },
    {
      path: '/inspection-variances',
      name: 'inspection-variances',
      component: InspectionVarianceListView,
      meta: { anyPermissions: ['purchase_order.manage', 'receipt.record', 'inspection.decide', 'audit.read'] },
    },
    {
      path: '/inventory',
      name: 'inventory',
      component: InventoryView,
      meta: { permissions: ['inventory.read'] },
    },
    {
      path: '/purchase-suggestions',
      name: 'purchase-suggestions',
      component: PurchaseSuggestionListView,
      meta: { permissions: ['purchase_suggestion.read'] },
    },
    {
      path: '/audit-logs',
      name: 'audit-logs',
      component: AuditLogListView,
      meta: { permissions: ['audit.read'] },
    },
    {
      path: '/audit-dashboard',
      name: 'audit-dashboard',
      component: AuditDashboardView,
      meta: { permissions: ['audit.read'] },
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
  if (!canAccess(auth.user?.permissions ?? [], to.meta.permissions, to.meta.anyPermissions)) return fallback ?? false
  return true
})

export default router
