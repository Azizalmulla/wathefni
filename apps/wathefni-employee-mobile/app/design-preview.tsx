import { useEffect, useRef, useState } from 'react'
import { Pressable, SafeAreaView, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'

import { useI18n, type AppLocale } from '@/i18n'
import { ActivationView } from '@/features/activation/ActivationView'
import { HomeErrorView, HomeLoadingView, HomeView } from '@/features/home/HomeView'
import {
  OnboardingErrorView,
  OnboardingLoadingView,
  OnboardingView,
} from '@/features/onboarding/OnboardingView'
import {
  DESIGN_PREVIEW_ENABLED,
  completedOnboarding,
  emptyNotifications,
  minimalFeatures,
  multiFeatures,
  previewAttendance,
  previewLeave,
  previewNotifications,
  previewOnboarding,
  previewProfile,
  previewShift,
  rejectedOnboarding,
  reviewOnboarding,
} from '@/designPreview'
import { colors, radius, spacing } from '@/theme'

type PreviewScreen = 'activation' | 'home' | 'onboarding'
type PreviewScenario =
  | 'default'
  | 'multi'
  | 'minimal'
  | 'loading'
  | 'empty'
  | 'error'
  | 'rejected'
  | 'review'
  | 'completed'

const SCREEN_SCENARIOS: Record<PreviewScreen, PreviewScenario[]> = {
  activation: ['default', 'loading', 'error'],
  home: ['multi', 'minimal', 'loading', 'empty', 'error'],
  onboarding: ['multi', 'loading', 'empty', 'error', 'review', 'rejected', 'completed'],
}

export default function DesignPreviewScreen() {
  const params = useLocalSearchParams<{
    screen?: string | string[]
    locale?: string | string[]
    scenario?: string | string[]
    capture?: string | string[]
  }>()
  const router = useRouter()
  const { locale, setLocale, t } = useI18n()
  const [phone, setPhone] = useState('0000 0000')
  const [code, setCode] = useState('123456')
  const localeSyncRef = useRef<AppLocale | null>(null)

  const screen = previewScreen(firstParam(params.screen))
  const previewLocale = previewLocaleFromParam(firstParam(params.locale))
  const scenario = coerceScenario(screen, firstParam(params.scenario))
  const capture = firstParam(params.capture) === '1'
  const availableScenarios = SCREEN_SCENARIOS[screen]

  // URL is the source of truth for preview controls. Sync i18n from the URL and
  // never let a stale locale=en query silently overwrite an AR selection.
  useEffect(() => {
    if (localeSyncRef.current === previewLocale && locale === previewLocale) return
    localeSyncRef.current = previewLocale
    if (locale !== previewLocale) void setLocale(previewLocale)
  }, [locale, previewLocale, setLocale])

  // Keep invalid combinations out of the address bar so refresh is stable.
  useEffect(() => {
    const rawScenario = firstParam(params.scenario)
    const rawScreen = firstParam(params.screen)
    const rawLocale = firstParam(params.locale)
    const needsNormalize =
      previewScreen(rawScreen) !== (rawScreen as PreviewScreen | undefined)
      || coerceScenario(screen, rawScenario) !== (rawScenario as PreviewScenario | undefined)
      || previewLocaleFromParam(rawLocale) !== (rawLocale as AppLocale | undefined)
    if (!needsNormalize) return
    router.setParams({
      screen,
      locale: previewLocale,
      scenario,
      ...(capture ? { capture: '1' } : {}),
    })
  }, [capture, params.locale, params.scenario, params.screen, previewLocale, router, scenario, screen])

  const updatePreview = (patch: {
    screen?: PreviewScreen
    locale?: AppLocale
    scenario?: PreviewScenario
  }) => {
    const nextScreen = patch.screen ?? screen
    const nextLocale = patch.locale ?? previewLocale
    const nextScenario = coerceScenario(nextScreen, patch.scenario ?? scenario)
    router.setParams({
      screen: nextScreen,
      locale: nextLocale,
      scenario: nextScenario,
      ...(capture ? { capture: '1' } : {}),
    })
    if (patch.locale && patch.locale !== locale) void setLocale(patch.locale)
  }

  if (!DESIGN_PREVIEW_ENABLED) {
    return (
      <SafeAreaView style={styles.disabled}>
        <Text>{t('notFound.message')}</Text>
      </SafeAreaView>
    )
  }

  const goHome = () => updatePreview({ screen: 'home', scenario: 'multi' })
  const navigate = (path: string) => {
    if (path === '/onboarding') updatePreview({ screen: 'onboarding', scenario: 'multi' })
  }

  return (
    <View style={styles.root}>
      <View style={styles.phone} accessibilityLabel={`preview-${screen}-${previewLocale}-${scenario}`}>
        {screen === 'activation' ? (
          <ActivationView
            phone={phone}
            code={code}
            busy={scenario === 'loading'}
            error={scenario === 'error' ? t('auth.invalidCode') : null}
            notice={null}
            onPhoneChange={setPhone}
            onCodeChange={setCode}
            onSignIn={goHome}
            onRequestCode={() => undefined}
          />
        ) : null}

        {screen === 'home' && scenario === 'loading' ? <HomeLoadingView /> : null}
        {screen === 'home' && scenario === 'error' ? (
          <HomeErrorView onRetry={() => updatePreview({ scenario: 'multi' })} />
        ) : null}
        {screen === 'home' && scenario !== 'loading' && scenario !== 'error' ? (
          <HomeView
            profile={previewProfile(previewLocale)}
            features={scenario === 'minimal' ? minimalFeatures : multiFeatures}
            shift={
              scenario === 'minimal' || scenario === 'empty'
                ? undefined
                : { ...previewShift, location: previewLocale === 'ar' ? 'دعم العملاء' : previewShift.location }
            }
            attendance={scenario === 'minimal' ? undefined : previewAttendance}
            leave={scenario === 'minimal' ? undefined : previewLeave}
            notifications={
              scenario === 'minimal' || scenario === 'empty'
                ? emptyNotifications
                : {
                    ...previewNotifications,
                    notifications: previewNotifications.notifications.map((notification) => ({
                      ...notification,
                      title: previewLocale === 'ar' ? 'تحديث على السياسات' : notification.title,
                    })),
                  }
            }
            onboarding={
              scenario === 'minimal'
                ? undefined
                : scenario === 'empty'
                  ? completedOnboarding
                  : previewOnboarding
            }
            canRequestLeave={scenario !== 'minimal'}
            onNavigate={navigate}
          />
        ) : null}

        {screen === 'onboarding' && scenario === 'loading' ? <OnboardingLoadingView /> : null}
        {screen === 'onboarding' && scenario === 'error' ? (
          <OnboardingErrorView onRetry={() => updatePreview({ scenario: 'multi' })} />
        ) : null}
        {screen === 'onboarding' && scenario !== 'loading' && scenario !== 'error' ? (
          <OnboardingView
            data={
              scenario === 'empty' || scenario === 'completed'
                ? completedOnboarding
                : scenario === 'rejected'
                  ? rejectedOnboarding
                  : scenario === 'review'
                    ? reviewOnboarding
                    : previewOnboarding
            }
            uploadingId={null}
            onUpload={() => undefined}
            onBack={goHome}
          />
        ) : null}
      </View>

      {!capture ? (
        <PreviewControls
          screen={screen}
          scenario={scenario}
          locale={previewLocale}
          availableScenarios={availableScenarios}
          onScreen={(value) => updatePreview({ screen: value })}
          onScenario={(value) => updatePreview({ scenario: value })}
          onLocale={(value) => updatePreview({ locale: value })}
          onClose={() => router.replace('/(auth)/activate')}
        />
      ) : null}
    </View>
  )
}

function PreviewControls({
  screen,
  scenario,
  locale,
  availableScenarios,
  onScreen,
  onScenario,
  onLocale,
  onClose,
}: {
  screen: PreviewScreen
  scenario: PreviewScenario
  locale: AppLocale
  availableScenarios: PreviewScenario[]
  onScreen: (value: PreviewScreen) => void
  onScenario: (value: PreviewScenario) => void
  onLocale: (value: AppLocale) => void
  onClose: () => void
}) {
  return (
    <View style={styles.controls} accessibilityLabel="preview-controls">
      <View style={styles.controlRow}>
        {(['activation', 'home', 'onboarding'] as const).map((value) => (
          <Control key={value} active={screen === value} label={value} onPress={() => onScreen(value)} />
        ))}
      </View>
      <View style={styles.controlRow}>
        {availableScenarios.map((value) => (
          <Control key={value} active={scenario === value} label={value} onPress={() => onScenario(value)} />
        ))}
      </View>
      <View style={styles.controlRow}>
        <Control active={locale === 'en'} label="EN" onPress={() => onLocale('en')} />
        <Control active={locale === 'ar'} label="AR" onPress={() => onLocale('ar')} />
        <Control active={false} label="Close" onPress={onClose} />
      </View>
    </View>
  )
}

function Control({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={active ? `${label} selected` : label}
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[styles.control, active && styles.controlActive]}
    >
      <Text style={[styles.controlText, active && styles.controlTextActive]}>{label}</Text>
    </Pressable>
  )
}

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

