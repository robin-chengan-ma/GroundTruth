import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post } }))

import { useAuthStore } from '../stores/auth'
import SupplierProductListView from '../views/SupplierProductListView.vue'

const supplierProduct = {
  id: 9, supplier: 1, supplier_name: '優品科技', product: 5, product_name: '辦公椅',
  supplier_sku: 'SUP-SKU-1', lead_time_days: 7, minimum_order_quantity: '1.000',
  quality_status: 'qualified', is_active: true,
  price_versions: [{
    id: 2, supplier_product: 9, unit_price: '1200.00', currency: 'TWD', minimum_quantity: '1.000',
    valid_from: '2026-01-01T00:00:00Z', valid_until: null, created_by: 1, created_by_name: 'Admin',
    created_at: '2026-01-01T00:00:00Z',
  }],
  created_at: '', updated_at: '',
}

describe('SupplierProductListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', permissions: ['master_data.read', 'master_data.manage'] }
  })

  it('顯示供應商品項與現行單價', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/supplier-products/') return Promise.resolve({ data: [supplierProduct] })
      return Promise.resolve({ data: { count: 0, next: null, previous: null, results: [] } })
    })
    const wrapper = mount(SupplierProductListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/supplier-products/')
    expect(wrapper.text()).toContain('優品科技')
    expect(wrapper.text()).toContain('辦公椅')
    expect(wrapper.text()).toContain('TWD 1,200')
  })

  it('新增價格版本送出正確 payload', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/supplier-products/') return Promise.resolve({ data: [supplierProduct] })
      return Promise.resolve({ data: { count: 0, next: null, previous: null, results: [] } })
    })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierProductListView)
    await flushPromises()

    const addPriceButton = wrapper.findAll('button').find((btn) => btn.text() === '新增價格版本')
    await addPriceButton?.trigger('click')
    await wrapper.get('#price-unit-price').setValue('1300')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/supplier-products/9/price-versions/', expect.objectContaining({
      unit_price: 1300, currency: 'TWD', minimum_quantity: '1',
    }))
  })
})
