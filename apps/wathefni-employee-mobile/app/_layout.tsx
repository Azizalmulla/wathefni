import 'react-native-gesture-handler'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Stack, useRouter, useSegments } from 'expo-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { StatusBar } from 'expo-status-bar'
import { ActivityIndicator, Alert, StyleSheet, View } from 'react-native'
import { useFonts } from 'expo-font'
import { Newsreader_600SemiBold } from '@expo-google-fonts/newsreader/600SemiBold'
import { NotoKufiArabic_600SemiBold } from '@expo-google-fonts/noto-kufi-arabic/600SemiBold'

import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { consumeReplacedDeviceNoticePending } from '@/auth/deviceSecurityNotice'
import { CreatePinFlow } from '@/features/pin/PinFlows'
import { BiometricOptInView } from '@/features/pin/BiometricOptInView'
import { UnlockWithBiometricGate } from '@/features/pin/UnlockWithBiometricGate'
import { LocalUnlockShell } from '@/features/pin/LocalUnlockShell'
import { I18nProvider, loadInitialLocale, useI18n, type AppLocale } from '@/i18n'
import { LoadingState } from '@/components/States'
import { AccessStateScreen } from '@/components/AccessStates'
import { AppErrorBoundary } from '@/components/AppErrorBoundary'
import { PushLifecycle } from '@/push/PushLifecycle'
import { ForegroundQueryRefresh } from '@/lib/refresh'
import { colors } from '@/theme'
import { PIN_MAX_FAILED_ATTEMPTS } from '@/auth/pinPolicy'
import * as Linking from 'expo-linking'
import { hrefFromHttpsAppLink } from '@/linking/httpsAppLink'
import {
  PrincipalBootSplash,
  PrincipalGateProvider,
  PrincipalMountAck,
  usePrincipalGate,
} from '@/principals/PrincipalGate'
import { CompanyBrandProvider } from '@/branding/CompanyBrand'
import {
  canonicalRouteForTarget,
  targetRouteIsMounted,
} from '@/principals/transitionModel'
import {
  principalRouteLabel,
  recordPrincipalDiagnostic,
} from '@/principals/principalDiagnostics'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
})

const principalOverlayStyle = {
  ...StyleSheet.absoluteFillObject,
  position: 'absolute' as const,
  zIndex: 20,
  backgroundColor: colors.bg,
}

