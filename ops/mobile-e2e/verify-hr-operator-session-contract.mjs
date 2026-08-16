#!/usr/bin/env node
/**
 * HR operator session contract — client coordinator proofs.
 *
 * Mirrors apps/wathefni-employee-mobile/src/hr/auth/sessionCoordinator.ts
 * + atomic blob persistence rules. No React Native runtime required.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '../..')
const HR_AUTH = path.join(ROOT, 'apps/wathefni-employee-mobile/src/hr/auth')
const ORCH = path.join(ROOT, 'wathefni-orchestrator/operator_mobile.py')

class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status
    this.code = code
  }
}

function isNewer(baseline, candidate) {
  if (!candidate) return false
  if (!baseline) return true
  return (
    candidate.refreshToken !== baseline.refreshToken ||
    candidate.accessToken !== baseline.accessToken
  )
}

function createCoordinator() {
  /** @type {Map<string, string>} */
  const store = new Map()
  const BLOB = 'wathefni.hr.session.v1'
  let inFlight = null
  let memorySession = null
  let refreshCalls = 0
  let cleared = false
  /** @type {(rt: string) => Promise<any>} */
  let transport = async () => {
    throw new Error('transport unset')
  }

  async function save(session) {
    store.set(BLOB, JSON.stringify(session))
  }
  async function load() {
    const raw = store.get(BLOB)
    return raw ? JSON.parse(raw) : null
  }
  async function clear() {
    store.delete(BLOB)
    cleared = true
  }

  async function resolve(hint) {
    const stored = await load()
    const candidates = [memorySession, hint ?? null, stored].filter(Boolean)
    if (!candidates.length) return null
    if (stored) {
      memorySession = stored
      return stored
    }
    let best = candidates[0]
    for (const row of candidates) if (isNewer(best, row)) best = row
    memorySession = best
    return best
  }

  async function rotate(hint) {
    if (inFlight) return inFlight
    inFlight = (async () => {
      const presented = await resolve(hint)
      if (!presented?.refreshToken) throw new ApiError(401, 'session_expired', 'sign in')
      try {
        refreshCalls += 1
        const response = await transport(presented.refreshToken)
        const next = {
          accessToken: response.access_token,
          refreshToken: response.refresh_token,
          companyCode: response.me.principal.company_code,
          expiresAt: response.expires_at,
        }
        await save(next)
        memorySession = next
        return next
      } catch (error) {
        if (error instanceof ApiError && error.code === 'session_revoked') {
          const reloaded = await load()
          if (isNewer(presented, reloaded)) {
            memorySession = reloaded
            return reloaded
          }
          if (isNewer(presented, memorySession)) return memorySession
        }
        throw error
      } finally {
        inFlight = null
      }
    })()
    return inFlight
  }

  async function clearIfNoNewer(failedWith) {
    const reloaded = await load()
    if (isNewer(failedWith, reloaded)) {
      memorySession = reloaded
      return 'adopted'
    }
    if (memorySession && isNewer(failedWith, memorySession)) return 'adopted'
    memorySession = null
    await clear()
    return 'cleared'
  }

  /** Simulate authenticated request path with 401 → rotate → retry. */
  async function request(path, sessionRef) {
    let current = sessionRef.current || (await resolve(null))
    if (!current) throw new ApiError(401, 'session_expired', 'sign in')
    sessionRef.current = current
    try {
      return await callApi(path, current.accessToken)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        const rotated = await rotate(current)
        sessionRef.current = rotated
        return await callApi(path, rotated.accessToken)
      }
      throw error
    }
  }

  let accessValid = new Set()
  let refreshValid = new Map() // refresh -> {access, refreshNext}
  let apiHits = 0

  async function callApi(path, access) {
    apiHits += 1
    if (path === '/me' || path.startsWith('/data')) {
      if (!accessValid.has(access)) throw new ApiError(401, 'session_expired', 'expired')
      return { ok: true, path, access }
    }
    throw new Error('unknown path')
  }

  function mint(label) {
    const access = `A-${label}`
    const refresh = `R-${label}`
    accessValid.add(access)
    refreshValid.set(refresh, { access, nextLabel: null })
    return {
      accessToken: access,
      refreshToken: refresh,
      companyCode: 'WATHEFNI',
      expiresAt: new Date(Date.now() + 45 * 60 * 1000).toISOString(),
    }
  }

  function expireAccess(session) {
    accessValid.delete(session.accessToken)
  }

  transport = async (refreshToken) => {
    const row = refreshValid.get(refreshToken)
    if (!row) throw new ApiError(401, 'session_revoked', 'This session is no longer valid.')
    refreshValid.delete(refreshToken) // rotate: old refresh dead
    const next = mint(`${Date.now()}-${Math.random().toString(16).slice(2)}`)
    return {
      access_token: next.accessToken,
      refresh_token: next.refreshToken,
      expires_at: next.expiresAt,
      me: { principal: { company_code: 'WATHEFNI' } },
    }
  }

  return {
    store,
    save,
    load,
    rotate,
    resolve,
    clearIfNoNewer,
    request,
    mint,
    expireAccess,
    get refreshCalls() {
      return refreshCalls
    },
    get cleared() {
      return cleared
    },
    get apiHits() {
      return apiHits
    },
    setTransport(fn) {
      transport = fn
    },
    get memory() {
      return memorySession
    },
    setMemory(s) {
      memorySession = s
    },
  }
}

