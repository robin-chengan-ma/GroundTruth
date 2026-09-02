import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post, patch } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post, patch } }))

import { useAuthStore } from '../stores/auth'
import SupplierListView from '../views/SupplierListView.vue'

const supplier = {
  id: 1, name: '優品科技', tier: 'priority', code: 'SUP-001', status: 'active', tax_id: '12345678',
  contact: { phone: '02-1234', email: 'a@example.com' }, payment_terms: '月結 30 天', is_active: true,
  created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z',
}

describe('SupplierListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', permissions: ['master_data.read', 'master_data.manage'] }
  })

  it('顯示供應商清單', async () => {
    get.mockResolvedValue({ data: { count: 1, next: null, previous: null, results: [supplier] } })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/suppliers/')
    expect(wrapper.text()).toContain('優品科技')
    expect(wrapper.text()).toContain('SUP-001')
  })

  it('新增供應商時送出完整表單內容', async () => {
    get.mockResolvedValue({ data: { count: 0, next: null, previous: null, results: [] } })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增供應商')
    await createButton?.trigger('click')
    await wrapper.get('#supplier-name').setValue('新供應商')
    await wrapper.get('#supplier-payment-terms').setValue('月結 60 天')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/suppliers/', expect.objectContaining({
      name: '新供應商', payment_terms: '月結 60 天', tier: 'normal', status: 'active', is_active: true,
    }))
  })

  it('編輯既有供應商送出 PATCH', async () => {
    get.mockResolvedValue({ data: { count: 1, next: null, previous: null, results: [supplier] } })
    patch.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    const editButton = wrapper.findAll('button').find((btn) => btn.text() === '編輯')
    await editButton?.trigger('click')
    await wrapper.get('#supplier-name').setValue('優品科技（改名）')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(patch).toHaveBeenCalledWith('/suppliers/1/', expect.objectContaining({ name: '優品科技（改名）' }))
  })

  it('停用供應商送出 is_active=false', async () => {
    get.mockResolvedValue({ data: { count: 1, next: null, previous: null, results: [supplier] } })
    patch.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    const disableButton = wrapper.findAll('button').find((btn) => btn.text() === '停用')
    await disableButton?.trigger('click')

    expect(patch).toHaveBeenCalledWith('/suppliers/1/', { is_active: false })
  })
})
