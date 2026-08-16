import * as SecureStore from 'expo-secure-store'

import { PIN_MAX_FAILED_ATTEMPTS, isValidPinFormat } from '@/auth/pinPolicy'
import { constantTimeEqual, deriveHrPinVerifier, randomSaltHex } from './hrPinCrypto'

const VERIFIER_KEY = 'wathefni.hr.pin.verifier'
const SALT_KEY = 'wathefni.hr.pin.salt'
const PRINCIPAL_KEY = 'wathefni.hr.pin.principal_key'
const ATTEMPTS_KEY = 'wathefni.hr.pin.failed_attempts'
/** Match HR session keychain accessibility. */
const STORE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }

export type HrPinRecord = {
  principalKey: string
  saltHex: string
  verifierHex: string
  failedAttempts: number
}

async function readAttempts(): Promise<number> {
  const raw = await SecureStore.getItemAsync(ATTEMPTS_KEY)
  const n = Number(raw || '0')
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
}

export async function loadHrPinRecord(): Promise<HrPinRecord | null> {
  const [principalKey, saltHex, verifierHex, failedAttempts] = await Promise.all([
    SecureStore.getItemAsync(PRINCIPAL_KEY),
    SecureStore.getItemAsync(SALT_KEY),
    SecureStore.getItemAsync(VERIFIER_KEY),
    readAttempts(),
  ])
  if (!principalKey || !saltHex || !verifierHex) return null
  return { principalKey, saltHex, verifierHex, failedAttempts }
}

export async function hasHrPinRecord(): Promise<boolean> {
  return (await loadHrPinRecord()) != null
}

export async function clearHrPinMaterial(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(VERIFIER_KEY),
    SecureStore.deleteItemAsync(SALT_KEY),
    SecureStore.deleteItemAsync(PRINCIPAL_KEY),
    SecureStore.deleteItemAsync(ATTEMPTS_KEY),
  ])
}

export async function setHrPin(principalKey: string, pin: string): Promise<void> {
  if (!isValidPinFormat(pin)) throw new Error('invalid_pin_format')
  const key = String(principalKey || '').trim()
  if (!key) throw new Error('missing_principal_key')
  const saltHex = randomSaltHex(16)
  const verifierHex = deriveHrPinVerifier(pin, saltHex)
  await Promise.all([
    SecureStore.setItemAsync(PRINCIPAL_KEY, key, STORE_OPTS),
    SecureStore.setItemAsync(SALT_KEY, saltHex, STORE_OPTS),
    SecureStore.setItemAsync(VERIFIER_KEY, verifierHex, STORE_OPTS),
    SecureStore.setItemAsync(ATTEMPTS_KEY, '0', STORE_OPTS),
  ])
}

export type VerifyHrPinResult =
  | { ok: true; failedAttempts: 0 }
  | { ok: false; failedAttempts: number; lockedOut: boolean }

export async function verifyHrPin(pin: string): Promise<VerifyHrPinResult> {
  const record = await loadHrPinRecord()
  if (!record) return { ok: false, failedAttempts: 0, lockedOut: false }
  if (!isValidPinFormat(pin)) {
    const failedAttempts = record.failedAttempts + 1
    await SecureStore.setItemAsync(ATTEMPTS_KEY, String(failedAttempts), STORE_OPTS)
    return {
      ok: false,
      failedAttempts,
      lockedOut: failedAttempts >= PIN_MAX_FAILED_ATTEMPTS,
    }
  }
  const candidate = deriveHrPinVerifier(pin, record.saltHex)
  if (constantTimeEqual(candidate, record.verifierHex)) {
    await SecureStore.setItemAsync(ATTEMPTS_KEY, '0', STORE_OPTS)
    return { ok: true, failedAttempts: 0 }
  }
  const failedAttempts = record.failedAttempts + 1
  await SecureStore.setItemAsync(ATTEMPTS_KEY, String(failedAttempts), STORE_OPTS)
  return {
    ok: false,
    failedAttempts,
    lockedOut: failedAttempts >= PIN_MAX_FAILED_ATTEMPTS,
  }
}

export async function changeHrPin(
  currentPin: string,
  nextPin: string,
): Promise<VerifyHrPinResult & { changed?: boolean }> {
  const verified = await verifyHrPin(currentPin)
  if (!verified.ok) return { ...verified, changed: false }
  if (!isValidPinFormat(nextPin)) return { ok: false, failedAttempts: 0, lockedOut: false, changed: false }
  const record = await loadHrPinRecord()
  if (!record) return { ok: false, failedAttempts: 0, lockedOut: false, changed: false }
  await setHrPin(record.principalKey, nextPin)
  return { ok: true, failedAttempts: 0, changed: true }
}
