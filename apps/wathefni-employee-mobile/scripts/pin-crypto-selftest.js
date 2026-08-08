#!/usr/bin/env node
/** Local PIN crypto/policy self-test (no React Native). */
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const root = path.resolve(__dirname, '..')
const cryptoSrc = fs.readFileSync(path.join(root, 'src/auth/pinCrypto.ts'), 'utf8')
// Strip TS types for a tiny eval of the crypto helpers.
const js = cryptoSrc
  .replace(/: string/g, '')
  .replace(/: number/g, '')
  .replace(/: Uint8Array/g, '')
  .replace(/: boolean/g, '')
  .replace(/: Crypto \| undefined/g, '')
  .replace(/export /g, '')
  .replace(/as Crypto \| undefined/g, '')

const sandbox = { globalThis, TextEncoder, console, Math, Array, Uint8Array, DataView, Uint32Array }
vm.createContext(sandbox)
vm.runInContext(js + '\nthis.__exports = { derivePinVerifier, constantTimeEqual, randomSaltHex, sha256Hex }', sandbox)
const { derivePinVerifier, constantTimeEqual, randomSaltHex } = sandbox.__exports

const salt = randomSaltHex(16)
const v1 = derivePinVerifier('123456', salt)
const v2 = derivePinVerifier('123456', salt)
const v3 = derivePinVerifier('123457', salt)
if (!constantTimeEqual(v1, v2)) throw new Error('same pin must match')
if (constantTimeEqual(v1, v3)) throw new Error('different pin must not match')
if (v1.length !== 64) throw new Error('verifier hex length')
console.log('PIN_CRYPTO_SELFTEST_PASS')
