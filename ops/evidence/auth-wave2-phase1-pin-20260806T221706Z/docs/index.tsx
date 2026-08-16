import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Alert, DevSettings, I18nManager, Platform, StyleSheet, View } from 'react-native'
import { I18n } from 'i18n-js'
import * as Localization from 'expo-localization'
import AsyncStorage from '@react-native-async-storage/async-storage'
import * as Updates from 'expo-updates'

import en from './en.json'
import ar from './ar.json'
import { markSkipUnlockOnce } from '@/auth/sessionResume'

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

/** Keep Yoga / I18nManager aligned with the selected app locale (EN=LTR, AR=RTL). */
export function syncNativeLayoutDirection(locale: AppLocale): boolean {
  if (Platform.OS === 'web') return false
  const rtl = locale === 'ar'
  I18nManager.allowRTL(true)
  I18nManager.swapLeftAndRightInRTL(true)
  const needsFlip = I18nManager.isRTL !== rtl
  if (needsFlip) {
    I18nManager.forceRTL(rtl)
  }
  return needsFlip
}

function nativeDirectionNeedsFlip(locale: AppLocale): boolean {
  if (Platform.OS === 'web') return false
  return I18nManager.isRTL !== (locale === 'ar')
}

async function reloadForLayoutDirection(): Promise<void> {
  try {
    await Updates.reloadAsync()
    return
  } catch {
    // Dev client / Expo Go may not support Updates.reloadAsync.
  }
  try {
    DevSettings.reload()
    return
  } catch {
    // fall through
  }
  Alert.alert(i18n.t('access.rtlRestart.title'), i18n.t('access.rtlRestart.manualMessage'), [
    { text: i18n.t('access.rtlRestart.ok') },
  ])
}

export async function loadInitialLocale(): Promise<AppLocale> {
  try {
    const stored = (await AsyncStorage.getItem(LOCALE_KEY)) as AppLocale | null
    if (stored === 'ar' || stored === 'en') return stored
  } catch {
    // Private mode / blocked storage must not block first paint.
  }
  return deviceLocale()
}

/**
 * Locale for signed-out / activation surfaces.
 * Uses the user's explicit app language preference only — never an employee
 * profile locale from a prior session.
 */
export async function resolveAuthLocale(): Promise<AppLocale> {
  return loadInitialLocale()
}

export type SetLocaleOptions = {
  /** When true, next boot skips PIN unlock once (intentional RTL restart while signed in). */
  resumeUnlockedSession?: boolean
}

type I18nContextValue = {
  locale: AppLocale
  isRTL: boolean
  t: (key: string, params?: Record<string, string | number>) => string
  setLocale: (next: AppLocale, opts?: SetLocaleOptions) => Promise<void>
  /** Re-apply stored preference + native direction (logout, login, deep links). */
  syncLayoutLocale: () => Promise<AppLocale>
  /** @deprecated alias — prefer syncLayoutLocale */
  syncAuthLocale: () => Promise<AppLocale>
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ initialLocale, children }: { initialLocale: AppLocale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>(initialLocale)
  i18n.locale = locale
  const isRTL = locale === 'ar'

  // Align native direction on first paint with the stored preference.
  useEffect(() => {
    syncNativeLayoutDirection(initialLocale)
  }, [initialLocale])

  const applyLocaleLocally = useCallback(async (next: AppLocale) => {
    i18n.locale = next
    setLocaleState(next)
    try {
      await AsyncStorage.setItem(LOCALE_KEY, next)
    } catch {
      // Persistence is best-effort; the active session still switches immediately.
    }
  }, [])

  const setLocale = useCallback(
    async (next: AppLocale, opts?: SetLocaleOptions) => {
      if (next === (i18n.locale as AppLocale)) return

      const needsFlip = nativeDirectionNeedsFlip(next)
      if (!needsFlip) {
        await applyLocaleLocally(next)
        syncNativeLayoutDirection(next)
        return
      }

      // Intentional process restart — never silent. Confirm first; do not flip RTL until OK.
      await new Promise<void>((resolve) => {
        Alert.alert(i18n.t('access.rtlRestart.title'), i18n.t('access.rtlRestart.message'), [
          {
            text: i18n.t('common.cancel'),
            style: 'cancel',
            onPress: () => resolve(),
          },
          {
            text: i18n.t('access.rtlRestart.confirm'),
            onPress: () => {
              void (async () => {
                try {
                  if (opts?.resumeUnlockedSession) {
                    await markSkipUnlockOnce()
                  }
                  await applyLocaleLocally(next)
                  syncNativeLayoutDirection(next)
                  await reloadForLayoutDirection()
                } finally {
                  resolve()
                }
              })()
            },
          },
        ])
      })
    },
    [applyLocaleLocally],
  )

  const syncLayoutLocale = useCallback(async () => {
    const next = await resolveAuthLocale()
    i18n.locale = next
    setLocaleState(next)
    syncNativeLayoutDirection(next)
    return next
  }, [])

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      isRTL,
      t: (key, params) => i18n.t(key, params),
      setLocale,
      syncLayoutLocale,
      syncAuthLocale: syncLayoutLocale,
    }),
    [locale, isRTL, setLocale, syncLayoutLocale],
  )

  return (
    <I18nContext.Provider value={value}>
      <View style={[styles.root, { direction: isRTL ? 'rtl' : 'ltr' }]}>{children}</View>
    </I18nContext.Provider>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1 },
})

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used within I18nProvider')
  return ctx
}

/** Active app locale for non-React helpers (API error presentation). */
export function activeAppLocale(): AppLocale {
  return (i18n.locale === 'ar' ? 'ar' : 'en') as AppLocale
}
