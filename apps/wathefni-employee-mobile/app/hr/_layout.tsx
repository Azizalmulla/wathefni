import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ActivityIndicator, View } from 'react-native'
import { Stack, useRouter, useSegments } from 'expo-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StatusBar } from 'expo-status-bar'

import { AuthProvider, useAuth } from '@hr/auth/AuthProvider'
import { AppErrorBoundary } from '@hr/components/AppErrorBoundary'
import { Screen, StatePanel } from '@hr/components/primitives'
import { LocaleProvider, loadInitialLocale, useLocale } from '@hr/i18n'
import { HR_BASE } from '@hr/navigation'
import { HRLocalUnlockShell } from '@hr/features/local-lock/HRLocalUnlockShell'
import { HrForegroundQueryRefresh } from '@hr/lib/hrRefresh'
import { CreatePinFlow } from '@/features/pin/PinFlows'
import { BiometricOptInView } from '@/features/pin/BiometricOptInView'
import { UnlockWithBiometricGate } from '@/features/pin/UnlockWithBiometricGate'
import { shouldAttemptHrBiometricUnlock, promptBiometricUnlock } from '@hr/auth/localLock/hrBiometricAuth'
import { PIN_MAX_FAILED_ATTEMPTS } from '@/auth/pinPolicy'
import { PrincipalMountAck, usePrincipalGate } from '@/principals/PrincipalGate'
import { useI18n } from '@/i18n'
import { colors } from '@/theme'
import * as Linking from 'expo-linking'
import { hrefFromHttpsAppLink } from '@/linking/httpsAppLink'
import { CompanyBrandProvider } from '@/branding/CompanyBrand'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 20_000,
      retry: 1,
      // Native focus is delivered by HrForegroundQueryRefresh as an explicit,
      // throttled soft refresh rather than a per-query refetch storm.
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: { retry: false },
  },
})

