import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post, patch } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post, patch } }))

import { useAuthStore } from '../stores/auth'
import AwardDecisionListView from '../views/AwardDecisionListView.vue'

const rfq = {
  id: 3, rfq_no: 'RFQ-001', request_id: 2, request_no: 'PR-002', request_purpose: '辦公設備',
  revision: 1, status: 'evaluating', response_due_at: '', rule_snapshot: {}, version: 2,
  supplier_ids: [1], invited_suppliers: [], criteria: [], request_items: [],
  created_at: '', updated_at: '',
}
const award = {
  id: 4, rfq_id: 3, revision: 1, status: 'draft', selection_reason: '', selected_by: { id: 1, name: 'PM' },
  submitted_at: null, approval_case_id: null, total_amount_twd: '6000.00',
  lines: [{
    id: 1, request_item_id: 21, supplier_quote_item_id: 1, supplier_id: 1, supplier_name: '優品科技',
    quantity: '5.000', unit_cost_twd: '1200.00', amount_twd: '6000.00', reason: '',
  }],
}

describe('AwardDecisionListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['award.recommend'] }
  })

  it('顯示得標方案清單並解析 RFQ 編號', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/award-decisions/') return Promise.resolve({ data: [award] })
      return Promise.resolve({ data: [rfq] })
    })
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    expect(wrapper.text()).toContain('RFQ-001')
    expect(wrapper.text()).toContain('PM')
  })

  it('提交草稿得標方案呼叫 submit 端點', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/award-decisions/') return Promise.resolve({ data: [award] })
      return Promise.resolve({ data: [rfq] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text() === '提交')
    await submitButton?.trigger('click')

    expect(post).toHaveBeenCalledWith('/award-decisions/4/submit/')
  })

  it('新增得標方案：選擇 RFQ 後載入評選結果並依品項送出分配', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/award-decisions/') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [rfq] })
    })
    post.mockImplementation((url: string) => {
      if (url === '/rfqs/3/evaluate/') {
        return Promise.resolve({
          data: {
            items: [{
              request_item_id: 21, line_no: 1, description: '辦公椅', requested_quantity: '5.000',
              unit_of_measure: 'EA', recommended_quote_ids: [1],
              quotes: [{
                quote_id: 1, quote_item_id: 1, supplier_id: 1, supplier_name: '優品科技',
                unit_price: '1200.00', currency: 'TWD', allocated_unit_cost_twd: '1200.00',
                eligible: true, eligibility_reason: '符合推薦資格', total_score: '92.50',
              }],
            }],
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增得標方案')
    await createButton?.trigger('click')
    await wrapper.get('#award-rfq').setValue(3)
    await wrapper.get('#award-rfq').trigger('change')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/rfqs/3/evaluate/')
    await wrapper.get('select[id^="award-line-supplier-"]').setValue(1)
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/award-decisions/', expect.objectContaining({
      rfq_id: 3,
      lines: [expect.objectContaining({ request_item_id: 21, supplier_quote_item_id: 1 })],
    }))
  })
})
