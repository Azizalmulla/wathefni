import * as SecureStore from 'expo-secure-store'

import { derivePinVerifier, constantTimeEqual, randomSaltHex } from './pinCrypto'
import { PIN_MAX_FAILED_ATTEMPTS, isValidPinFormat } from './pinPolicy'

const VERIFIER_KEY = 'wathefni.pin.verifier'
const SALT_KEY = 'wathefni.pin.salt'
const EMPLOYEE_KEY = 'wathefni.pin.employee_key'
const ATTEMPTS_KEY = 'wathefni.pin.failed_attempts'
const STORE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED }

export type PinRecord = {
  employeeKey: string
  saltHex: string
  verifierHex: string
  failedAttempts: number
}

async function readAttempts(): Promise<number> {
  const raw = await SecureStore.getItemAsync(ATTEMPTS_KEY)
  const n = Number(raw || '0')
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
}

export async function loadPinRecord(): Promise<PinRecord | null> {
  const [employeeKey, saltHex, verifierHex, failedAttempts] = await Promise.all([
    SecureStore.getItemAsync(EMPLOYEE_KEY),
    SecureStore.getItemAsync(SALT_KEY),
    SecureStore.getItemAsync(VERIFIER_KEY),
    readAttempts(),
  ])
  if (!employeeKey || !saltHex || !verifierHex) return null
  return { employeeKey, saltHex, verifierHex, failedAttempts }
}

export async function hasPinRecord(): Promise<boolean> {
  return (await loadPinRecord()) != null
}

export async function clearPinMaterial(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(VERIFIER_KEY),
    SecureStore.deleteItemAsync(SALT_KEY),
    SecureStore.deleteItemAsync(EMPLOYEE_KEY),
    SecureStore.deleteItemAsync(ATTEMPTS_KEY),
  ])
}

export async function setPin(employeeKey: string, pin: string): Promise<void> {
  if (!isValidPinFormat(pin)) throw new Error('invalid_pin_format')
  const key = String(employeeKey || '').trim()
  if (!key) throw new Error('missing_employee_key')
  const saltHex = randomSaltHex(16)
  const verifierHex = derivePinVerifier(pin, saltHex)
  await Promise.all([
    SecureStore.setItemAsync(EMPLOYEE_KEY, key, STORE_OPTS),
    SecureStore.setItemAsync(SALT_KEY, saltHex, STORE_OPTS),
    SecureStore.setItemAsync(VERIFIER_KEY, verifierHex, STORE_OPTS),
    SecureStore.setItemAsync(ATTEMPTS_KEY, '0', STORE_OPTS),
  ])
}

export type VerifyPinResult =
  | { ok: true; failedAttempts: 0 }
  | { ok: false; failedAttempts: number; lockedOut: boolean }

export async function verifyPin(pin: string): Promise<VerifyPinResult> {
  const record = await loadPinRecord()
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
  const candidate = derivePinVerifier(pin, record.saltHex)
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

export async function changePin(currentPin: string, nextPin: string): Promise<VerifyPinResult & { changed?: boolean }> {
  const verified = await verifyPin(currentPin)
  if (!verified.ok) return { ...verified, changed: false }
  if (!isValidPinFormat(nextPin)) return { ok: false, failedAttempts: 0, lockedOut: false, changed: false }
  const record = await loadPinRecord()
  if (!record) return { ok: false, failedAttempts: 0, lockedOut: false, changed: false }
  await setPin(record.employeeKey, nextPin)
  return { ok: true, failedAttempts: 0, changed: true }
}
