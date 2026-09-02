import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post, patch } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post, patch } }))

const { replace, route } = vi.hoisted(() => ({
  replace: vi.fn(),
  route: { query: {} as Record<string, string> },
}))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
}))

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

function mockLists(awardResults = [award], rfqResults = [rfq]) {
  get.mockImplementation((url: string) => {
    if (url === '/award-decisions/') {
      return Promise.resolve({ data: { count: awardResults.length, page: 1, page_size: 20, total_pages: 1, results: awardResults } })
    }
    return Promise.resolve({ data: { count: rfqResults.length, page: 1, page_size: 50, total_pages: 1, results: rfqResults } })
  })
}

describe('AwardDecisionListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    route.query = {}
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['award.recommend'] }
  })

  it('顯示得標方案清單並解析 RFQ 編號', async () => {
    mockLists()
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/award-decisions/', { params: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('RFQ-001')
    expect(wrapper.text()).toContain('PM')
  })

  it('搜尋得標方案時帶入 search 查詢參數並回到第一頁', async () => {
    mockLists([], [])
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    await wrapper.get('input[aria-label="搜尋得標方案"]').setValue('RFQ-001')
    await wrapper.get('form.filter-bar').trigger('submit.prevent')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', search: 'RFQ-001' } })
  })

  it('依狀態篩選時帶入 status 查詢參數', async () => {
    mockLists([], [])
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    await wrapper.get('select[aria-label="狀態篩選"]').setValue('approved')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', status: 'approved' } })
  })

  it('沒有符合條件的得標方案時顯示對應空狀態文字', async () => {
    mockLists([], [])
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有符合條件的得標方案資料。')
  })

  it('提交草稿得標方案呼叫 submit 端點', async () => {
    mockLists()
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(AwardDecisionListView)
    await flushPromises()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text() === '提交')
    await submitButton?.trigger('click')

    expect(post).toHaveBeenCalledWith('/award-decisions/4/submit/')
  })

  it('新增得標方案：選擇 RFQ 後載入評選結果並依品項送出分配', async () => {
    mockLists([], [rfq])
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
    await wrapper.get('.detail-modal form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/award-decisions/', expect.objectContaining({
      rfq_id: 3,
      lines: [expect.objectContaining({ request_item_id: 21, supplier_quote_item_id: 1 })],
    }))
  })
})
