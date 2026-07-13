import { useEffect, useState } from 'react'
import { Pressable, SafeAreaView, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'

import { useI18n, type AppLocale } from '@/i18n'
import { ActivationView } from '@/features/activation/ActivationView'
import { HomeView } from '@/features/home/HomeView'
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
} from '@/designPreview'
import { colors, radius, spacing } from '@/theme'

type PreviewScreen = 'activation' | 'home' | 'onboarding'
type PreviewScenario = 'multi' | 'minimal' | 'loading' | 'empty' | 'error'

export default function DesignPreviewScreen() {
  const params = useLocalSearchParams<{
    screen?: string
    locale?: string
    scenario?: string
    capture?: string
  }>()
  const router = useRouter()
  const { locale, setLocale, t } = useI18n()
  const [screen, setScreen] = useState<PreviewScreen>(previewScreen(params.screen))
  const [scenario, setScenario] = useState<PreviewScenario>(previewScenario(params.scenario))
  const [phone, setPhone] = useState('0000 0000')
  const [code, setCode] = useState('123456')
  const capture = params.capture === '1'

  useEffect(() => {
    const requested: AppLocale = params.locale === 'ar' ? 'ar' : 'en'
    if (locale !== requested) void setLocale(requested)
  }, [locale, params.locale, setLocale])

  if (!DESIGN_PREVIEW_ENABLED) {
    return (
      <SafeAreaView style={styles.disabled}>
        <Text>{t('notFound.message')}</Text>
      </SafeAreaView>
    )
  }

  const goHome = () => {
    setScenario('multi')
    setScreen('home')
  }
  const navigate = (path: string) => {
    if (path === '/onboarding') setScreen('onboarding')
  }

  return (
    <View style={styles.root}>
      <View style={styles.phone}>
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

        {screen === 'home' ? (
          <HomeView
            profile={previewProfile(locale)}
            features={scenario === 'minimal' ? minimalFeatures : multiFeatures}
            shift={scenario === 'minimal' || scenario === 'empty' ? undefined : previewShift}
            attendance={scenario === 'minimal' ? undefined : previewAttendance}
            leave={scenario === 'minimal' ? undefined : previewLeave}
            notifications={scenario === 'minimal' || scenario === 'empty' ? emptyNotifications : previewNotifications}
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
        {screen === 'onboarding' && scenario === 'error' ? <OnboardingErrorView onRetry={() => setScenario('multi')} /> : null}
        {screen === 'onboarding' && scenario !== 'loading' && scenario !== 'error' ? (
          <OnboardingView
            data={scenario === 'empty' ? completedOnboarding : previewOnboarding}
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
          locale={locale}
          onScreen={setScreen}
          onScenario={setScenario}
          onLocale={(next) => void setLocale(next)}
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
  onScreen,
  onScenario,
  onLocale,
  onClose,
}: {
  screen: PreviewScreen
  scenario: PreviewScenario
  locale: AppLocale
  onScreen: (value: PreviewScreen) => void
  onScenario: (value: PreviewScenario) => void
  onLocale: (value: AppLocale) => void
  onClose: () => void
}) {
  return (
    <View style={styles.controls}>
      <View style={styles.controlRow}>
        {(['activation', 'home', 'onboarding'] as const).map((value) => (
          <Control key={value} active={screen === value} label={value} onPress={() => onScreen(value)} />
        ))}
      </View>
      <View style={styles.controlRow}>
        {(['multi', 'minimal', 'loading', 'empty', 'error'] as const).map((value) => (
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
    <Pressable onPress={onPress} style={[styles.control, active && styles.controlActive]}>
      <Text style={[styles.controlText, active && styles.controlTextActive]}>{label}</Text>
    </Pressable>
  )
}

function previewScreen(value: string | undefined): PreviewScreen {
  return value === 'home' || value === 'onboarding' ? value : 'activation'
}

function previewScenario(value: string | undefined): PreviewScenario {
  return value === 'minimal' || value === 'loading' || value === 'empty' || value === 'error'
    ? value
    : 'multi'
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
