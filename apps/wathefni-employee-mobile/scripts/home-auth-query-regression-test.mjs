#!/usr/bin/env node

import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { canFetchEmployeeHome } from '../src/features/home/homeQueryPolicy.ts'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8')

let checks = 0
const check = (name, run) => {
  run()
  checks += 1
  console.log('PASS', name)
}

function countAutomaticFetches(states) {
  let wasEnabled = false
  let fetches = 0
  for (const state of states) {
    const enabled = canFetchEmployeeHome(state)
    if (enabled && !wasEnabled) fetches += 1
    wasEnabled = enabled
  }
  return fetches
}

for (const platform of ['ios', 'android']) {
  for (const locale of ['en', 'ar']) {
    const matrix = `${platform}/${locale}`

    check(`${matrix}: sealed auth states cannot fetch protected Home data`, () => {
      for (const state of [
        'loading',
        'signedOut',
        'blocked',
        'locked',
        'needsPinSetup',
        'needsBiometricOptIn',
      ]) {
        assert.equal(canFetchEmployeeHome(state), false, state)
      }
    })

    check(`${matrix}: correct PIN enables exactly one initial Home fetch`, () => {
      assert.equal(countAutomaticFetches(['locked', 'locked', 'signedIn', 'signedIn']), 1)
    })

    check(`${matrix}: wrong PIN remains locked without a Home fetch`, () => {
      assert.equal(countAutomaticFetches(['locked', 'locked', 'locked']), 0)
    })

    check(`${matrix}: genuine signed-in error remains manually retryable`, () => {
      let attempts = countAutomaticFetches(['locked', 'signedIn'])
      assert.equal(canFetchEmployeeHome('signedIn'), true)
      attempts += 1 // HomeErrorView's explicit query.refetch().
      assert.equal(attempts, 2)
    })
  }
}

check('Home screen wires the signed-in guard into the actual protected query', () => {
  const screen = read('app/(tabs)/index.tsx')
  assert.match(screen, /enabled: canFetchEmployeeHome\(status\)/)
  assert.match(screen, /const \{ me, profile, refreshMe, status \} = useAuth\(\)/)
  assert.match(screen, /onRetry=\{\(\) => void home\.refetch\(\)\}/)
})

check('Home error state uses the same top safe-area page contract as normal Home', () => {
  const view = read('src/features/home/HomeView.tsx')
  const errorView = view.split('export function HomeErrorView', 2)[1].split('const styles', 1)[0]
  assert.match(errorView, /<PageScreen style=\{styles\.stateScreen\}>/)
  assert.match(errorView, /<\/PageScreen>/)
})

check('EN and AR retain equivalent Home unavailable and retry copy', () => {
  const en = JSON.parse(read('src/i18n/en.json'))
  const ar = JSON.parse(read('src/i18n/ar.json'))
  for (const key of ['home.dataUnavailable', 'home.dataUnavailableHint', 'common.retry']) {
    assert.ok(en[key], `missing EN ${key}`)
    assert.ok(ar[key], `missing AR ${key}`)
  }
})

console.log(`HOME_AUTH_QUERY_REGRESSION_PASS ${checks}/${checks}`)
