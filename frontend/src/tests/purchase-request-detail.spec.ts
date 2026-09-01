import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get } }))
import PurchaseRequestDetailView from '../views/PurchaseRequestDetailView.vue'

describe('PurchaseRequestDetailView', () => {
  it('以唯讀彈窗顯示本人採購需求快照並支援三種關閉方式', async () => {
    get.mockResolvedValue({ data: {
      id: 9,
      request_no: 'PR-DETAIL',
      purpose: '辦公設備汰換',
      needed_by: '2026-09-30',
      currency: 'TWD',
      requester_name: 'Alice Chen',
      status: 'submitted',
      source: 'ai',
      candidate_suppliers: [{ supplier_id: 1, supplier_name: '優品科技' }],
      items: [{
        id: 1, line_no: 1, product_id: 1, product_name: 'A產品-辦公椅',
        description_snapshot: 'A產品-辦公椅', quantity: '5.000', unit_of_measure: 'EA',
        specifications: { material: '網布', feature: '有頭枕' },
      }],
      created_at: '2026-08-31T08:00:00Z',
      updated_at: '2026-08-31T08:00:00Z',
    } })

    const wrapper = mount(PurchaseRequestDetailView, {
      props: { id: '9', page: '2', pageSize: '10' },
    })
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/purchase-requests/9/')
    expect(wrapper.text()).toContain('PR-DETAIL')
    expect(wrapper.text()).toContain('辦公設備汰換')
    expect(wrapper.text()).toContain('優品科技')
    expect(wrapper.text()).toContain('A產品-辦公椅')
    expect(wrapper.text()).toContain('網布')
    expect(wrapper.text()).not.toContain('修改')
    expect(wrapper.text()).not.toContain('刪除')
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')

    await wrapper.get('button[aria-label="關閉採購需求詳情"]').trigger('click')
    await wrapper.get('.modal-backdrop').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(wrapper.emitted('close')).toHaveLength(3)
  })
})
