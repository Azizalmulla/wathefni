import { afterEach, describe, expect, test } from 'vitest'

import {
  applyDocumentLocale,
  documentDirection,
  persistRecruitingLocale,
  readStoredRecruitingLocale,
  RECRUITING_LOCALE_STORAGE_KEY,
} from './dashboardLocale'

afterEach(() => {
  localStorage.removeItem(RECRUITING_LOCALE_STORAGE_KEY)
  document.documentElement.lang = 'en'
  document.documentElement.dir = 'ltr'
})

describe('canonical recruiting locale', () => {
  test('defaults to en and only treats stored ar as Arabic', () => {
    expect(readStoredRecruitingLocale()).toBe('en')
    localStorage.setItem(RECRUITING_LOCALE_STORAGE_KEY, 'ar')
    expect(readStoredRecruitingLocale()).toBe('ar')
    localStorage.setItem(RECRUITING_LOCALE_STORAGE_KEY, 'fr')
    expect(readStoredRecruitingLocale()).toBe('en')
  })

  test('persists to the existing wathefni_recruiting_locale key', () => {
    persistRecruitingLocale('ar')
    expect(localStorage.getItem(RECRUITING_LOCALE_STORAGE_KEY)).toBe('ar')
    persistRecruitingLocale('en')
    expect(localStorage.getItem(RECRUITING_LOCALE_STORAGE_KEY)).toBe('en')
  })

  test('applyDocumentLocale sets html lang and dir together', () => {
    applyDocumentLocale('ar')
    expect(document.documentElement.lang).toBe('ar')
    expect(document.documentElement.dir).toBe('rtl')
    expect(documentDirection('ar')).toBe('rtl')
    applyDocumentLocale('en')
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
    expect(documentDirection('en')).toBe('ltr')
  })
})
