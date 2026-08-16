import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ActivityIndicator, DevSettings, I18nManager, Platform, StyleSheet, View } from 'react-native'
import { I18n } from 'i18n-js'
import * as Localization from 'expo-localization'
import AsyncStorage from '@react-native-async-storage/async-storage'
import * as Updates from 'expo-updates'

import en from './en.json'
import ar from './ar.json'
import { markLocaleRestartPreserveAuth } from '@/auth/sessionResume'
import { colors } from '@/theme'

export type AppLocale = 'en' | 'ar'

const LOCALE_KEY = 'wathefni.locale'

function isTranslationObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function mergeTranslationObjects(
  existing: Record<string, unknown>,
  incoming: Record<string, unknown>,
): Record<string, unknown> {
  const merged = { ...existing }
  for (const [key, value] of Object.entries(incoming)) {
    const current = merged[key]
    merged[key] =
      isTranslationObject(current) && isTranslationObject(value)
        ? mergeTranslationObjects(current, value)
        : value
  }
  return merged
}

function expandFlatTranslations(flat: Record<string, unknown>): Record<string, unknown> {
  const nested: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split('.')
    let cursor = nested
    parts.forEach((part, index) => {
      if (index === parts.length - 1) {
        const current = cursor[part]
        cursor[part] =
          isTranslationObject(current) && isTranslationObject(value)
            ? mergeTranslationObjects(current, value)
            : value
        return
      }
      const current = cursor[part]
      if (!isTranslationObject(current)) cursor[part] = {}
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

const ALIGN_LEADING = { textAlign: 'left' } as const
const ALIGN_LITERAL_RIGHT = { textAlign: 'right' } as const

/**
 * Text alignment against the reading edge.
 *
 * iOS swaps `textAlign` left↔right itself whenever the view's native layout
 * direction is RTL (`RCTTextAttributes.effectiveParagraphStyle`). Arabic is
 * therefore expressed as `left` and arrives as right; stating `right` directly
 * would be swapped to left and pin Arabic against the wrong edge.
 *
 * The literal value is only correct in the degraded case where Arabic is showing
 * but the native direction was never applied, i.e. an RTL reload that did not
 * happen. That is why this reads `I18nManager.isRTL` — the direction actually in
 * force — rather than the selected locale.
 */
export function readingEdgeAlign(isRTL: boolean) {
  return isRTL && !I18nManager.isRTL ? ALIGN_LITERAL_RIGHT : ALIGN_LEADING
}

const ALIGN_TRAILING = { textAlign: 'right' } as const
const ALIGN_LITERAL_LEFT = { textAlign: 'left' } as const

/** Mirror of {@link readingEdgeAlign}, for values set against the far edge. */
export function trailingEdgeAlign(isRTL: boolean) {
  return isRTL && !I18nManager.isRTL ? ALIGN_LITERAL_LEFT : ALIGN_TRAILING
}

/** Silent process reload for RTL. No user-facing restart copy. */
async function reloadForLayoutDirection(): Promise<boolean> {
  try {
    await Updates.reloadAsync()
    return true
  } catch {
    // Dev client / Expo Go may not support Updates.reloadAsync.
  }
  try {
    DevSettings.reload()
    return true
  } catch {
    return false
  }
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
  const [layoutSwitching, setLayoutSwitching] = useState(false)
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

      // Immediate: cover UI → persist locale + preserve-auth → silent RTL reload.
      // No confirmation Alert — user should not need to understand a restart.
      setLayoutSwitching(true)
      try {
        if (opts?.resumeUnlockedSession) {
          await markLocaleRestartPreserveAuth()
        }
        await applyLocaleLocally(next)
        syncNativeLayoutDirection(next)
        // Let SecureStore/AsyncStorage dual-write settle before process reload.
        await new Promise((r) => setTimeout(r, 150))
        const reloaded = await reloadForLayoutDirection()
        if (!reloaded) {
          // Reload unavailable: keep new strings + CSS direction; clear cover.
          setLayoutSwitching(false)
        }
        // If reload succeeded, this JS context is torn down — overlay stays until remount.
      } catch {
        setLayoutSwitching(false)
      }
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
      <View style={[styles.root, { direction: isRTL ? 'rtl' : 'ltr' }]}>
        {children}
        {layoutSwitching ? (
          <View style={styles.switchCover} pointerEvents="auto" accessibilityElementsHidden>
            <ActivityIndicator testID="e2e.boot.locale-switch" color={colors.accent} size="large" />
          </View>
        ) : null}
      </View>
    </I18nContext.Provider>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  switchCover: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
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
