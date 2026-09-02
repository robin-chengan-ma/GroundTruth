import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get } }))

import { useAuthStore } from '../stores/auth'
import InventoryView from '../views/InventoryView.vue'

const balance = {
  product: 5, product_name: '辦公椅', on_hand_quantity: '3.000', reserved_quantity: '1.000',
  in_transit_quantity: '0.000', available_quantity: '2.000', threshold: 5, updated_at: '2026-08-20T00:00:00Z',
}
const movementPage1 = {
  count: 2, next: '/inventory-movements/?cursor=abc', previous: null,
  results: [{
    id: 1, product: 5, product_name: '辦公椅', movement_type: 'receipt_accept', quantity_delta: '3.000',
    reference_type: 'goods_receipt', reference_id: 12, affects_balance: true, posted_by_name: 'PM',
    posted_at: '2026-08-20T00:00:00Z',
  }],
}
const movementPage2 = {
  count: 2, next: null, previous: null,
  results: [{
    id: 2, product: 5, product_name: '辦公椅', movement_type: 'issue_out', quantity_delta: '-1.000',
    reference_type: 'manual', reference_id: 1, affects_balance: true, posted_by_name: 'PM',
    posted_at: '2026-08-21T00:00:00Z',
  }],
}

describe('InventoryView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'PM', email: 'pm@example.com', role: 'manager', permissions: ['inventory.read'] }
  })

  it('顯示庫存餘額並標示低於門檻', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/inventory-balances/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [balance] } })
      return Promise.resolve({ data: movementPage1 })
    })
    const wrapper = mount(InventoryView)
    await flushPromises()

    expect(wrapper.text()).toContain('辦公椅')
    expect(wrapper.text()).toContain('低於門檻')
  })

  it('載入更多流水帳會依 next 游標請求並附加結果', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/inventory-balances/') return Promise.resolve({ data: { count: 1, next: null, previous: null, results: [balance] } })
      if (url === '/inventory-movements/') return Promise.resolve({ data: movementPage1 })
      if (url === '/inventory-movements/?cursor=abc') return Promise.resolve({ data: movementPage2 })
      return Promise.resolve({ data: { count: 0, next: null, previous: null, results: [] } })
    })
    const wrapper = mount(InventoryView)
    await flushPromises()

    expect(wrapper.text()).toContain('驗收入庫')
    const loadMoreButton = wrapper.findAll('button').find((btn) => btn.text() === '載入更多')
    await loadMoreButton?.trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/inventory-movements/?cursor=abc')
    expect(wrapper.text()).toContain('領用出庫')
  })
})
