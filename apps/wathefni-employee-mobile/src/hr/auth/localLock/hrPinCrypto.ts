/**
 * HR local PIN crypto — same stretch as Employee, distinct pepper.
 * Never shares the Employee local PIN pepper/verifiers.
 */

import { constantTimeEqual, randomSaltHex, sha256Hex } from '@/auth/pinCrypto'

const HR_PEPPER = 'wathefni.hr.local.pin.v1'
const STRETCH_ROUNDS = 8_192

export { constantTimeEqual, randomSaltHex }

export function deriveHrPinVerifier(pin: string, saltHex: string): string {
  let x = `${saltHex}:${pin}:${HR_PEPPER}`
  for (let i = 0; i < STRETCH_ROUNDS; i++) x = sha256Hex(x)
  return x
}
