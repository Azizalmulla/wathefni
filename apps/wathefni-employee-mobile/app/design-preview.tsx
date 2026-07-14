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
  previewDocuments,
  previewProfile,
  previewShift,
  previewUpcomingShifts,
  rejectedOnboarding,
  reviewOnboarding,
} from '@/designPreview'
import { PreviewErrorBoundary } from '@/components/PreviewErrorBoundary'
import { AccessStateScreen } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import {
  AttendanceView,
  DocumentsView,
  LeaveRequestView,
  LeaveView,
  NotFoundView,
  NotificationsView,
  PrivacySupportView,
  ProfileView,
  SettingsView,
  ShiftsView,
} from '@/features/remaining/RemainingViews'
import type { AppAccessState } from '@/capabilities'
import { colors, radius, spacing } from '@/theme'

type PreviewScreen =
  | 'activation'
  | 'home'
  | 'onboarding'
  | 'inbox'
  | 'leave'
  | 'leave-request'
  | 'shifts'
  | 'attendance'
  | 'documents'
  | 'profile'
  | 'settings'
  | 'privacy-support'
  | 'not-found'
  | 'offline'
  | 'session-expired'
  | 'employee-inactive'
  | 'company-disabled'
  | 'company-archived'
  | 'module-removed'
  | 'app-unavailable'
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
  inbox: ['default', 'empty', 'loading', 'error'],
  leave: ['default', 'minimal', 'empty', 'loading', 'error'],
  'leave-request': ['default', 'error'],
  shifts: ['default', 'empty', 'loading', 'error'],
  attendance: ['default', 'empty', 'loading', 'error'],
  documents: ['default', 'empty', 'loading', 'error'],
  profile: ['default'],
  settings: ['default', 'minimal'],
  'privacy-support': ['default'],
  'not-found': ['default'],
  offline: ['default'],
  'session-expired': ['default'],
  'employee-inactive': ['default'],
  'company-disabled': ['default'],
  'company-archived': ['default'],
  'module-removed': ['default'],
  'app-unavailable': ['default'],
}

const PREVIEW_SCREENS = Object.keys(SCREEN_SCENARIOS) as PreviewScreen[]

export default function DesignPreviewScreen() {
  return (
    <PreviewErrorBoundary label="Design preview">
      <DesignPreviewBody />
    </PreviewErrorBoundary>
  )
}

