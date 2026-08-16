import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Loader2, Save, Search, Users } from 'lucide-react'

import { ConfigureInOpsLink } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { dashboardPageHref } from '@/lib/setupConsoleOwnership'

import {
  getEmployeeAppAccessPolicy,
  previewEmployeeAppAccessDrilldown,
  previewEmployeeAppAccessPolicy,
  resolveEmployeeAppAccessAttention,
  searchEmployeeAppAccessEmployees,
  updateEmployeeAppAccessPolicy,
  type EmployeeAppAccessEmployee,
  type EmployeeAppAccessPolicy,
  type EmployeeAppAccessPreview,
} from './api'
import type { SetupCredentials } from './types'

type UxMode = 'everyone' | 'departments' | 'employees'
type DrillBucket = 'gain' | 'lose' | 'unchanged'

const PAGE_SIZE = 40

export function EmployeeAppAccessPolicyCard({
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
  const [policy, setPolicy] = useState<EmployeeAppAccessPolicy | null>(null)
  const [uxMode, setUxMode] = useState<UxMode>('employees')
  const [selectedOrgUnitIds, setSelectedOrgUnitIds] = useState<string[]>([])
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [reason, setReason] = useState('')
  const [preview, setPreview] = useState<EmployeeAppAccessPreview | null>(null)
  const [confirmLarge, setConfirmLarge] = useState(false)
  const [employeeQuery, setEmployeeQuery] = useState('')
  const [deptFilter, setDeptFilter] = useState('')
  const [employeeHits, setEmployeeHits] = useState<EmployeeAppAccessEmployee[]>([])
  const [employeeTotal, setEmployeeTotal] = useState(0)
  const [employeeOffset, setEmployeeOffset] = useState(0)
  const [employeeHasMore, setEmployeeHasMore] = useState(false)
  const [searching, setSearching] = useState(false)
  const [drillBucket, setDrillBucket] = useState<DrillBucket | null>(null)
  const [drillQuery, setDrillQuery] = useState('')
  const [drillRows, setDrillRows] = useState<EmployeeAppAccessEmployee[]>([])
  const [drillTotal, setDrillTotal] = useState(0)
  const [drillOffset, setDrillOffset] = useState(0)
  const [drillHasMore, setDrillHasMore] = useState(false)
  const [drillLoading, setDrillLoading] = useState(false)

  const departmentOptions = policy?.departments || []

  const selectedDeptCount = useMemo(() => {
    const map = new Map(
      departmentOptions.map((d) => [d.org_unit_id || d.id || '', d.active_employee_count || 0]),
    )
    return selectedOrgUnitIds.reduce((sum, id) => sum + (map.get(id) || 0), 0)
  }, [departmentOptions, selectedOrgUnitIds])

  const hydrate = useCallback((next: EmployeeAppAccessPolicy) => {
    setPolicy(next)
    const mode = (next.ux_mode as UxMode) || 'employees'
    setUxMode(mode === 'everyone' || mode === 'departments' || mode === 'employees' ? mode : 'employees')
    setSelectedOrgUnitIds([...(next.selected_department_org_unit_ids || [])])
    setSelectedKeys([...(next.selected_employee_keys || [])])
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      hydrate(await getEmployeeAppAccessPolicy(credentials, companyCode))
    } catch (error) {
      onError(error)
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials, hydrate, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    if (uxMode !== 'employees' || !moduleEnabled) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      setSearching(true)
      void searchEmployeeAppAccessEmployees(credentials, companyCode, {
        q: employeeQuery,
        limit: PAGE_SIZE,
        offset: employeeOffset,
        department_org_unit_id: deptFilter || undefined,
      })
        .then((result) => {
          if (cancelled) return
          setEmployeeHits(result.employees || [])
          setEmployeeTotal(result.total_count || 0)
          setEmployeeHasMore(Boolean(result.has_more))
        })
        .catch((error) => {
          if (!cancelled) onError(error)
        })
        .finally(() => {
          if (!cancelled) setSearching(false)
        })
    }, 220)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [companyCode, credentials, deptFilter, employeeOffset, employeeQuery, moduleEnabled, onError, uxMode])

  function proposalPayload() {
    return {
      ux_mode: uxMode,
      selected_department_org_unit_ids: uxMode === 'departments' ? selectedOrgUnitIds : [],
      selected_employee_keys: uxMode === 'employees' ? selectedKeys : [],
    }
  }

  async function runPreview() {
    setWorking(true)
    setConfirmLarge(false)
    setDrillBucket(null)
    try {
      setPreview(await previewEmployeeAppAccessPolicy(credentials, companyCode, proposalPayload()))
    } catch (error) {
      onError(error)
    } finally {
      setWorking(false)
    }
  }

  async function loadDrill(bucket: DrillBucket, offset = 0, append = false) {
    setDrillLoading(true)
    setDrillBucket(bucket)
    try {
      const result = await previewEmployeeAppAccessDrilldown(credentials, companyCode, {
        ...proposalPayload(),
        bucket,
        q: drillQuery,
        limit: PAGE_SIZE,
        offset,
      })
      setDrillRows((current) => (append ? [...current, ...(result.employees || [])] : result.employees || []))
      setDrillTotal(result.total_count || 0)
      setDrillOffset(offset)
      setDrillHasMore(Boolean(result.has_more))
    } catch (error) {
      onError(error)
    } finally {
      setDrillLoading(false)
    }
  }

  async function apply(forceConfirm = false) {
    const trimmed = reason.trim()
    if (!trimmed) {
      onError(new Error(isAr ? 'أدخل سبب التغيير قبل التطبيق.' : 'Enter a reason before applying the access policy.'))
      return
    }
    setWorking(true)
    try {
      const result = await updateEmployeeAppAccessPolicy(credentials, companyCode, {
        ...proposalPayload(),
        apply_reconcile: true,
        confirm_large_impact: forceConfirm || confirmLarge,
        reason: trimmed,
      })
      if (result.policy) hydrate(result.policy as EmployeeAppAccessPolicy)
      else await reload()
      setPreview(null)
      setConfirmLarge(false)
      setDrillBucket(null)
      await onChanged()
    } catch (error) {
      if (preview?.requires_large_removal_confirm && !confirmLarge) setConfirmLarge(true)
      onError(error)
    } finally {
      setWorking(false)
    }
  }

  async function removeArchivedAttention() {
    const archived = policy?.policy_attention?.archived_org_unit_ids || []
    const missing = policy?.policy_attention?.missing_org_unit_ids || []
    const remove = [...archived, ...missing]
    if (!remove.length) return
    const trimmed = reason.trim() || (isAr ? 'إزالة أقسام مؤرشفة/مفقودة من سياسة الوصول' : 'Remove archived/missing departments from access policy')
    setWorking(true)
    try {
      const result = await resolveEmployeeAppAccessAttention(credentials, companyCode, {
        remove_org_unit_ids: remove,
        reason: trimmed,
      })
      if (result.policy) hydrate(result.policy)
      else await reload()
      await onChanged()
    } catch (error) {
      onError(error)
    } finally {
      setWorking(false)
    }
  }

  function toggleDepartment(orgUnitId: string) {
    setSelectedOrgUnitIds((current) =>
      current.includes(orgUnitId) ? current.filter((item) => item !== orgUnitId) : [...current, orgUnitId],
    )
    setPreview(null)
  }

  function toggleEmployee(key: string) {
    setSelectedKeys((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]))
    setPreview(null)
  }

  function selectVisiblePage(select: boolean) {
    const keys = employeeHits.map((e) => e.employee_key).filter(Boolean)
    setSelectedKeys((current) => {
      if (select) return Array.from(new Set([...current, ...keys]))
      const drop = new Set(keys)
      return current.filter((k) => !drop.has(k))
    })
    setPreview(null)
  }

  const attention = policy?.policy_attention
  const reasonLabels: Record<string, { en: string; ar: string }> = {
    selected_department: { en: 'In selected department', ar: 'ضمن قسم مختار' },
    selected_employee: { en: 'Explicitly selected', ar: 'محدد صراحة' },
    everyone_policy: { en: 'Everyone policy', ar: 'سياسة الجميع' },
    no_longer_in_selected_department: { en: 'No longer in selected department', ar: 'لم يعد ضمن الأقسام المختارة' },
    no_longer_explicitly_selected: { en: 'No longer explicitly selected', ar: 'لم يعد محدداً صراحة' },
    unchanged_in_scope: { en: 'Still in scope', ar: 'ما زال ضمن النطاق' },
    unchanged_out_of_scope: { en: 'Still out of scope', ar: 'ما زال خارج النطاق' },
  }

  return (
    <Card
      id="classic-app-access"
      data-ownership="employee_app_access_policy"
      data-phase="2c"
      dir={isAr ? 'rtl' : 'ltr'}
      lang={locale}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-4 w-4" aria-hidden />
          {isAr ? 'تطبيق الموظف · من يمكنه الدخول؟' : 'Employee App · Who should have access?'}
        </CardTitle>
        <CardDescription>
          {isAr
            ? 'تشغيل/إيقاف التطبيق من الوحدات أعلاه. هذه السياسة تجيب: من يدخل؟ ما يراه بعد الدخول تضبطه صلاحيات الوحدات.'
            : 'Turn the app on/off under Modules above. This policy answers who can enter. What they see inside stays controlled by module entitlements.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!moduleEnabled ? (
          <p className="rounded-2xl border border-amber-200/70 bg-amber-50/60 px-4 py-3 text-sm text-amber-950">
            {isAr
              ? 'تطبيق الموظف متوقف — لا دعوات ولا وصول. فعّله من الوحدات أولاً.'
              : 'Employee App is off — no invites and no access. Enable it under Modules first.'}
          </p>
        ) : null}

        {attention?.needs_attention ? (
          <div className="rounded-2xl border border-amber-300/80 bg-amber-50/70 px-4 py-3 text-sm text-amber-950" data-policy-attention>
            <p className="flex items-start gap-2 font-medium">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{isAr ? attention.message_ar || 'السياسة تحتاج مراجعة' : attention.message_en || 'Policy needs attention'}</span>
            </p>
            {(attention.archived_org_unit_ids?.length || attention.missing_org_unit_ids?.length) ? (
              <Button type="button" size="sm" variant="secondary" className="mt-3" disabled={working} onClick={() => void removeArchivedAttention()}>
                {isAr ? 'إزالة الأقسام المؤرشفة/المفقودة' : 'Remove archived/missing departments'}
              </Button>
            ) : null}
            {attention.ambiguous_names?.length ? (
              <p className="mt-2 text-xs">
                {isAr
                  ? 'أسماء غامضة — اختر الأقسام بالمعرّف أدناه دون تخمين تلقائي.'
                  : 'Ambiguous names — choose departments by ID below; nothing was guessed automatically.'}
              </p>
            ) : null}
          </div>
        ) : null}

        {loading || !policy ? (
          <p className="flex items-center gap-2 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading access policy…'}
          </p>
        ) : (
          <>
            <div className="grid gap-2 sm:grid-cols-3">
              {(
                [
                  {
                    key: 'everyone' as const,
                    title: isAr ? 'الجميع' : 'Everyone',
                    body: isAr
                      ? 'كل الموظفين النشطين. الموظفون الجدد يصبحون مؤهلين تلقائياً.'
                      : 'All active employees. Future active hires become eligible automatically.',
                  },
                  {
                    key: 'departments' as const,
                    title: isAr ? 'أقسام محددة' : 'Specific departments',
                    body: isAr
                      ? 'حسب الوحدات التنظيمية الثابتة. إعادة التسمية لا تكسر السياسة.'
                      : 'By stable org units. Renames do not break the policy.',
                  },
                  {
                    key: 'employees' as const,
                    title: isAr ? 'موظفون محددون' : 'Specific employees',
                    body: isAr
                      ? 'قائمة صريحة فقط. الموظفون الجدد لا يحصلون على وصول تلقائي.'
                      : 'Explicit list only. Future hires get no automatic access.',
                  },
                ] as const
              ).map((option) => (
                <button
                  key={option.key}
                  type="button"
                  disabled={!moduleEnabled || working}
                  className={cn(
                    'rounded-2xl border px-4 py-3 text-left transition',
                    uxMode === option.key
                      ? 'border-accent/45 bg-accent-soft/50'
                      : 'border-line/60 bg-white/45 hover:border-accent/25',
                  )}
                  onClick={() => {
                    setUxMode(option.key)
                    setPreview(null)
                    setConfirmLarge(false)
                    setDrillBucket(null)
                    setEmployeeOffset(0)
                  }}
                >
                  <span className="block text-sm font-semibold">{option.title}</span>
                  <span className="mt-1 block text-xs leading-5 text-subtle">{option.body}</span>
                </button>
              ))}
            </div>

            {uxMode === 'departments' ? (
              <div className="space-y-2 rounded-2xl border border-line/55 bg-white/45 px-4 py-3">
                <p className="text-xs font-medium text-subtle">
                  {isAr
                    ? `الأقسام المختارة · تقريباً ${selectedDeptCount} موظفاً نشطاً متأثراً`
                    : `Selected departments · about ${selectedDeptCount} active employees affected`}
                </p>
                {departmentOptions.length === 0 ? (
                  <p className="text-sm text-subtle">
                    {isAr ? 'لا توجد أقسام تنظيمية بعد — أضفها في الهيكل أولاً.' : 'No org departments yet — add them in organization first.'}
                  </p>
                ) : (
                  <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto" data-dept-picker="org-unit-id">
                    {departmentOptions.map((dept) => {
                      const id = dept.org_unit_id || dept.id || ''
                      if (!id) return null
                      const checked = selectedOrgUnitIds.includes(id)
                      const archived = (dept.status || '').toLowerCase() === 'archived'
                      return (
                        <label
                          key={id}
                          className={cn(
                            'inline-flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-xs',
                            checked ? 'border-accent/40 bg-accent-soft/60' : 'border-line/60 bg-white/70',
                            archived && 'opacity-70',
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={!moduleEnabled || working}
                            onChange={() => toggleDepartment(id)}
                          />
                          <span>
                            {dept.name}
                            <span className="text-subtle"> · {dept.active_employee_count || 0}</span>
                            {archived ? <span className="text-amber-800"> · {isAr ? 'مؤرشف' : 'archived'}</span> : null}
                          </span>
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
            ) : null}

            {uxMode === 'employees' ? (
              <div className="space-y-3 rounded-2xl border border-line/55 bg-white/45 px-4 py-3" data-employee-picker="paged">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-medium text-subtle">
                  <span>{isAr ? `المحددون: ${selectedKeys.length}` : `Selected: ${selectedKeys.length}`}</span>
                  <span>{isAr ? `النتائج: ${employeeHits.length} من ${employeeTotal}` : `Showing ${employeeHits.length} of ${employeeTotal}`}</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <label className="flex items-center gap-2 rounded-2xl border border-line/70 bg-white/80 px-3 py-2">
                    <Search className="h-4 w-4 text-subtle" aria-hidden />
                    <Input
                      className="border-0 bg-transparent p-0 shadow-none focus-visible:ring-0"
                      value={employeeQuery}
                      disabled={!moduleEnabled || working}
                      onChange={(event) => {
                        setEmployeeQuery(event.target.value)
                        setEmployeeOffset(0)
                      }}
                      placeholder={isAr ? 'ابحث بالاسم أو الهاتف أو القسم' : 'Search by name, phone, or department'}
                    />
                    {searching ? <Loader2 className="h-4 w-4 animate-spin text-subtle" /> : null}
                  </label>
                  <select
                    className="rounded-2xl border border-line/70 bg-white/80 px-3 py-2 text-sm"
                    value={deptFilter}
                    disabled={!moduleEnabled || working}
                    onChange={(event) => {
                      setDeptFilter(event.target.value)
                      setEmployeeOffset(0)
                    }}
                    aria-label={isAr ? 'تصفية بالقسم' : 'Filter by department'}
                  >
                    <option value="">{isAr ? 'كل الأقسام' : 'All departments'}</option>
                    {departmentOptions.map((dept) => {
                      const id = dept.org_unit_id || dept.id || ''
                      return (
                        <option key={id} value={id}>
                          {dept.name}
                        </option>
                      )
                    })}
                  </select>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="secondary" disabled={!moduleEnabled || working || !employeeHits.length} onClick={() => selectVisiblePage(true)}>
                    {isAr ? 'تحديد الصفحة' : 'Select page'}
                  </Button>
                  <Button type="button" size="sm" variant="secondary" disabled={!moduleEnabled || working || !employeeHits.length} onClick={() => selectVisiblePage(false)}>
                    {isAr ? 'إلغاء تحديد الصفحة' : 'Deselect page'}
                  </Button>
                </div>
                <div className="max-h-64 space-y-1 overflow-y-auto" style={{ contain: 'content' }}>
                  {employeeHits.map((emp) => {
                    const checked = selectedKeys.includes(emp.employee_key)
                    return (
                      <label
                        key={emp.employee_key}
                        className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-line/45 px-3 py-2 text-sm"
                      >
                        <span className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={!moduleEnabled || working}
                            onChange={() => toggleEmployee(emp.employee_key)}
                          />
                          <span>
                            <span className="font-medium">{emp.name || emp.employee_key}</span>
                            <span className="mt-0.5 block text-xs text-subtle">
                              {[emp.department, emp.phone].filter(Boolean).join(' · ') || emp.employee_key}
                            </span>
                          </span>
                        </span>
                        {emp.app_access_enabled ? (
                          <span className="text-[11px] text-emerald-700">{isAr ? 'مفعّل' : 'Enabled'}</span>
                        ) : null}
                      </label>
                    )
                  })}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={!moduleEnabled || working || employeeOffset === 0}
                    onClick={() => setEmployeeOffset((o) => Math.max(0, o - PAGE_SIZE))}
                  >
                    {isAr ? 'السابق' : 'Previous'}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={!moduleEnabled || working || !employeeHasMore}
                    onClick={() => setEmployeeOffset((o) => o + PAGE_SIZE)}
                  >
                    {isAr ? 'التالي' : 'Next'}
                  </Button>
                </div>
              </div>
            ) : null}

            <label className="flex flex-col gap-1.5 text-xs font-medium text-subtle">
              {isAr ? 'سبب التغيير (للتدقيق)' : 'Reason for change (audit)'}
              <Input
                value={reason}
                disabled={!moduleEnabled || working}
                onChange={(event) => setReason(event.target.value)}
                placeholder={isAr ? 'مثال: إطلاق التطبيق لقسم العمليات' : 'e.g. Launch app for Operations'}
              />
            </label>

            {preview ? (
              <div className="space-y-3 rounded-2xl border border-sky-200/70 bg-sky-50/50 px-4 py-3 text-sm" data-access-preview>
                <p className="font-medium text-text">{isAr ? preview.message_ar : preview.message_en}</p>
                <div className="grid gap-2 sm:grid-cols-3 text-xs text-subtle">
                  <button type="button" className="rounded-xl border border-line/50 bg-white/70 px-3 py-2 text-left" onClick={() => void loadDrill('gain')}>
                    {isAr ? `سيكتسبون: ${preview.will_gain_access}` : `Will gain: ${preview.will_gain_access}`}
                  </button>
                  <button type="button" className="rounded-xl border border-line/50 bg-white/70 px-3 py-2 text-left" onClick={() => void loadDrill('lose')}>
                    {isAr ? `سيفقدون: ${preview.will_lose_access}` : `Will lose: ${preview.will_lose_access}`}
                  </button>
                  <button type="button" className="rounded-xl border border-line/50 bg-white/70 px-3 py-2 text-left" onClick={() => void loadDrill('unchanged')}>
                    {isAr ? `بلا تغيير: ${preview.unchanged}` : `Unchanged: ${preview.unchanged}`}
                  </button>
                </div>
                {preview.requires_large_removal_confirm ? (
                  <label className="mt-1 flex items-start gap-2 text-sm text-amber-950">
                    <input
                      type="checkbox"
                      checked={confirmLarge}
                      disabled={working}
                      onChange={(event) => setConfirmLarge(event.target.checked)}
                    />
                    <span>
                      {isAr
                        ? `أؤكد إزالة الوصول عن ${preview.will_lose_access} موظفاً وتسجيل الخروج من الجلسات النشطة (${preview.active_sessions_affected}).`
                        : `I confirm removing access from ${preview.will_lose_access} employees and signing out active sessions (${preview.active_sessions_affected}).`}
                    </span>
                  </label>
                ) : null}

                {drillBucket ? (
                  <div className="rounded-xl border border-line/50 bg-white/80 p-3" data-access-drilldown>
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-medium">
                        {isAr ? `تفاصيل · ${drillBucket} · ${drillTotal}` : `Drill-down · ${drillBucket} · ${drillTotal}`}
                      </span>
                      <label className="flex items-center gap-2">
                        <Search className="h-3.5 w-3.5 text-subtle" />
                        <Input
                          className="h-8 w-40 border-line/60"
                          value={drillQuery}
                          onChange={(event) => setDrillQuery(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') void loadDrill(drillBucket, 0, false)
                          }}
                          placeholder={isAr ? 'بحث' : 'Search'}
                        />
                      </label>
                    </div>
                    <div className="max-h-48 space-y-1 overflow-y-auto text-xs">
                      {drillLoading ? (
                        <p className="flex items-center gap-2 text-subtle">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading…'}
                        </p>
                      ) : (
                        drillRows.map((row) => (
                          <div key={row.employee_key} className="rounded-lg border border-line/40 px-2 py-1.5">
                            <div className="font-medium">{row.name || row.employee_key}</div>
                            <div className="text-subtle">
                              {[row.department, reasonLabels[row.reason || '']?.[isAr ? 'ar' : 'en'] || row.reason]
                                .filter(Boolean)
                                .join(' · ')}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                    {drillHasMore ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        className="mt-2"
                        disabled={drillLoading}
                        onClick={() => void loadDrill(drillBucket, drillOffset + PAGE_SIZE, true)}
                      >
                        {isAr ? 'المزيد' : 'Load more'}
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" variant="secondary" disabled={!moduleEnabled || working} onClick={() => void runPreview()}>
                {working ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {isAr ? 'معاينة الأثر' : 'Preview impact'}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={!moduleEnabled || working || Boolean(preview?.requires_large_removal_confirm && !confirmLarge)}
                onClick={() => void apply(false)}
              >
                {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {isAr ? 'تطبيق السياسة' : 'Apply policy'}
              </Button>
              <ConfigureInOpsLink
                href={dashboardPageHref('employees')}
                label={isAr ? 'الحالات اليومية في الموظفين' : 'Day-to-day status in Employees'}
              />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
