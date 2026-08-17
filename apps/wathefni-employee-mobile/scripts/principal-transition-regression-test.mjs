#!/usr/bin/env node

import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

import {
  canonicalRouteForTarget,
  routePrincipal,
  shellWithPendingTarget,
  targetRouteIsMounted,
} from '../src/principals/transitionModel.ts'
import {
  constantTimeEqual,
  derivePinVerifier,
  randomSaltHex,
  sha256Hex,
} from '../src/auth/pinCrypto.ts'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8')

let checks = 0
const check = (name, run) => {
  run()
  checks += 1
  console.log('PASS', name)
}

for (const platform of ['ios', 'android']) {
  for (const locale of ['en', 'ar']) {
    const matrix = `${platform}/${locale}`
    check(`${matrix}: Employee session + no HR session stays targeted at HR sign-in`, () => {
      const availability = { employeeSession: true, hrSession: false }
      assert.equal(shellWithPendingTarget(availability, 'employee', 'hr'), 'hr')
      assert.equal(canonicalRouteForTarget('hr', availability), '/hr/sign-in')
      assert.equal(targetRouteIsMounted('hr', availability, ['hr', 'sign-in']), true)
    })
    check(`${matrix}: both sessions target HR shell`, () => {
      const availability = { employeeSession: true, hrSession: true }
      assert.equal(shellWithPendingTarget(availability, 'employee', 'hr'), 'hr')
      assert.equal(canonicalRouteForTarget('hr', availability), '/hr')
      assert.equal(targetRouteIsMounted('hr', availability, ['hr', '(tabs)']), true)
    })
    check(`${matrix}: HR targets existing Employee shell`, () => {
      const availability = { employeeSession: true, hrSession: true }
      assert.equal(shellWithPendingTarget(availability, 'hr', 'employee'), 'employee')
      assert.equal(canonicalRouteForTarget('employee', availability), '/(tabs)')
      assert.equal(targetRouteIsMounted('employee', availability, ['(tabs)']), true)
    })
    check(`${matrix}: HR targets Employee activation without Employee session`, () => {
      const availability = { employeeSession: false, hrSession: true }
      assert.equal(shellWithPendingTarget(availability, 'hr', 'employee'), 'employee')
      assert.equal(canonicalRouteForTarget('employee', availability), '/(auth)/activate')
      assert.equal(targetRouteIsMounted('employee', availability, ['(auth)', 'activate']), true)
    })
  }
}

check('pending target survives serialization and overrides normal session fallback', () => {
  const stored = JSON.parse(JSON.stringify({
    id: 'transition-test',
    from: 'employee',
    to: 'hr',
    previousPreference: 'employee',
    startedAt: 1,
  }))
  assert.equal(stored.to, 'hr')
  assert.equal(
    shellWithPendingTarget({ employeeSession: true, hrSession: false }, 'employee', stored.to),
    'hr',
  )
})

check('route principal classification does not merge HR and Employee trees', () => {
  assert.equal(routePrincipal(['hr', 'settings']), 'hr')
  assert.equal(routePrincipal(['(tabs)', 'profile']), 'employee')
  assert.equal(routePrincipal([]), 'unsigned')
})

check('distinct PIN derivations reject the other principal PIN', () => {
  const hrCrypto = read('src/hr/auth/localLock/hrPinCrypto.ts')
    .replace(/^import .*$/gm, '')
    .replace(/: string/g, '')
    .replace(/export /g, '')
  const sandbox = { sha256Hex, constantTimeEqual, randomSaltHex }
  vm.createContext(sandbox)
  vm.runInContext(`${hrCrypto}\nthis.deriveHrPinVerifier = deriveHrPinVerifier`, sandbox)
  const deriveHrPinVerifier = sandbox.deriveHrPinVerifier
  const salt = randomSaltHex(16)
  const employeeStored = derivePinVerifier('111111', salt)
  const hrStored = deriveHrPinVerifier('222222', salt)
  assert.equal(constantTimeEqual(derivePinVerifier('222222', salt), employeeStored), false)
  assert.equal(constantTimeEqual(deriveHrPinVerifier('111111', salt), hrStored), false)
  assert.notEqual(derivePinVerifier('111111', salt), deriveHrPinVerifier('111111', salt))
})

