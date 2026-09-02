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
import ProductListView from '../views/ProductListView.vue'

const category = { id: 1, code: 'CAT-1', name: '辦公家具', spec_schema: {}, is_active: true, created_at: '', updated_at: '' }
const product = {
  id: 5, name: '辦公椅', category: 1, category_name: '辦公家具', sku: 'SKU-1', description: '',
  specifications: {}, unit_of_measure: 'EA', is_active: true, price: '1500.00', currency: 'TWD', updated_at: '',
}

function mockLists(categoryResults = [category], productResults = [product]) {
  get.mockImplementation((url: string) => {
    if (url === '/product-categories/') {
      return Promise.resolve({ data: { count: categoryResults.length, page: 1, page_size: 50, total_pages: 1, results: categoryResults } })
    }
    return Promise.resolve({ data: { count: productResults.length, page: 1, page_size: 20, total_pages: 1, results: productResults } })
  })
}

describe('ProductListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    route.query = {}
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', permissions: ['master_data.read', 'master_data.manage'] }
  })

  it('顯示品項分類與品項清單', async () => {
    mockLists()
    const wrapper = mount(ProductListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/product-categories/', { params: { page: 1, page_size: 50 } })
    expect(get).toHaveBeenCalledWith('/products/', { params: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('辦公家具')
    expect(wrapper.text()).toContain('辦公椅')
    expect(wrapper.text()).toContain('SKU-1')
  })

  it('品項分類超過一頁時仍會用 fetchAllPages 抓完整清單，不會漏第 51 筆以後的分類', async () => {
    const categoryPage1 = [category]
    const categoryPage2 = [{ ...category, id: 2, code: 'CAT-2', name: '文具用品' }]
    get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/product-categories/') {
        const page = (config?.params?.page as number | undefined) ?? 1
        if (page === 1) {
          return Promise.resolve({ data: { count: 2, page: 1, page_size: 50, total_pages: 2, results: categoryPage1 } })
        }
        return Promise.resolve({ data: { count: 2, page: 2, page_size: 50, total_pages: 2, results: categoryPage2 } })
      }
      return Promise.resolve({ data: { count: 0, page: 1, page_size: 20, total_pages: 1, results: [] } })
    })
    const wrapper = mount(ProductListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/product-categories/', { params: { page: 1, page_size: 50 } })
    expect(get).toHaveBeenCalledWith('/product-categories/', { params: { page: 2, page_size: 50 } })
    expect(wrapper.text()).toContain('辦公家具')
    expect(wrapper.text()).toContain('文具用品')
  })

  it('搜尋品項時帶入 search 查詢參數並回到第一頁', async () => {
    mockLists([], [])
    const wrapper = mount(ProductListView)
    await flushPromises()

    await wrapper.get('input[aria-label="搜尋品項"]').setValue('辦公椅')
    await wrapper.get('form.filter-bar').trigger('submit.prevent')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', search: '辦公椅' } })
  })

  it('依啟用狀態篩選品項時帶入 is_active 查詢參數', async () => {
    mockLists([], [])
    const wrapper = mount(ProductListView)
    await flushPromises()

    await wrapper.get('select[aria-label="啟用狀態篩選"]').setValue('false')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', is_active: 'false' } })
  })

  it('沒有符合條件的品項時顯示對應空狀態文字', async () => {
    mockLists([], [])
    const wrapper = mount(ProductListView)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有符合條件的品項主檔資料。')
  })

  it('新增品項分類送出正確 payload', async () => {
    mockLists([], [])
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(ProductListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增分類')
    await createButton?.trigger('click')
    await wrapper.get('#category-code').setValue('CAT-2')
    await wrapper.get('#category-name').setValue('文具用品')
    await wrapper.get('.detail-modal form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/product-categories/', { code: 'CAT-2', name: '文具用品', is_active: true })
  })

  it('停用品項送出 is_active=false', async () => {
    mockLists()
    patch.mockResolvedValue({ data: {} })
    const wrapper = mount(ProductListView)
    await flushPromises()

    const productRow = wrapper.findAll('tr').find((row) => row.text().includes('辦公椅'))
    const disableButton = productRow?.findAll('button').find((btn) => btn.text() === '停用')
    await disableButton?.trigger('click')

    expect(patch).toHaveBeenCalledWith('/products/5/', { is_active: false })
  })
})
