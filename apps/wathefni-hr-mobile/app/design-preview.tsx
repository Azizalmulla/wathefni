import { useEffect, useMemo, useState } from 'react'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { Pressable, Platform, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import type { Locale } from '@/api/types'
import { LocaleProvider, useLocale } from '@/i18n'
import { HRHomeView, type HomeState } from '@/features/home/HRHomeView'
import { LeaveApprovalView, type LeaveViewState } from '@/features/leave/LeaveApprovalView'
import { CandidateReviewView, type CandidateViewState } from '@/features/recruiting/CandidateReviewView'
import { SignInView } from '@/features/auth/SignInView'
import {
  OperationalDetailView,
  OperationalListView,
} from '@/features/operations/OperationalViews'
import { SettingsView } from '@/features/settings/SettingsView'
import {
  localizedCandidateFixture,
  localizedLeaveFixture,
  localizedPrioritiesFixture,
  meFixture,
  operationalFixture,
} from '@/preview/fixtures'
import { PreviewEmbedProvider } from '@/preview/PreviewEmbedContext'
import {
  previewOperators as operators,
  previewScenarios as scenarios,
  previewViews as screens,
} from '@/preview/inventory'
import { routeAvailable } from '@/capabilities'
import { colors, radius, spacing, type as typography } from '@/theme'

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
  if (process.env.EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE === '1') {
    return (
      <View style={styles.disabled}>
        <Text>Preview unavailable.</Text>
      </View>
    )
  }
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
  const [markerVisible, setMarkerVisible] = useState(true)

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

  useEffect(() => {
    if (capture) return
    const timer = setTimeout(() => setMarkerVisible(false), 4200)
    return () => clearTimeout(timer)
  }, [capture])

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
      : scenario === 'company-archived'
        ? 'company_archived'
        : scenario === 'session-expired'
          ? 'session_expired'
        : scenario
  const leaveState: LeaveViewState =
    scenario === 'company-disabled'
      ? 'company_disabled'
      : scenario === 'company-archived'
        ? 'company_archived'
        : scenario === 'session-expired'
          ? 'session_expired'
          : scenario === 'empty'
            ? 'ready'
            : scenario
  const candidateState: CandidateViewState =
    scenario === 'company-disabled'
      ? 'company_disabled'
      : scenario === 'company-archived'
        ? 'company_archived'
        : scenario === 'session-expired'
          ? 'session_expired'
          : scenario === 'empty'
            ? 'ready'
            : scenario
  const operationalRouteKey =
    screen === 'delivery-alerts'
      ? 'deliveryAlerts'
      : screen === 'shift-swap'
        ? 'shifts'
        : screen === 'employee-profile'
          ? 'employees'
          : screen === 'interview'
            ? 'interviews'
            : screen
  const operatorHasRoute =
    screen === 'settings' ||
    screen === 'sign-in' ||
    !['tasks', 'onboarding', 'documents', 'attendance', 'shifts', 'shift-swap', 'employees', 'employee-profile', 'delivery-alerts', 'candidates', 'interviews', 'interview'].includes(screen) ||
    routeAvailable(meFixture(operator), operationalRouteKey)
  const operationalState =
    !operatorHasRoute
      ? 'permission'
      :
    scenario === 'company-disabled'
      ? 'company_disabled'
      : scenario === 'company-archived'
        ? 'company_archived'
        : scenario === 'session-expired'
          ? 'session_expired'
          : scenario

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
      {markerVisible ? (
        <View
          accessibilityLabel={`Preview build ${previewBuild}`}
          pointerEvents="none"
          style={styles.buildMarker}
        >
          <Text style={styles.buildMarkerText}>HR3 · {previewBuild}</Text>
        </View>
      ) : null}

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
            {screen === 'sign-in' ? (
              <SignInView onSignIn={async () => undefined} />
            ) : screen === 'home' ? (
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
            ) : screen === 'candidate' ? (
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
            ) : screen === 'settings' ? (
              <SettingsView
                me={meFixture(operator)}
                onLocale={() => select({ locale: locale === 'ar' ? 'en' : 'ar' })}
                onRefresh={() => undefined}
                onSignOut={() => undefined}
                onSignOutAll={() => undefined}
              />
            ) : screen === 'shift-swap' ? (
              <OperationalDetailView
                company="NORTHSTAR"
                eyebrow={locale === 'ar' ? 'قرار التبديل' : 'Swap decision'}
                title={locale === 'ar' ? 'دلال العوضي' : 'Dalal Al-Awadi'}
                status={locale === 'ar' ? 'بانتظار القرار' : 'requested'}
                state={operationalState}
                facts={[
                  { label: locale === 'ar' ? 'الموظف البديل' : 'Replacement', value: locale === 'ar' ? 'يوسف الغانم' : 'Yousef Al-Ghanem' },
                  { label: locale === 'ar' ? 'التاريخ' : 'Date', value: locale === 'ar' ? '١٧ يوليو ٢٠٢٦' : '17 July 2026' },
                  { label: locale === 'ar' ? 'السبب' : 'Reason', value: locale === 'ar' ? 'تعارض مع موعد طبي' : 'Medical appointment conflict' },
                ]}
                actions={[
                  { key: 'approve', label: locale === 'ar' ? 'موافقة' : 'Approve' },
                  { key: 'reject', label: locale === 'ar' ? 'رفض' : 'Reject', tone: 'danger' },
                ]}
                onLocale={() => select({ locale: locale === 'ar' ? 'en' : 'ar' })}
              />
            ) : screen === 'employee-profile' ? (
              <OperationalDetailView
                company="NORTHSTAR"
                eyebrow={locale === 'ar' ? 'ملف مختصر' : 'Quick profile'}
                title={locale === 'ar' ? 'سارة الكندري' : 'Sara Al-Kandari'}
                status={locale === 'ar' ? 'نشطة' : 'active'}
                state={operationalState}
                facts={[
                  { label: locale === 'ar' ? 'المسمى الوظيفي' : 'Position', value: locale === 'ar' ? 'مديرة عمليات' : 'Operations Manager' },
                  { label: locale === 'ar' ? 'القسم' : 'Department', value: locale === 'ar' ? 'العمليات' : 'Operations' },
                  { label: locale === 'ar' ? 'تاريخ البدء' : 'Start date', value: locale === 'ar' ? '١ فبراير ٢٠٢٤' : '1 February 2024' },
                ]}
                onLocale={() => select({ locale: locale === 'ar' ? 'en' : 'ar' })}
              />
            ) : screen === 'interview' ? (
              <OperationalDetailView
                company="NORTHSTAR"
                eyebrow={locale === 'ar' ? 'سجل المقابلة' : 'Interview record'}
                title={locale === 'ar' ? 'لينا الخالد' : 'Lina Al-Khaled'}
                status={locale === 'ar' ? 'المقابلة' : 'Interview'}
                state={operationalState}
                facts={[
                  { label: locale === 'ar' ? 'مرحلة الطلب' : 'Application stage', value: locale === 'ar' ? 'المقابلة' : 'Interview' },
                  { label: locale === 'ar' ? 'حالة المقابلة' : 'Interview status', value: locale === 'ar' ? 'مجدولة' : 'Scheduled' },
                  { label: locale === 'ar' ? 'الموعد' : 'Scheduled', value: locale === 'ar' ? '١٦ يوليو ٢٠٢٦، ١٠:٣٠ ص' : '16 July 2026, 10:30 am' },
                  { label: locale === 'ar' ? 'القناة أو الموقع' : 'Channel or location', value: 'Google Meet' },
                  { label: locale === 'ar' ? 'حالة الدعوة' : 'Invitation status', value: locale === 'ar' ? 'تم الإرسال' : 'Sent' },
                  { label: locale === 'ar' ? 'تأكيد المرشح' : 'Candidate confirmation', value: locale === 'ar' ? 'لم يتم التأكيد' : 'Not confirmed' },
                  { label: locale === 'ar' ? 'حالة الملاحظات' : 'Notes status', value: locale === 'ar' ? 'قيد الانتظار' : 'Pending' },
                  { label: locale === 'ar' ? 'ملاحظات المقابلة' : 'Interview notes', value: locale === 'ar' ? 'تفكير قوي في الأنظمة؛ يلزم التحقق من أمثلة القيادة.' : 'Strong systems thinking; validate leadership examples.' },
                  { label: locale === 'ar' ? 'تحليل وظفني — استشاري فقط' : 'Wathefni analysis — advisory only', value: locale === 'ar' ? 'أظهرت الأدلة تفكيراً قوياً في الأنظمة، مع ضرورة التحقق من أمثلة القيادة.' : 'Evidence indicates strong systems thinking; leadership examples still require human verification.' },
                  { label: locale === 'ar' ? 'الإجراء البشري المطلوب التالي' : 'Next required human action', value: locale === 'ar' ? 'تسجيل ملاحظات المقابلة' : 'Record interview notes' },
                ]}
                onLocale={() => select({ locale: locale === 'ar' ? 'en' : 'ar' })}
              />
            ) : (
              <OperationalListView
                company="NORTHSTAR"
                eyebrow={previewCopy(screen, locale).eyebrow}
                title={previewCopy(screen, locale).title}
                items={operationalFixture(screen, locale)}
                state={operationalState}
                onOpen={() => undefined}
                onRetry={() => undefined}
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

function previewCopy(screen: PreviewScreen, locale: Locale): { eyebrow: string; title: string } {
  const ar = locale === 'ar'
  const copy: Partial<Record<PreviewScreen, { eyebrow: string; title: string }>> = {
    tasks: {
      eyebrow: ar ? 'قائمة العمليات' : 'Operational queue',
      title: ar ? 'مهام الموارد البشرية' : 'HR tasks',
    },
    onboarding: {
      eyebrow: ar ? 'الموظفون الجدد' : 'New starters',
      title: ar ? 'مراجعة التهيئة الوظيفية' : 'Onboarding review',
    },
    documents: {
      eyebrow: ar ? 'مراجعة الامتثال' : 'Compliance review',
      title: ar ? 'مراجعة المستندات' : 'Document reviews',
    },
    attendance: {
      eyebrow: ar ? 'ضبط الحضور' : 'Attendance control',
      title: ar ? 'استثناءات تحتاج إلى معالجة' : 'Exceptions to resolve',
    },
    shifts: {
      eyebrow: ar ? 'جدول القوى العاملة' : 'Workforce schedule',
      title: ar ? 'مناوبات اليوم وطلبات التبديل' : 'Today’s shifts and swaps',
    },
    employees: {
      eyebrow: ar ? 'الدليل المصرّح' : 'Authorized directory',
      title: ar ? 'الموظفون' : 'Employees',
    },
    'delivery-alerts': {
      eyebrow: ar ? 'عمليات التواصل' : 'Communication operations',
      title: ar ? 'تنبيهات الإرسال' : 'Delivery alerts',
    },
    candidates: {
      eyebrow: ar ? 'قائمة المرشحين المرتبة' : 'Ranked pipeline',
      title: ar ? 'المرشحون' : 'Candidates',
    },
    interviews: {
      eyebrow: ar ? 'جدول التوظيف' : 'Recruiting schedule',
      title: ar ? 'المقابلات' : 'Interviews',
    },
  }
  return copy[screen] || { eyebrow: '', title: '' }
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
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
  },
  buildMarkerText: { color: colors.white, fontSize: 8, fontWeight: '800' },
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
