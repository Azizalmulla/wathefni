import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, Save, ShieldCheck } from 'lucide-react'

import { ConfigureInOpsLink } from '@/components/ConfigureInSetupBanner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { dashboardPageHref } from '@/lib/setupConsoleOwnership'

import {
  getPayrollSetup,
  searchPayrollAllowlistCandidates,
  updatePayrollSetup,
  type PayrollSetupResponse,
} from './api'
import type { SetupCredentials } from './types'

function readinessTone(state: string): 'success' | 'warning' | 'danger' | 'muted' {
  if (state === 'ready_authoritative' || state === 'ready_preview' || state === 'ready_external') return 'success'
  if (state === 'needs_attention') return 'warning'
  if (state === 'setup_incomplete') return 'danger'
  return 'muted'
}

export function PayrollSetupCard({
  credentials,
  companyCode,
  moduleEnabled,
  locale = 'en',
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  moduleEnabled: boolean
  locale?: 'en' | 'ar'
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [showOptional, setShowOptional] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [setup, setSetup] = useState<PayrollSetupResponse | null>(null)
  const [reason, setReason] = useState('')

  const [payrollMode, setPayrollMode] = useState<'native' | 'external' | 'parallel_shadow'>('native')
  const [attendanceUx, setAttendanceUx] = useState('informational')
  const [cutoffDay, setCutoffDay] = useState('')
  const [lateness, setLateness] = useState(false)
  const [absence, setAbsence] = useState(false)
  const [unpaid, setUnpaid] = useState(false)
  const [reviewStep, setReviewStep] = useState(true)
  const [distinctApprover, setDistinctApprover] = useState(true)
  const [allowApproverFinalize, setAllowApproverFinalize] = useState(true)
  const [enterpriseSod, setEnterpriseSod] = useState(false)
  const [entitlement, setEntitlement] = useState('disabled')
  const [weekendDays, setWeekendDays] = useState<string[]>(['fri', 'sat'])
  const [confirmAuthoritative, setConfirmAuthoritative] = useState(false)
  const [grossDelta, setGrossDelta] = useState('50')
  const [netDelta, setNetDelta] = useState('50')
  const [allowlistQuery, setAllowlistQuery] = useState('')
  const [allowlistHits, setAllowlistHits] = useState<
    Array<{ employee_key: string; name?: string; on_allowlist?: boolean }>
  >([])

  const hydrate = useCallback((payload: PayrollSetupResponse) => {
    setSetup(payload)
    setPayrollMode((payload.payroll_mode as typeof payrollMode) || 'native')
    setAttendanceUx(payload.attendance_ux || 'informational')
    setCutoffDay(payload.setup_extras?.cutoff_day != null ? String(payload.setup_extras.cutoff_day) : '')
    const pol = payload.approved_policy
    setLateness(Boolean(pol?.lateness_money_enabled))
    setAbsence(Boolean(pol?.absence_money_enabled))
    setUnpaid(Boolean(pol?.unpaid_leave_money_enabled))
    const fin = payload.finalize_policy
    setReviewStep(Boolean(fin?.require_review_step ?? true))
    setDistinctApprover(Boolean(fin?.require_distinct_approver ?? true))
    setAllowApproverFinalize(Boolean(fin?.allow_approver_as_finalizer ?? true))
    setEnterpriseSod(Boolean(fin?.enterprise_sod_strict))
    setEntitlement(payload.entitlement?.state || 'disabled')
    setWeekendDays(payload.working_calendar?.weekend_days?.length ? [...payload.working_calendar.weekend_days] : ['fri', 'sat'])
    setGrossDelta(String(payload.variance_policy?.gross_delta_abs ?? 50))
    setNetDelta(String(payload.variance_policy?.net_delta_abs ?? 50))
    if (fin?.enterprise_sod_strict || payload.entitlement?.state === 'authoritative_allowlisted') setShowAdvanced(true)
    if (!(payload.working_calendar?.configured)) setShowOptional(true)
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const payload = await getPayrollSetup(credentials, companyCode)
      hydrate(payload)
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, hydrate, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  async function save(patch: Record<string, unknown>, successNote?: string) {
    const trimmed = reason.trim()
    if (!trimmed) {
      onError(new Error(isAr ? 'أدخل سبب التغيير قبل الحفظ.' : 'Enter a reason before saving payroll setup changes.'))
      return
    }
    setWorking(true)
    try {
      const result = await updatePayrollSetup(credentials, companyCode, {
        reason: trimmed,
        ...patch,
      })
      if (result.setup) hydrate(result.setup)
      else await reload()
      await onChanged()
      if (successNote) {
        /* soft success via status text below */
      }
    } catch (error) {
      onError(error)
    } finally {
      setWorking(false)
    }
  }

  const readiness = setup?.readiness
  const isExternal = payrollMode === 'external'
  const isNative = payrollMode === 'native' || payrollMode === 'parallel_shadow'

  return (
    <Card
      id="classic-payroll-setup"
      data-ownership="payroll_company_setup"
      data-phase="3a"
      dir={isAr ? 'rtl' : 'ltr'}
      lang={locale}
    >
      <CardHeader>
        <CardTitle>{isAr ? 'الرواتب' : 'Payroll'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'ماذا تستخدم الشركة؟ كيف يعمل؟ من يعتمد؟ التشغيل اليومي يبقى في مساحة الرواتب.'
            : 'What does this company use? How should it work? Who approves? Day-to-day runs stay in Payroll.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {!moduleEnabled ? (
          <p className="rounded-2xl border border-amber-200/70 bg-amber-50/60 px-4 py-3 text-sm text-amber-950">
            {isAr
              ? 'وحدة الرواتب متوقفة. فعّلها من «ما تستخدمه الشركة» قبل ضبط الإعداد أو السلطة.'
              : 'Payroll module is off. Enable it under “What this company uses” before configuring setup or authority.'}
          </p>
        ) : null}

        {loading || !setup ? (
          <p className="flex items-center gap-2 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading payroll setup…'}
          </p>
        ) : (
          <>
            {/* Readiness */}
            <section className="rounded-2xl border border-line/60 bg-white/50 px-4 py-3" data-payroll-readiness>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.08em] text-subtle">
                    {isAr ? 'الجاهزية' : 'Readiness'}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-text">
                    {isAr ? readiness?.label_ar : readiness?.label_en}
                  </p>
                </div>
                <Badge tone={readinessTone(String(readiness?.state || ''))}>
                  {isAr ? readiness?.label_ar : readiness?.label_en}
                </Badge>
              </div>
              {(readiness?.blockers || []).length ? (
                <ul className="mt-3 space-y-2">
                  {(readiness?.blockers || []).map((issue, idx) => (
                    <li
                      key={`${issue.field || issue.code || idx}`}
                      className="rounded-xl border border-amber-200/60 bg-amber-50/40 px-3 py-2 text-sm"
                    >
                      <p className="font-medium text-text">{isAr ? issue.message_ar : issue.message_en}</p>
                      {issue.how_to_fix ? <p className="mt-1 text-xs text-subtle">{issue.how_to_fix}</p> : null}
                      {issue.fix_href ? (
                        <a href={issue.fix_href} className="mt-1 inline-block text-xs font-medium text-accent hover:underline">
                          {isAr ? 'افتح الإعداد المطلوب' : 'Open the required setting'}
                        </a>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-subtle">
                  {isAr ? 'لا توجد عوائق حالية للإعداد الأساسي.' : 'No current blockers for base setup.'}
                </p>
              )}
              {(readiness?.attention || []).length ? (
                <ul className="mt-3 space-y-2">
                  {(readiness?.attention || []).map((issue, idx) => (
                    <li key={`att-${issue.code || idx}`} className="rounded-xl border border-sky-200/60 bg-sky-50/40 px-3 py-2 text-sm">
                      <p className="font-medium text-text">{isAr ? issue.message_ar : issue.message_en}</p>
                      {issue.fix_href ? (
                        <a href={issue.fix_href} className="mt-1 inline-block text-xs font-medium text-accent hover:underline">
                          {isAr ? 'راجع التصنيفات' : 'Review classifications'}
                        </a>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>

            {/* OctoHR-owned customer presentation; legacy API field names remain stable. */}
            <section
              id="classic-payroll-setup-statutory"
              className="rounded-2xl border border-line/55 bg-panel-muted/40 px-4 py-3"
              data-wathefni-owned
            >
              <p className="flex items-center gap-2 text-sm font-semibold text-text">
                <ShieldCheck className="h-4 w-4" aria-hidden />
                {isAr ? 'يملكه OctoHR (للقراءة فقط)' : 'Owned by OctoHR (read-only)'}
              </p>
              <dl className="mt-2 grid gap-2 text-xs text-subtle sm:grid-cols-2">
                <div>
                  <dt>{isAr ? 'خط الأساس القانوني الكويتي' : 'Kuwait statutory baseline'}</dt>
                  <dd className="font-medium text-text">{setup.wathefni_owned?.kuwait_statutory_baseline_version}</dd>
                </div>
                <div>
                  <dt>{isAr ? 'محرك الاحتساب / الختم' : 'Calculation & sealing'}</dt>
                  <dd className="font-medium text-text">{isAr ? 'قواعد OctoHR' : 'OctoHR rules'}</dd>
                </div>
                <div>
                  <dt>{isAr ? 'معالجة الدفع' : 'Payment processing'}</dt>
                  <dd className="font-medium text-text">{isAr ? 'معطّلة' : 'Disabled'}</dd>
                </div>
              </dl>
              <p className="mt-2 text-xs leading-5 text-subtle">
                {isAr
                  ? 'لا تُطلب من الشركة كتابة نسب العمل الإضافي أو التأمينات أو الإجازة المرضية — يملكها OctoHR.'
                  : 'Companies are never asked to type OT, PIFSS, or sick-leave percentages — OctoHR owns those rates.'}
              </p>
            </section>

            <label className="flex flex-col gap-1.5 text-xs font-medium text-subtle">
              {isAr ? 'سبب التغيير (مطلوب لكل حفظ)' : 'Reason for change (required for every save)'}
              <Input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder={isAr ? 'مثال: إعداد أولي للشركة' : 'e.g. Initial company payroll setup'}
                disabled={working}
              />
            </label>

            {/* Required — Mode */}
            <section id="classic-payroll-setup-mode" className="space-y-3">
              <h3 className="text-sm font-semibold text-text">{isAr ? 'مطلوب · وضع الرواتب' : 'Required · Payroll mode'}</h3>
              <div className="grid gap-2 sm:grid-cols-2">
                <button
                  type="button"
                  disabled={working || !moduleEnabled}
                  className={cn(
                    'rounded-2xl border px-4 py-3 text-left transition',
                    isNative ? 'border-accent/45 bg-accent-soft/50' : 'border-line/60 bg-white/45 hover:border-accent/25',
                  )}
                  onClick={() => setPayrollMode('native')}
                >
                  <span className="block text-sm font-semibold">{isAr ? 'رواتب OctoHR' : 'OctoHR Payroll'}</span>
                  <span className="mt-1 block text-xs text-subtle">
                    {isAr ? 'إعداد الجاهزية والسلطة الأصلية.' : 'Configure native readiness and authority.'}
                  </span>
                </button>
                <button
                  type="button"
                  disabled={working || !moduleEnabled}
                  className={cn(
                    'rounded-2xl border px-4 py-3 text-left transition',
                    isExternal ? 'border-accent/45 bg-accent-soft/50' : 'border-line/60 bg-white/45 hover:border-accent/25',
                  )}
                  onClick={() => setPayrollMode('external')}
                >
                  <span className="block text-sm font-semibold">{isAr ? 'رواتب خارجية' : 'External Payroll'}</span>
                  <span className="mt-1 block text-xs text-subtle">
                    {isAr ? 'سلطة خارجية دون إعدادات الاحتساب الأصلي.' : 'External authority — hide native calc settings.'}
                  </span>
                </button>
              </div>
              <Button
                type="button"
                size="sm"
                disabled={working || !moduleEnabled}
                onClick={() =>
                  void save({
                    payroll_mode: payrollMode,
                    ...(payrollMode === 'external' ? { entitlement_state: 'disabled' } : {}),
                  })
                }
              >
                {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {isAr ? 'حفظ الوضع' : 'Save mode'}
              </Button>
            </section>

            {isExternal ? (
              <section className="space-y-3 rounded-2xl border border-line/55 bg-white/45 px-4 py-3">
                <h3 className="text-sm font-semibold">{isAr ? 'توقعات الرواتب الخارجية' : 'External payroll expectations'}</h3>
                <p className="text-sm text-subtle">
                  {isAr
                    ? 'التشغيل اليومي للاستيراد/المطابقة يبقى في مساحة الرواتب والأنظمة المتصلة. إعدادات الاحتساب الأصلي مخفية عمداً.'
                    : 'Day-to-day import/reconcile stays in Payroll and Connected systems. Native calculation settings stay hidden on purpose.'}
                </p>
                <div className="flex flex-wrap gap-3">
                  <ConfigureInOpsLink href={dashboardPageHref('payroll')} label={isAr ? 'مساحة الرواتب' : 'Payroll workspace'} />
                  <ConfigureInOpsLink
                    href={dashboardPageHref('employees', { view: 'migration' })}
                    label={isAr ? 'الأنظمة المتصلة' : 'Connected systems'}
                  />
                </div>
              </section>
            ) : (
              <>
                {/* Required — cycle / attendance / approval / authority */}
                <section id="classic-payroll-setup-attendance" className="space-y-3">
                  <h3 className="text-sm font-semibold">{isAr ? 'مطلوب · الدورة والحضور' : 'Required · Cycle & attendance'}</h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="flex flex-col gap-1.5 text-xs font-medium text-subtle">
                      {isAr ? 'دورة الرواتب' : 'Payroll frequency'}
                      <select
                        className="h-11 rounded-2xl border border-line/70 bg-white/80 px-3 text-sm"
                        value="monthly"
                        disabled
                      >
                        <option value="monthly">{isAr ? 'شهري' : 'Monthly'}</option>
                      </select>
                    </label>
                    <label className="flex flex-col gap-1.5 text-xs font-medium text-subtle">
                      {isAr ? 'يوم القطع (1–28، اختياري)' : 'Cut-off day (1–28, optional)'}
                      <Input
                        type="number"
                        min={1}
                        max={28}
                        value={cutoffDay}
                        disabled={working || !moduleEnabled}
                        onChange={(event) => setCutoffDay(event.target.value)}
                        placeholder={isAr ? 'نهاية الشهر إن تُرك فارغاً' : 'Calendar month-end if blank'}
                      />
                    </label>
                    <label className="flex flex-col gap-1.5 text-xs font-medium text-subtle sm:col-span-2">
                      {isAr ? 'كيف يؤثر الحضور على الأجر؟' : 'How should attendance affect pay?'}
                      <select
                        className="h-11 rounded-2xl border border-line/70 bg-white/80 px-3 text-sm"
                        value={attendanceUx}
                        disabled={working || !moduleEnabled}
                        onChange={(event) => setAttendanceUx(event.target.value)}
                      >
                        {(setup.attendance_choices || []).map((choice) => (
                          <option key={choice.key} value={choice.key}>
                            {isAr ? choice.label_ar : choice.label_en}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                </section>

                <section id="classic-payroll-setup-calendar" className="space-y-3">
                  <h3 className="text-sm font-semibold">{isAr ? 'مطلوب · تقويم العمل' : 'Required · Working calendar'}</h3>
                  <p className="text-xs text-subtle">
                    {isAr
                      ? 'الشركة تملك أيام العمل والراحة. يملك OctoHR تفسير العطل الرسمية القانونية.'
                      : 'The company owns working/rest days. OctoHR owns statutory public-holiday interpretation.'}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {(['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const).map((day) => {
                      const checked = weekendDays.includes(day)
                      const labels: Record<string, { en: string; ar: string }> = {
                        sun: { en: 'Sun', ar: 'أحد' },
                        mon: { en: 'Mon', ar: 'إثنين' },
                        tue: { en: 'Tue', ar: 'ثلاثاء' },
                        wed: { en: 'Wed', ar: 'أربعاء' },
                        thu: { en: 'Thu', ar: 'خميس' },
                        fri: { en: 'Fri', ar: 'جمعة' },
                        sat: { en: 'Sat', ar: 'سبت' },
                      }
                      return (
                        <label key={day} className="inline-flex items-center gap-1.5 rounded-full border border-line/60 px-3 py-1.5 text-xs">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={working || !moduleEnabled}
                            onChange={() =>
                              setWeekendDays((current) =>
                                checked ? current.filter((d) => d !== day) : [...current, day],
                              )
                            }
                          />
                          {isAr ? labels[day].ar : labels[day].en}
                          <span className="text-subtle">{isAr ? 'راحة' : 'rest'}</span>
                        </label>
                      )
                    })}
                  </div>
                  <p className="text-xs text-subtle">
                    {isAr
                      ? `العطل لهذا العام: ${setup.working_calendar?.holiday_count ?? 0}`
                      : `Holidays this year: ${setup.working_calendar?.holiday_count ?? 0}`}
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={working || !moduleEnabled || weekendDays.length === 0}
                    onClick={() =>
                      void save({
                        weekend_days: weekendDays,
                        seed_kuwait_holidays: true,
                        setup_extras: {
                          payroll_frequency: 'monthly',
                          cutoff_day: cutoffDay === '' ? null : Number(cutoffDay),
                          period_end_rule: 'calendar_month',
                          weekend_days: weekendDays,
                          calendar_configured: true,
                        },
                      })
                    }
                  >
                    {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {isAr ? 'حفظ التقويم وبذر العطل الكويتية الثابتة' : 'Save calendar & seed fixed Kuwait holidays'}
                  </Button>
                </section>

                <section id="classic-payroll-setup-statutory-inputs" className="space-y-3">
                  <h3 className="text-sm font-semibold">
                    {isAr ? 'مطلوب للمتابعة السلطوية · التصنيف القانوني' : 'Required for authoritative · Statutory classifications'}
                  </h3>
                  <p className="text-sm text-subtle">
                    {isAr ? setup.statutory_inputs?.message_ar : setup.statutory_inputs?.message_en}
                  </p>
                  <p className="text-xs text-subtle">
                    {isAr
                      ? `ناقص التصنيف: ${setup.statutory_inputs?.missing_category_count ?? 0} · ناقص أساس التأمينات: ${setup.statutory_inputs?.missing_pifss_wage_count ?? 0}`
                      : `Missing category: ${setup.statutory_inputs?.missing_category_count ?? 0} · Missing PIFSS wage base: ${setup.statutory_inputs?.missing_pifss_wage_count ?? 0}`}
                  </p>
                  <p className="text-xs text-subtle">
                    {isAr
                      ? 'لا تُدخل نسب التأمينات — يملكها OctoHR. أكمل تصنيف الموظف وأساس الأجر فقط.'
                      : 'Never type PIFSS percentages — OctoHR owns rates. Complete category and wage-base facts only.'}
                  </p>
                  <ConfigureInOpsLink
                    href={dashboardPageHref('employees')}
                    label={isAr ? 'أكمل التصنيفات في الموظفين' : 'Complete classifications in Employees'}
                  />
                </section>

                <section id="classic-payroll-setup-policy" className="space-y-3">
                  <h3 className="text-sm font-semibold">{isAr ? 'مطلوب · سياسة الشركة' : 'Required · Company policy'}</h3>
                  <p className="text-xs text-subtle">
                    {isAr
                      ? setup.approved_policy
                        ? `سياسة معتمدة · حضور ${setup.approved_policy.attendance_payroll_mode}`
                        : 'لا توجد سياسة معتمدة بعد — احفظ الإعداد المطلوب أدناه.'
                      : setup.approved_policy
                        ? `Approved policy · attendance ${setup.approved_policy.attendance_payroll_mode}`
                        : 'No approved policy yet — save required setup below.'}
                  </p>
                  <p className="text-xs text-subtle">
                    {isAr
                      ? `عقود التعويض المعتمدة: ${setup.approved_compensation_contracts}`
                      : `Approved compensation contracts: ${setup.approved_compensation_contracts}`}
                    {' · '}
                    <ConfigureInOpsLink href={dashboardPageHref('employees')} label={isAr ? 'إدارة التعويض في الموظفين' : 'Manage compensation in Employees'} />
                  </p>
                </section>

                <section id="classic-payroll-setup-approval" className="space-y-3">
                  <h3 className="text-sm font-semibold">{isAr ? 'مطلوب · الاعتماد' : 'Required · Approvals'}</h3>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={reviewStep} disabled={working} onChange={(e) => setReviewStep(e.target.checked)} />
                    {isAr ? 'تتطلب خطوة مراجعة' : 'Require a review step'}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={distinctApprover}
                      disabled={working}
                      onChange={(e) => setDistinctApprover(e.target.checked)}
                    />
                    {isAr ? 'المعتمد يختلف عن المُعِد' : 'Approver must differ from preparer'}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={allowApproverFinalize}
                      disabled={working || enterpriseSod}
                      onChange={(e) => setAllowApproverFinalize(e.target.checked)}
                    />
                    {isAr ? 'يسمح للمعتمد بالختم النهائي (مناسب للشركات الصغيرة)' : 'Approver may finalize (SME-friendly)'}
                  </label>
                </section>

                <section id="classic-payroll-setup-authority" className="space-y-3">
                  <h3 className="text-sm font-semibold">{isAr ? 'مطلوب · سلطة OctoHR' : 'Required · OctoHR authority'}</h3>
                  <label className="flex flex-col gap-1.5 text-xs font-medium text-subtle">
                    {isAr ? 'مستوى التفعيل' : 'Activation level'}
                    <select
                      className="h-11 rounded-2xl border border-line/70 bg-white/80 px-3 text-sm"
                      value={entitlement}
                      disabled={working || !moduleEnabled}
                      onChange={(event) => {
                        setEntitlement(event.target.value)
                        setConfirmAuthoritative(false)
                      }}
                    >
                      <option value="disabled">{isAr ? 'متوقف' : 'Off'}</option>
                      <option value="preview_only">{isAr ? 'معاينة فقط' : 'Preview only'}</option>
                      <option value="authoritative_allowlisted">{isAr ? 'سلطوي · قائمة مسموحة' : 'Authoritative · allowlisted'}</option>
                      <option value="authoritative">{isAr ? 'سلطوي · الشركة كاملة' : 'Authoritative · full company'}</option>
                    </select>
                  </label>
                  {entitlement === 'authoritative' ? (
                    <label className="flex items-start gap-2 text-sm text-amber-950">
                      <input
                        type="checkbox"
                        checked={confirmAuthoritative}
                        disabled={working}
                        onChange={(e) => setConfirmAuthoritative(e.target.checked)}
                      />
                      <span>
                        {isAr
                          ? 'أؤكد التفعيل السلطوي الكامل. السجلات المختومة سابقاً لن تُعاد كتابتها.'
                          : 'I confirm full authoritative activation. Previously finalized payroll history will not be rewritten.'}
                      </span>
                    </label>
                  ) : null}
                  <p className="text-xs text-subtle">
                    {isAr
                      ? 'لا يُستنتج تلقائياً من تفعيل الوحدة. السلطة السلطوية تتطلب جاهزية مكتملة.'
                      : 'Never inferred from module enablement. Authoritative levels require complete readiness.'}
                  </p>
                </section>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={working || !moduleEnabled}
                    onClick={() =>
                      void save({
                        apply_sme_defaults: true,
                        payroll_mode: 'native',
                        attendance_ux: attendanceUx,
                        setup_extras: {
                          payroll_frequency: 'monthly',
                          cutoff_day: cutoffDay === '' ? null : Number(cutoffDay),
                          period_end_rule: 'calendar_month',
                        },
                        require_review_step: reviewStep,
                        require_distinct_approver: distinctApprover,
                        allow_approver_as_finalizer: allowApproverFinalize,
                        entitlement_state: entitlement === 'disabled' ? 'preview_only' : entitlement,
                      })
                    }
                  >
                    {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {isAr ? 'تطبيق إعداد الشركات الصغيرة' : 'Apply SME defaults'}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={working || !moduleEnabled}
                    onClick={() =>
                      void save({
                        payroll_mode: payrollMode,
                        attendance_ux: attendanceUx,
                        apply_sme_policy: true,
                        lateness_money_enabled: lateness,
                        absence_money_enabled: absence,
                        unpaid_leave_money_enabled: unpaid,
                        ot_money_enabled: false,
                        require_review_step: reviewStep,
                        require_distinct_approver: distinctApprover,
                        allow_approver_as_finalizer: enterpriseSod ? false : allowApproverFinalize,
                        enterprise_sod_strict: enterpriseSod,
                        entitlement_state: entitlement,
                        confirm_authoritative: entitlement === 'authoritative' ? confirmAuthoritative : false,
                        weekend_days: weekendDays,
                        setup_extras: {
                          payroll_frequency: 'monthly',
                          cutoff_day: cutoffDay === '' ? null : Number(cutoffDay),
                          period_end_rule: 'calendar_month',
                          weekend_days: weekendDays,
                          calendar_configured: true,
                        },
                      })
                    }
                  >
                    {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {isAr ? 'حفظ الإعداد المطلوب' : 'Save required setup'}
                  </Button>
                </div>

                {/* Optional */}
                <section className="rounded-2xl border border-dashed border-line/60 px-4 py-3">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between text-sm font-semibold"
                    onClick={() => setShowOptional((v) => !v)}
                  >
                    <span>{isAr ? 'اختياري · سياسات شائعة' : 'Optional · Common policies'}</span>
                    {showOptional ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </button>
                  {showOptional ? (
                    <div className="mt-3 space-y-2">
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={lateness} disabled={working} onChange={(e) => setLateness(e.target.checked)} />
                        {isAr ? 'التأخير يؤثر على الأجر' : 'Lateness can affect pay'}
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={absence} disabled={working} onChange={(e) => setAbsence(e.target.checked)} />
                        {isAr ? 'الغياب يؤثر على الأجر' : 'Absence can affect pay'}
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={unpaid} disabled={working} onChange={(e) => setUnpaid(e.target.checked)} />
                        {isAr ? 'الإجازة غير المدفوعة تؤثر على الأجر' : 'Unpaid leave can affect pay'}
                      </label>
                      <p className="text-xs text-subtle">
                        {isAr
                          ? 'أهلية العمل الإضافي ونسبها يملكها OctoHR — لا تُدخل النسب هنا.'
                          : 'OT eligibility rates stay OctoHR-owned — never type percentages here.'}
                      </p>
                    </div>
                  ) : null}
                </section>

                {/* Advanced */}
                <section className="rounded-2xl border border-dashed border-line/60 px-4 py-3">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between text-sm font-semibold"
                    onClick={() => setShowAdvanced((v) => !v)}
                  >
                    <span>{isAr ? 'متقدم · فصل الصلاحيات والقوائم والتباين' : 'Advanced · SOD, allowlists & variance'}</span>
                    {showAdvanced ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </button>
                  {showAdvanced ? (
                    <div className="mt-3 space-y-4">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={enterpriseSod}
                          disabled={working}
                          onChange={(e) => {
                            setEnterpriseSod(e.target.checked)
                            if (e.target.checked) setAllowApproverFinalize(false)
                          }}
                        />
                        {isAr ? 'فصل صارم: المعتمد ≠ الخاتم النهائي' : 'Strict SOD: approver ≠ finalizer'}
                      </label>

                      <div id="classic-payroll-setup-variance" className="space-y-2 rounded-xl border border-line/50 bg-white/50 px-3 py-2">
                        <p className="text-sm font-medium">{isAr ? 'عتبات مراجعة التباين (استشارية)' : 'Variance review thresholds (advisory)'}</p>
                        <p className="text-xs text-subtle">
                          {isAr
                            ? 'تُنتج إشارات مراجعة فقط — لا تغيّر مبالغ الرواتب.'
                            : 'Produce review signals only — never change payroll amounts.'}
                        </p>
                        <div className="grid gap-2 sm:grid-cols-2">
                          <label className="text-xs">
                            {isAr ? 'فرق الإجمالي (د.ك)' : 'Gross delta (KWD)'}
                            <Input value={grossDelta} disabled={working} onChange={(e) => setGrossDelta(e.target.value)} />
                          </label>
                          <label className="text-xs">
                            {isAr ? 'فرق الصافي (د.ك)' : 'Net delta (KWD)'}
                            <Input value={netDelta} disabled={working} onChange={(e) => setNetDelta(e.target.value)} />
                          </label>
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={working}
                          onClick={() =>
                            void save({
                              variance_policy: {
                                gross_delta_abs: Number(grossDelta) || 50,
                                net_delta_abs: Number(netDelta) || 50,
                              },
                            })
                          }
                        >
                          {isAr ? 'حفظ عتبات المراجعة' : 'Save review thresholds'}
                        </Button>
                      </div>

                      <div id="classic-payroll-setup-allowlist" className="space-y-2 rounded-xl border border-line/50 bg-white/50 px-3 py-2">
                        <p className="text-sm font-medium">
                          {isAr
                            ? `القائمة المسموحة · ${setup.allowlist?.active_count ?? 0}`
                            : `Authoritative allowlist · ${setup.allowlist?.active_count ?? 0}`}
                        </p>
                        <div className="flex gap-2">
                          <Input
                            value={allowlistQuery}
                            disabled={working || entitlement !== 'authoritative_allowlisted'}
                            onChange={(e) => setAllowlistQuery(e.target.value)}
                            placeholder={isAr ? 'ابحث عن موظف' : 'Search employees'}
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            disabled={working || entitlement !== 'authoritative_allowlisted'}
                            onClick={() => {
                              void searchPayrollAllowlistCandidates(credentials, companyCode, {
                                q: allowlistQuery,
                                limit: 20,
                              })
                                .then((result) => setAllowlistHits(result.employees || []))
                                .catch(onError)
                            }}
                          >
                            {isAr ? 'بحث' : 'Search'}
                          </Button>
                        </div>
                        <div className="max-h-40 space-y-1 overflow-y-auto text-sm">
                          {allowlistHits.map((emp) => (
                            <div key={emp.employee_key} className="flex items-center justify-between gap-2 rounded-lg border border-line/40 px-2 py-1">
                              <span>{emp.name || emp.employee_key}</span>
                              {emp.on_allowlist ? (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="ghost"
                                  disabled={working}
                                  onClick={() => void save({ allowlist_revoke: [emp.employee_key] })}
                                >
                                  {isAr ? 'إزالة' : 'Remove'}
                                </Button>
                              ) : (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="secondary"
                                  disabled={working}
                                  onClick={() => void save({ allowlist_add: [emp.employee_key] })}
                                >
                                  {isAr ? 'إضافة' : 'Add'}
                                </Button>
                              )}
                            </div>
                          ))}
                        </div>
                        <ConfigureInOpsLink href={dashboardPageHref('payroll')} label={isAr ? 'تشغيل الرواتب' : 'Payroll operations'} />
                      </div>
                    </div>
                  ) : null}
                </section>
              </>
            )}

            <div className="flex flex-wrap gap-3 border-t border-line/50 pt-3">
              <ConfigureInOpsLink href={dashboardPageHref('payroll')} label={isAr ? 'تشغيل الرواتب' : 'Payroll operations'} />
              <Button type="button" variant="ghost" size="sm" disabled={working} onClick={() => void reload()}>
                {isAr ? 'تحديث' : 'Refresh'}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
