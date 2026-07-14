import { useEffect, useMemo, useState } from 'react'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import type { Locale } from '@/api/types'
import { LocaleProvider, useLocale } from '@/i18n'
import { HRHomeView, type HomeState } from '@/features/home/HRHomeView'
import { LeaveApprovalView, type LeaveViewState } from '@/features/leave/LeaveApprovalView'
import { CandidateReviewView, type CandidateViewState } from '@/features/recruiting/CandidateReviewView'
import {
  localizedCandidateFixture,
  localizedLeaveFixture,
  localizedPrioritiesFixture,
  meFixture,
} from '@/preview/fixtures'
import { colors, radius, spacing, type as typography } from '@/theme'

const screens = ['home', 'leave', 'candidate'] as const
const operators = ['hr-only', 'recruiter-only', 'restricted-manager', 'multi-workspace'] as const
const scenarios = ['ready', 'loading', 'empty', 'error', 'revoked', 'company-disabled', 'stale', 'success'] as const
type PreviewScreen = (typeof screens)[number]
type Operator = (typeof operators)[number]
type Scenario = (typeof scenarios)[number]

function valid<T extends readonly string[]>(value: string | string[] | undefined, values: T, fallback: T[number]): T[number] {
  const text = Array.isArray(value) ? value[0] : value
  return values.includes(text as T[number]) ? (text as T[number]) : fallback
}

export default function DesignPreviewRoute() {
  const [mounted, setMounted] = useState(false)
  const params = useLocalSearchParams()
  useEffect(() => setMounted(true), [])
  if (process.env.EXPO_PUBLIC_HR_DESIGN_PREVIEW !== '1') {
    return (
      <View style={styles.disabled}>
        <Text>Preview unavailable.</Text>
      </View>
    )
  }
  if (!mounted) return <View style={styles.disabled} />
  const screen = valid(params.screen, screens, 'home')
  const locale = valid(params.locale, ['en', 'ar'] as const, 'en')
  const scenario = valid(params.scenario, scenarios, 'ready')
  const operator = valid(params.operator, operators, 'multi-workspace')
  const capture = params.capture === '1'
  return (
    <LocaleProvider initialLocale={locale as Locale} persist={false} key={locale}>
      <Preview screen={screen} locale={locale} scenario={scenario} operator={operator} capture={capture} />
    </LocaleProvider>
  )
}

function Preview({
  screen,
  locale,
  scenario,
  operator,
  capture,
}: {
  screen: PreviewScreen
  locale: Locale
  scenario: Scenario
  operator: Operator
  capture: boolean
}) {
  const router = useRouter()
  const { t } = useLocale()
  const params = useMemo(() => ({ screen, locale, scenario, operator, capture: capture ? '1' : '0' }), [screen, locale, scenario, operator, capture])
  const set = (patch: Partial<typeof params>) =>
    router.replace({ pathname: '/design-preview', params: { ...params, ...patch } })

  const controls = capture ? null : (
    <View style={styles.controls}>
      <Text style={styles.previewLabel}>{t('preview.label')}</Text>
      <Control label={t('preview.screen')} values={screens} selected={screen} onSelect={(value) => set({ screen: value })} />
      <Control label={t('preview.locale')} values={['en', 'ar'] as const} selected={locale} onSelect={(value) => set({ locale: value })} />
      <Control label="Operator" values={operators} selected={operator} onSelect={(value) => set({ operator: value })} />
      <Control label={t('preview.scenario')} values={scenarios} selected={scenario} onSelect={(value) => set({ scenario: value })} />
    </View>
  )

  const homeState: HomeState =
    scenario === 'company-disabled'
      ? 'company_disabled'
      : scenario === 'stale' || scenario === 'success'
        ? 'ready'
        : scenario
  const leaveState: LeaveViewState =
    scenario === 'company-disabled' ? 'revoked' : scenario === 'empty' ? 'ready' : scenario
  const candidateState: CandidateViewState =
    scenario === 'company-disabled' ? 'revoked' : scenario === 'empty' ? 'ready' : scenario

  return (
    <View style={styles.root}>
      {controls}
      <View style={styles.phone}>
        {screen === 'home' ? (
          <HRHomeView
            me={meFixture(operator)}
            priorities={localizedPrioritiesFixture(operator, locale)}
            state={homeState}
            onLocale={() => set({ locale: locale === 'ar' ? 'en' : 'ar' })}
          />
        ) : screen === 'leave' ? (
          <LeaveApprovalView
            request={{
              ...localizedLeaveFixture(locale),
              allowed_actions:
                operator === 'recruiter-only' ? [] : localizedLeaveFixture(locale).allowed_actions,
            }}
            state={leaveState}
            company="NORTHSTAR"
            onLocale={() => set({ locale: locale === 'ar' ? 'en' : 'ar' })}
          />
        ) : (
          <CandidateReviewView
            review={{
              ...localizedCandidateFixture(locale),
              allowed_actions:
                operator === 'hr-only' || operator === 'restricted-manager'
                  ? []
                  : localizedCandidateFixture(locale).allowed_actions,
            }}
            state={candidateState}
            company="NORTHSTAR"
            onLocale={() => set({ locale: locale === 'ar' ? 'en' : 'ar' })}
          />
        )}
      </View>
    </View>
  )
}

function Control<T extends readonly string[]>({
  label,
  values,
  selected,
  onSelect,
}: {
  label: string
  values: T
  selected: T[number]
  onSelect: (value: T[number]) => void
}) {
  return (
    <View style={styles.controlGroup}>
      <Text style={styles.controlLabel}>{label}</Text>
      <View style={styles.controlValues}>
        {values.map((value) => (
          <Pressable
            key={value}
            accessibilityRole="button"
            accessibilityLabel={`${value}${value === selected ? ' selected' : ''}`}
            accessibilityState={{ selected: value === selected }}
            onPress={() => onSelect(value)}
            style={[styles.control, value === selected && styles.controlSelected]}
          >
            <Text style={[styles.controlText, value === selected && styles.controlTextSelected]}>{value}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, minHeight: '100%', backgroundColor: '#E9E1D8', alignItems: 'center', padding: spacing.lg, gap: spacing.lg },
  disabled: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.canvas },
  controls: { width: '100%', maxWidth: 900, padding: spacing.lg, backgroundColor: colors.surface, borderRadius: radius.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.line },
  previewLabel: { color: colors.plum, fontSize: typography.label, fontWeight: '900' },
  controlGroup: { gap: spacing.xs },
  controlLabel: { color: colors.muted, fontSize: typography.micro, fontWeight: '800', textTransform: 'uppercase' },
  controlValues: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  control: { minHeight: 36, justifyContent: 'center', paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceStrong, borderWidth: 1, borderColor: colors.line },
  controlSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  controlText: { color: colors.muted, fontSize: typography.micro, fontWeight: '700' },
  controlTextSelected: { color: colors.white },
  phone: { width: '100%', maxWidth: 430, minHeight: 820, overflow: 'hidden', backgroundColor: colors.canvas, borderRadius: 36, borderWidth: 7, borderColor: colors.ink },
})
