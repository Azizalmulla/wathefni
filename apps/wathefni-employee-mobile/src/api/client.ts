// Low-level HTTP for the /app/* surface. No business logic, no token state —
// that lives in AuthProvider. Base URL comes from a public (non-secret) env var.

export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || 'https://api.wathefni.ai').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  code: string
  messageEn?: string
  messageAr?: string
  problems?: string[]
  fields?: string[]
  constructor(
    status: number,
    code: string,
    message: string,
    extras?: {
      messageEn?: string
      messageAr?: string
      problems?: string[]
      fields?: string[]
    },
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.messageEn = extras?.messageEn
    this.messageAr = extras?.messageAr
    this.problems = extras?.problems
    this.fields = extras?.fields
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST'
  token?: string | null
  json?: unknown
  body?: FormData
  signal?: AbortSignal
}

function detailMessage(payload: unknown, fallback: string): {
  code: string
  message: string
  messageEn?: string
  messageAr?: string
  problems?: string[]
  fields?: string[]
} {
  const detail = (payload as { detail?: unknown })?.detail ?? payload
  if (detail && typeof detail === 'object') {
    const d = detail as {
      error?: string
      message?: string
      message_en?: string
      message_ar?: string
      problems?: unknown
      fields?: unknown
    }
    const problems = Array.isArray(d.problems) ? d.problems.map((item) => String(item)) : undefined
    const fields = Array.isArray(d.fields) ? d.fields.map((item) => String(item)) : undefined
    return {
      code: d.error || 'error',
      message: d.message || d.message_en || d.message_ar || fallback,
      messageEn: d.message_en,
      messageAr: d.message_ar,
      problems,
      fields,
    }
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
  } catch (error) {
    if (signal?.aborted) throw error
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
    const { code, message, messageEn, messageAr, problems, fields } = detailMessage(
      parsed,
      'Something went wrong. Please try again.',
    )
    throw new ApiError(response.status, code, message, { messageEn, messageAr, problems, fields })
  }
  return parsed as T
}
