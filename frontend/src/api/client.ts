import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

let accessToken: string | null = null
let refreshPromise: Promise<string> | null = null

export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
})

export function setAccessToken(token: string | null) {
  accessToken = token
}

function csrfToken() {
  const item = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrftoken='))
  return item ? decodeURIComponent(item.split('=')[1] ?? '') : ''
}

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

api.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as (InternalAxiosRequestConfig & { retried?: boolean }) | undefined
  const isAuthEndpoint = config?.url?.startsWith('/auth/')
  if (error.response?.status !== 401 || !config || config.retried || isAuthEndpoint) {
    return Promise.reject(error)
  }

  config.retried = true
  refreshPromise ??= api
    .post<{ access: string }>('/auth/refresh/', undefined, { headers: { 'X-CSRFToken': csrfToken() } })
    .then((response) => {
      setAccessToken(response.data.access)
      return response.data.access
    })
    .finally(() => {
      refreshPromise = null
    })

  const token = await refreshPromise
  config.headers.Authorization = `Bearer ${token}`
  return api(config)
})

export function authCsrfToken() {
  return csrfToken()
}
