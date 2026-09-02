import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get } }))

import { useAuthStore } from '../stores/auth'
import AuditLogListView from '../views/AuditLogListView.vue'

const logPage1 = {
  count: 2, next: '/audit-logs/?cursor=abc', previous: null,
  results: [{
    id: 1, action_type: 'hallucination_check', verification_result: 'pass', quote: 7,
    real_query_summary: 'Google 搜尋核對供應商報價', created_at: '2026-08-20T00:00:00Z',
  }],
}
const logPage2 = {
  count: 2, next: null, previous: null,
  results: [{
    id: 2, action_type: 'supplier_match', verification_result: null, quote: null,
    real_query_summary: '', created_at: '2026-08-21T00:00:00Z',
  }],
}

describe('AuditLogListView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', permissions: ['audit.read'] }
  })

  it('顯示稽核紀錄清單', async () => {
    get.mockResolvedValue({ data: logPage1 })
    const wrapper = mount(AuditLogListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/audit-logs/')
    expect(wrapper.text()).toContain('hallucination_check')
    expect(wrapper.text()).toContain('pass')
  })

  it('載入更多會依 next 游標請求並附加結果', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/audit-logs/') return Promise.resolve({ data: logPage1 })
      if (url === '/audit-logs/?cursor=abc') return Promise.resolve({ data: logPage2 })
      return Promise.resolve({ data: { count: 0, next: null, previous: null, results: [] } })
    })
    const wrapper = mount(AuditLogListView)
    await flushPromises()

    const loadMoreButton = wrapper.findAll('button').find((btn) => btn.text() === '載入更多')
    await loadMoreButton?.trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/audit-logs/?cursor=abc')
    expect(wrapper.text()).toContain('supplier_match')
  })
})
