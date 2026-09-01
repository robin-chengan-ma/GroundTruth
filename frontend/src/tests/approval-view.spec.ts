import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

import { useAuthStore } from '../stores/auth'
import ApprovalView from '../views/ApprovalView.vue'

const approvalCase = {
  id: 21,
  award_id: 8,
  request_id: 5,
  request_no: 'PR-2026-005',
  purpose: '辦公設備汰換',
  requester: { id: 1, name: 'Alice Chen' },
  policy: { id: 3, name: '中額採購簽核' },
  total_amount: '30000.00',
  currency: 'TWD',
  status: 'pending',
  submitted_at: '2026-09-01T08:00:00Z',
  decided_at: null,
  steps: [{
    id: 31,
    sequence: 1,
    step_type: 'amount_approval',
    role: { id: 2, code: 'manager' },
    status: 'pending',
    claimed_by: null,
    claimed_at: null,
    decided_by: null,
    decided_at: null,
    decision_reason: null,
    can_claim: true,
    can_decide: false,
  }],
}

describe('ApprovalView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = {
      id: 3,
      name: 'Carol',
      email: 'carol@example.invalid',
      role: 'manager',
      permissions: ['approval.read_all', 'approval.claim', 'approval.decide'],
    }
  })

  it('讀取並顯示新版簽核案件與關卡', async () => {
    get.mockResolvedValue({ data: [approvalCase] })

    const wrapper = mount(ApprovalView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/approval-cases/')
    expect(wrapper.text()).toContain('PR-2026-005')
    expect(wrapper.text()).toContain('辦公設備汰換')
    expect(wrapper.text()).toContain('Alice Chen')
    expect(wrapper.text()).toContain('中額採購簽核')
    expect(wrapper.text()).toContain('關卡 1')
    expect(wrapper.text()).toContain('manager')
  })

  it('透過新版 step API 認領並以理由決議', async () => {
    get
      .mockResolvedValueOnce({ data: [approvalCase] })
      .mockResolvedValueOnce({
        data: [{
          ...approvalCase,
          status: 'in_progress',
          steps: [{
            ...approvalCase.steps[0],
            status: 'claimed',
            claimed_by: { id: 3, name: 'Carol' },
            can_claim: false,
            can_decide: true,
          }],
        }],
      })
      .mockResolvedValueOnce({ data: [] })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(ApprovalView)
    await flushPromises()

    await wrapper.get('button[data-action="claim"]').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/approval-steps/31/claim/')

    await wrapper.get('textarea[aria-label="簽核理由"]').setValue('預算與規格皆符合')
    await wrapper.get('button[data-action="approve"]').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/approval-steps/31/decide/', {
      decision: 'approved',
      reason: '預算與規格皆符合',
    })
  })
})
