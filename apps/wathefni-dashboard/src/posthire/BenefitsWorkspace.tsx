/**
 * R5F Benefits workspace — thin client over frozen Wave 6 C3.
 * Eligible ≠ enrolled ≠ coverage active ≠ provider confirmed ≠ payroll deducted.
 */
import { RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { useUrlBackedTab, URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getBenefitsContributions,
  getBenefitsCoverage,
  getBenefitsEnrollments,
  getBenefitsHandoffs,
  getBenefitsHistory,
  getBenefitsPlans,
  getBenefitsWorkspace,
  postBenefitsJson,
  type BenefitsWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type BenefitsWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'plans' | 'enrollment' | 'coverage' | 'contributions' | 'history'

const WORKSPACE_TABS = URL_BACKED_WORKSPACE_TABS.benefits as readonly Tab[]

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'إدارة المزايا',
        subtitle: 'الخطط والأهلية والتسجيل والتغطية — ليست مطالبات وليست استقطاع رواتب.',
        overview: 'نظرة عامة',
        plans: 'الخطط',
        enrollment: 'التسجيل',
        coverage: 'التغطية',
        contributions: 'المساهمات',
        history: 'السجل',
        refresh: 'تحديث',
        active: 'خطط نشطة',
        action: 'موظفون يحتاجون إجراءً',
        windows: 'نوافذ تسجيل',
        upcoming: 'تغييرات سارية قادمة',
        exceptions: 'استثناءات مزود',
        emptyPlans: 'لا توجد خطط بعد',
        emptyEnroll: 'لا توجد تسجيلات',
        emptyCoverage: 'لا توجد تغطية',
        emptyContrib: 'لا توجد مساهمات',
        emptyHistory: 'لا يوجد سجل مزايا بعد',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        loadError: 'تعذر تحميل هذا القسم. هذه ليست نتيجة فارغة.',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'المزايا غير متاحة لهذه الشركة.',
        boundaries: 'الأهلية ليست تسجيلاً. الانتخاب ليس تغطية. التنازل ليس عدم أهلية. المساهمة ليست استقطاعاً.',
        createPlan: 'خطة',
        evaluate: 'تقييم أهلية',
        elect: 'انتخاب',
        waive: 'تنازل',
        confirm: 'تفعيل تغطية',
        prepare: 'بدء تسجيل',
        handoff: 'تسليم رواتب (ليس خصماً)',
        emptyHandoff: 'لا يوجد تسليم رواتب',
        employeeKey: 'مفتاح الموظف',
        titleEn: 'العنوان (إنجليزي)',
        titleAr: 'العنوان (عربي)',
        code: 'الرمز',
        reason: 'السبب',
      }
    : {
        title: 'Benefits Administration',
        subtitle: 'Plans, eligibility, enrollment, and coverage — not claims and not payroll deductions.',
        overview: 'Overview',
        plans: 'Plans',
        enrollment: 'Enrollment',
        coverage: 'Coverage',
        contributions: 'Contributions',
        history: 'History',
        refresh: 'Refresh',
        active: 'Active plans',
        action: 'Employees requiring action',
        windows: 'Enrollment windows',
        upcoming: 'Upcoming effective changes',
        exceptions: 'Provider exceptions',
        emptyPlans: 'No plans yet',
        emptyEnroll: 'No enrollments',
        emptyCoverage: 'No coverage',
        emptyContrib: 'No contributions',
        emptyHistory: 'No benefits history yet',
        emptyHint: 'This is a true empty result — not a load failure.',
        loadError: 'This section could not be loaded. This is not an empty result.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Benefits is not available for this company.',
        boundaries: 'Eligible is not enrolled. Election is not coverage. Waiver is not ineligibility. Contribution is not a deduction.',
        createPlan: 'Plan',
        evaluate: 'Evaluate eligibility',
        elect: 'Elect',
        waive: 'Waive',
        confirm: 'Activate coverage',
        prepare: 'Start enrollment',
        handoff: 'Payroll handoff (not a deduction)',
        emptyHandoff: 'No payroll handoff',
        employeeKey: 'Employee key',
        titleEn: 'Title (EN)',
        titleAr: 'Title (AR)',
        code: 'Code',
        reason: 'Reason',
      }
}

