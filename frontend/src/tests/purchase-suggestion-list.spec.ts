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
import PurchaseSuggestionListView from '../views/PurchaseSuggestionListView.vue'

const suggestion = {
  id: 9, product: 5, suggested_qty: '10.000', status: 'pending', purchase_request: null,
  created_at: '2026-08-25T00:00:00Z',
}
const product = {
  id: 5, name: '辦公椅', category: 1, category_name: '辦公家具', sku: 'SKU-1', description: '',
  specifications: {}, unit_of_measure: 'EA', is_active: true, price: '1500.00', currency: 'TWD', updated_at: '',
}
const supplier = {
  id: 1, name: '優品科技', tier: 'strategic', code: 'SUP-1', status: 'active', tax_id: '', contact_name: '',
  contact_phone: '', contact_email: '', payment_terms: '', is_active: true, created_at: '', updated_at: '',
}

function mockLists(suggestionResults = [suggestion], productResults = [product], supplierResults = [supplier]) {
  get.mockImplementation((url: string) => {
    if (url === '/purchase-suggestions/') {
      return Promise.resolve({ data: { count: suggestionResults.length, page: 1, page_size: 20, total_pages: 1, results: suggestionResults } })
    }
    if (url === '/products/') {
      return Promise.resolve({ data: { count: productResults.length, page: 1, page_size: 50, total_pages: 1, results: productResults } })
    }
    if (url === '/suppliers/') {
      return Promise.resolve({ data: { count: supplierResults.length, page: 1, page_size: 50, total_pages: 1, results: supplierResults } })
    }
    return Promise.resolve({ data: { count: 0, page: 1, page_size: 50, total_pages: 1, results: [] } })
  })
}

describe('PurchaseSuggestionListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    route.query = {}
    const auth = useAuthStore()
    auth.user = {
      id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin',
      permissions: ['purchase_request.create'],
    }
  })

  it('顯示採購建議清單', async () => {
    mockLists()
    const wrapper = mount(PurchaseSuggestionListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/purchase-suggestions/', { params: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('辦公椅')
    expect(wrapper.text()).toContain('轉為採購需求')
  })

  it('搜尋採購建議時帶入 search 查詢參數並回到第一頁', async () => {
    mockLists([], [], [])
    const wrapper = mount(PurchaseSuggestionListView)
    await flushPromises()

    await wrapper.get('input[aria-label="搜尋採購建議"]').setValue('辦公椅')
    await wrapper.get('form.filter-bar').trigger('submit.prevent')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', search: '辦公椅' } })
  })

  it('依狀態篩選時帶入 status 查詢參數', async () => {
    mockLists([], [], [])
    const wrapper = mount(PurchaseSuggestionListView)
    await flushPromises()

    await wrapper.get('select[aria-label="狀態篩選"]').setValue('dismissed')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', status: 'dismissed' } })
  })

  it('沒有符合條件的採購建議時顯示對應空狀態文字', async () => {
    mockLists([], [], [])
    const wrapper = mount(PurchaseSuggestionListView)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有符合條件的採購建議。')
  })

  it('轉單：勾選候選供應商後送出正確 payload', async () => {
    mockLists()
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(PurchaseSuggestionListView)
    await flushPromises()

    const convertButton = wrapper.findAll('button').find((btn) => btn.text() === '轉為採購需求')
    await convertButton?.trigger('click')
    await wrapper.get('.choice-card input[type="checkbox"]').setValue(true)
    await wrapper.get('.detail-modal form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/purchase-suggestions/9/convert/', expect.objectContaining({
      supplier_ids: [1], currency: 'TWD',
    }))
  })
})