function previewScreen(value: string | undefined): PreviewScreen {
  return value === 'home' || value === 'onboarding' ? value : 'activation'
}

function previewLocaleFromParam(value: string | undefined): AppLocale {
  return value === 'ar' ? 'ar' : 'en'
}

function coerceScenario(screen: PreviewScreen, value: string | undefined): PreviewScenario {
  const allowed = SCREEN_SCENARIOS[screen]
  if (value && allowed.includes(value as PreviewScenario)) return value as PreviewScenario
  return allowed[0]
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: 'center', backgroundColor: '#D8D1C7' },
  phone: { flex: 1, width: '100%', maxWidth: 430, overflow: 'hidden', backgroundColor: colors.bg },
  disabled: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg },
  controls: {
    position: 'absolute',
    left: spacing.sm,
    right: spacing.sm,
    bottom: spacing.sm,
    gap: 5,
    padding: spacing.sm,
    borderRadius: radius.lg,
    backgroundColor: 'rgba(28,27,25,0.92)',
  },
  controlRow: { flexDirection: 'row', gap: 5, justifyContent: 'center', flexWrap: 'wrap' },
  control: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: 'rgba(255,255,255,0.11)' },
  controlActive: { backgroundColor: colors.pastelButter },
  controlText: { color: colors.surface, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  controlTextActive: { color: colors.ink },
})
