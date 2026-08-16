import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, Save } from 'lucide-react'

import { ConfigureInOpsLink } from '@/components/ConfigureInSetupBanner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { dashboardPageHref } from '@/lib/setupConsoleOwnership'

import {
  getModulePolicies,
  updateModulePolicy,
  type ModulePoliciesResponse,
  type ModulePolicyPayload,
} from './api'
import type { SetupCredentials } from './types'

type ModuleId = 'leave' | 'attendance' | 'shifts' | 'documents' | 'onboarding'

const MODULE_META: Record<
  ModuleId,
  { titleEn: string; titleAr: string; opsPage: string; anchor: string; moduleKeys: string[] }
> = {
  leave: {
    titleEn: 'Leave',
    titleAr: 'الإجازات',
    opsPage: 'leave',
    anchor: 'classic-module-leave',
    moduleKeys: ['leave'],
  },
  attendance: {
    titleEn: 'Attendance',
    titleAr: 'الحضور',
    opsPage: 'attendance',
    anchor: 'classic-module-attendance',
    moduleKeys: ['attendance'],
  },
  shifts: {
    titleEn: 'Shifts',
    titleAr: 'المناوبات',
    opsPage: 'shifts',
    anchor: 'classic-module-shifts',
    moduleKeys: ['shifts'],
  },
  documents: {
    titleEn: 'Documents & compliance',
    titleAr: 'المستندات والامتثال',
    opsPage: 'compliance',
    anchor: 'classic-module-documents',
    moduleKeys: ['compliance', 'documents'],
  },
  onboarding: {
    titleEn: 'Onboarding',
    titleAr: 'التهيئة',
    opsPage: 'onboarding',
    anchor: 'classic-module-onboarding',
    moduleKeys: ['onboarding'],
  },
}

function statusTone(state: string): 'success' | 'warning' | 'danger' | 'muted' {
  if (state === 'ready') return 'success'
  if (state === 'needs_attention') return 'warning'
  if (state === 'inactive') return 'muted'
  return 'muted'
}

