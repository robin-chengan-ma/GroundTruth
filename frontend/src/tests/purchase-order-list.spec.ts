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
import PurchaseOrderListView from '../views/PurchaseOrderListView.vue'

const order = {
  id: 8, po_no: 'PO-001', request_no: 'PR-002', supplier: { id: 1, name: '優品科技' },
  status: 'draft', currency: 'TWD', total_amount: '6000.00', version: 1,
  issued_at: null, expected_delivery_date: null,
  items: [{ id: 1, line_no: 1, product_name: '辦公椅', quantity: '5.000', unit_price: '1200.00', amount: '6000.00' }],
  created_at: '', updated_at: '',
}

function mockList(items = [order]) {
  get.mockResolvedValue({ data: { count: items.length, page: 1, page_size: 20, total_pages: 1, results: items } })
}

describe('PurchaseOrderListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    route.query = {}
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['purchase_order.manage'] }
  })

  it('顯示採購單清單', async () => {
    mockList()
    const wrapper = mount(PurchaseOrderListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/purchase-orders/', { params: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('PO-001')
    expect(wrapper.text()).toContain('優品科技')
    expect(wrapper.text()).toContain('TWD 6,000')
  })

  it('搜尋採購單時帶入 search 查詢參數並回到第一頁', async () => {
    mockList([])
    const wrapper = mount(PurchaseOrderListView)
    await flushPromises()

    await wrapper.get('input[aria-label="搜尋採購單"]').setValue('PO-001')
    await wrapper.get('form.filter-bar').trigger('submit.prevent')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', search: 'PO-001' } })
  })

  it('依狀態篩選時帶入 status 查詢參數', async () => {
    mockList([])
    const wrapper = mount(PurchaseOrderListView)
    await flushPromises()

    await wrapper.get('select[aria-label="狀態篩選"]').setValue('issued')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', status: 'issued' } })
  })

  it('沒有符合條件的採購單時顯示對應空狀態文字', async () => {
    mockList([])
    const wrapper = mount(PurchaseOrderListView)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有符合條件的採購單資料。')
  })

  it('草稿採購單可發出，呼叫 issue 端點', async () => {
    mockList()
    post.mockResolvedValue({ data: { ...order, status: 'issued' } })
    const wrapper = mount(PurchaseOrderListView)
    await flushPromises()

    const issueButton = wrapper.findAll('button').find((btn) => btn.text() === '發出')
    await issueButton?.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/purchase-orders/8/issue/', { version: 1 })
  })
})
