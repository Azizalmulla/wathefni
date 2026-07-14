import { describe, expect, it } from 'vitest'

import en from './en.json'
import ar from './ar.json'

describe('English and Arabic localization', () => {
  it('has exact key parity', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
  })

  it('uses the owner-selected provisional Arabic wordmark', () => {
    expect(ar['brand.wordmark']).toBe('وظفني للموارد البشرية')
  })

  it('does not ship empty copy', () => {
    expect(Object.values(en).every(Boolean)).toBe(true)
    expect(Object.values(ar).every(Boolean)).toBe(true)
  })
})
