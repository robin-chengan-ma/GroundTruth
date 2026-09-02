import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

import { useAuthStore } from '../stores/auth'
import GoodsReceiptListView from '../views/GoodsReceiptListView.vue'

const purchaseOrder = {
  id: 8, po_no: 'PO-001', request_no: 'PR-002', supplier: { id: 1, name: '優品科技' },
  status: 'issued', currency: 'TWD', total_amount: '6000.00', version: 1,
  issued_at: '2026-08-10T00:00:00Z', expected_delivery_date: null,
  items: [{ id: 31, line_no: 1, product_name: '辦公椅', quantity: '5.000', unit_price: '1200.00', amount: '6000.00' }],
  created_at: '', updated_at: '',
}
const receipt = {
  id: 12, receipt_no: 'GR-001', po_id: 8, po_no: 'PO-001', supplier: { id: 1, name: '優品科技' },
  status: 'draft', version: 1, received_by: { id: 1, name: 'PM' }, received_at: '2026-08-15T00:00:00Z',
  items: [{
    id: 41, purchase_order_item_id: 31, product_name: '辦公椅', received_quantity: '5.000', lot_no: '',
    inspection: null,
  }],
  created_at: '', updated_at: '',
}

describe('GoodsReceiptListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['receipt.record', 'inspection.decide'] }
  })

  it('顯示收貨單清單', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/goods-receipts/') return Promise.resolve({ data: [receipt] })
      return Promise.resolve({ data: [purchaseOrder] })
    })
    const wrapper = mount(GoodsReceiptListView)
    await flushPromises()

    expect(wrapper.text()).toContain('GR-001')
    expect(wrapper.text()).toContain('PO-001')
    expect(wrapper.text()).toContain('優品科技')
  })

  it('草稿收貨單送驗呼叫 submit 端點', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/goods-receipts/') return Promise.resolve({ data: [receipt] })
      return Promise.resolve({ data: [purchaseOrder] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(GoodsReceiptListView)
    await flushPromises()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text() === '送驗')
    await submitButton?.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/goods-receipts/12/submit/', { version: 1 })
  })

  it('新增收貨單：選擇採購單後勾選明細並送出', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/goods-receipts/') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [purchaseOrder] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(GoodsReceiptListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增收貨單')
    await createButton?.trigger('click')
    await wrapper.get('#receipt-po').setValue(8)
    await wrapper.get('#receipt-po').trigger('change')

    const lineCheckbox = wrapper.get('.line-editor input[type="checkbox"]')
    await lineCheckbox.setValue(true)
    await wrapper.get('#receipt-qty-31').setValue(5)
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/goods-receipts/', {
      purchase_order_id: 8,
      items: [expect.objectContaining({ purchase_order_item_id: 31, received_quantity: 5 })],
    })
  })

  it('品質驗收：送出合格／瑕疵／拒收數量', async () => {
    const inspectingReceipt = { ...receipt, status: 'inspecting' }
    get.mockImplementation((url: string) => {
      if (url === '/goods-receipts/') return Promise.resolve({ data: [inspectingReceipt] })
      return Promise.resolve({ data: [purchaseOrder] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(GoodsReceiptListView)
    await flushPromises()

    const inspectButton = wrapper.findAll('button').find((btn) => btn.text() === '品質驗收')
    await inspectButton?.trigger('click')
    await wrapper.get('#inspect-accepted-41').setValue(5)
    await wrapper.get('#inspect-defective-41').setValue(0)
    await wrapper.get('#inspect-rejected-41').setValue(0)
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/goods-receipts/12/inspect/', {
      version: 1,
      items: [expect.objectContaining({ receipt_item_id: 41, accepted_quantity: 5, defective_quantity: 0, rejected_quantity: 0 })],
    })
  })
})
