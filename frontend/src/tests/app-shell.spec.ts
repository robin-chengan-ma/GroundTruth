import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { vi } from 'vitest'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import AppShell from '../components/AppShell.vue'
import { useAuthStore } from '../stores/auth'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :data-to="to"><slot /></a>',
}

describe('AppShell', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('只顯示使用者有權限的垂直導覽項目', () => {
    const auth = useAuthStore()
    auth.user = {
      id: 1,
      name: 'Alice',
      email: 'alice@example.com',
      role: 'employee',
      permissions: ['purchase_request.create', 'purchase_request.read_own'],
    }
    const wrapper = mount(AppShell, {
      global: {
        stubs: { RouterLink: RouterLinkStub },
        mocks: { $route: { path: '/inquiry' } },
      },
    })

    expect(wrapper.text()).toContain('工作台')
    expect(wrapper.text()).toContain('新增採購需求')
    expect(wrapper.text()).toContain('我的採購需求')
    expect(wrapper.text()).not.toContain('簽核工作區')
    expect(wrapper.text()).not.toContain('AI 人工複核')
  })

  it('依實際 permission 顯示簽核與人工複核', () => {
    const auth = useAuthStore()
    auth.user = {
      id: 3,
      name: 'Eva',
      email: 'eva@example.com',
      role: 'admin',
      permissions: ['approval.read_all', 'manual_review.decide'],
    }
    const wrapper = mount(AppShell, {
      global: {
        stubs: { RouterLink: RouterLinkStub },
        mocks: { $route: { path: '/reviews' } },
      },
    })

    expect(wrapper.text()).toContain('待辦工作')
    expect(wrapper.text()).toContain('簽核工作區')
    expect(wrapper.text()).toContain('AI 人工複核')
  })

  it('窄螢幕導覽可開啟並以 Escape 關閉', async () => {
    const auth = useAuthStore()
    auth.user = {
      id: 1,
      name: 'Alice',
      email: 'alice@example.com',
      role: 'employee',
      permissions: ['purchase_request.create'],
    }
    const wrapper = mount(AppShell, {
      attachTo: document.body,
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    await wrapper.get('[aria-label="開啟導覽"]').trigger('click')
    expect(wrapper.classes()).toContain('navigation-open')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.classes()).not.toContain('navigation-open')
    wrapper.unmount()
  })
})
