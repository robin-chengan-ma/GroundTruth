export interface NavigationItem {
  label: string
  to: string
  permissions: string[]
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
]

export function canAccess(
  userPermissions: string[],
  requiredPermissions: string[] = [],
) {
  return requiredPermissions.every((permission) => userPermissions.includes(permission))
}

export function firstAccessiblePath(userPermissions: string[]) {
  for (const group of navigationGroups) {
    const item = group.items.find((candidate) =>
      canAccess(userPermissions, candidate.permissions),
    )
    if (item) return item.to
  }
  return null
}