function AuthGate() {
  const {
    status,
    accessState,
    refreshMe,
    signOut,
    createLocalPin,
    unlockWithPin,
    unlockWithBiometric,
    recoverPinByReactivation,
    finishBiometricOptIn,
    biometricEnabled,
    biometricKind,
  } = useAuth()
  const gate = usePrincipalGate()
  const { refreshAvailability } = gate
  const { t, syncLayoutLocale } = useI18n()
  const segments = useSegments()
  const router = useRouter()
  const [pinBusy, setPinBusy] = useState(false)
  const [pinError, setPinError] = useState<string | null>(null)
  const [bioBusy, setBioBusy] = useState(false)
  const pendingHttpsHref = useRef<string | null>(null)
  const consumedHttpsHref = useRef<string | null>(null)
  const activePrincipal = gate.pendingTarget || gate.shell?.kind || null
  const employeeActive =
    activePrincipal === 'employee' &&
    !(gate.transition.status === 'switching' && gate.transition.to === 'hr')
  const route = principalRouteLabel(segments)

  useEffect(() => {
    if (status === 'loading') return
    if (typeof syncLayoutLocale === 'function') void syncLayoutLocale()
  }, [status, syncLayoutLocale])

  useEffect(() => {
    if (!employeeActive) return
    if (
      status === 'loading' ||
      status === 'blocked' ||
      status === 'locked' ||
      status === 'needsPinSetup' ||
      status === 'needsBiometricOptIn'
    ) {
      return
    }
    const inAuthGroup = segments[0] === '(auth)'
    if (status === 'signedOut' && !inAuthGroup) {
      router.replace('/(auth)/activate')
    } else if (status === 'signedIn' && inAuthGroup) {
      router.replace('/(tabs)')
    }
  }, [employeeActive, status, segments, router])

  useEffect(() => {
    if (!employeeActive) return
    const capture = (url: string | null) => {
      const href = hrefFromHttpsAppLink(url)
      if (!href || href.startsWith('/hr')) return
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
  }, [employeeActive, status, router])

  useEffect(() => {
    if (!employeeActive) return
    if (status !== 'signedIn' || !pendingHttpsHref.current) return
    const href = pendingHttpsHref.current
    pendingHttpsHref.current = null
    if (consumedHttpsHref.current === href) return
    consumedHttpsHref.current = href
    router.push(href as never)
  }, [employeeActive, status, router])

  useEffect(() => {
    if (!employeeActive) return
    if (status !== 'signedIn') return
    let cancelled = false
    void (async () => {
      const pending = await consumeReplacedDeviceNoticePending()
      if (cancelled || !pending) return
      Alert.alert(t('deviceSecurity.replacedTitle'), t('deviceSecurity.replacedBody'), [
        { text: t('common.close'), style: 'default' },
      ])
    })()
    return () => {
      cancelled = true
    }
  }, [employeeActive, status, t])

  useEffect(() => {
    if (!employeeActive || status !== 'locked') return
    recordPrincipalDiagnostic({
      event: 'lock_gate_rendered',
      target: 'employee',
      route,
      employeeSession: gate.employeeSession,
      hrSession: gate.hrSession,
      lockPrincipal: 'employee',
    })
  }, [employeeActive, gate.employeeSession, gate.hrSession, route, status])

  if (!employeeActive) return null

  if (status === 'loading') {
    return (
      <View style={principalOverlayStyle}>
        <LoadingState />
      </View>
    )
  }

  if (status === 'needsPinSetup') {
    return (
      <View style={principalOverlayStyle} testID="e2e.auth.employee.pinSetup">
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
      <View style={principalOverlayStyle}>
        <BiometricOptInView
          kind={biometricKind}
          busy={bioBusy}
          onEnable={() => {
            void (async () => {
              setBioBusy(true)
              try {
                await finishBiometricOptIn(true, {
                  promptMessage: t('biometric.unlockPrompt'),
                  cancelLabel: t('common.cancel'),
                })
              } finally {
                setBioBusy(false)
              }
            })()
          }}
          onSkip={() => {
            void (async () => {
              setBioBusy(true)
              try {
                await finishBiometricOptIn(false)
              } finally {
                setBioBusy(false)
              }
            })()
          }}
        />
      </View>
    )
  }

  if (status === 'locked') {
    return (
      <View style={principalOverlayStyle} testID="e2e.auth.employee.locked">
        <UnlockWithBiometricGate
          biometricFeatureOn={biometricEnabled}
          busy={pinBusy}
          error={pinError}
          onUnlockBiometric={unlockWithBiometric}
          onForgotPin={() => {
            void recoverPinByReactivation()
          }}
          onUnlockPin={(pin) => {
            void (async () => {
              setPinBusy(true)
              setPinError(null)
              try {
                const result = await unlockWithPin(pin)
                if (!result.ok && !result.lockedOut) {
                  const left = Math.max(0, PIN_MAX_FAILED_ATTEMPTS - result.failedAttempts)
                  setPinError(left > 0 ? t('pin.wrongWithTries', { count: left }) : t('pin.wrong'))
                }
              } finally {
                setPinBusy(false)
              }
            })()
          }}
        />
      </View>
    )
  }

  if (status === 'blocked' && accessState !== 'active') {
    return (
      <View style={principalOverlayStyle}>
        <AccessStateScreen
          state={accessState}
          onRetry={() => void refreshMe()}
          onSignOut={() => void signOut().then(() => refreshAvailability())}
        />
      </View>
    )
  }

  return null
}

function EmployeeBrandBoundary({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  return <CompanyBrandProvider identity={me?.company_identity}>{children}</CompanyBrandProvider>
}

function PrincipalRouteController() {
  const gate = usePrincipalGate()
  const segments = useSegments()
  const segmentList = segments as string[]
  const router = useRouter()
  const route = principalRouteLabel(segments)
  const target = gate.pendingTarget || gate.shell?.kind || null

  useEffect(() => {
    recordPrincipalDiagnostic({
      event: 'route_observed',
      target: target === 'employee' || target === 'hr' ? target : undefined,
      route,
      employeeSession: gate.employeeSession,
      hrSession: gate.hrSession,
    })
  }, [gate.employeeSession, gate.hrSession, route, target])

  useEffect(() => {
    if (!gate.ready || !target) return
    if (target === 'unsigned') {
      if (segmentList.length === 0 || !segmentList[0] || segmentList[0] === 'index') return
      recordPrincipalDiagnostic({
        event: 'route_replace',
        route: '/',
        employeeSession: gate.employeeSession,
        hrSession: gate.hrSession,
      })
      router.replace('/' as never)
      return
    }

    const availability = {
      employeeSession: gate.employeeSession,
      hrSession: gate.hrSession,
    }
    const canonical = canonicalRouteForTarget(target, availability)
    const mounted = targetRouteIsMounted(target, availability, segmentList)
    const transitioning = gate.transition.status === 'switching'
    const wrongPrincipal = target === 'hr' ? segmentList[0] !== 'hr' : segmentList[0] === 'hr'
    const missingSessionRoute =
      target === 'hr'
        ? !gate.hrSession && !(segmentList[0] === 'hr' && segmentList[1] === 'sign-in')
        : !gate.employeeSession && segmentList[0] !== '(auth)'

    if ((transitioning && !mounted) || wrongPrincipal || missingSessionRoute) {
      recordPrincipalDiagnostic({
        event: 'route_replace',
        target,
        route: canonical,
        employeeSession: gate.employeeSession,
        hrSession: gate.hrSession,
      })
      router.replace(canonical as never)
    }
  }, [gate, router, segmentList, target])

  return null
}

function StableRootNavigator() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        title: '',
        headerTitle: '',
        headerBackVisible: false,
        contentStyle: { backgroundColor: colors.bg },
      }}
    >
      <Stack.Screen name="index" options={{ animation: 'none', gestureEnabled: false }} />
      <Stack.Screen name="(auth)" options={{ animation: 'none', gestureEnabled: false }} />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="hr" options={{ animation: 'none', gestureEnabled: false }} />
      <Stack.Screen name="onboarding" options={{ animation: 'fade_from_bottom' }} />
      <Stack.Screen name="bank" />
      <Stack.Screen name="documents" />
      <Stack.Screen name="notifications" />
      <Stack.Screen name="settings" />
      <Stack.Screen name="change-pin" />
      <Stack.Screen name="privacy-support" />
      <Stack.Screen name="leave/request" options={{ presentation: 'modal' }} />
      <Stack.Screen name="leave/history" />
      <Stack.Screen name="schedule/history" />
    </Stack>
  )
}

