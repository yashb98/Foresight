/**
 * FORESIGHT API Client
 *
 * Axios instance with:
 *  - JWT Bearer token injection
 *  - 401 auto-redirect to login
 *  - Consistent error normalisation
 */

import axios, { type AxiosError } from 'axios'
import { useAuthStore } from '@/store/auth'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Inject JWT token on every request
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle auth errors globally
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(normaliseError(error))
  }
)

export interface ApiError {
  message: string
  status: number
  detail?: string
}

function normaliseError(error: AxiosError): ApiError {
  const status = error.response?.status ?? 0
  const data = error.response?.data as { detail?: string } | undefined
  return {
    message: data?.detail ?? error.message ?? 'Unknown error',
    status,
    detail: data?.detail,
  }
}
