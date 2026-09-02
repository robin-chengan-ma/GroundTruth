import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

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

describe('SupplierQuoteListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['supplier_quote.manage'] }
  })

  it('顯示供應商報價清單並解析 RFQ 編號', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/supplier-quotes/') return Promise.resolve({ data: [quote] })
      return Promise.resolve({ data: [rfq] })
    })
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    expect(wrapper.text()).toContain('SQ-001')
    expect(wrapper.text()).toContain('RFQ-001')
    expect(wrapper.text()).toContain('優品科技')
  })

  it('提交草稿報價呼叫 submit 端點', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/supplier-quotes/') return Promise.resolve({ data: [quote] })
      return Promise.resolve({ data: [rfq] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierQuoteListView)
    await flushPromises()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text() === '提交')
    await submitButton?.trigger('click')

    expect(post).toHaveBeenCalledWith('/supplier-quotes/7/submit/')
  })

  it('新增報價：選擇 RFQ 與供應商後載入需求明細並送出', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/supplier-quotes/') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [rfq] })
    })
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
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/supplier-quotes/', expect.objectContaining({
      rfq_supplier_id: 11,
      items: [expect.objectContaining({ request_item_id: 21, unit_price: 1250 })],
    }))
  })
})