check('SecureStore session and PIN namespaces remain distinct', () => {
  const employeeSession = read('src/auth/session.ts')
  const hrSession = read('src/hr/auth/session.ts')
  const employeePin = read('src/auth/pinStorage.ts')
  const hrPin = read('src/hr/auth/localLock/hrPinStorage.ts')
  assert.match(employeeSession, /wathefni\.session\.token/)
  assert.match(hrSession, /wathefni\.hr\.session\.v1/)
  assert.match(employeePin, /wathefni\.pin\.verifier/)
  assert.match(hrPin, /wathefni\.hr\.pin\.verifier/)
  assert.doesNotMatch(employeePin, /wathefni\.hr\.pin\.verifier/)
})

check('transition is single-flight, persistent, acknowledged, and never swallows errors', () => {
  const gate = read('src/principals/PrincipalGate.tsx')
  assert.match(gate, /if \(transitionPromiseRef\.current\) return transitionPromiseRef\.current/)
  assert.match(gate, /setTransition\(\{[\s\S]*status: 'switching'[\s\S]*to: mode/)
  assert.match(gate, /await prepareExit\(\)/)
  assert.match(gate, /principal_transition_exit_seal_failed/)
  assert.match(gate, /savePendingPrincipalTransition\(pending\)/)
  assert.match(gate, /loadPendingPrincipalTransition\(\)/)
  assert.match(gate, /provider_mount_ack/)
  assert.match(gate, /principal_transition_mount_timeout/)
  assert.doesNotMatch(gate, /catch\s*\{\s*\}/)
})

check('leaving Employee seals only its in-memory request session before HR mounts', () => {
  const auth = read('src/auth/AuthProvider.tsx')
  const control = read('src/principals/SwitchToHrControl.tsx')
  assert.match(auth, /const sealForPrincipalSwitch = useCallback/)
  assert.match(auth, /sealedSessionRef\.current = current/)
  assert.match(auth, /sessionRef\.current = null/)
  assert.match(auth, /setStatus\('locked'\)/)
  assert.doesNotMatch(auth.match(/const sealForPrincipalSwitch[\s\S]*?\n  \}, \[\]\)/)?.[0] || '', /clearSession\(/)
  assert.match(control, /selectMode\('hr', sealForPrincipalSwitch\)/)
})

check('both switch controls stay available without the target principal session', () => {
  assert.match(read('src/principals/SwitchToHrControl.tsx'), /testID="e2e\.principal\.switch\.hr"/)
  assert.match(read('src/hr/features/more/HRMoreLauncherView.tsx'), /testID="e2e\.principal\.switch\.employee"/)
  assert.doesNotMatch(read('src/hr/features/more/HRMoreLauncherView.tsx'), /employeeSession\s*\?\s*\(\s*<ListRow/)
})

check('root navigator and coordinator stay mounted while target subtrees change', () => {
  const rootLayout = read('app/_layout.tsx')
  assert.match(rootLayout, /<PrincipalGateProvider>/)
  assert.match(rootLayout, /<AuthProvider>/)
  assert.match(rootLayout, /<StablePrincipalFrame \/>/)
  assert.match(rootLayout, /function StableRootNavigator\(\)/)
  assert.match(rootLayout, /<StableRootNavigator \/>/)
  assert.doesNotMatch(rootLayout, /function ModeRedirect/)
  assert.doesNotMatch(rootLayout, /return <EmployeeShell/)
})

check('correct backend namespace is owned by each principal provider', () => {
  assert.match(read('src/auth/AuthProvider.tsx'), /['"]\/app\/me['"]/)
  assert.match(read('src/hr/auth/AuthProvider.tsx'), /['"]\/dashboard\/mobile\/me['"]/)
})

check('EN and AR expose the same principal transition contract', () => {
  const en = JSON.parse(read('src/i18n/en.json'))
  const ar = JSON.parse(read('src/i18n/ar.json'))
  assert.deepEqual(Object.keys(en).sort(), Object.keys(ar).sort())
  for (const key of [
    'principal.switchHr',
    'principal.switchEmployee',
    'principal.switchingHr',
    'principal.switchingEmployee',
    'principal.transitionError',
  ]) {
    assert.ok(en[key])
    assert.ok(ar[key])
  }
})

console.log(`PRINCIPAL_TRANSITION_REGRESSION_PASS ${checks}/${checks}`)
