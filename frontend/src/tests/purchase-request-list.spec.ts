import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get } }))
vi.mock('../views/PurchaseRequestDetailView.vue', () => ({
  default: {
    props: ['id'],
    emits: ['close'],
    template: '<div role="dialog"><button aria-label="關閉採購需求詳情" @click="$emit(\'close\')">×</button></div>',
  },
}))
const { replace, route } = vi.hoisted(() => ({
  replace: vi.fn(),
  route: { query: { page: '2', page_size: '10' }, params: {} as Record<string, string> },
}))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))
import PurchaseRequestListView from '../views/PurchaseRequestListView.vue'

describe('PurchaseRequestList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    route.params = {}
  })

  it('顯示新版採購需求與建立時間', async () => {
    get.mockResolvedValue({ data: {
      count: 21, page: 2, page_size: 10, total_pages: 3,
      results: [{
        id: 9, request_no: 'PR-NEWER', purpose: '辦公設備汰換', requester_name: 'Alice Chen',
        status: 'submitted', item_summary: 'A產品-辦公椅', supplier_summary: '優品科技',
        created_at: '2026-08-31T08:00:00Z',
      }],
    } })
    const wrapper = mount(PurchaseRequestListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/purchase-requests/', { params: { page: 2, page_size: 10 } })
    expect(wrapper.text()).toContain('PR-NEWER')
    expect(wrapper.text()).toContain('建立時間')
    expect(wrapper.text()).toContain('辦公設備汰換')
    expect(wrapper.text()).toContain('共 21 筆')
    expect(wrapper.text()).toContain('2 / 3')
    expect(wrapper.get('a').attributes('href')).toContain('/purchase-requests/9?page=2&page_size=10')
  })

  it('切換每頁筆數時回到第一頁並更新網址', async () => {
    get.mockResolvedValue({ data: { count: 0, page: 2, page_size: 10, total_pages: 1, results: [] } })
    const wrapper = mount(PurchaseRequestListView)
    await flushPromises()

    await wrapper.get('select[aria-label="每頁筆數"]').setValue('50')

    expect(replace).toHaveBeenCalledWith({ query: { page: '1', page_size: '50' } })
  })

  it('關閉詳情彈窗時回到原清單查詢狀態', async () => {
    route.params = { id: '9' }
    get.mockResolvedValue({ data: { count: 0, page: 2, page_size: 10, total_pages: 1, results: [] } })
    const wrapper = mount(PurchaseRequestListView)
    await flushPromises()

    await wrapper.get('button[aria-label="關閉採購需求詳情"]').trigger('click')

    expect(replace).toHaveBeenCalledWith({
      path: '/purchase-requests',
      query: { page: '2', page_size: '10' },
    })
  })
})
