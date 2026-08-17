import 'react-native-gesture-handler'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Redirect, Slot, Stack, useRouter, useSegments } from 'expo-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { StatusBar } from 'expo-status-bar'
import { ActivityIndicator, Alert, View } from 'react-native'
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
import { UnsignedEntry } from '@/principals/UnifiedSignInView'
import { CompanyBrandProvider } from '@/branding/CompanyBrand'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
})

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
  const { refreshAvailability } = usePrincipalGate()
  const { t, syncLayoutLocale } = useI18n()
  const segments = useSegments()
  const router = useRouter()
  const [pinBusy, setPinBusy] = useState(false)
  const [pinError, setPinError] = useState<string | null>(null)
  const [bioBusy, setBioBusy] = useState(false)
  const pendingHttpsHref = useRef<string | null>(null)
  const consumedHttpsHref = useRef<string | null>(null)

  useEffect(() => {
    if (status === 'loading') return
    if (typeof syncLayoutLocale === 'function') void syncLayoutLocale()
  }, [status, syncLayoutLocale])

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
    // Employee principal must never host HR routes — hard redirect (no silent skip).
    if (segments[0] === 'hr') {
      router.replace('/(tabs)')
      return
    }
    const inAuthGroup = segments[0] === '(auth)'
    if (status === 'signedOut' && !inAuthGroup) {
      router.replace('/(auth)/activate')
    } else if (status === 'signedIn' && inAuthGroup) {
      router.replace('/(tabs)')
    }
  }, [status, segments, router])

  useEffect(() => {
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
  }, [status, router])

  useEffect(() => {
    if (status !== 'signedIn' || !pendingHttpsHref.current) return
    const href = pendingHttpsHref.current
    pendingHttpsHref.current = null
    if (consumedHttpsHref.current === href) return
    consumedHttpsHref.current = href
    router.push(href as never)
  }, [status, router])

  useEffect(() => {
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
  }, [status, t])

  if (status === 'loading') {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg }}>
        <LoadingState />
      </View>
    )
  }

  if (status === 'needsPinSetup') {
    return (
      <View style={{ flex: 1 }} testID="e2e.auth.employee.pinSetup">
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
    )
  }

  if (status === 'locked') {
    return (
      <View style={{ flex: 1 }} testID="e2e.auth.employee.locked">
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
      <AccessStateScreen
        state={accessState}
        onRetry={() => void refreshMe()}
        onSignOut={() => void signOut().then(() => refreshAvailability())}
      />
    )
  }

  // Auth-only tree: signed-out must not keep authenticated routes in the navigator.
  if (status === 'signedOut') {
    return (
      <Stack
        screenOptions={{
          headerShown: false,
          title: '',
          headerTitle: '',
          headerBackVisible: false,
          contentStyle: { backgroundColor: colors.bg },
          gestureEnabled: false,
          animation: 'none',
        }}
      >
        <Stack.Screen name="(auth)" options={{ headerShown: false, gestureEnabled: false }} />
      </Stack>
    )
  }

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
      <Stack.Screen name="(auth)" options={{ headerShown: false }} />
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="onboarding" options={{ headerShown: false, animation: 'fade_from_bottom' }} />
      <Stack.Screen name="bank" options={{ headerShown: false }} />
      <Stack.Screen name="documents" options={{ headerShown: false }} />
      <Stack.Screen name="notifications" options={{ headerShown: false }} />
      <Stack.Screen name="settings" options={{ headerShown: false }} />
      <Stack.Screen name="change-pin" options={{ headerShown: false }} />
      <Stack.Screen name="privacy-support" options={{ headerShown: false }} />
      <Stack.Screen name="leave/request" options={{ headerShown: false, presentation: 'modal' }} />
      <Stack.Screen name="leave/history" options={{ headerShown: false }} />
      <Stack.Screen name="schedule/history" options={{ headerShown: false }} />
      {/* HR routes mount only under shell.kind === 'hr' via ModeRedirect Slot — never here. */}
    </Stack>
  )
}

function EmployeeShell() {
  const { t } = useI18n()
  return (
    <AppErrorBoundary title={t('error.fatalTitle')} message={t('error.fatalMessage')} retryLabel={t('common.retry')}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <PrincipalMountAck mode="employee" />
          <EmployeeBrandBoundary>
            <StatusBar style="dark" />
            {/* HR must not register on /app/push — PushLifecycle stays employee-only. */}
            <PushLifecycle />
            <ForegroundQueryRefresh />
            <LocalUnlockShell>
              <AuthGate />
            </LocalUnlockShell>
          </EmployeeBrandBoundary>
        </AuthProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  )
}

function EmployeeBrandBoundary({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  return <CompanyBrandProvider identity={me?.company_identity}>{children}</CompanyBrandProvider>
}

function ModeRedirect() {
  const { ready, shell, employeeSession, transition } = usePrincipalGate()
  const segments = useSegments()

  if (!ready || !shell) return <PrincipalBootSplash />

  // A principal transition owns the whole frame. Keep the outgoing principal
  // unmounted, drive the target route declaratively, then mount only the target
  // provider. PrincipalMountAck ends the transition after that provider exists.
  if (transition.status === 'switching') {
    if (shell.kind !== transition.to) return <PrincipalBootSplash />

    if (transition.to === 'hr') {
      if (segments[0] !== 'hr') {
        return (
          <>
            <Redirect href="/hr" />
            <PrincipalBootSplash />
          </>
        )
      }
      return <Slot />
    }

    const employeeHref = employeeSession ? '/(tabs)' : '/(auth)/activate'
    const employeeRouteReady = employeeSession
      ? segments[0] === '(tabs)'
      : segments[0] === '(auth)'
    if (!employeeRouteReady) {
      return (
        <>
          <Redirect href={employeeHref} />
          <PrincipalBootSplash />
        </>
      )
    }
    return <EmployeeShell />
  }

  // No startup principal chooser. Workspace comes from authenticated sessions.
  if (shell.kind === 'unsigned') {
    return <UnsignedEntry />
  }

  if (shell.kind === 'hr') {
    // Post Work-email auth the URL is often still `/` because UnsignedEntry has no
    // navigator. Mounting a root Stack on that URL focuses Employee `(tabs)` /
    // `+not-found` without Employee AuthProvider → fatal:
    //   Error: useAuth must be used within AuthProvider
    //   at TabsLayout (app/(tabs)/_layout.tsx)
    // Guard: never Slot until the route is already under /hr.
    if (segments[0] !== 'hr') {
      return (
        <>
          <Redirect href="/hr" />
          <PrincipalBootSplash />
        </>
      )
    }
    return <Slot />
  }

  // Employee principal: synchronous hard-deny of /hr/* (no async race, no flag skip).
  if (segments[0] === 'hr') {
    return (
      <>
        <Redirect href="/(tabs)" />
        <PrincipalBootSplash />
      </>
    )
  }

  return <EmployeeShell />
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
          <ModeRedirect />
        </PrincipalGateProvider>
      </I18nProvider>
    </SafeAreaProvider>
  )
}
