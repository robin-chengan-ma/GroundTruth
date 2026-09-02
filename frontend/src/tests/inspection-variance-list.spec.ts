import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

import { useAuthStore } from '../stores/auth'
import InspectionVarianceListView from '../views/InspectionVarianceListView.vue'

const varianceCase = {
  id: 5, quality_inspection_id: 41, product: { id: 5, name: '辦公椅' }, supplier: { id: 1, name: '優品科技' },
  variance_quantity: '2.000', status: 'draft', version: 1, created_by: { id: 1, name: 'PM' },
  submitted_at: null,
  lines: [{ id: 1, action_type: 'replacement', quantity: '2.000', reason: '破損', status: 'pending' }],
  created_at: '', updated_at: '',
}
const receiptWithInspection = {
  id: 12, receipt_no: 'GR-001', po_id: 8, po_no: 'PO-001', supplier: { id: 1, name: '優品科技' },
  status: 'inspected', version: 1, received_by: { id: 1, name: 'PM' }, received_at: '2026-08-15T00:00:00Z',
  items: [{
    id: 41, purchase_order_item_id: 31, product_name: '辦公椅', received_quantity: '5.000', lot_no: '',
    inspection: { id: 41, status: 'completed', accepted_quantity: '3.000', defective_quantity: '2.000', rejected_quantity: '0.000' },
  }],
  created_at: '', updated_at: '',
}

describe('InspectionVarianceListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['purchase_order.manage'] }
  })

  it('顯示驗收差異案件清單', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/inspection-variances/') return Promise.resolve({ data: [varianceCase] })
      return Promise.resolve({ data: [] })
    })
    const wrapper = mount(InspectionVarianceListView)
    await flushPromises()

    expect(wrapper.text()).toContain('辦公椅')
    expect(wrapper.text()).toContain('優品科技')
  })

  it('草稿案件送出呼叫 submit 端點', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/inspection-variances/') return Promise.resolve({ data: [varianceCase] })
      return Promise.resolve({ data: [] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(InspectionVarianceListView)
    await flushPromises()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text() === '送出')
    await submitButton?.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/inspection-variances/5/submit/', { version: 1 })
  })

  it('新增差異案件：從候選驗收清單選擇並送出處理明細', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/inspection-variances/') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [receiptWithInspection] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(InspectionVarianceListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增差異案件')
    await createButton?.trigger('click')
    await wrapper.get('#variance-inspection').setValue(41)
    await wrapper.get('#variance-qty-0').setValue(2)
    await wrapper.get('#variance-reason-0').setValue('破損')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/inspection-variances/', {
      quality_inspection_id: 41,
      lines: [expect.objectContaining({ action_type: 'replacement', quantity: 2, reason: '破損' })],
    })
  })

  it('open 案件的處理明細可標記結案', async () => {
    const openCase = { ...varianceCase, status: 'open' }
    get.mockImplementation((url: string) => {
      if (url === '/inspection-variances/') return Promise.resolve({ data: [openCase] })
      return Promise.resolve({ data: [] })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(InspectionVarianceListView)
    await flushPromises()

    const detailButton = wrapper.findAll('button').find((btn) => btn.text() === '詳情')
    await detailButton?.trigger('click')
    const completeButton = wrapper.findAll('button').find((btn) => btn.text() === '標記結案')
    await completeButton?.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/inspection-variances/5/complete-line/', { line_id: 1, version: 1 })
  })
})
