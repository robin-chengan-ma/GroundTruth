import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { post, get, setAccessToken } = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  setAccessToken: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: { post, get },
  authCsrfToken: () => 'csrf-token',
  setAccessToken,
}))

import { useAuthStore } from '../stores/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('登入後只把 access token 放進記憶體並保存使用者', async () => {
    post.mockResolvedValue({
      data: {
        access: 'access-token',
        user: { id: 1, name: 'Alice', email: 'alice@example.com', role: 'employee' },
      },
    })
    const store = useAuthStore()

    await store.login('alice@example.com', 'password')

    expect(setAccessToken).toHaveBeenCalledWith('access-token')
    expect(store.user?.name).toBe('Alice')
    expect(store.isAuthenticated).toBe(true)
  })

  it('bootstrap 以 HttpOnly refresh cookie 恢復登入', async () => {
    post.mockResolvedValue({ data: { access: 'rotated-access' } })
    get.mockResolvedValue({ data: { id: 3, name: 'Eva', email: 'eva@example.com', role: 'admin' } })
    const store = useAuthStore()

    await store.bootstrap()

    expect(post).toHaveBeenCalledWith('/auth/refresh/', undefined, { headers: { 'X-CSRFToken': 'csrf-token' } })
    expect(store.isAdmin).toBe(true)
    expect(store.initialized).toBe(true)
  })

  it('refresh 失敗時維持登出狀態', async () => {
    post.mockRejectedValue(new Error('expired'))
    const store = useAuthStore()

    await store.bootstrap()

    expect(store.user).toBeNull()
    expect(setAccessToken).toHaveBeenCalledWith(null)
  })
})
