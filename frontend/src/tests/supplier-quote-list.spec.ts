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
import SupplierQuoteListView from '../views/SupplierQuoteListView.vue'

const rfq = {
  id: 3, rfq_no: 'RFQ-001', request_id: 2, request_no: 'PR-002', request_purpose: '辦公設備',
  revision: 1, status: 'issued', response_due_at: '', rule_snapshot: {}, version: 1,
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
const quote = {
  id: 7, quote_no: 'SQ-001', rfq_id: 3, supplier_id: 1, supplier_name: '優品科技', revision: 1,
  status: 'draft', currency: 'TWD', exchange_rate_to_twd: '1.000000', items_subtotal: '6000.00',
  tax_amount: '0.00', shipping_amount: '0.00', discount_amount: '0.00', landed_total_twd: '6000.00',
  payment_terms_snapshot: '', valid_until: null, submitted_at: null,
  items: [{ id: 1, request_item_id: 21, quantity: '5.000', unit_price: '1200.00', subtotal: '6000.00', lead_time_days: 7, warranty_months: null, specifications: {} }],
  created_at: '2026-08-05T00:00:00Z',
}

function mockLists(quoteResults = [quote], rfqResults = [rfq]) {
  get.mockImplementation((url: string) => {
    if (url === '/supplier-quotes/') {
      return Promise.resolve({ data: { count: quoteResults.length, page: 1, page_size: 20, total_pages: 1, results: quoteResults } })
    }
    return Promise.resolve({ data: { count: rfqResults.length, page: 1, page_size: 50, total_pages: 1, results: rfqResults } })
  })
}

describe('SupplierQuoteListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    route.query = {}
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['supplier_quote.manage'] }
  })

  it('顯示供應商報價清單並解析 RFQ 編號', async () => {
    mockLists()
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/supplier-quotes/', { params: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('SQ-001')
    expect(wrapper.text()).toContain('RFQ-001')
    expect(wrapper.text()).toContain('優品科技')
  })

  it('搜尋供應商報價時帶入 search 查詢參數並回到第一頁', async () => {
    mockLists([], [])
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    await wrapper.get('input[aria-label="搜尋供應商報價"]').setValue('SQ-001')
    await wrapper.get('form.filter-bar').trigger('submit.prevent')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', search: 'SQ-001' } })
  })

  it('依狀態篩選時帶入 status 查詢參數', async () => {
    mockLists([], [])
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    await wrapper.get('select[aria-label="狀態篩選"]').setValue('submitted')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', status: 'submitted' } })
  })

  it('沒有符合條件的報價時顯示對應空狀態文字', async () => {
    mockLists([], [])
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有符合條件的供應商報價資料。')
  })

  it('提交草稿報價呼叫 submit 端點', async () => {
    mockLists()
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text() === '提交')
    await submitButton?.trigger('click')

    expect(post).toHaveBeenCalledWith('/supplier-quotes/7/submit/')
  })

  it('新增報價：選擇 RFQ 與供應商後載入需求明細並送出', async () => {
    mockLists([], [rfq])
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增報價')
    await createButton?.trigger('click')
    await wrapper.get('#quote-rfq').setValue(3)
    await wrapper.get('#quote-rfq').trigger('change')
    await wrapper.get('#quote-supplier').setValue(11)
    expect(wrapper.text()).toContain('辦公椅')

    const lineCheckbox = wrapper.get('.line-editor input[type="checkbox"]')
    await lineCheckbox.setValue(true)
    await wrapper.get('input[type="number"][step="0.01"][min="0"]#line-price-21').setValue(1250)
    await wrapper.get('.detail-modal form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/supplier-quotes/', expect.objectContaining({
      rfq_supplier_id: 11,
      items: [expect.objectContaining({ request_item_id: 21, unit_price: 1250 })],
    }))
  })
})