function EmployeePrincipalMountAck() {
  const { status } = useAuth()
  const gate = usePrincipalGate()
  const segments = useSegments()
  const route = principalRouteLabel(segments)
  const ready =
    status !== 'loading' &&
    targetRouteIsMounted(
      'employee',
      { employeeSession: gate.employeeSession, hrSession: gate.hrSession },
      segments,
    )

  return (
    <PrincipalMountAck
      mode="employee"
      ready={ready}
      route={route}
      lockPrincipal={status === 'locked' ? 'employee' : null}
    />
  )
}

function EmployeeOnlyLifecycle() {
  const gate = usePrincipalGate()
  const active = gate.pendingTarget || gate.shell?.kind
  if (active !== 'employee' || gate.transition.status === 'switching') return null
  return (
    <>
      {/* HR must never register through the Employee /app/push namespace. */}
      <PushLifecycle />
      <ForegroundQueryRefresh />
    </>
  )
}

function StablePrincipalFrame() {
  const gate = usePrincipalGate()
  const { t } = useI18n()

  return (
    <AppErrorBoundary
      title={t('error.fatalTitle')}
      message={t('error.fatalMessage')}
      retryLabel={t('common.retry')}
    >
      <EmployeeBrandBoundary>
        <StatusBar style="dark" />
        <EmployeeOnlyLifecycle />
        <LocalUnlockShell>
          <View style={{ flex: 1, backgroundColor: colors.bg }}>
            <PrincipalRouteController />
            <EmployeePrincipalMountAck />
            <StableRootNavigator />
            <AuthGate />
            {!gate.ready ? (
              <View style={principalOverlayStyle}>
                <PrincipalBootSplash />
              </View>
            ) : null}
          </View>
        </LocalUnlockShell>
      </EmployeeBrandBoundary>
    </AppErrorBoundary>
  )
}

export default function RootLayout() {
  const [locale, setLocale] = useState<AppLocale | null>(null)
  const [fontsLoaded, fontError] = useFonts({
    Newsreader_600SemiBold,
    NotoKufiArabic_600SemiBold,
  })

  useEffect(() => {
    void loadInitialLocale()
      .then(setLocale)
      .catch(() => setLocale('en'))
  }, [])

  if (!locale || (!fontsLoaded && !fontError)) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator testID="e2e.boot.locale-font" color={colors.accent} />
      </View>
    )
  }

  return (
    <SafeAreaProvider>
      <I18nProvider initialLocale={locale}>
        <PrincipalGateProvider>
          <QueryClientProvider client={queryClient}>
            <AuthProvider>
              <StablePrincipalFrame />
            </AuthProvider>
          </QueryClientProvider>
        </PrincipalGateProvider>
      </I18nProvider>
    </SafeAreaProvider>
  )
}
