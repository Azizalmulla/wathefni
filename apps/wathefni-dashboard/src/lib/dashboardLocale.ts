import type { RecruitingLocale } from '@/lib/recruitingLifecycle'

/** Canonical persistence key for HR Web EN/AR. Do not introduce a second locale store. */
export const RECRUITING_LOCALE_STORAGE_KEY = 'wathefni_recruiting_locale'

export function readStoredRecruitingLocale(): RecruitingLocale {
  try {
    return globalThis.localStorage?.getItem(RECRUITING_LOCALE_STORAGE_KEY) === 'ar' ? 'ar' : 'en'
  } catch {
    return 'en'
  }
}

export function persistRecruitingLocale(locale: RecruitingLocale) {
  try {
    globalThis.localStorage?.setItem(RECRUITING_LOCALE_STORAGE_KEY, locale)
  } catch {
    // Storage can be unavailable in hardened/private browser contexts.
  }
}

export function documentDirection(locale: RecruitingLocale): 'rtl' | 'ltr' {
  return locale === 'ar' ? 'rtl' : 'ltr'
}

export function applyDocumentLocale(locale: RecruitingLocale) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.lang = locale
  root.dir = documentDirection(locale)
}
