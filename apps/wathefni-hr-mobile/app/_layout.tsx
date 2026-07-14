import { useEffect, useMemo, useState } from 'react'
import { ActivityIndicator, Platform, View } from 'react-native'
import { Stack, useRouter, useSegments } from 'expo-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { StatusBar } from 'expo-status-bar'
import { useFonts } from 'expo-font'
import { Newsreader_600SemiBold } from '@expo-google-fonts/newsreader/600SemiBold'
import { NotoKufiArabic_600SemiBold } from '@expo-google-fonts/noto-kufi-arabic/600SemiBold'

import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { AppErrorBoundary } from '@/components/AppErrorBoundary'
import { Screen, StatePanel } from '@/components/primitives'
import { LocaleProvider, loadInitialLocale, useLocale } from '@/i18n'
import type { Locale } from '@/api/types'
import { colors } from '@/theme'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
})

function AccessGate({ preview }: { preview: boolean }) {
  const { status, accessState, signOut, refreshMe } = useAuth()
  const { t } = useLocale()
  const router = useRouter()
  const segments = useSegments()
  useEffect(() => {
    if (preview || status === 'loading' || status === 'blocked') return
    const signedOutRoute = segments[0] === 'sign-in'
    if (status === 'signedOut' && !signedOutRoute) router.replace('/sign-in')
    if (status === 'signedIn' && signedOutRoute) router.replace('/')
  }, [preview, router, segments, status])

  if (preview) {
    return <Stack screenOptions={{ headerShown: false, animation: 'none' }} />
  }
  if (status === 'loading') {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.canvas }}>
        <ActivityIndicator color={colors.plum} />
      </View>
    )
  }
  if (status === 'blocked') {
    const disabled = accessState === 'company_disabled' || accessState === 'company_archived'
    return (
      <Screen>
        <StatePanel
          title={disabled ? t('state.companyDisabledTitle') : t('state.revokedTitle')}
          body={disabled ? t('state.companyDisabledBody') : t('state.revokedBody')}
          action={disabled ? undefined : t('common.retry')}
          onAction={disabled ? undefined : () => void refreshMe()}
          icon={disabled ? 'business-outline' : 'lock-closed-outline'}
        />
        <StatePanel
          title="Sign out"
          body="Clear this device’s operator session."
          action="Sign out"
          onAction={() => void signOut()}
          icon="log-out-outline"
        />
      </Screen>
    )
  }
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.canvas } }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="sign-in" />
      <Stack.Screen name="leave/[id]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="candidates/[appKey]" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="design-preview" options={{ animation: 'none' }} />
    </Stack>
  )
}

function Runtime({ preview }: { preview: boolean }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider disabled={preview}>
        <StatusBar style="dark" />
        <AccessGate preview={preview} />
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default function RootLayout() {
  const segments = useSegments()
  const preview =
    process.env.EXPO_PUBLIC_HR_DESIGN_PREVIEW === '1' &&
    (segments[0] === 'design-preview' || Platform.OS === 'web')
  const [locale, setLocale] = useState<Locale | null>(preview ? 'en' : null)
  const [fontsLoaded, fontError] = useFonts({
    Newsreader_600SemiBold,
    NotoKufiArabic_600SemiBold,
  })
  useEffect(() => {
    if (preview) {
      setLocale('en')
      if (Platform.OS === 'web' && 'serviceWorker' in navigator) {
        void navigator.serviceWorker.getRegistrations().then((registrations) => {
          registrations.forEach((registration) => void registration.unregister())
        })
      }
      return
    }
    void loadInitialLocale().then(setLocale).catch(() => setLocale('en'))
  }, [preview])
  const ready = useMemo(() => Boolean(locale && (fontsLoaded || fontError)), [fontError, fontsLoaded, locale])
  if (!ready || !locale) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.canvas }}>
        <ActivityIndicator color={colors.plum} />
      </View>
    )
  }
  return (
    <AppErrorBoundary>
      <SafeAreaProvider>
        <LocaleProvider initialLocale={locale}>
          <Runtime preview={preview} />
        </LocaleProvider>
      </SafeAreaProvider>
    </AppErrorBoundary>
  )
}
