import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

const { replace, route } = vi.hoisted(() => ({
  replace: vi.fn(),
  route: { query: {} as Record<string, string> },
}))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
}))

import { useAuthStore } from '../stores/auth'
import RfqListView from '../views/RfqListView.vue'

const rfq = {
  id: 3, rfq_no: 'RFQ-001', request_id: 2, request_no: 'PR-002', request_purpose: '辦公設備',
  revision: 1, status: 'draft', response_due_at: '', rule_snapshot: {}, version: 1,
  supplier_ids: [1], invited_suppliers: [{
    rfq_supplier_id: 11, supplier_id: 1, supplier_name: '優品科技', status: 'invited',
    invited_at: '2026-08-01T00:00:00Z', responded_at: null,
  }],
  criteria: [], request_items: [{
    id: 21, line_no: 1, product_id: 5, product_name: '辦公椅', description_snapshot: '辦公椅',
    specifications: {}, quantity: '5.000', unit_of_measure: 'EA',
  }],
  created_at: '', updated_at: '',
}

function mockList(items = [rfq]) {
  get.mockResolvedValue({ data: { count: items.length, page: 1, page_size: 20, total_pages: 1, results: items } })
}

describe('RfqListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    route.query = {}
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['rfq.manage'] }
  })

  it('顯示 RFQ 清單', async () => {
    mockList()
    const wrapper = mount(RfqListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/rfqs/', { params: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('RFQ-001')
    expect(wrapper.text()).toContain('PR-002')
  })

  it('搜尋 RFQ 時帶入 search 查詢參數並回到第一頁', async () => {
    mockList([])
    const wrapper = mount(RfqListView)
    await flushPromises()

    await wrapper.get('input[aria-label="搜尋 RFQ"]').setValue('RFQ-001')
    await wrapper.get('form.filter-bar').trigger('submit.prevent')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', search: 'RFQ-001' } })
  })

  it('依狀態篩選時帶入 status 查詢參數', async () => {
    mockList([])
    const wrapper = mount(RfqListView)
    await flushPromises()

    await wrapper.get('select[aria-label="狀態篩選"]').setValue('issued')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', status: 'issued' } })
  })

  it('沒有符合條件的 RFQ 時顯示對應空狀態文字', async () => {
    mockList([])
    const wrapper = mount(RfqListView)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有符合條件的 RFQ 資料。')
  })

  it('點擊詳情後可發出草稿 RFQ', async () => {
    mockList()
    post.mockResolvedValue({ data: { ...rfq, status: 'issued' } })
    const wrapper = mount(RfqListView)
    await flushPromises()

    const detailButton = wrapper.findAll('button').find((btn) => btn.text() === '查看詳情')
    await detailButton?.trigger('click')
    await wrapper.get('#rfq-due-at').setValue('2026-12-01T10:00')
    await wrapper.get('.detail-modal form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/rfqs/3/issue/', {
      version: 1, response_due_at: new Date('2026-12-01T10:00').toISOString(),
    })
  })

  it('執行評選會呼叫 evaluate 並顯示比較結果', async () => {
    const issuedRfq = { ...rfq, status: 'issued' }
    mockList([issuedRfq])
    post.mockResolvedValue({
      data: {
        rfq_id: 3, rfq_no: 'RFQ-001', status: 'evaluating', comparison_basis: '逐項比較',
        items: [{
          request_item_id: 21, line_no: 1, description: '辦公椅', requested_quantity: '5.000',
          unit_of_measure: 'EA', quotes: [{
            quote_id: 1, quote_item_id: 1, supplier_id: 1, supplier_name: '優品科技',
            quoted_quantity: '5.000', unit_price: '1200.00', currency: 'TWD',
            allocated_unit_cost_twd: '1200.00', eligible: true, eligibility_reason: '符合推薦資格',
            total_score: '92.50', data_completeness_pct: '100.00',
          }],
          recommended_supplier_names: ['優品科技'],
        }],
        quote_summaries: [],
      },
    })
    const wrapper = mount(RfqListView)
    await flushPromises()

    const detailButton = wrapper.findAll('button').find((btn) => btn.text() === '查看詳情')
    await detailButton?.trigger('click')
    const evaluateButton = wrapper.findAll('button').find((btn) => btn.text().includes('執行評選'))
    await evaluateButton?.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/rfqs/3/evaluate/')
    expect(wrapper.text()).toContain('92.50')
  })
})
