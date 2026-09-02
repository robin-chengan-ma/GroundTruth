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
    route.query = {}
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', permissions: ['master_data.read', 'master_data.manage'] }
  })

  it('顯示供應商清單並帶入分頁查詢參數', async () => {
    get.mockResolvedValue({ data: { count: 1, page: 1, page_size: 20, total_pages: 1, results: [supplier] } })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/suppliers/', { params: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('優品科技')
    expect(wrapper.text()).toContain('SUP-001')
    expect(wrapper.text()).toContain('共 1 筆')
  })

  it('搜尋供應商時帶入 search 查詢參數並回到第一頁', async () => {
    get.mockResolvedValue({ data: { count: 0, page: 1, page_size: 20, total_pages: 1, results: [] } })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    await wrapper.get('input[aria-label="搜尋供應商"]').setValue('優品')
    await wrapper.get('form.filter-bar').trigger('submit.prevent')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', search: '優品' } })
  })

  it('依狀態篩選時帶入 status 查詢參數並回到第一頁', async () => {
    get.mockResolvedValue({ data: { count: 0, page: 1, page_size: 20, total_pages: 1, results: [] } })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    await wrapper.get('select[aria-label="狀態篩選"]').setValue('on_hold')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20', status: 'on_hold' } })
  })

  it('清除篩選條件時移除 search／status／tier 查詢參數', async () => {
    route.query = { page: '2', page_size: '20', search: '優品', status: 'on_hold', tier: 'priority' }
    get.mockResolvedValue({ data: { count: 0, page: 2, page_size: 20, total_pages: 1, results: [] } })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    const resetButton = wrapper.findAll('button').find((btn) => btn.text() === '清除條件')
    await resetButton?.trigger('click')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '20' } })
  })

  it('沒有符合條件的資料時顯示對應空狀態文字', async () => {
    get.mockResolvedValue({ data: { count: 0, page: 1, page_size: 20, total_pages: 1, results: [] } })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有符合條件的供應商主檔資料。')
  })

  it('新增供應商時送出完整表單內容', async () => {
    get.mockResolvedValue({ data: { count: 0, page: 1, page_size: 20, total_pages: 1, results: [] } })
    post.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    const createButton = wrapper.findAll('button').find((btn) => btn.text() === '新增供應商')
    await createButton?.trigger('click')
    await wrapper.get('#supplier-name').setValue('新供應商')
    await wrapper.get('#supplier-payment-terms').setValue('月結 60 天')
    await wrapper.get('.detail-modal form').trigger('submit.prevent')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/suppliers/', expect.objectContaining({
      name: '新供應商', payment_terms: '月結 60 天', tier: 'normal', status: 'active', is_active: true,
    }))
  })

  it('編輯既有供應商送出 PATCH', async () => {
    get.mockResolvedValue({ data: { count: 1, page: 1, page_size: 20, total_pages: 1, results: [supplier] } })
    patch.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    const editButton = wrapper.findAll('button').find((btn) => btn.text() === '編輯')
    await editButton?.trigger('click')
    await wrapper.get('#supplier-name').setValue('優品科技（改名）')
    await wrapper.get('.detail-modal form').trigger('submit.prevent')
    await flushPromises()

    expect(patch).toHaveBeenCalledWith('/suppliers/1/', expect.objectContaining({ name: '優品科技（改名）' }))
  })

  it('停用供應商送出 is_active=false', async () => {
    get.mockResolvedValue({ data: { count: 1, page: 1, page_size: 20, total_pages: 1, results: [supplier] } })
    patch.mockResolvedValue({ data: {} })
    const wrapper = mount(SupplierListView)
    await flushPromises()

    const disableButton = wrapper.findAll('button').find((btn) => btn.text() === '停用')
    await disableButton?.trigger('click')

    expect(patch).toHaveBeenCalledWith('/suppliers/1/', { is_active: false })
  })
})
