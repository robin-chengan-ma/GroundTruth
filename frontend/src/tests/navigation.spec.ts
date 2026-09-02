import { describe, expect, it } from 'vitest'

import { canAccess, firstAccessiblePath } from '../navigation'

describe('權限導覽', () => {
  it('必須擁有 route 要求的全部權限', () => {
    expect(canAccess(['approval.read_all'], ['approval.read_all'])).toBe(true)
    expect(canAccess([], ['approval.read_all'])).toBe(false)
  })

  it('回傳使用者第一個可存取頁面', () => {
    expect(firstAccessiblePath(['manual_review.decide'])).toBe('/reviews')
    expect(firstAccessiblePath([])).toBeNull()
  })

  it('anyPermissions 只需擁有其中之一（例如管理角色或稽核角色皆可讀取 RFQ）', () => {
    expect(canAccess(['rfq.manage'], [], ['rfq.manage', 'audit.read'])).toBe(true)
    expect(canAccess(['audit.read'], [], ['rfq.manage', 'audit.read'])).toBe(true)
    expect(canAccess(['purchase_request.create'], [], ['rfq.manage', 'audit.read'])).toBe(false)
  })
})
