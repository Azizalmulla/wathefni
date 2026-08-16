import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { I18nManager, Platform } from 'react-native'
import * as Localization from 'expo-localization'
import AsyncStorage from '@react-native-async-storage/async-storage'

import type { Locale } from '@hr/api/types'
import en from './en.json'
import ar from './ar.json'

const LOCALE_KEY = 'wathefni.hr.locale'
const translations = { en, ar }

type LocaleContextValue = {
  locale: Locale
  isRTL: boolean
  t: (key: keyof typeof en, params?: Record<string, string | number>) => string
  setLocale: (locale: Locale) => Promise<void>
}

const LocaleContext = createContext<LocaleContextValue | null>(null)

function deviceLocale(): Locale {
  return Localization.getLocales()[0]?.languageCode === 'ar' ? 'ar' : 'en'
}

export async function loadInitialLocale(): Promise<Locale> {
  try {
    const stored = await AsyncStorage.getItem(LOCALE_KEY)
    return stored === 'ar' || stored === 'en' ? stored : deviceLocale()
  } catch {
    return deviceLocale()
  }
}

export function LocaleProvider({
  children,
  initialLocale,
  persist = true,
}: {
  children: ReactNode
  initialLocale: Locale
  persist?: boolean
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale)
  const setLocale = useCallback(
    async (next: Locale) => {
      setLocaleState(next)
      if (Platform.OS !== 'web' && I18nManager.isRTL !== (next === 'ar')) {
        I18nManager.allowRTL(next === 'ar')
        I18nManager.forceRTL(next === 'ar')
      }
      if (persist) {
        try {
          await AsyncStorage.setItem(LOCALE_KEY, next)
        } catch {
          // Locale persistence is best-effort and never blocks the UI.
        }
      }
    },
    [persist],
  )

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      isRTL: locale === 'ar',
      t: (key) => translations[locale][key] || translations.en[key],
      setLocale,
    }),
    [locale, setLocale],
  )
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

export function useLocale(): LocaleContextValue {
  const value = useContext(LocaleContext)
  if (!value) throw new Error('useLocale must be used inside LocaleProvider')
  return value
}
