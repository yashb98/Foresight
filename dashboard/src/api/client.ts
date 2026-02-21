/**
 * FORESIGHT API Client
 *
 * Axios instance with consistent error normalisation.
 */

import axios, { type AxiosError } from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Handle errors globally
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
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
