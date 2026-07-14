import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { I18nManager, Platform } from 'react-native'
import { I18n } from 'i18n-js'
import * as Localization from 'expo-localization'
import AsyncStorage from '@react-native-async-storage/async-storage'

import en from './en.json'
import ar from './ar.json'

export type AppLocale = 'en' | 'ar'

const LOCALE_KEY = 'wathefni.locale'

function expandFlatTranslations(flat: Record<string, string>): Record<string, unknown> {
  const nested: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split('.')
    let cursor = nested
    parts.forEach((part, index) => {
      if (index === parts.length - 1) {
        cursor[part] = value
        return
      }
      const current = cursor[part]
      if (!current || typeof current !== 'object') cursor[part] = {}
      cursor = cursor[part] as Record<string, unknown>
    })
  }
  return nested
}

const i18n = new I18n({
  en: expandFlatTranslations(en),
  ar: expandFlatTranslations(ar),
})
i18n.enableFallback = true
i18n.defaultLocale = 'en'

function deviceLocale(): AppLocale {
  const tag = Localization.getLocales()[0]?.languageCode ?? 'en'
  return tag === 'ar' ? 'ar' : 'en'
}

type I18nContextValue = {
  locale: AppLocale
  isRTL: boolean
  t: (key: string, params?: Record<string, string | number>) => string
  setLocale: (next: AppLocale) => Promise<void>
}

const I18nContext = createContext<I18nContextValue | null>(null)

export async function loadInitialLocale(): Promise<AppLocale> {
  try {
    const stored = (await AsyncStorage.getItem(LOCALE_KEY)) as AppLocale | null
    if (stored === 'ar' || stored === 'en') return stored
  } catch {
    // Private mode / blocked storage must not block first paint.
  }
  return deviceLocale()
}

export function I18nProvider({ initialLocale, children }: { initialLocale: AppLocale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>(initialLocale)
  i18n.locale = locale

  const setLocale = useCallback(async (next: AppLocale) => {
    // Update in-memory locale first so interactive previews and settings switches
    // never stall behind AsyncStorage or native RTL bookkeeping.
    i18n.locale = next
    setLocaleState(next)
    const rtl = next === 'ar'
    // Native RTL flips need a reload. Skip the native bridge on web — RN-web's
    // I18nManager is a no-op for isRTL, and calling it during preview remounts
    // has been a source of Safari instability.
    if (Platform.OS !== 'web' && I18nManager.isRTL !== rtl) {
      I18nManager.allowRTL(rtl)
      I18nManager.forceRTL(rtl)
    }
    try {
      await AsyncStorage.setItem(LOCALE_KEY, next)
    } catch {
      // Persistence is best-effort; the active session still switches immediately.
    }
  }, [])

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      isRTL: locale === 'ar',
      t: (key, params) => i18n.t(key, params),
      setLocale,
    }),
    [locale, setLocale],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used within I18nProvider')
  return ctx
}
