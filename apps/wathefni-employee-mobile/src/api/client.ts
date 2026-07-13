// Low-level HTTP for the /app/* surface. No business logic, no token state —
// that lives in AuthProvider. Base URL comes from a public (non-secret) env var.

export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || 'https://api.wathefni.ai').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST'
  token?: string | null
  json?: unknown
  body?: FormData
  signal?: AbortSignal
}

function detailMessage(payload: unknown, fallback: string): { code: string; message: string } {
  const detail = (payload as { detail?: unknown })?.detail ?? payload
  if (detail && typeof detail === 'object') {
    const d = detail as { error?: string; message?: string }
    return { code: d.error || 'error', message: d.message || fallback }
  }
  return { code: 'error', message: fallback }
}

export async function rawRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', token, json, body, signal } = options
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  let payload: BodyInit | undefined
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(json)
  } else if (body) {
    // FormData: let the runtime set the multipart boundary.
    payload = body
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body: payload, signal })
  } catch {
    throw new ApiError(0, 'network_error', 'No connection. Please check your internet and try again.')
  }

  const text = await response.text()
  let parsed: unknown = null
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    parsed = null
  }

  if (!response.ok) {
    const { code, message } = detailMessage(parsed, 'Something went wrong. Please try again.')
    throw new ApiError(response.status, code, message)
  }
  return parsed as T
}
