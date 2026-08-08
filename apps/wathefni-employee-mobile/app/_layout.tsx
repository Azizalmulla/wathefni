import { useEffect, useState } from 'react'
import { Stack, useRouter, useSegments } from 'expo-router'
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

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
})

// Routes the user between the auth stack and the app once the session resolves,
// and declares the navigation stack (tabs + pushed detail screens with headers).
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
  const { t, syncLayoutLocale } = useI18n()
  const segments = useSegments()
  const router = useRouter()
  const [pinBusy, setPinBusy] = useState(false)
  const [pinError, setPinError] = useState<string | null>(null)
  const [bioBusy, setBioBusy] = useState(false)

  // Keep EN=LTR / AR=RTL aligned on every auth transition (login, logout, blocked).
  useEffect(() => {
    if (status === 'loading') return
    // Guard: older OTA bases without syncLayoutLocale must not fatal the app.
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
    const inAuthGroup = segments[0] === '(auth)'
    if (status === 'signedOut' && !inAuthGroup) {
      router.replace('/(auth)/activate')
    } else if (status === 'signedIn' && inAuthGroup) {
      router.replace('/(tabs)')
    }
  }, [status, segments, router])

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
    )
  }

  if (status === 'blocked' && accessState !== 'active') {
    return (
      <AccessStateScreen
        state={accessState}
        onRetry={() => void refreshMe()}
        onSignOut={() => void signOut()}
      />
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
    </Stack>
  )
}

function RuntimeProviders() {
  const { t } = useI18n()
  return (
    <AppErrorBoundary title={t('error.fatalTitle')} message={t('error.fatalMessage')} retryLabel={t('common.retry')}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StatusBar style="dark" />
          <PushLifecycle />
          <ForegroundQueryRefresh />
          <LocalUnlockShell>
            <AuthGate />
          </LocalUnlockShell>
        </AuthProvider>
      </QueryClientProvider>
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
    // Pre-i18n: must not use any component that calls useI18n yet.
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={colors.accent} />
      </View>
    )
  }

  return (
    <SafeAreaProvider>
      <I18nProvider initialLocale={locale}>
        <RuntimeProviders />
      </I18nProvider>
    </SafeAreaProvider>
  )
}
