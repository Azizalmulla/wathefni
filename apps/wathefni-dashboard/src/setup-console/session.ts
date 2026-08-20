/** Persistent Setup Console operator session (access + refresh). */

import type { SetupCredentials } from './types'

const ACCESS_KEY = 'wathefni_setup_access_token'
const REFRESH_KEY = 'wathefni_setup_refresh_token'
const PHONE_KEY = 'wathefni_setup_operator_phone'
const EXPIRES_KEY = 'wathefni_setup_access_expires_at'
const LEGACY_TOKEN_KEY = 'wathefni_setup_operator_token'

export type SetupSession = SetupCredentials & {
  refreshToken: string
  expiresAt?: string | null
}

export type SetupAuthLoginResponse = {
  ok?: boolean
  access_token: string
  refresh_token: string
  phone: string
  email?: string
  expires_at?: string
  refresh_expires_at?: string
  access_ttl_seconds?: number
  refresh_ttl_seconds?: number
  token_type?: string
}

function clearLegacySessionStorage() {
  try {
    sessionStorage.removeItem(LEGACY_TOKEN_KEY)
    sessionStorage.removeItem(PHONE_KEY)
  } catch {
    /* ignore */
  }
}

export function readStoredSession(): SetupSession | null {
  clearLegacySessionStorage()
  const token = localStorage.getItem(ACCESS_KEY)?.trim() || ''
  const refreshToken = localStorage.getItem(REFRESH_KEY)?.trim() || ''
  const phone = localStorage.getItem(PHONE_KEY)?.trim() || ''
  const expiresAt = localStorage.getItem(EXPIRES_KEY)?.trim() || null
  if (!token || !refreshToken || !phone) return null
  return { token, refreshToken, phone, expiresAt }
}

export function persistSession(session: SetupAuthLoginResponse) {
  const access = String(session.access_token || '').trim()
  const refresh = String(session.refresh_token || '').trim()
  const phone = String(session.phone || '').trim()
  if (!access || !refresh || !phone) {
    throw new Error('Setup Console session response was incomplete.')
  }
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
  localStorage.setItem(PHONE_KEY, phone)
  if (session.expires_at) localStorage.setItem(EXPIRES_KEY, String(session.expires_at))
  else localStorage.removeItem(EXPIRES_KEY)
  clearLegacySessionStorage()
}

export function clearStoredSession() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(PHONE_KEY)
  localStorage.removeItem(EXPIRES_KEY)
  clearLegacySessionStorage()
}

export function credentialsFromSession(session: SetupSession): SetupCredentials {
  return { token: session.token, phone: session.phone }
}

let refreshInFlight: Promise<SetupSession | null> | null = null

export async function loginWithOperatorPassword(input: {
  email: string
  password: string
}): Promise<SetupSession> {
  const response = await fetch('/dashboard/superadmin/setup/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      email: input.email.trim(),
      password: input.password,
    }),
  })
  const payload = (await response.json().catch(() => ({}))) as SetupAuthLoginResponse & {
    detail?: unknown
  }
  if (!response.ok) {
    const detail = payload.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object' && detail !== null && 'message' in detail
          ? String((detail as { message: unknown }).message)
          : 'Platform admin access was rejected.'
    throw new Error(message)
  }
  persistSession(payload)
  return {
    token: payload.access_token.trim(),
    refreshToken: payload.refresh_token.trim(),
    phone: payload.phone.trim(),
    expiresAt: payload.expires_at || null,
  }
}

export async function refreshSetupSession(refreshToken?: string): Promise<SetupSession | null> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const current = readStoredSession()
    const presented = (refreshToken || current?.refreshToken || '').trim()
    if (!presented) return null
    const response = await fetch('/dashboard/superadmin/setup/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ refresh_token: presented }),
    })
    const payload = (await response.json().catch(() => ({}))) as SetupAuthLoginResponse
    if (!response.ok || !payload.access_token || !payload.refresh_token) {
      clearStoredSession()
      return null
    }
    persistSession(payload)
    return {
      token: payload.access_token.trim(),
      refreshToken: payload.refresh_token.trim(),
      phone: String(payload.phone || current?.phone || '').trim(),
      expiresAt: payload.expires_at || null,
    }
  })().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

export async function logoutSetupSession(session?: SetupSession | null) {
  const current = session || readStoredSession()
  try {
    if (current?.token || current?.refreshToken) {
      await fetch('/dashboard/superadmin/setup/auth/logout', {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          ...(current.token ? { Authorization: `Bearer ${current.token}` } : {}),
          ...(current.phone ? { 'X-HR-Phone': current.phone } : {}),
        },
        body: JSON.stringify({ refresh_token: current.refreshToken || null }),
      })
    }
  } catch {
    /* best-effort revoke */
  } finally {
    clearStoredSession()
  }
}

export async function probeSetupSession(session: SetupSession): Promise<boolean> {
  const response = await fetch('/dashboard/superadmin/setup/auth/session', {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${session.token}`,
      'X-HR-Phone': session.phone,
    },
  })
  return response.ok
}
