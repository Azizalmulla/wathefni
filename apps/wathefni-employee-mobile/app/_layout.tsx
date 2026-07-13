import { useEffect, useState } from 'react'
import { Stack, useRouter, useSegments } from 'expo-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { StatusBar } from 'expo-status-bar'
import { ActivityIndicator, View } from 'react-native'

import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { I18nProvider, loadInitialLocale, useI18n, type AppLocale } from '@/i18n'
import { LoadingState } from '@/components/States'
import { AccessStateScreen } from '@/components/AccessStates'
import { DESIGN_PREVIEW_ENABLED } from '@/designPreview'
import { colors, font } from '@/theme'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
})

// Routes the user between the auth stack and the app once the session resolves,
// and declares the navigation stack (tabs + pushed detail screens with headers).
function AuthGate() {
  const { status, accessState, refreshMe, signOut } = useAuth()
  const { t } = useI18n()
  const segments = useSegments()
  const router = useRouter()
  const inDesignPreview = DESIGN_PREVIEW_ENABLED && segments[0] === 'design-preview'

  useEffect(() => {
    if (inDesignPreview || status === 'loading' || status === 'blocked') return
    const inAuthGroup = segments[0] === '(auth)'
    if (status === 'signedOut' && !inAuthGroup) {
      router.replace('/(auth)/activate')
    } else if (status === 'signedIn' && inAuthGroup) {
      router.replace('/(tabs)')
    }
  }, [status, segments, router, inDesignPreview])

  if (status === 'loading' && !inDesignPreview) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg }}>
        <LoadingState />
      </View>
    )
  }

  if (status === 'blocked' && accessState !== 'active' && !inDesignPreview) {
    return (
      <AccessStateScreen
        state={accessState}
        onRetry={() => void refreshMe()}
        onSignOut={() => void signOut()}
      />
    )
  }

  const headerStyle = {
    headerStyle: { backgroundColor: colors.bg },
    headerShadowVisible: false,
    headerTintColor: colors.text,
    headerTitleStyle: { color: colors.text, fontWeight: '700' as const, fontSize: font.h3 },
    contentStyle: { backgroundColor: colors.bg },
  }

  return (
    <Stack screenOptions={headerStyle}>
      <Stack.Screen name="(auth)" options={{ headerShown: false }} />
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="design-preview" options={{ headerShown: false }} />
      <Stack.Screen name="onboarding" options={{ headerShown: false }} />
      <Stack.Screen name="documents" options={{ title: t('documents.title') }} />
      <Stack.Screen name="attendance" options={{ title: t('attendance.title') }} />
      <Stack.Screen name="settings" options={{ title: t('settings.title') }} />
      <Stack.Screen name="leave/request" options={{ title: t('leave.request'), presentation: 'modal' }} />
    </Stack>
  )
}

export default function RootLayout() {
  const [locale, setLocale] = useState<AppLocale | null>(null)

  useEffect(() => {
    void loadInitialLocale().then(setLocale)
  }, [])

  if (!locale) {
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
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <StatusBar style="dark" />
            <AuthGate />
          </AuthProvider>
        </QueryClientProvider>
      </I18nProvider>
    </SafeAreaProvider>
  )
}
