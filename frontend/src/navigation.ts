export interface NavigationItem {
  label: string
  to: string
  /** 必須同時擁有的權限（AND）。 */
  permissions?: string[]
  /** 只要擁有其中之一即可（OR）；例如管理角色與稽核角色都能讀取同一份查詢資料。 */
  anyPermissions?: string[]
}

export interface NavigationGroup {
  label: string
  items: NavigationItem[]
}

export const navigationGroups: NavigationGroup[] = [
  {
    label: '工作台',
    items: [
      {
        label: '新增採購需求',
        to: '/inquiry',
        permissions: ['purchase_request.create'],
      },
      {
        label: '我的採購需求',
        to: '/purchase-requests',
        permissions: ['purchase_request.read_own'],
      },
    ],
  },
  {
    label: '待辦工作',
    items: [
      {
        label: '簽核工作區',
        to: '/approvals',
        permissions: ['approval.read_all'],
      },
      {
        label: 'AI 人工複核',
        to: '/reviews',
        permissions: ['manual_review.decide'],
      },
    ],
  },
  {
    label: '主檔管理',
    items: [
      { label: '供應商', to: '/suppliers', permissions: ['master_data.read'] },
      { label: '品項與分類', to: '/products', permissions: ['master_data.read'] },
      { label: '供應商品項與價格', to: '/supplier-products', permissions: ['master_data.read'] },
    ],
  },
  {
    label: '詢價與評選',
    items: [
      { label: 'RFQ', to: '/rfqs', anyPermissions: ['rfq.manage', 'audit.read'] },
      { label: '供應商報價', to: '/supplier-quotes', anyPermissions: ['supplier_quote.manage', 'audit.read'] },
      { label: '得標方案', to: '/award-decisions', anyPermissions: ['award.recommend', 'audit.read'] },
    ],
  },
  {
    label: '訂單與到貨',
    items: [
      { label: '採購單', to: '/purchase-orders', anyPermissions: ['purchase_order.manage', 'audit.read'] },
      { label: '收貨與驗收', to: '/goods-receipts', anyPermissions: ['receipt.record', 'inspection.decide', 'audit.read'] },
      {
        label: '驗收差異',
        to: '/inspection-variances',
        anyPermissions: ['purchase_order.manage', 'receipt.record', 'inspection.decide', 'audit.read'],
      },
    ],
  },
  {
    label: '庫存與建議',
    items: [
      { label: '庫存', to: '/inventory', permissions: ['inventory.read'] },
      { label: '採購建議', to: '/purchase-suggestions', permissions: ['purchase_suggestion.read'] },
    ],
  },
  {
    label: '稽核',
    items: [
      { label: '稽核紀錄', to: '/audit-logs', permissions: ['audit.read'] },
      { label: '採購稽核與流程健康總覽', to: '/audit-dashboard', permissions: ['audit.read'] },
    ],
  },
]

export function canAccess(
  userPermissions: string[],
  requiredPermissions: string[] = [],
  anyPermissions?: string[],
) {
  const passesAll = requiredPermissions.every((permission) => userPermissions.includes(permission))
  const passesAny = !anyPermissions || anyPermissions.length === 0
    || anyPermissions.some((permission) => userPermissions.includes(permission))
  return passesAll && passesAny
}

export function firstAccessiblePath(userPermissions: string[]) {
  for (const group of navigationGroups) {
    const item = group.items.find((candidate) =>
      canAccess(userPermissions, candidate.permissions, candidate.anyPermissions),
    )
    if (item) return item.to
  }
  return null
}
