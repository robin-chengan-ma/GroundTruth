import { defineStore } from 'pinia'

import { api, authCsrfToken, setAccessToken } from '../api/client'
import type { UserProfile } from '../types/api'

interface LoginResponse {
  access: string
  user: UserProfile
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as UserProfile | null,
    initialized: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user),
    isAdmin: (state) => state.user?.role === 'admin',
    hasPermission: (state) => (permission: string) =>
      Boolean(state.user?.permissions.includes(permission)),
    hasAllPermissions: (state) => (permissions: string[]) =>
      permissions.every((permission) => state.user?.permissions.includes(permission)),
    hasAnyPermission: (state) => (permissions: string[]) =>
      permissions.some((permission) => state.user?.permissions.includes(permission)),
    canApprove: (state) => Boolean(state.user?.permissions.includes('approval.read_all')),
  },
  actions: {
    async login(email: string, password: string) {
      const response = await api.post<LoginResponse>('/auth/login/', { email, password })
      setAccessToken(response.data.access)
      this.user = response.data.user
      this.initialized = true
    },
    async bootstrap() {
      if (this.initialized) return
      try {
        const refresh = await api.post<{ access: string }>('/auth/refresh/', undefined, {
          headers: { 'X-CSRFToken': authCsrfToken() },
        })
        setAccessToken(refresh.data.access)
        this.user = (await api.get<UserProfile>('/auth/me/')).data
      } catch {
        setAccessToken(null)
        this.user = null
      } finally {
        this.initialized = true
      }
    },
    async logout() {
      try {
        await api.post('/auth/logout/', undefined, { headers: { 'X-CSRFToken': authCsrfToken() } })
      } finally {
        setAccessToken(null)
        this.user = null
        this.initialized = true
      }
    },
  },
})
