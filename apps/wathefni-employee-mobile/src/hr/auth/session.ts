import * as SecureStore from 'expo-secure-store'

/**
 * HR operator session — completely separate from Employee App keys
 * (`wathefni.session.token` / `wathefni.session.refresh`).
 *
 * Persistence is a single SecureStore blob so access+refresh never tear
 * across concurrent readers during rotation.
 */

const SESSION_BLOB_KEY = 'wathefni.hr.session.v1'

/** Legacy per-field keys — migrated on load, cleared on save/clear. */
const ACCESS_KEY = 'wathefni.hr.access_token'
const REFRESH_KEY = 'wathefni.hr.refresh_token'
const COMPANY_KEY = 'wathefni.hr.company_code'
const EXPIRY_KEY = 'wathefni.hr.access_expires_at'

export type StoredOperatorSession = {
  accessToken: string
  refreshToken: string
  companyCode: string
  expiresAt: string
}

const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }

function isSessionShape(value: unknown): value is StoredOperatorSession {
  if (!value || typeof value !== 'object') return false
  const row = value as Record<string, unknown>
  return (
    typeof row.accessToken === 'string' &&
    typeof row.refreshToken === 'string' &&
    typeof row.companyCode === 'string' &&
    typeof row.expiresAt === 'string' &&
    Boolean(row.accessToken) &&
    Boolean(row.refreshToken) &&
    Boolean(row.companyCode) &&
    Boolean(row.expiresAt)
  )
}

async function clearLegacyKeys(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
    SecureStore.deleteItemAsync(COMPANY_KEY),
    SecureStore.deleteItemAsync(EXPIRY_KEY),
  ])
}

async function loadLegacySession(): Promise<StoredOperatorSession | null> {
  const [accessToken, refreshToken, companyCode, expiresAt] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_KEY),
    SecureStore.getItemAsync(REFRESH_KEY),
    SecureStore.getItemAsync(COMPANY_KEY),
    SecureStore.getItemAsync(EXPIRY_KEY),
  ])
  if (!accessToken || !refreshToken || !companyCode || !expiresAt) return null
  return { accessToken, refreshToken, companyCode, expiresAt }
}

/** Atomically persist access + refresh (+ company/expiry) as one keystore value. */
export async function saveOperatorSession(session: StoredOperatorSession): Promise<void> {
  await SecureStore.setItemAsync(SESSION_BLOB_KEY, JSON.stringify(session), options)
  // Drop legacy shards so readers cannot observe a torn mid-rotation pair.
  await clearLegacyKeys()
}

export async function loadOperatorSession(): Promise<StoredOperatorSession | null> {
  const raw = await SecureStore.getItemAsync(SESSION_BLOB_KEY)
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw)
      if (isSessionShape(parsed)) return parsed
    } catch {
      // Fall through to legacy migration.
    }
  }
  const legacy = await loadLegacySession()
  if (!legacy) return null
  await saveOperatorSession(legacy)
  return legacy
}

export async function clearOperatorSession(): Promise<void> {
  await Promise.all([SecureStore.deleteItemAsync(SESSION_BLOB_KEY), clearLegacyKeys()])
}

/** True when `candidate` is a different persisted session than `baseline` (newer rotation). */
export function isNewerOperatorSession(
  baseline: StoredOperatorSession | null,
  candidate: StoredOperatorSession | null,
): boolean {
  if (!candidate) return false
  if (!baseline) return true
  return (
    candidate.refreshToken !== baseline.refreshToken ||
    candidate.accessToken !== baseline.accessToken
  )
}
