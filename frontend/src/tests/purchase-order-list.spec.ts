import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

import { useAuthStore } from '../stores/auth'
import PurchaseOrderListView from '../views/PurchaseOrderListView.vue'

const order = {
  id: 8, po_no: 'PO-001', request_no: 'PR-002', supplier: { id: 1, name: '優品科技' },
  status: 'draft', currency: 'TWD', total_amount: '6000.00', version: 1,
  issued_at: null, expected_delivery_date: null,
  items: [{ id: 1, line_no: 1, product_name: '辦公椅', quantity: '5.000', unit_price: '1200.00', amount: '6000.00' }],
  created_at: '', updated_at: '',
}

describe('PurchaseOrderListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['purchase_order.manage'] }
  })

  it('顯示採購單清單', async () => {
    get.mockResolvedValue({ data: [order] })
    const wrapper = mount(PurchaseOrderListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/purchase-orders/')
    expect(wrapper.text()).toContain('PO-001')
    expect(wrapper.text()).toContain('優品科技')
    expect(wrapper.text()).toContain('TWD 6,000')
  })

  it('草稿採購單可發出，呼叫 issue 端點', async () => {
    get.mockResolvedValue({ data: [order] })
    post.mockResolvedValue({ data: { ...order, status: 'issued' } })
    const wrapper = mount(PurchaseOrderListView)
    await flushPromises()

    const issueButton = wrapper.findAll('button').find((btn) => btn.text() === '發出')
    await issueButton?.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/purchase-orders/8/issue/', { version: 1 })
  })
})
