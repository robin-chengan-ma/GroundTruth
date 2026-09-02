import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get } }))

import { useAuthStore } from '../stores/auth'
import AuditDashboardView from '../views/AuditDashboardView.vue'

const stats = {
  candidate_quality: { direct_adoption_count: 8, corrected_count: 2, direct_adoption_rate_pct: '80.00', corrections_by_field: {} },
  supplier_match: { supplier_matched_count: 8, supplier_unmatched_count: 1, product_matched_count: 10, product_unmatched_count: 2, fuzzy_match_total: 5, fuzzy_match_approved: 3, fuzzy_match_rejected: 1, fuzzy_match_pending: 1 },
  manual_review_queue: { pending_count: 2, processed_count: 6, by_decision: { approved: 4, rejected: 2 } },
  price_anomaly: {
    threshold_pct: '20.00', checked_count: 12, anomaly_count: 1, anomaly_rate_pct: '8.33',
    items: [{
      supplier_quote_item_id: 1, rfq_no: 'RFQ-001', supplier_name: '優品科技', product_name: '辦公椅',
      unit_price: '2000.00', historical_average: '1200.00', currency: 'TWD', deviation_pct: '66.67',
    }],
  },
  quality: { inspection_count: 4, accepted_quantity: '8.000', exception_quantity: '2.000', acceptance_rate_pct: '80.00' },
}

describe('AuditDashboardView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const auth = useAuthStore()
    auth.user = { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', permissions: ['audit.read'] }
  })

  it('顯示四張統計卡片與價格異常清單', async () => {
    get.mockResolvedValue({ data: stats })
    const wrapper = mount(AuditDashboardView)
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/audit-dashboard/stats/', { params: { date_from: undefined, date_to: undefined } })
    expect(wrapper.text()).toContain('80.00%')
    expect(wrapper.text()).not.toContain('幻覺驗證')
    expect(wrapper.text()).toContain('RFQ-001')
    expect(wrapper.text()).toContain('66.67')
  })

  it('套用日期篩選會帶入 date_from／date_to 查詢參數', async () => {
    get.mockResolvedValue({ data: stats })
    const wrapper = mount(AuditDashboardView)
    await flushPromises()

    await wrapper.get('#dashboard-date-from').setValue('2026-08-01')
    await wrapper.get('#dashboard-date-to').setValue('2026-08-31')
    await wrapper.get('form').trigger('submit.prevent')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/audit-dashboard/stats/', { params: { date_from: '2026-08-01', date_to: '2026-08-31' } })
  })
})