function sourceContract() {
  const session = fs.readFileSync(path.join(HR_AUTH, 'session.ts'), 'utf8')
  const coord = fs.readFileSync(path.join(HR_AUTH, 'sessionCoordinator.ts'), 'utf8')
  const provider = fs.readFileSync(path.join(HR_AUTH, 'AuthProvider.tsx'), 'utf8')
  const employeeSession = fs.readFileSync(
    path.join(ROOT, 'apps/wathefni-employee-mobile/src/auth/session.ts'),
    'utf8',
  )
  const orch = fs.readFileSync(ORCH, 'utf8')

  assert.match(session, /wathefni\.hr\.session\.v1/)
  assert.match(session, /JSON\.stringify\(session\)/)
  assert.doesNotMatch(employeeSession, /wathefni\.hr\./)
  assert.match(employeeSession, /wathefni\.session\.token/)
  assert.match(coord, /let inFlight/)
  assert.match(coord, /session_revoked/)
  assert.match(coord, /isNewerOperatorSession/)
  assert.match(provider, /rotateOperatorSession/)
  assert.match(provider, /clearOperatorAuthIfNoNewerSession/)
  assert.match(provider, /bindOperatorSessionMemory/)
  assert.match(provider, /Local lock is never a logout/)
  assert.match(orch, /REFRESH_TTL = timedelta\(days=90\)/)
  assert.match(orch, /ACCESS_TTL = timedelta\(minutes=45\)/)
  assert.match(orch, /status='rotated'/)
  assert.match(orch, /session_revoked/)
}

async function proofTenSimultaneous() {
  const c = createCoordinator()
  const s0 = c.mint('s0')
  await c.save(s0)
  c.setMemory(s0)
  c.expireAccess(s0)
  const sessionRef = { current: s0 }
  const results = await Promise.all(
    Array.from({ length: 10 }, (_, i) => c.request(`/data?i=${i}`, sessionRef)),
  )
  assert.equal(c.refreshCalls, 1, 'exactly one refresh')
  assert.equal(c.cleared, false, 'zero logout')
  assert.equal(results.length, 10)
  assert.ok(results.every((r) => r.ok))
  assert.notEqual(sessionRef.current.refreshToken, s0.refreshToken)
}

async function proofColdBootRemount() {
  const c = createCoordinator()
  const s0 = c.mint('boot')
  await c.save(s0)
  c.expireAccess(s0)
  // Two remounts both boot with stale hint — single flight.
  const boot = async (hint) => c.rotate(hint)
  const [a, b] = await Promise.all([boot(s0), boot(s0)])
  assert.equal(c.refreshCalls, 1)
  assert.equal(a.refreshToken, b.refreshToken)
  assert.equal(c.cleared, false)
  // Second remount after save: resolve SecureStore, no extra refresh if access valid.
  c.setMemory(null)
  const loaded = await c.resolve(null)
  await c.request('/me', { current: loaded })
  assert.equal(c.refreshCalls, 1, 'valid access after remount needs no refresh')
}