function DesignPreviewBody() {
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

  // One-shot address-bar cleanup from window.location. Do not call router.replace
  // here — Expo Router remounts the screen on Safari and can loop into a blank tree.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    if (!url.pathname.includes('design-preview')) return
    const rawScreen = url.searchParams.get('screen') ?? undefined
    const rawLocale = url.searchParams.get('locale') ?? undefined
    const rawScenario = url.searchParams.get('scenario') ?? undefined
    const rawCapture = url.searchParams.get('capture')
    const nextScreen = previewScreen(rawScreen)
    const nextLocale = previewLocaleFromParam(rawLocale)
    const nextScenario = coerceScenario(nextScreen, rawScenario)
    const nextCapture = rawCapture === '1'
    const needsNormalize =
      rawScreen !== nextScreen
      || rawLocale !== nextLocale
      || rawScenario !== nextScenario
      || (nextCapture ? rawCapture !== '1' : Boolean(rawCapture))
    if (!needsNormalize) return
    const next = previewQuery({
      screen: nextScreen,
      locale: nextLocale,
      scenario: nextScenario,
      capture: nextCapture,
    })
    window.history.replaceState(window.history.state, '', `${url.pathname}?${next}`)
  }, [])

  const updatePreview = (patch: {
    screen?: PreviewScreen
    locale?: AppLocale
    scenario?: PreviewScenario
  }) => {
    const nextScreen = patch.screen ?? screen
    const nextLocale = patch.locale ?? previewLocale
    const nextScenario = coerceScenario(nextScreen, patch.scenario ?? scenario)
    // User-driven updates only. Do not call setParams from a normalize effect —
    // that remount loop is what blanked Safari after the first paint.
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
        <PreviewSurface
          screen={screen}
          scenario={scenario}
          locale={previewLocale}
          phone={phone}
          code={code}
          onPhone={setPhone}
          onCode={setCode}
          onHome={goHome}
          onNavigate={navigate}
          onScenario={(next) => updatePreview({ scenario: next })}
        />
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

function PreviewSurface({
  screen,
  scenario,
  locale,
  phone,
  code,
  onPhone,
  onCode,
  onHome,
  onNavigate,
  onScenario,
}: {
  screen: PreviewScreen
  scenario: PreviewScenario
  locale: AppLocale
  phone: string
  code: string
  onPhone: (value: string) => void
  onCode: (value: string) => void
  onHome: () => void
  onNavigate: (path: string) => void
  onScenario: (value: PreviewScenario) => void
}) {
  const { t } = useI18n()
  const retry = () => onScenario(SCREEN_SCENARIOS[screen][0])
  const noop = () => undefined
  const localizedNotifications = {
    ...previewNotifications,
    notifications: previewNotifications.notifications.map((item, index) => ({
      ...item,
      title:
        locale === 'ar'
          ? ['تحديث على السياسات', 'تمت الموافقة على طلب الإجازة', 'مرحباً بك في تطبيق الموظف'][index]
          : item.title,
      body:
        locale === 'ar'
          ? ['راجع آخر تحديثات فريق الموارد البشرية.', 'تمت الموافقة على إجازتك السنوية.', 'ملفك وأدوات العمل جاهزة.'][index]
          : item.body,
    })),
  }
  const localizedShift = {
    ...previewShift,
    role: locale === 'ar' ? 'تجربة العملاء' : 'Customer experience',
    location: locale === 'ar' ? 'مدينة الكويت' : 'Kuwait City',
  }
  const localizedUpcoming = previewUpcomingShifts.map((shift) => ({
    ...shift,
    role: locale === 'ar' ? 'تجربة العملاء' : shift.role,
    location: locale === 'ar' ? 'مدينة الكويت' : shift.location,
  }))
  const localizedDocuments = previewDocuments.map((document, index) => ({
    ...document,
    label: locale === 'ar' ? (index ? 'البطاقة المدنية' : 'عقد العمل') : document.label,
  }))
  const localizedLeave = {
    ...previewLeave,
    requests: previewLeave.requests.map((request, index) => ({
      ...request,
      reason: locale === 'ar' && request.reason ? (index ? 'موعد طبي' : 'خطط عائلية') : request.reason,
    })),
  }

  if (screen === 'activation') {
    return (
      <ActivationView
        phone={phone}
        code={code}
        busy={scenario === 'loading'}
        error={scenario === 'error' ? t('auth.invalidCode') : null}
        notice={null}
        onPhoneChange={onPhone}
        onCodeChange={onCode}
        onSignIn={onHome}
        onRequestCode={noop}
      />
    )
  }
  if (screen === 'home') {
    if (scenario === 'loading') return <HomeLoadingView />
    if (scenario === 'error') return <HomeErrorView onRetry={retry} />
    return (
      <HomeView
        profile={previewProfile(locale)}
        features={scenario === 'minimal' ? minimalFeatures : multiFeatures}
        shift={scenario === 'minimal' || scenario === 'empty' ? undefined : localizedShift}
        attendance={scenario === 'minimal' ? undefined : previewAttendance}
        leave={scenario === 'minimal' ? undefined : localizedLeave}
        notifications={scenario === 'minimal' || scenario === 'empty' ? emptyNotifications : localizedNotifications}
        onboarding={scenario === 'minimal' ? undefined : scenario === 'empty' ? completedOnboarding : previewOnboarding}
        canRequestLeave={scenario !== 'minimal'}
        onNavigate={onNavigate}
      />
    )
  }
  if (screen === 'onboarding') {
    if (scenario === 'loading') return <OnboardingLoadingView />
    if (scenario === 'error') return <OnboardingErrorView onRetry={retry} />
    return (
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
        onUpload={noop}
        onBack={onHome}
      />
    )
  }

  if (scenario === 'loading') return <LoadingState />
  if (scenario === 'error') return <ErrorState message={t('error.generic')} onRetry={retry} />

  if (screen === 'inbox') {
    return <NotificationsView data={scenario === 'empty' ? emptyNotifications : localizedNotifications} onMarkRead={noop} />
  }
  if (screen === 'leave') {
    const data = scenario === 'empty'
      ? { ...localizedLeave, balances: [], requests: [] }
      : scenario === 'minimal'
        ? { ...localizedLeave, balances_enabled: false, balances: [], requests: localizedLeave.requests.slice(0, 1) }
        : localizedLeave
    return <LeaveView data={data} canRequest={scenario !== 'minimal'} canCancel={scenario !== 'minimal'} onRequest={noop} onCancel={noop} />
  }
  if (screen === 'leave-request') {
    return <LeaveRequestView leaveTypes={previewLeave.types} busy={false} error={null} onSubmit={noop} onBack={onHome} />
  }
  if (screen === 'shifts') {
    return <ShiftsView today={scenario === 'empty' ? [] : [localizedShift]} upcoming={scenario === 'empty' ? [] : localizedUpcoming} />
  }
  if (screen === 'attendance') {
    return (
      <AttendanceView
        data={scenario === 'empty' ? { ...previewAttendance, summary: { present: 0, late: 0, absent: 0 }, records: [] } : previewAttendance}
      />
    )
  }
  if (screen === 'documents') {
    return <DocumentsView documents={scenario === 'empty' ? [] : localizedDocuments} openingId={null} onOpen={noop} />
  }
  if (screen === 'profile') {
    return <ProfileView profile={previewProfile(locale)} onSettings={noop} onPrivacySupport={noop} onSignOut={noop} />
  }
  if (screen === 'settings') {
    return (
      <SettingsView
        locale={locale}
        pushOn
        pushBusy={false}
        canManagePush={scenario !== 'minimal'}
        version="0.1.0"
        onLocale={noop}
        onTogglePush={noop}
        onPrivacySupport={noop}
        onDelete={noop}
      />
    )
  }
  if (screen === 'privacy-support') {
    return <PrivacySupportView onPrivacy={noop} onSupport={noop} onBack={onHome} />
  }
  if (screen === 'not-found') {
    return <NotFoundView onHome={onHome} />
  }

  return (
    <AccessStateScreen
      state={accessStateForPreview(screen)}
      onRetry={noop}
      onSignOut={noop}
    />
  )
}

function accessStateForPreview(screen: PreviewScreen): Exclude<AppAccessState, 'active'> {
  const map: Partial<Record<PreviewScreen, Exclude<AppAccessState, 'active'>>> = {
    offline: 'offline',
    'session-expired': 'session_expired',
    'employee-inactive': 'employee_inactive',
    'company-disabled': 'company_disabled',
    'company-archived': 'company_archived',
    'module-removed': 'company_app_disabled',
    'app-unavailable': 'app_disabled',
  }
  return map[screen] ?? 'unknown_error'
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
  const currentIndex = PREVIEW_SCREENS.indexOf(screen)
  const previous = PREVIEW_SCREENS[(currentIndex - 1 + PREVIEW_SCREENS.length) % PREVIEW_SCREENS.length]
  const next = PREVIEW_SCREENS[(currentIndex + 1) % PREVIEW_SCREENS.length]
  return (
    <View style={styles.controls} accessibilityLabel="preview-controls">
      <View style={styles.controlRow}>
        {(['activation', 'home', 'onboarding'] as const).map((value) => (
          <Control key={value} active={screen === value} label={value} onPress={() => onScreen(value)} />
        ))}
        <Control active={false} label="‹" onPress={() => onScreen(previous)} />
        <Text style={styles.currentScreen}>{screen}</Text>
        <Control active={false} label="›" onPress={() => onScreen(next)} />
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
  return value && PREVIEW_SCREENS.includes(value as PreviewScreen) ? value as PreviewScreen : 'activation'
}

function previewLocaleFromParam(value: string | undefined): AppLocale {
  return value === 'ar' ? 'ar' : 'en'
}

function coerceScenario(screen: PreviewScreen, value: string | undefined): PreviewScenario {
  const allowed = SCREEN_SCENARIOS[screen]
  if (value && allowed.includes(value as PreviewScenario)) return value as PreviewScenario
  return allowed[0]
}

function previewQuery({
  screen,
  locale,
  scenario,
  capture,
}: {
  screen: PreviewScreen
  locale: AppLocale
  scenario: PreviewScenario
  capture: boolean
}): string {
  const params = new URLSearchParams({ screen, locale, scenario })
  if (capture) params.set('capture', '1')
  return params.toString()
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: 'center', backgroundColor: '#D8D1C7' },
  // Avoid overflow:'hidden' + animated transforms: iOS Safari can composite that into a blank layer.
  phone: { flex: 1, width: '100%', maxWidth: 430, backgroundColor: colors.bg },
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
  currentScreen: { color: colors.pastelButter, fontSize: 10, fontWeight: '800', paddingHorizontal: 5, alignSelf: 'center' },
})
