import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

const TOKEN_KEY = 'wins.access_token'

export const getAccessToken = () => localStorage.getItem(TOKEN_KEY)
export const setAccessToken = (token: string | null) => {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  withCredentials: true,
  timeout: 20_000,
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<string> | null = null

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    const skipRefresh = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/logout']
      .some((path) => original?.url?.includes(path))
    if (error.response?.status !== 401 || !original || original._retry || skipRefresh) {
      return Promise.reject(error)
    }
    original._retry = true
    refreshing ??= api
      .post<{ access_token: string }>('/auth/refresh')
      .then(({ data }) => {
        setAccessToken(data.access_token)
        return data.access_token
      })
      .finally(() => {
        refreshing = null
      })
    try {
      const token = await refreshing
      original.headers.Authorization = `Bearer ${token}`
      return api(original)
    } catch (refreshError) {
      setAccessToken(null)
      window.dispatchEvent(new Event('auth:expired'))
      return Promise.reject(refreshError)
    }
  },
)

export const errorMessage = (error: unknown, fallback = '操作失败，请稍后重试') => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join('；')
  }
  return fallback
}