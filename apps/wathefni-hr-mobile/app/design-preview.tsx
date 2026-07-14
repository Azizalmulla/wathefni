import { useEffect, useMemo, useState } from 'react'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { Pressable, Platform, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

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
import { PreviewEmbedProvider } from '@/preview/PreviewEmbedContext'
import { colors, radius, spacing, type as typography } from '@/theme'

const screens = ['home', 'leave', 'candidate'] as const
const operators = ['hr-only', 'recruiter-only', 'restricted-manager', 'multi-workspace'] as const
const scenarios = ['ready', 'loading', 'empty', 'error', 'revoked', 'company-disabled', 'stale', 'success'] as const
const previewBuild = process.env.EXPO_PUBLIC_HR_PREVIEW_BUILD || 'UNMARKED'
const MOBILE_BREAKPOINT = 768

type PreviewScreen = (typeof screens)[number]
type Operator = (typeof operators)[number]
type Scenario = (typeof scenarios)[number]
type ControlsMode = '0' | '1' | 'auto'

function valid<T extends readonly string[]>(value: string | string[] | undefined, values: T, fallback: T[number]): T[number] {
  const text = Array.isArray(value) ? value[0] : value
  return values.includes(text as T[number]) ? (text as T[number]) : fallback
}

function parseControlsMode(value: string | string[] | undefined): ControlsMode {
  const text = Array.isArray(value) ? value[0] : value
  if (text === '0' || text === 'false' || text === 'hidden') return '0'
  if (text === '1' || text === 'true' || text === 'shown') return '1'
  return 'auto'
}

function readQueryValue(key: string): string | undefined {
  if (typeof window === 'undefined') return undefined
  return new URLSearchParams(window.location.search).get(key) || undefined
}

function resolvePreviewScreen(params: Record<string, string | string[] | undefined>): PreviewScreen {
  // Expo Router reserves `screen` for navigator deep links, so the preview uses `view`.
  // Legacy `?screen=` links are still honored via the raw query string.
  const fromView = Array.isArray(params.view) ? params.view[0] : params.view
  if (fromView) return valid(fromView, screens, 'home')
  return valid(readQueryValue('view') || readQueryValue('screen'), screens, 'home')
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
  const screen = resolvePreviewScreen(params)
  const locale = valid(params.locale, ['en', 'ar'] as const, 'en')
  const scenario = valid(params.scenario, scenarios, 'ready')
  const operator = valid(params.operator, operators, 'multi-workspace')
  const capture = params.capture === '1'
  const controlsMode = parseControlsMode(params.controls)
  return (
    <LocaleProvider initialLocale={locale as Locale} persist={false} key={locale}>
      <Preview
        screen={screen}
        locale={locale}
        scenario={scenario}
        operator={operator}
        capture={capture}
        controlsMode={controlsMode}
      />
    </LocaleProvider>
  )
}

function Preview({
  screen,
  locale,
  scenario,
  operator,
  capture,
  controlsMode,
}: {
  screen: PreviewScreen
  locale: Locale
  scenario: Scenario
  operator: Operator
  capture: boolean
  controlsMode: ControlsMode
}) {
  const router = useRouter()
  const { t } = useLocale()
  const insets = useSafeAreaInsets()
  const { width } = useWindowDimensions()
  const mobile = width < MOBILE_BREAKPOINT
  const controlsAllowed = !capture && controlsMode !== '0'
  const [panelOpen, setPanelOpen] = useState(() => controlsAllowed && (controlsMode === '1' || !mobile))

  useEffect(() => {
    if (!controlsAllowed) {
      setPanelOpen(false)
      return
    }
    if (controlsMode === '1') {
      setPanelOpen(true)
      return
    }
    if (mobile) setPanelOpen(false)
    else setPanelOpen(true)
  }, [controlsAllowed, controlsMode, mobile])

  const params = useMemo(() => {
    const next: Record<string, string> = {
      view: screen,
      locale,
      scenario,
      operator,
      capture: capture ? '1' : '0',
    }
    if (controlsMode !== 'auto') next.controls = controlsMode
    return next
  }, [screen, locale, scenario, operator, capture, controlsMode])

  const set = (patch: Partial<{ view: PreviewScreen; locale: Locale; scenario: Scenario; operator: Operator; capture: string; controls: string }>) =>
    router.replace({ pathname: '/design-preview', params: { ...params, ...patch } })

  const select = (patch: Partial<{ view: PreviewScreen; locale: Locale; scenario: Scenario; operator: Operator }>) => {
    set(patch)
    if (mobile) setPanelOpen(false)
  }

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

  const bottomPad = Math.max(insets.bottom, 16) + 28
  const controlsPanel = (
    <View style={styles.controls} accessibilityLabel="Preview controls">
      <Text style={styles.previewLabel}>{t('preview.label')}</Text>
      <Control label={t('preview.screen')} values={screens} selected={screen} onSelect={(value) => select({ view: value })} />
      <Control label={t('preview.locale')} values={['en', 'ar'] as const} selected={locale} onSelect={(value) => select({ locale: value })} />
      <Control label={t('preview.operator')} values={operators} selected={operator} onSelect={(value) => select({ operator: value })} />
      <Control label={t('preview.scenario')} values={scenarios} selected={scenario} onSelect={(value) => select({ scenario: value })} />
      {mobile ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('preview.closeControls')}
          onPress={() => setPanelOpen(false)}
          style={styles.doneButton}
        >
          <Text style={styles.doneButtonText}>{t('preview.done')}</Text>
        </Pressable>
      ) : null}
    </View>
  )

  return (
    <View style={styles.shell}>
      <View
        accessibilityLabel={`Preview build ${previewBuild}`}
        pointerEvents="none"
        style={styles.buildMarker}
      >
        <Text style={styles.buildMarkerText}>HR2 · {previewBuild}</Text>
      </View>

      <ScrollView
        style={styles.rootScroll}
        contentContainerStyle={[styles.rootContent, { paddingBottom: bottomPad }]}
        showsVerticalScrollIndicator
        keyboardShouldPersistTaps="handled"
        bounces
      >
        {!mobile && controlsAllowed && panelOpen ? controlsPanel : null}

        <View style={styles.phone} accessibilityLabel="App preview">
          <PreviewEmbedProvider>
            {screen === 'home' ? (
              <HRHomeView
                me={meFixture(operator)}
                priorities={localizedPrioritiesFixture(operator, locale)}
                state={homeState}
                onLocale={() => select({ locale: locale === 'ar' ? 'en' : 'ar' })}
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
                onLocale={() => select({ locale: locale === 'ar' ? 'en' : 'ar' })}
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
                onLocale={() => select({ locale: locale === 'ar' ? 'en' : 'ar' })}
              />
            )}
          </PreviewEmbedProvider>
        </View>
      </ScrollView>

      {mobile && controlsAllowed && panelOpen ? (
        <View style={[styles.sheetRoot, webFixedInset]} pointerEvents="box-none">
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('preview.closeControls')}
            onPress={() => setPanelOpen(false)}
            style={styles.sheetBackdrop}
          />
          <View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) + spacing.md }]}>{controlsPanel}</View>
        </View>
      ) : null}

      {controlsAllowed && !panelOpen ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('preview.openControls')}
          onPress={() => setPanelOpen(true)}
          style={[styles.fab, webFixed, { bottom: Math.max(insets.bottom, 12) + 12 }]}
        >
          <Text style={styles.fabText}>{t('preview.controls')}</Text>
        </Pressable>
      ) : null}
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
  shell: {
    flex: 1,
    width: '100%',
    backgroundColor: '#E9E1D8',
    position: 'relative',
  },
  rootScroll: {
    flex: 1,
    width: '100%',
    backgroundColor: '#E9E1D8',
  },
  rootContent: {
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    gap: spacing.lg,
    width: '100%',
    flexGrow: 1,
  },
  buildMarker: {
    position: 'absolute',
    top: spacing.xs,
    right: spacing.sm,
    zIndex: 50,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
  },
  buildMarkerText: { color: colors.white, fontSize: 9, fontWeight: '800' },
  disabled: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.canvas },
  controls: {
    width: '100%',
    maxWidth: 900,
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.line,
  },
  previewLabel: { color: colors.plum, fontSize: typography.label, fontWeight: '900' },
  controlGroup: { gap: spacing.xs },
  controlLabel: { color: colors.muted, fontSize: typography.micro, fontWeight: '800', textTransform: 'uppercase' },
  controlValues: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  control: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceStrong,
    borderWidth: 1,
    borderColor: colors.line,
  },
  controlSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  controlText: { color: colors.muted, fontSize: typography.micro, fontWeight: '700' },
  controlTextSelected: { color: colors.white },
  phone: {
    width: '100%',
    maxWidth: 430,
    backgroundColor: colors.canvas,
    borderRadius: 36,
    borderWidth: 7,
    borderColor: colors.ink,
    alignSelf: 'center',
  },
  fab: {
    position: 'absolute',
    right: spacing.lg,
    zIndex: 30,
    minHeight: 44,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.ink,
  },
  fabText: { color: colors.white, fontSize: typography.label, fontWeight: '800' },
  sheetRoot: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'flex-end',
    zIndex: 40,
  },
  sheetBackdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(28,26,24,0.42)',
  },
  sheet: {
    width: '100%',
    maxHeight: '78%',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    backgroundColor: colors.canvas,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  doneButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: colors.ink,
  },
  doneButtonText: { color: colors.white, fontSize: typography.body, fontWeight: '800' },
})

const webFixed = Platform.OS === 'web' ? ({ position: 'fixed' } as object) : null
const webFixedInset =
  Platform.OS === 'web' ? ({ position: 'fixed', top: 0, right: 0, bottom: 0, left: 0 } as object) : null
