import axios from 'axios'

interface ApiErrorBody {
  detail?: string
  code?: string
}

export function apiErrorMessage(reason: unknown, fallback: string) {
  if (!axios.isAxiosError<ApiErrorBody>(reason)) return fallback
  return reason.response?.data?.detail || fallback
}
