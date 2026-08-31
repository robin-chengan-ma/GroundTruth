import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post, patch, remove } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), remove: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get, post, patch, delete: remove } }))
import InquiryView from '../views/InquiryView.vue'

const parsedCandidate = {
  purpose: '補貨', needed_by: null, currency: 'TWD', assistant_message: '請確認',
  supplier_candidates: [{ supplier_id: 1, supplier_name: '優品科技' }],
  items: [{ product_id: 10, product_name: '辦公椅', quantity: '5', unit_of_measure: 'EA', specifications: {} }],
  missing_fields: [], ready_for_draft: true,
  supplier_product_coverage: [{ supplier_id: 1, supplier_name: '優品科技', product_id: 10, product_name: '辦公椅', status: 'priced', label: '可供應，且有有效價格', unit_price: '1500.00', currency: 'TWD' }],
}

describe('InquiryView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
    get.mockImplementation((url: string) => Promise.resolve({ data: url.includes('suppliers') ? [{ id: 1, name: '優品科技' }] : [{ id: 10, name: '辦公椅', price: '1500.00', currency: 'TWD' }] }))
  })

  it('解析後顯示可編輯候選內容，不顯示 JSON', async () => {
    post.mockResolvedValueOnce({ data: structuredClone(parsedCandidate) })
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('跟優品科技買 5 張辦公椅')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/inquiries/parse/', { raw_text: '跟優品科技買 5 張辦公椅' })
    expect(wrapper.text()).toContain('確認與修正需求')
    expect(wrapper.text()).toContain('優品科技')
    expect(wrapper.find('pre').exists()).toBe(false)
  })

  it('解析後顯示供應商與品項的供應能力對照', async () => {
    post.mockResolvedValueOnce({ data: structuredClone(parsedCandidate) })
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('跟優品科技買 5 張辦公椅')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('每個品項由哪些供應商供應')
    expect(wrapper.text()).toContain('可供應，且有有效價格')
    expect(wrapper.text()).toContain('參考單價 TWD 1,500')
  })

  it('先建立草稿試算，確認後才提交', async () => {
    post.mockResolvedValueOnce({ data: structuredClone(parsedCandidate) })
      .mockResolvedValueOnce({ data: { id: 7, version: 1, status: 'draft' } })
      .mockResolvedValueOnce({ data: { request_id: 7, version: 1, status: 'estimate_only', message: '僅供參考', suppliers: [{ supplier_id: 1, supplier_name: '優品科技', estimated_total: '7500.00', currency: 'TWD', items: [{ product_id: 10, product_name: '辦公椅', quantity: '5', unit_of_measure: 'EA', available: true, unit_price: '1500.00', total_amount: '7500.00', currency: 'TWD', price_comparison: { status: 'normal', label: '接近歷史均價', deviation_pct: '2.39' } }] }] } })
      .mockResolvedValueOnce({ data: { request_no: 'PR-2026-0007' } })
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('補貨')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('儲存草稿'))!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('TWD 7,500')
    expect(wrapper.text()).toContain('接近歷史均價 · 2.39%')
    await wrapper.findAll('button').find((button) => button.text().includes('提交採購申請'))!.trigger('click')
    await flushPromises()
    expect(post.mock.calls.at(-1)?.[0]).toBe('/purchase-request-drafts/7/submit/')
    expect(wrapper.text()).toContain('PR-2026-0007 已成功送出')
    expect((wrapper.get('#inquiry').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.text()).not.toContain('確認與修正需求')
    expect(patch).not.toHaveBeenCalled()
  })

  it('缺少有效價格時顯示尚無報價而不是零元', async () => {
    post.mockResolvedValueOnce({ data: structuredClone(parsedCandidate) })
      .mockResolvedValueOnce({ data: { id: 8, version: 1, status: 'draft' } })
      .mockResolvedValueOnce({ data: { request_id: 8, version: 1, status: 'estimate_only', message: '僅供參考', suppliers: [{ supplier_id: 1, supplier_name: '優品科技', estimated_total: '0.00', currency: 'TWD', items: [{ product_id: 10, product_name: '辦公椅', quantity: '5', unit_of_measure: 'EA', available: false, message: '目前沒有有效價格' }] }] } })
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('補貨')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('儲存草稿'))!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('尚無報價')
    expect(wrapper.text()).not.toContain('TWD 0')
  })

  it('品項未匹配時顯示 AI 辨識內容與試算停用原因', async () => {
    post.mockResolvedValueOnce({
      data: {
        ...parsedCandidate,
        items: [{ product_id: null, product_name: '升降桌', quantity: '3', unit_of_measure: 'EA', specifications: { material: '木製' } }],
        missing_fields: ['items.0.product_id'],
        ready_for_draft: false,
      },
    })
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('採購木製升降桌 3 張')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('AI 辨識內容')
    expect(wrapper.text()).toContain('升降桌／數量 3 EA／材質：木製')
    expect(wrapper.text()).toContain('尚未找到正式品項')
    expect(wrapper.text()).toContain('請從下方手動選擇其他品項，或移除此品項')
    expect(wrapper.text()).toContain('尚有品項未選擇正式品項，請先手動選擇或移除')
    expect(wrapper.findAll('button').find((button) => button.text().includes('儲存草稿'))!.attributes('disabled')).toBeDefined()
  })

  it('解析後將缺少或無效的必填欄位標示為錯誤', async () => {
    post.mockResolvedValueOnce({
      data: {
        ...parsedCandidate,
        supplier_candidates: [],
        items: [{ product_id: null, product_name: '升降桌', quantity: null, unit_of_measure: 'EA', specifications: {} }],
        missing_fields: ['supplier_candidates', 'items.0.product_id', 'items.0.quantity'],
        ready_for_draft: false,
      },
    })
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('採購升降桌')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('fieldset').classes()).toContain('invalid-group')
    expect(wrapper.get('#product-0').classes()).toContain('invalid-field')
    expect(wrapper.get('#quantity-0').classes()).toContain('invalid-field')
    expect(wrapper.text()).toContain('請至少選擇一間候選供應商')
    expect(wrapper.text()).toContain('請選擇正式品項')
    expect(wrapper.text()).toContain('請填寫大於 0 的數量')
  })

  it('刪除品項前要求確認，取消時保留品項', async () => {
    post.mockResolvedValueOnce({ data: structuredClone(parsedCandidate) })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('跟優品科技買 5 張辦公椅')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '移除')!.trigger('click')

    expect(confirm).toHaveBeenCalledWith('確定要移除「辦公椅／數量 5 EA」嗎？')
    expect(wrapper.text()).toContain('品項 1')
  })

  it('刪除最後一項時刪除已存草稿並回到自然語言輸入畫面', async () => {
    post.mockResolvedValueOnce({ data: structuredClone(parsedCandidate) })
      .mockResolvedValueOnce({ data: { id: 9, version: 1, status: 'draft' } })
      .mockResolvedValueOnce({ data: { request_id: 9, version: 1, status: 'estimate_only', message: '僅供參考', suppliers: [] } })
    remove.mockResolvedValueOnce({ status: 204 })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(InquiryView)
    await flushPromises()
    await wrapper.get('#inquiry').setValue('跟優品科技買 5 張辦公椅')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('儲存草稿'))!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '移除')!.trigger('click')
    await flushPromises()

    expect(remove).toHaveBeenCalledWith('/purchase-request-drafts/9/')
    expect(wrapper.text()).not.toContain('確認與修正需求')
    expect(wrapper.text()).not.toContain('試算結果')
    expect((wrapper.get('#inquiry').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.text()).toContain('已移除最後一個品項，請重新輸入採購需求')
  })
})