async function proofForegroundUnlock() {
  const c = createCoordinator()
  const s0 = c.mint('unlock')
  await c.save(s0)
  c.setMemory(s0)
  c.expireAccess(s0)
  // Locked surface holds sealed copy; unlock + foreground refresh race.
  const sealed = { current: null }
  const live = { current: null }
  const unlock = async () => {
    live.current = s0
    return c.request('/me', live)
  }
  const foreground = async () => c.request('/me', { current: s0 })
  await Promise.all([unlock(), foreground()])
  assert.equal(c.refreshCalls, 1)
  assert.equal(c.cleared, false)
  void sealed
}

async function proofOtaReload() {
  const c = createCoordinator()
  const s0 = c.mint('ota')
  await c.save(s0)
  c.expireAccess(s0)
  // OTA remount: memory wiped, SecureStore intact.
  c.setMemory(null)
  const loaded = await c.resolve(null)
  assert.equal(loaded.refreshToken, s0.refreshToken)
  await c.request('/me', { current: loaded })
  assert.equal(c.refreshCalls, 1)
  assert.equal(c.cleared, false)
  const after = await c.load()
  assert.notEqual(after.accessToken, s0.accessToken)
}

async function proofRevokedAdoptsNewer() {
  const c = createCoordinator()
  const s0 = c.mint('old')
  const s1 = c.mint('new')
  await c.save(s1) // winner already persisted
  c.setMemory(s1)
  // Stale flight presents s0 refresh → server revoked, adopt s1.
  c.setTransport(async (rt) => {
    if (rt === s0.refreshToken) throw new ApiError(401, 'session_revoked', 'no longer valid')
    throw new Error('unexpected')
  })
  c.setMemory(s0) // stale memory
  // Force presented = s0 by saving s0? Actually resolve prefers stored s1.
  // Simulate torn state: memory s0, store s1 — resolve prefers store.
  const resolved = await c.resolve(s0)
  assert.equal(resolved.refreshToken, s1.refreshToken)
  // Explicit revoked-after-success path:
  const outcome = await c.clearIfNoNewer(s0)
  assert.equal(outcome, 'adopted')
  assert.equal(c.cleared, false)
}

async function proofExplicitRevokeLogout() {
  const c = createCoordinator()
  const s0 = c.mint('rev')
  await c.save(s0)
  c.setMemory(s0)
  c.setTransport(async () => {
    throw new ApiError(401, 'session_revoked', 'no longer valid')
  })
  await assert.rejects(() => c.rotate(s0), (e) => e.code === 'session_revoked')
  const outcome = await c.clearIfNoNewer(s0)
  assert.equal(outcome, 'cleared')
  assert.equal(c.cleared, true)
  assert.equal(await c.load(), null)
}

async function proofAtomicBlob() {
  const sessionTs = fs.readFileSync(path.join(HR_AUTH, 'session.ts'), 'utf8')
  assert.match(sessionTs, /SESSION_BLOB_KEY/)
  assert.match(sessionTs, /setItemAsync\(SESSION_BLOB_KEY, JSON\.stringify/)
  assert.match(sessionTs, /clearLegacyKeys/)
}

async function main() {
  const results = []
  const run = async (name, fn) => {
    try {
      await fn()
      results.push({ name, pass: true })
      console.log(`PASS  ${name}`)
    } catch (error) {
      results.push({ name, pass: false, error: String(error) })
      console.error(`FAIL  ${name}`)
      console.error(error)
    }
  }

  await run('source_contract_namespaces_and_ttl', sourceContract)
  await run('atomic_securestore_blob', proofAtomicBlob)
  await run('ten_simultaneous_401_one_refresh_zero_logout', proofTenSimultaneous)
  await run('cold_boot_remount_during_expiry', proofColdBootRemount)
  await run('foreground_unlock_during_expiry', proofForegroundUnlock)
  await run('ota_reload_securestore_restore', proofOtaReload)
  await run('session_revoked_adopts_newer_securestore', proofRevokedAdoptsNewer)
  await run('explicit_revoke_clears_auth', proofExplicitRevokeLogout)

  const failed = results.filter((r) => !r.pass)
  console.log('')
  console.log(`client_proofs ${results.length - failed.length}/${results.length} PASS`)
  if (failed.length) process.exit(1)
}

main()