function ModulePolicyCard({
  moduleId,
  policy,
  moduleEnabled,
  locale,
  credentials,
  companyCode,
  reason,
  onReason,
  onSaved,
  onError,
}: {
  moduleId: ModuleId
  policy: ModulePolicyPayload
  moduleEnabled: boolean
  locale: 'en' | 'ar'
  credentials: SetupCredentials
  companyCode: string
  reason: string
  onReason: (v: string) => void
  onSaved: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  const meta = MODULE_META[moduleId]
  const inactive = !moduleEnabled || Boolean(policy.inactive)
  const [open, setOpen] = useState(false)
  const [showOptional, setShowOptional] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [working, setWorking] = useState(false)

  // Leave
  const [annualDays, setAnnualDays] = useState('')
  const [eligibility, setEligibility] = useState('')
  const [noticeDays, setNoticeDays] = useState('0')
  const [requireSickAttachment, setRequireSickAttachment] = useState(false)

  // Attendance
  const [grace, setGrace] = useState('15')
  const [requireClockOut, setRequireClockOut] = useState(true)
  const [missingPunch, setMissingPunch] = useState(true)
  const [correctionApproval, setCorrectionApproval] = useState(true)

  // Shifts
  const [leaveConflict, setLeaveConflict] = useState('require_ack')
  const [allowOvernight, setAllowOvernight] = useState(true)
  const [publishAck, setPublishAck] = useState(true)
  const [swapEnabled, setSwapEnabled] = useState(false)

  // Documents
  const [requiredTypes, setRequiredTypes] = useState('civil_id,passport')
  const [civilWarn, setCivilWarn] = useState('30')
  const [passportWarn, setPassportWarn] = useState('60')
  const [renewalOn, setRenewalOn] = useState(true)
  const [evidenceReview, setEvidenceReview] = useState(true)

  // Onboarding
  const [templateId, setTemplateId] = useState('default_kuwait')
  const [dueOffset, setDueOffset] = useState('7')
  const [employeeActions, setEmployeeActions] = useState(true)
  const [autoSeed, setAutoSeed] = useState(true)

  useEffect(() => {
    if (moduleId === 'leave') {
      const annual = (policy.policies || []).find((p) => p.leave_type === 'annual')
      setAnnualDays(annual?.days_per_year != null ? String(annual.days_per_year) : '30')
      setEligibility(annual?.eligibility_months != null ? String(annual.eligibility_months) : '0')
      setNoticeDays(String(policy.optional?.notice_days_default ?? 0))
      setRequireSickAttachment(Boolean(policy.optional?.require_attachment_for_sick))
    }
    if (moduleId === 'attendance') {
      setGrace(String(policy.optional?.lateness_grace_minutes ?? 15))
      setRequireClockOut(Boolean(policy.optional?.require_clock_out ?? true))
      setMissingPunch(Boolean(policy.optional?.missing_punch_creates_exception ?? true))
      setCorrectionApproval(Boolean(policy.optional?.correction_requires_approval ?? true))
    }
    if (moduleId === 'shifts') {
      setLeaveConflict(String(policy.required?.leave_conflict_mode || 'require_ack'))
      setAllowOvernight(Boolean(policy.optional?.allow_overnight ?? true))
      setPublishAck(Boolean(policy.optional?.publishing_requires_ack ?? true))
      setSwapEnabled(Boolean(policy.optional?.swap_requests_enabled))
    }
    if (moduleId === 'documents') {
      const types = (policy.required?.required_document_types as string[] | undefined) || ['civil_id', 'passport']
      setRequiredTypes(types.join(','))
      const w = (policy.optional?.warning_days as Record<string, number> | undefined) || {}
      setCivilWarn(String(w.civil_id ?? 30))
      setPassportWarn(String(w.passport ?? 60))
      setRenewalOn(Boolean(policy.optional?.renewal_reminder_enabled ?? true))
      setEvidenceReview(Boolean(policy.advanced?.evidence_review_required ?? true))
    }
    if (moduleId === 'onboarding') {
      setTemplateId(String(policy.required?.template_id || 'default_kuwait'))
      setDueOffset(String(policy.optional?.default_due_offset_days ?? 7))
      setEmployeeActions(Boolean(policy.optional?.employee_actions_enabled ?? true))
      setAutoSeed(Boolean(policy.advanced?.auto_seed_on_hire ?? true))
    }
  }, [moduleId, policy])

  async function save(body: Record<string, unknown>) {
    const trimmed = reason.trim()
    if (!trimmed) {
      onError(new Error(isAr ? 'أدخل سبب التغيير قبل الحفظ.' : 'Enter a reason before saving.'))
      return
    }
    if (inactive) {
      onError(new Error(isAr ? 'الوحدة متوقفة — فعّلها أولاً.' : 'Module is off — enable it first.'))
      return
    }
    setWorking(true)
    try {
      await updateModulePolicy(credentials, companyCode, moduleId === 'documents' ? 'documents' : moduleId, {
        reason: trimmed,
        ...body,
      })
      await onSaved()
    } catch (error) {
      onError(error)
    } finally {
      setWorking(false)
    }
  }

  const summary = isAr ? policy.summary_ar : policy.summary_en
  const status = String(policy.setup_status || (inactive ? 'inactive' : 'needs_attention'))

  return (
    <section
      id={meta.anchor}
      className={cn('rounded-2xl border border-line/60 bg-white/60 px-4 py-4', inactive && 'opacity-80')}
      data-module-policy={moduleId}
      data-inactive={inactive ? '1' : '0'}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-text">{isAr ? meta.titleAr : meta.titleEn}</h3>
            <Badge tone={inactive ? 'muted' : 'success'}>
              {inactive ? (isAr ? 'متوقف' : 'Disabled') : isAr ? 'مفعّل' : 'Enabled'}
            </Badge>
            <Badge tone={statusTone(status)}>{status === 'ready' ? (isAr ? 'جاهز' : 'Ready') : status === 'inactive' ? (isAr ? 'غير نشط' : 'Inactive') : isAr ? 'يحتاج انتباهاً' : 'Needs attention'}</Badge>
          </div>
          <p className="text-sm text-subtle">{summary}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ConfigureInOpsLink href={dashboardPageHref(meta.opsPage)} label={isAr ? 'مساحة التشغيل' : 'Open operations'} />
          <Button size="sm" variant="secondary" onClick={() => setOpen((v) => !v)} disabled={working}>
            {open ? (isAr ? 'إخفاء' : 'Hide') : isAr ? 'إعداد' : 'Configure'}
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>

      {open ? (
        <div className="mt-4 space-y-4 border-t border-line/50 pt-4">
          {inactive ? (
            <p className="rounded-xl border border-amber-200/70 bg-amber-50/50 px-3 py-2 text-sm text-amber-950">
              {isAr
                ? 'السياسة محفوظة للقراءة فقط. فعّل الوحدة من «ما تستخدمه الشركة» لاستعادة التعديل دون إنشاء إعدادات جديدة.'
                : 'Policy is preserved read-only. Enable the module under “What this company uses” to edit again — existing configuration is restored, not replaced.'}
            </p>
          ) : null}

          <label className="block space-y-1">
            <span className="text-xs font-medium text-subtle">{isAr ? 'سبب التغيير' : 'Reason for change'}</span>
            <Input value={reason} onChange={(e) => onReason(e.target.value)} disabled={inactive || working} placeholder={isAr ? 'مثال: سياسة الشركة السنوية' : 'e.g. annual company policy refresh'} />
          </label>

          {/* Required */}
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">{isAr ? 'مطلوب' : 'Required'}</p>

            {moduleId === 'leave' ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span>{isAr ? 'أيام الإجازة السنوية' : 'Annual leave days / year'}</span>
                  <Input type="number" value={annualDays} disabled={inactive || working} onChange={(e) => setAnnualDays(e.target.value)} />
                </label>
                <label className="space-y-1 text-sm">
                  <span>{isAr ? 'أشهر الأهلية' : 'Eligibility (months)'}</span>
                  <Input type="number" value={eligibility} disabled={inactive || working} onChange={(e) => setEligibility(e.target.value)} />
                </label>
                <p className="sm:col-span-2 text-xs text-subtle">
                  {isAr ? 'أيام الراحة والعطل من تقويم الرواتب — ' : 'Rest days and holidays come from Payroll working calendar — '}
                  <a href="/setup-console#classic-payroll-setup-calendar" className="font-medium text-accent hover:underline">
                    {isAr ? 'فتح التقويم' : 'Open calendar'}
                  </a>
                </p>
              </div>
            ) : null}

            {moduleId === 'attendance' ? (
              <div className="space-y-2 text-sm">
                <p>
                  {isAr ? 'أثر الحضور على الأجر:' : 'Attendance → pay mode:'}{' '}
                  <strong>{String(policy.required?.payroll_attendance_mode || '—')}</strong>
                </p>
                <p className="text-xs text-subtle">
                  {isAr ? 'يُضبط من إعداد الرواتب — ' : 'Configured in Payroll setup — '}
                  <a href="/setup-console#classic-payroll-setup-attendance" className="font-medium text-accent hover:underline">
                    {isAr ? 'فتح إعداد الحضور للرواتب' : 'Open payroll attendance'}
                  </a>
                </p>
              </div>
            ) : null}

            {moduleId === 'shifts' ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span>{isAr ? 'تعارض الإجازة مع المناوبة' : 'Leave vs shift conflict'}</span>
                  <Select value={leaveConflict} disabled={inactive || working} onChange={(e) => setLeaveConflict(e.target.value)}>
                    <option value="require_ack">{isAr ? 'يتطلب إقراراً' : 'Require acknowledgement'}</option>
                    <option value="block">{isAr ? 'منع الجدولة' : 'Block scheduling'}</option>
                    <option value="cancel_shift">{isAr ? 'إلغاء المناوبة' : 'Cancel shift'}</option>
                  </Select>
                </label>
                <p className="text-xs text-subtle sm:col-span-2">
                  {isAr ? 'أيام الراحة من تقويم الرواتب (لا يُعدَّل هنا). القوالب والجداول في مساحة المناوبات.' : 'Rest days follow Payroll working calendar (not edited here). Templates and rosters stay in Shifts operations.'}
                </p>
              </div>
            ) : null}

            {moduleId === 'documents' ? (
              <label className="block space-y-1 text-sm">
                <span>{isAr ? 'أنواع المستندات المطلوبة (مفصولة بفاصلة)' : 'Required document types (comma-separated)'}</span>
                <Input value={requiredTypes} disabled={inactive || working} onChange={(e) => setRequiredTypes(e.target.value)} />
                <span className="text-xs text-subtle">
                  {isAr ? 'سطح الموظف يبقى المستندات — لا وحدة امتثال منفصلة للموظف.' : 'Employee surface stays Documents — no separate employee Compliance module.'}
                </span>
              </label>
            ) : null}

            {moduleId === 'onboarding' ? (
              <div className="space-y-2">
                <label className="block space-y-1 text-sm">
                  <span>{isAr ? 'قالب التهيئة' : 'Onboarding template'}</span>
                  <Select value={templateId} disabled={inactive || working} onChange={(e) => setTemplateId(e.target.value)}>
                    <option value="default_kuwait">{isAr ? 'الكويت الافتراضي' : 'Default Kuwait'}</option>
                  </Select>
                </label>
                <p className="text-xs text-subtle">
                  {isAr
                    ? 'التغيير يؤثر على التعيينات الجديدة فقط. الرحلات الحالية تبقى مثبتة.'
                    : 'Changes apply to new assignments only. Existing journeys stay pinned.'}
                </p>
              </div>
            ) : null}
          </div>

          {/* Optional */}
          <button type="button" className="flex items-center gap-1 text-xs font-semibold uppercase tracking-[0.08em] text-subtle" onClick={() => setShowOptional((v) => !v)}>
            {showOptional ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            {isAr ? 'اختياري' : 'Optional'}
          </button>
          {showOptional ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {moduleId === 'leave' ? (
                <>
                  <label className="space-y-1 text-sm">
                    <span>{isAr ? 'أيام الإشعار الافتراضية' : 'Default notice days'}</span>
                    <Input type="number" value={noticeDays} disabled={inactive || working} onChange={(e) => setNoticeDays(e.target.value)} />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={requireSickAttachment} disabled={inactive || working} onChange={(e) => setRequireSickAttachment(e.target.checked)} />
                    {isAr ? 'مرفق مطلوب للإجازة المرضية' : 'Attachment required for sick leave'}
                  </label>
                </>
              ) : null}
              {moduleId === 'attendance' ? (
                <>
                  <label className="space-y-1 text-sm">
                    <span>{isAr ? 'سماحية التأخر (دقائق)' : 'Lateness grace (minutes)'}</span>
                    <Input type="number" value={grace} disabled={inactive || working} onChange={(e) => setGrace(e.target.value)} />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={requireClockOut} disabled={inactive || working} onChange={(e) => setRequireClockOut(e.target.checked)} />
                    {isAr ? 'يتطلب تسجيل الخروج' : 'Require clock-out'}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={missingPunch} disabled={inactive || working} onChange={(e) => setMissingPunch(e.target.checked)} />
                    {isAr ? 'البصمة الناقصة تُنشئ استثناءً' : 'Missing punch creates exception'}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={correctionApproval} disabled={inactive || working} onChange={(e) => setCorrectionApproval(e.target.checked)} />
                    {isAr ? 'التصحيح يتطلب موافقة' : 'Correction requires approval'}
                  </label>
                </>
              ) : null}
              {moduleId === 'shifts' ? (
                <>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={allowOvernight} disabled={inactive || working} onChange={(e) => setAllowOvernight(e.target.checked)} />
                    {isAr ? 'السماح بالمناوبات الليلية' : 'Allow overnight shifts'}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={publishAck} disabled={inactive || working} onChange={(e) => setPublishAck(e.target.checked)} />
                    {isAr ? 'النشر يتطلب إقراراً' : 'Publishing requires acknowledgement'}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={swapEnabled} disabled={inactive || working} onChange={(e) => setSwapEnabled(e.target.checked)} />
                    {isAr ? 'طلبات التبديل مفعّلة' : 'Swap requests enabled'}
                  </label>
                </>
              ) : null}
              {moduleId === 'documents' ? (
                <>
                  <label className="space-y-1 text-sm">
                    <span>{isAr ? 'تذكير البطاقة المدنية (أيام)' : 'Civil ID warning (days)'}</span>
                    <Input type="number" value={civilWarn} disabled={inactive || working} onChange={(e) => setCivilWarn(e.target.value)} />
                  </label>
                  <label className="space-y-1 text-sm">
                    <span>{isAr ? 'تذكير جواز السفر (أيام)' : 'Passport warning (days)'}</span>
                    <Input type="number" value={passportWarn} disabled={inactive || working} onChange={(e) => setPassportWarn(e.target.value)} />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={renewalOn} disabled={inactive || working} onChange={(e) => setRenewalOn(e.target.checked)} />
                    {isAr ? 'تذكيرات التجديد' : 'Renewal reminders'}
                  </label>
                </>
              ) : null}
              {moduleId === 'onboarding' ? (
                <>
                  <label className="space-y-1 text-sm">
                    <span>{isAr ? 'أيام الاستحقاق الافتراضية' : 'Default due offset (days)'}</span>
                    <Input type="number" value={dueOffset} disabled={inactive || working} onChange={(e) => setDueOffset(e.target.value)} />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={employeeActions} disabled={inactive || working} onChange={(e) => setEmployeeActions(e.target.checked)} />
                    {isAr ? 'إجراءات الموظف مفعّلة' : 'Employee actions enabled'}
                  </label>
                </>
              ) : null}
            </div>
          ) : null}

          {/* Advanced */}
          <button type="button" className="flex items-center gap-1 text-xs font-semibold uppercase tracking-[0.08em] text-subtle" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            {isAr ? 'متقدم' : 'Advanced'}
          </button>
          {showAdvanced ? (
            <div className="space-y-2 text-sm text-subtle">
              {moduleId === 'leave' ? (
                <p>{isAr ? 'بوابات دورة الحياة تبقى مفروضة من المنصة.' : 'Lifecycle gates remain platform-enforced.'}</p>
              ) : null}
              {moduleId === 'attendance' ? (
                <p>{isAr ? 'قيود الموقع والجهاز تبقى في عمليات الالتقاط — ليست إعداداً للشركة هنا.' : 'Location/device capture stays in Capture Ops — not company setup here.'}</p>
              ) : null}
              {moduleId === 'shifts' ? (
                <p>{isAr ? 'قوالب المناوبات والجداول والنشر ملك مساحة المناوبات.' : 'Shift templates, rosters, and publishing belong to Shifts operations.'}</p>
              ) : null}
              {moduleId === 'documents' ? (
                <label className="flex items-center gap-2 text-sm text-text">
                  <input type="checkbox" checked={evidenceReview} disabled={inactive || working} onChange={(e) => setEvidenceReview(e.target.checked)} />
                  {isAr ? 'مراجعة الأدلة مطلوبة قبل التذكير' : 'Evidence review required before reminders'}
                </label>
              ) : null}
              {moduleId === 'onboarding' ? (
                <label className="flex items-center gap-2 text-sm text-text">
                  <input type="checkbox" checked={autoSeed} disabled={inactive || working} onChange={(e) => setAutoSeed(e.target.checked)} />
                  {isAr ? 'بذر تلقائي عند التعيين' : 'Auto-seed checklist on hire'}
                </label>
              ) : null}
              {moduleId === 'documents' ? (
                <p className="text-xs">{isAr ? 'استخراج المستندات مملوك لـ OctoHR — غير قابل لإعداد العميل.' : 'Document extraction is OctoHR-owned — not customer-configurable.'}</p>
              ) : null}
            </div>
          ) : null}

          <div className="flex justify-end">
            <Button
              disabled={inactive || working}
              onClick={() => {
                if (moduleId === 'leave') {
                  void save({
                    policy_updates: [
                      {
                        leave_type: 'annual',
                        days_per_year: Number(annualDays) || 30,
                        eligibility_months: Number(eligibility) || 0,
                      },
                    ],
                    optional: {
                      notice_days_default: Number(noticeDays) || 0,
                      require_attachment_for_sick: requireSickAttachment,
                    },
                    sync_calendar: true,
                  })
                } else if (moduleId === 'attendance') {
                  void save({
                    optional: {
                      lateness_grace_minutes: Number(grace) || 15,
                      require_clock_out: requireClockOut,
                      missing_punch_creates_exception: missingPunch,
                      correction_requires_approval: correctionApproval,
                    },
                  })
                } else if (moduleId === 'shifts') {
                  void save({
                    required: { leave_conflict_mode: leaveConflict, shifts_enabled: true },
                    optional: {
                      allow_overnight: allowOvernight,
                      publishing_requires_ack: publishAck,
                      swap_requests_enabled: swapEnabled,
                    },
                    sync_calendar: true,
                  })
                } else if (moduleId === 'documents') {
                  void save({
                    required: {
                      required_document_types: requiredTypes
                        .split(',')
                        .map((t) => t.trim())
                        .filter(Boolean),
                    },
                    optional: {
                      warning_days: { civil_id: Number(civilWarn) || 30, passport: Number(passportWarn) || 60 },
                      renewal_reminder_enabled: renewalOn,
                    },
                    advanced: { evidence_review_required: evidenceReview },
                  })
                } else {
                  void save({
                    required: { template_id: templateId },
                    optional: {
                      default_due_offset_days: Number(dueOffset) || 7,
                      employee_actions_enabled: employeeActions,
                    },
                    advanced: { auto_seed_on_hire: autoSeed },
                  })
                }
              }}
            >
              {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {isAr ? 'حفظ' : 'Save'}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  )
}

export function ModuleCompanyPoliciesCard({
  credentials,
  companyCode,
  locale = 'en',
  availableModules,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  locale?: 'en' | 'ar'
  availableModules: Array<{ key: string; configured?: boolean; effective?: boolean }>
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  const [loading, setLoading] = useState(true)
  const [payload, setPayload] = useState<ModulePoliciesResponse | null>(null)
  const [reason, setReason] = useState('')

  const enabled = useCallback(
    (keys: string[]) =>
      keys.some((key) => {
        const row = availableModules.find((m) => m.key === key)
        return Boolean(row?.configured || row?.effective)
      }),
    [availableModules],
  )

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      setPayload(await getModulePolicies(credentials, companyCode))
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  return (
    <Card id="classic-module-policies" data-ownership="module_company_policies" data-phase="3b" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      <CardHeader>
        <CardTitle>{isAr ? 'سياسات الوحدات' : 'Module company policies'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'كيف يجب أن تعمل الشركة لكل وحدة. العمل اليومي يبقى في مساحات التشغيل.'
            : 'How this company should operate for each module. Day-to-day work stays in operations.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading || !payload ? (
          <p className="flex items-center gap-2 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading policies…'}
          </p>
        ) : (
          (['leave', 'attendance', 'shifts', 'documents', 'onboarding'] as ModuleId[]).map((id) => {
            const policy = payload[id]
            if (!policy) return null
            return (
              <ModulePolicyCard
                key={id}
                moduleId={id}
                policy={policy}
                moduleEnabled={enabled(MODULE_META[id].moduleKeys)}
                locale={locale}
                credentials={credentials}
                companyCode={companyCode}
                reason={reason}
                onReason={setReason}
                onSaved={async () => {
                  await reload()
                  await onChanged()
                }}
                onError={onError}
              />
            )
          })
        )}
      </CardContent>
    </Card>
  )
}