export function BenefitsWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: BenefitsWorkspaceProps) {
  const isAr = useEmployees360Locale() === 'ar'
  const t = copy(isAr)
  const [tab, setTab] = useUrlBackedTab<Tab>('benefits', WORKSPACE_TABS, 'overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<BenefitsWorkspacePayload | null>(null)
  const [plans, setPlans] = useState<Array<Record<string, unknown>>>([])
  const [enrollments, setEnrollments] = useState<Array<Record<string, unknown>>>([])
  const [coverage, setCoverage] = useState<Array<Record<string, unknown>>>([])
  const [contributions, setContributions] = useState<Array<Record<string, unknown>>>([])
  const [handoffs, setHandoffs] = useState<Array<Record<string, unknown>>>([])
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([])
  const [tabError, setTabError] = useState(false)
  const [tabReady, setTabReady] = useState(false)
  const [code, setCode] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [titleAr, setTitleAr] = useState('')
  const [empKey, setEmpKey] = useState('')
  const [planId, setPlanId] = useState('')
  const [reason, setReason] = useState('')

  const canManage = hasActorPermission(permissions, 'benefits.manage')
  const canEnroll = hasActorPermission(permissions, 'benefits.enroll') || canManage
  const managerOnly = String(role || '').toLowerCase() === 'manager'

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      const data = await getBenefitsWorkspace(access)
      setPayload(data)
      if (data.resource_state === 'unavailable' || data.enabled === false) {
        setUnavailable(true)
      }
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      if (err instanceof DashboardApiError) {
        if (err.status === 403) setForbidden(true)
        else if (err.status === 404) setUnavailable(true)
        else setError(true)
      } else {
        setError(true)
      }
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void load()
  }, [load])

  const loadTab = useCallback(async () => {
    setTabError(false)
    setTabReady(false)
    try {
      if (tab === 'plans') {
        const data = await getBenefitsPlans(access)
        setPlans(data.plans || [])
      } else if (tab === 'enrollment') {
        const data = await getBenefitsEnrollments(access)
        setEnrollments(data.enrollments || [])
      } else if (tab === 'coverage') {
        const data = await getBenefitsCoverage(access)
        setCoverage(data.coverage || [])
      } else if (tab === 'contributions') {
        const [contrib, handoff] = await Promise.all([
          getBenefitsContributions(access),
          getBenefitsHandoffs(access),
        ])
        setContributions(contrib.contributions || [])
        setHandoffs(handoff.handoffs || [])
      } else if (tab === 'history') {
        const data = await getBenefitsHistory(access)
        setHistory(data.events || data.enrollments || [])
      }
      setTabReady(true)
    } catch {
      setTabError(true)
      setTabReady(false)
      onNotice(t.loadError, 'error')
    }
  }, [access, onNotice, t.loadError, tab])

  useEffect(() => {
    if (tab !== 'overview') void loadTab()
  }, [loadTab, tab])

  const counts = payload?.counts
  const state = resolveListDataState({
    forbidden: forbidden || managerOnly,
    unavailable,
    loading,
    error,
    itemCount: counts ? 1 : 0,
  })

  function tabEmpty(label: string, count: number) {
    if (tabError) {
      return (
        <ResourceState
          kind="error"
          locale={isAr ? 'ar' : 'en'}
          title={t.loadError}
          onRetry={() => void loadTab()}
          testId="benefits-tab-state"
        />
      )
    }
    if (tabReady && count === 0) return <p className="text-sm text-muted-foreground">{label}</p>
    return null
  }

  const tabs = useMemo(() => {
    const all: Array<{ id: Tab; label: string }> = [
      { id: 'overview', label: t.overview },
      { id: 'plans', label: t.plans },
      { id: 'enrollment', label: t.enrollment },
      { id: 'coverage', label: t.coverage },
      { id: 'contributions', label: t.contributions },
      { id: 'history', label: t.history },
    ]
    return all
  }, [t])

  async function author(path: string, body: Record<string, unknown>) {
    try {
      await postBenefitsJson(access, path, body)
      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
      await load()
      await loadTab()
    } catch (err) {
      onNotice(err instanceof Error ? err.message : 'Error', 'error')
    }
  }

  return (
    <div className="space-y-6" dir={isAr ? 'rtl' : 'ltr'}>
      <ConfigureInSetupBanner anchor="classic-wave6-benefits" />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t.title}</h1>
          <p className="text-sm text-muted-foreground">{t.subtitle}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t.boundaries}</p>
        </div>
        <Button type="button" variant="outline" onClick={() => void load()}>
          <RefreshCw className="h-4 w-4" />
          {t.refresh}
        </Button>
      </div>

      {state !== 'ready' ? (
        <ResourceState
          kind={state}
          locale={isAr ? 'ar' : 'en'}
          title={
            state === 'forbidden'
              ? t.forbidden
              : state === 'unavailable'
                ? t.unavailable
                : state === 'empty'
                  ? t.emptyEnroll
                  : state === 'error'
                    ? isAr
                      ? 'تعذر تحميل المزايا'
                      : 'Could not load Benefits'
                    : undefined
          }
          detail={state === 'empty' ? t.emptyHint : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="benefits-workspace-state"
        />
      ) : (
        <>
        <div className="flex flex-wrap gap-2">
          {tabs.map((item) => (
            <Button key={item.id} type="button" variant={tab === item.id ? 'default' : 'outline'} onClick={() => setTab(item.id)}>
              {item.label}
            </Button>
          ))}
        </div>

        {tab === 'overview' ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              [t.active, counts?.active_plans],
              [t.action, counts?.employees_requiring_action],
              [t.windows, counts?.open_windows],
              [t.upcoming, counts?.upcoming_effective_changes],
              [t.exceptions, counts?.coverage_provider_exceptions],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-lg border border-border/70 p-3">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="text-2xl font-semibold">{value ?? '—'}</div>
              </div>
            ))}
          </div>
        ) : null}

        {tab === 'plans' ? (
          <section className="space-y-3">
            {canManage ? (
              <div className="grid gap-2 sm:grid-cols-4">
                <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.code} />
                <Input value={titleEn} onChange={(e) => setTitleEn(e.target.value)} placeholder={t.titleEn} />
                <Input value={titleAr} onChange={(e) => setTitleAr(e.target.value)} placeholder={t.titleAr} />
                <Button
                  type="button"
                  onClick={() =>
                    void (async () => {
                      const created = await postBenefitsJson<Record<string, unknown>>(access, '/dashboard/benefits/plans', {
                        code,
                        category: 'medical',
                        title_en: titleEn,
                        title_ar: titleAr,
                        status: 'published',
                        reason: reason || 'catalog',
                      })
                      const id = String(
                        (created as { plan?: { plan_id?: string }; stable_id?: string }).plan?.plan_id ||
                          (created as { stable_id?: string }).stable_id ||
                          '',
                      )
                      if (id) {
                        await postBenefitsJson(access, '/dashboard/benefits/eligibility/rules', {
                          plan_id: id,
                          code: `${code || 'OPEN'}-ELIG`,
                          title_en: 'Open eligibility',
                          title_ar: 'أهلية مفتوحة',
                          criteria: {},
                        })
                      }
                      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
                      await load()
                      await loadTab()
                    })().catch((err) => onNotice(err instanceof Error ? err.message : 'Error', 'error'))
                  }
                >
                  {t.createPlan}
                </Button>
              </div>
            ) : null}
            {tabEmpty(t.emptyPlans, plans.length)}
            <ul className="space-y-2">
              {plans.map((item) => (
                <li key={String(item.plan_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(item.title_en || item.code)} · v{String(item.effective_version)} · {String(item.status)}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'enrollment' ? (
          <section className="space-y-3">
            {canEnroll ? (
              <div className="grid gap-2 sm:grid-cols-4">
                <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
                <Input value={planId} onChange={(e) => setPlanId(e.target.value)} placeholder="plan_id" />
                <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.reason} />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author('/dashboard/benefits/enrollments/prepare', {
                      employee_key: empKey,
                      plan_id: planId,
                    })
                  }
                >
                  {t.prepare}
                </Button>
              </div>
            ) : null}
            {tabEmpty(t.emptyEnroll, enrollments.length)}
            <ul className="space-y-2">
              {enrollments.map((row) => (
                <li key={String(row.enrollment_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.employee_key)} · {String(row.title_en || row.plan_id)} · {String(row.status)}
                  {row.waived ? ` · ${isAr ? 'متنازل' : 'waived'}` : ''}
                  {row.coverage_active ? ` · ${isAr ? 'تغطية سارية' : 'coverage active'}` : ''}
                  {canEnroll && (row.status === 'enrollment_open' || row.status === 'eligible') ? (
                    <>
                      <Button
                        type="button"
                        variant="ghost"
                        className="ms-2 h-7 px-2"
                        onClick={() =>
                          void author(`/dashboard/benefits/enrollments/${row.enrollment_id}/elect`, {
                            waive: false,
                            tier: 'employee_only',
                            reason: reason || 'hr elect',
                          })
                        }
                      >
                        {t.elect}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        className="ms-2 h-7 px-2"
                        onClick={() =>
                          void author(`/dashboard/benefits/enrollments/${row.enrollment_id}/elect`, {
                            waive: true,
                            reason: reason || 'hr waive',
                          })
                        }
                      >
                        {t.waive}
                      </Button>
                    </>
                  ) : null}
                  {canEnroll && row.status === 'elected' ? (
                    <Button
                      type="button"
                      variant="ghost"
                      className="ms-2 h-7 px-2"
                      onClick={() =>
                        void author(`/dashboard/benefits/enrollments/${row.enrollment_id}/confirm`, {
                          coverage_start: new Date().toISOString().slice(0, 10),
                          provider_confirmed: false,
                        })
                      }
                    >
                      {t.confirm}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'coverage' ? (
          <section className="space-y-3">
            {tabEmpty(t.emptyCoverage, coverage.length)}
            <ul className="space-y-2">
              {coverage.map((row) => (
                <li key={String(row.coverage_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.employee_key)} · {String(row.title_en || row.plan_id)} · {String(row.status)} · v
                  {String(row.plan_version)} · {row.provider_confirmed ? (isAr ? 'مؤكد من المزود' : 'provider confirmed') : isAr ? 'داخلي فقط' : 'internal only'}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'contributions' ? (
          <section className="space-y-3">
            {tabEmpty(t.emptyContrib, contributions.length)}
            <ul className="space-y-2">
              {contributions.map((row) => (
                <li key={String(row.contribution_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.kind)} · {String(row.mode)} · {String(row.amount ?? row.percent ?? '—')} {String(row.currency || '')} ·{' '}
                  {isAr ? 'مساهمة وليست خصماً' : 'contribution, not a deduction'}
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">{t.handoff}</p>
            {tabEmpty(t.emptyHandoff, handoffs.length)}
            <ul className="space-y-2">
              {handoffs.map((row) => (
                <li key={String(row.handoff_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.employee_key)} · {isAr ? 'لم يُطبَّق على الرواتب' : 'not applied to payroll'}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'history' ? (
          <section className="space-y-3">
            {tabEmpty(t.emptyHistory, history.length)}
            <ul className="space-y-2">
              {history.map((row, index) => (
                <li key={String(row.audit_id || row.enrollment_id || index)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.action || row.status || row.title_en || 'event')}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        </>
      )}
    </div>
  )
}
