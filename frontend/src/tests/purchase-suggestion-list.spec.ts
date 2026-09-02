import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

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

describe('PurchaseSuggestionListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = {
      id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin',
      permissions: ['purchase_request.create'],
    }
  })

  it('顯示採購建議清單', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/purchase-suggestions/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [suggestion] } })
      if (url === '/products/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [product] } })
      if (url === '/suppliers/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [supplier] } })
      return Promise.resolve({ data: { count: 0, next: null, previous: null, results: [] } })
    })
    const wrapper = mount(PurchaseSuggestionListView)
    await flushPromises()

    expect(wrapper.text()).toContain('辦公椅')
    expect(wrapper.text()).toContain('轉為採購需求')
  })

  it('轉單：勾選候選供應商後送出正確 payload', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/purchase-suggestions/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [suggestion] } })
      if (url === '/products/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [product] } })
      if (url === '/suppliers/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [supplier] } })
      return Promise.resolve({ data: { count: 0, next: null, previous: null, results: [] } })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(PurchaseSuggestionListView)
    await flushPromises()

    const convertButton = wrapper.findAll('button').find((btn) => btn.text() === '轉為採購需求')
    await convertButton?.trigger('click')
    await wrapper.get('.choice-card input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/purchase-suggestions/9/convert/', expect.objectContaining({
      supplier_ids: [1], currency: 'TWD',
    }))
  })
})
