import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post, patch } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post, patch } }))

import { useAuthStore } from '../stores/auth'
import ProductListView from '../views/ProductListView.vue'

const category = { id: 1, code: 'CAT-1', name: '辦公家具', spec_schema: {}, is_active: true, created_at: '', updated_at: '' }
const product = {
  id: 5, name: '辦公椅', category: 1, category_name: '辦公家具', sku: 'SKU-1', description: '',
  specifications: {}, unit_of_measure: 'EA', is_active: true, price: '1500.00', currency: 'TWD', updated_at: '',
}

describe('ProductListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', permissions: ['master_data.read', 'master_data.manage'] }
  })

  it('顯示品項分類與品項清單', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/product-categories/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [category] } })
      return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [product] } })
    })
    const wrapper = mount(ProductListView)
    await flushPromises()

    expect(wrapper.text()).toContain('辦公家具')
    expect(wrapper.text()).toContain('辦公椅')
    expect(wrapper.text()).toContain('SKU-1')
  })

  it('新增品項分類送出正確 payload', async () => {
    get.mockResolvedValue({ data: { count: 0, next: null, previous: null, results: [] } })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(ProductListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增分類')
    await createButton?.trigger('click')
    await wrapper.get('#category-code').setValue('CAT-2')
    await wrapper.get('#category-name').setValue('文具用品')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/product-categories/', { code: 'CAT-2', name: '文具用品', is_active: true })
  })

  it('停用品項送出 is_active=false', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/product-categories/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [category] } })
      return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [product] } })
    })
    patch.mockResolvedValue({ data: {} })
    const wrapper = mount(ProductListView)
    await flushPromises()

    const productRow = wrapper.findAll('tr').find((row) => row.text().includes('辦公椅'))
    const disableButton = productRow?.findAll('button').find((btn) => btn.text() === '停用')
    await disableButton?.trigger('click')

    expect(patch).toHaveBeenCalledWith('/products/5/', { is_active: false })
  })
})
