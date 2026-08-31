import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get } }))
import QuoteListView from '../views/QuoteListView.vue'

describe('PurchaseRequestList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('顯示新版採購需求與建立時間', async () => {
    get.mockResolvedValue({ data: [{
      id: 9, request_no: 'PR-NEWER', purpose: '辦公設備汰換', requester_name: 'Alice Chen',
      status: 'submitted', item_summary: 'A產品-辦公椅', supplier_summary: '優品科技',
      created_at: '2026-08-31T08:00:00Z',
    }] })
    const wrapper = mount(QuoteListView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/purchase-requests/')
    expect(wrapper.text()).toContain('PR-NEWER')
    expect(wrapper.text()).toContain('建立時間')
    expect(wrapper.text()).toContain('辦公設備汰換')
  })
})