function AccessGate() {
  const {
    status,
    accessState,
    signOut,
    refreshMe,
    createLocalPin,
    unlockWithPin,
    unlockWithBiometric,
    recoverLocalLockByReauth,
    finishBiometricOptIn,
    biometricEnabled,
    biometricKind,
  } = useAuth()
  const { t } = useLocale()
  const { t: tApp } = useI18n()
  const router = useRouter()
  const segments = useSegments()
  const {
    selectMode,
    employeeSession,
    transition,
    clearTransitionError,
    refreshAvailability,
  } = usePrincipalGate()
  const [pinBusy, setPinBusy] = useState(false)
  const [pinError, setPinError] = useState<string | null>(null)
  const [bioBusy, setBioBusy] = useState(false)
  const pendingHttpsHref = useRef<string | null>(null)
  const consumedHttpsHref = useRef<string | null>(null)

  useEffect(() => {
    if (
      status === 'loading' ||
      status === 'blocked' ||
      status === 'locked' ||
      status === 'needsPinSetup' ||
      status === 'needsBiometricOptIn'
    ) {
      return
    }
    const seg = segments as string[]
    const onSignIn = seg[0] === 'hr' && seg[1] === 'sign-in'
    if (status === 'signedOut' && !onSignIn) router.replace('/hr/sign-in')
    if (status === 'signedIn' && onSignIn) router.replace(HR_BASE)
  }, [router, segments, status])

  useEffect(() => {
    const capture = (url: string | null) => {
      const href = hrefFromHttpsAppLink(url)
      if (!href || !href.startsWith('/hr')) return
      if (status === 'signedIn') {
        if (consumedHttpsHref.current === href) return
        consumedHttpsHref.current = href
        pendingHttpsHref.current = null
        router.push(href as never)
        return
      }
      pendingHttpsHref.current = href
    }
    void Linking.getInitialURL().then(capture)
    const sub = Linking.addEventListener('url', (event) => capture(event.url))
    return () => sub.remove()
  }, [status, router])

  useEffect(() => {
    if (status !== 'signedIn' || !pendingHttpsHref.current) return
    const href = pendingHttpsHref.current
    pendingHttpsHref.current = null
    if (consumedHttpsHref.current === href) return
    consumedHttpsHref.current = href
    router.push(href as never)
  }, [status, router])

  if (status === 'loading') {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg }}>
        <ActivityIndicator color={colors.accent} />
      </View>
    )
  }

  if (status === 'needsPinSetup') {
    return (
      <View style={{ flex: 1 }} testID="e2e.auth.hr.pinSetup">
        <CreatePinFlow
          busy={pinBusy}
          onCreate={async (pin) => {
            setPinBusy(true)
            setPinError(null)
            try {
              await createLocalPin(pin)
            } finally {
              setPinBusy(false)
            }
          }}
        />
      </View>
    )
  }

  if (status === 'needsBiometricOptIn') {
    return (
      <BiometricOptInView
        kind={biometricKind}
        busy={bioBusy}
        onEnable={async () => {
          setBioBusy(true)
          try {
            await finishBiometricOptIn(true, {
              promptMessage: tApp('biometric.unlockPrompt'),
              cancelLabel: tApp('common.cancel'),
            })
          } finally {
            setBioBusy(false)
          }
        }}
        onSkip={async () => {
          setBioBusy(true)
          try {
            await finishBiometricOptIn(false)
          } finally {
            setBioBusy(false)
          }
        }}
      />
    )
  }

  if (status === 'locked') {
    return (
      <View style={{ flex: 1 }} testID="e2e.auth.hr.locked">
        <UnlockWithBiometricGate
          biometricFeatureOn={biometricEnabled}
          busy={pinBusy}
          error={pinError}
          forgotTitleKey="hrPin.forgotTitle"
          forgotConfirmKey="hrPin.forgotConfirm"
          shouldAttempt={shouldAttemptHrBiometricUnlock}
          promptUnlock={promptBiometricUnlock}
          onUnlockPin={(pin) => {
            void (async () => {
              setPinBusy(true)
              setPinError(null)
              try {
                const result = await unlockWithPin(pin)
                if (!result.ok && !result.lockedOut) {
                  const left = Math.max(0, PIN_MAX_FAILED_ATTEMPTS - result.failedAttempts)
                  setPinError(
                    left > 0 ? tApp('pin.wrongWithTries', { count: left }) : tApp('pin.wrong'),
                  )
                }
              } finally {
                setPinBusy(false)
              }
            })()
          }}
          onUnlockBiometric={async () => unlockWithBiometric()}
          onForgotPin={() => {
            void recoverLocalLockByReauth()
          }}
        />
      </View>
    )
  }

  if (status === 'blocked') {
    const companyDisabled = accessState === 'company_disabled'
    const companyArchived = accessState === 'company_archived'
    const sessionExpired = accessState === 'session_expired' || accessState === 'session_revoked'
    const offline = accessState === 'network_error'
    const operatorDisabled = accessState === 'operator_disabled'
    const title = companyDisabled
      ? t('state.companyDisabledTitle')
      : companyArchived
        ? t('state.companyArchivedTitle')
        : sessionExpired
          ? t('state.sessionExpiredTitle')
          : offline
            ? t('state.offlineTitle')
            : t('state.revokedTitle')
    const body = companyDisabled
      ? t('state.companyDisabledBody')
      : companyArchived
        ? t('state.companyArchivedBody')
        : sessionExpired
          ? t('state.sessionExpiredBody')
          : offline
            ? t('state.offlineBody')
            : t('state.revokedBody')
    return (
      <Screen>
        <StatePanel
          title={title}
          body={body}
          action={
            companyDisabled || companyArchived || operatorDisabled
              ? undefined
              : sessionExpired
                ? t('auth.signIn')
                : t('common.retry')
          }
          onAction={sessionExpired ? () => void signOut() : () => void refreshMe()}
          icon={
            companyDisabled
              ? 'business-outline'
              : companyArchived
                ? 'archive-outline'
                : sessionExpired
                  ? 'time-outline'
                  : offline
                    ? 'cloud-offline-outline'
                    : 'lock-closed-outline'
          }
        />
        {employeeSession ? (
          <StatePanel
            title={tApp('principal.switchEmployee')}
            body={
              transition.status === 'error' && transition.to === 'employee'
                ? tApp('principal.transitionError')
                : tApp('principal.employeeSessionAvailable')
            }
            action={
              transition.status === 'switching'
                ? tApp('principal.switchingEmployee')
                : tApp('principal.openEmployee')
            }
            onAction={
              transition.status === 'switching'
                ? undefined
                : () => {
                    clearTransitionError()
                    void selectMode('employee')
                  }
            }
            icon="people-outline"
          />
        ) : null}
        <StatePanel
          title={t('settings.signOut')}
          body={t('state.signOutBody')}
          action={t('settings.signOut')}
          onAction={() => void signOut().then(() => refreshAvailability())}
          icon="log-out-outline"
        />
      </Screen>
    )
  }

  // Auth-only tree: signed-out must not keep authenticated routes in the navigator.
  if (status === 'signedOut') {
    return (
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.bg },
          gestureEnabled: false,
          animation: 'none',
        }}
      >
        <Stack.Screen name="sign-in" options={{ gestureEnabled: false }} />
      </Stack>
    )
  }

  // Tab shell + preserved module/detail routes (no redesign of modules yet).
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="sign-in" />
      <Stack.Screen name="leave/[id]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="candidates/[appKey]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="tasks" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="onboarding/index" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="onboarding/[employeeKey]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="documents/index" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="documents/[employeeKey]/[documentType]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="attendance/index" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="attendance/[attendanceId]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="shifts" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="shift-swaps/[swapId]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="employees/index" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="employees/[employeeKey]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="delivery-alerts" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="assistant" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="candidates/index" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="jobs/index" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="interviews/index" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="interviews/[interviewId]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="settings" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="change-pin" options={{ animation: 'slide_from_right' }} />
    </Stack>
  )
}

function HrRuntime() {
  const [locale, setLocale] = useState<'en' | 'ar' | null>(null)
  useEffect(() => {
    void loadInitialLocale().then(setLocale).catch(() => setLocale('en'))
  }, [])
  if (!locale) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg }}>
        <ActivityIndicator color={colors.accent} />
      </View>
    )
  }
  return (
    <AppErrorBoundary>
      <LocaleProvider initialLocale={locale}>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <PrincipalMountAck mode="hr" />
            <HrBrandBoundary>
              <StatusBar style="dark" />
              <HrForegroundQueryRefresh />
              <HRLocalUnlockShell>
                <AccessGate />
              </HRLocalUnlockShell>
            </HrBrandBoundary>
          </AuthProvider>
        </QueryClientProvider>
      </LocaleProvider>
    </AppErrorBoundary>
  )
}

function HrBrandBoundary({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  return <CompanyBrandProvider identity={me?.company_identity}>{children}</CompanyBrandProvider>
}

export default function HrLayout() {
  return <HrRuntime />
}
