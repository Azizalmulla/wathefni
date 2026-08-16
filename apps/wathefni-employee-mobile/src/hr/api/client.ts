const configuredBase = (process.env.EXPO_PUBLIC_API_BASE_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export type RequestOptions = {
  method?: 'GET' | 'POST'
  token?: string | null
  json?: unknown
  signal?: AbortSignal
  responseType?: 'json' | 'arrayBuffer'
}

function safeError(payload: unknown, fallback: string): { code: string; message: string } {
  const detail = (payload as { detail?: unknown })?.detail ?? payload
  if (detail && typeof detail === 'object') {
    const value = detail as { error?: string; message?: string }
    return { code: value.error || 'request_failed', message: value.message || fallback }
  }
  return { code: 'request_failed', message: fallback }
}

export async function rawRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!path.startsWith('/dashboard/mobile/')) {
    throw new ApiError(0, 'unapproved_api_path', 'This API path is not approved for Wathefni HR.')
  }
  if (!configuredBase) {
    throw new ApiError(0, 'api_not_configured', 'Wathefni HR is not connected to an API environment.')
  }
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.token) headers.Authorization = `Bearer ${options.token}`
  let body: string | undefined
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  }
  let response: Response
  try {
    response = await fetch(`${configuredBase}${path}`, {
      method: options.method || 'GET',
      headers,
      body,
      signal: options.signal,
      cache: 'no-store',
    })
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError(0, 'network_error', 'No connection. Check your network and try again.')
  }
  if (response.ok && options.responseType === 'arrayBuffer') {
    return (await response.arrayBuffer()) as T
  }
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  if (!response.ok) {
    const safe = safeError(payload, 'This request could not be completed.')
    throw new ApiError(response.status, safe.code, safe.message)
  }
  return payload as T
}
