import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StatusBadge from '../components/StatusBadge.vue'

describe('StatusBadge', () => {
  it('把後端狀態轉為繁體中文標籤', () => {
    const wrapper = mount(StatusBadge, { props: { status: 'pending_approval' } })
    expect(wrapper.text()).toBe('待簽核')
    expect(wrapper.attributes('data-status')).toBe('pending_approval')
  })
})
