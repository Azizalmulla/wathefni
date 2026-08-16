/**
 * R5J Workforce Planning workspace — thin client over frozen Wave 6 C7.
 * Actual ≠ baseline ≠ plan ≠ scenario ≠ approved execution.
 * Planned headcount is not actual Wave 5 headcount. Planned cost is not payroll.
 */
import { RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getWorkforcePlanningActualVsPlan,
  getWorkforcePlanningApprovals,
  getWorkforcePlanningBaseline,
  getWorkforcePlanningCost,
  getWorkforcePlanningDemand,
  getWorkforcePlanningExecution,
  getWorkforcePlanningHistory,
  getWorkforcePlanningManager,
  getWorkforcePlanningPlans,
  getWorkforcePlanningProjection,
  getWorkforcePlanningScenarios,
  getWorkforcePlanningWorkspace,
  postWorkforcePlanningJson,
  type WorkforcePlanningWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type WorkforcePlanningWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'plan' | 'scenarios' | 'demand' | 'cost' | 'approvals' | 'execution' | 'history'

function formatKwd(value: unknown, isAr: boolean) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  const formatted = n.toLocaleString(isAr ? 'ar-KW' : 'en-KW', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  })
  return isAr ? `${formatted} د.ك` : `KWD ${formatted}`
}

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'تخطيط القوى العاملة',
        subtitle: 'دورات محكومة وخط أساس مجمّد وسيناريوهات وطلب صريح. القوة العاملة الفعلية ليست خط الأساس وليست الخطة وليست التنفيذ المعتمد.',
        overview: 'نظرة عامة',
        plan: 'الخطة',
        scenarios: 'السيناريوهات',
        demand: 'الطلب',
        cost: 'التكلفة',
        approvals: 'الاعتمادات',
        execution: 'التنفيذ',
        history: 'السجل',
        refresh: 'تحديث',
        live: 'خطط مباشرة',
        drafts: 'مسودات',
        approved: 'سيناريوهات معتمدة',
        demandCount: 'بنود طلب',
        emptyPlans: 'لا توجد خطط قوى عاملة بعد',
        emptyDemand: 'لا يوجد طلب مخطط بعد — النمو والاستبدال والشاغر والتخفيض صريحة.',
        emptyGap: 'لا توجد فجوة معرفة. هذه ليست صفراً مخفياً.',
        emptyScenarios: 'لا توجد سيناريوهات بعد',
        emptyApprovals: 'لا توجد اعتمادات بعد — الاعتماد ليس تغييراً في القوة العاملة الفعلية.',
        emptyExecution: 'لا توجد تسليمات تنفيذ بعد',
        emptyHistory: 'لا يوجد سجل بعد',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        loadError: 'تعذر تحميل هذا القسم. هذه ليست نتيجة فارغة وليست «لا توجد فجوة».',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'تخطيط القوى العاملة غير متاح. هيكل الوظائف إلزامي.',
        boundaries: 'الفعلي ليس خط الأساس. خط الأساس ليس السيناريو. السيناريو ليس التنفيذ المعتمد. الرأس المال البشري المخطط ليس الفعلي.',
        kwdOnly: 'العملة دينار كويتي فقط. التكلفة المخططة تقديرية وليست رواتب نهائية. لا يوجد تحويل عملات.',
        jaRequired: 'هيكل الوظائف إلزامي. لا كتالوج أدوار محلي.',
        plannedCost: 'تكلفة القوى العاملة المخططة/التقديرية — ليست تكلفة رواتب نهائية.',
        createPlan: 'خطة',
        freezeBaseline: 'تجميد خط الأساس (من الفعلي)',
        createScenario: 'سيناريو',
        addDemand: 'طلب صريح',
        submit: 'تقديم (ليس تنفيذاً)',
        approve: 'اعتماد (ليس تغييراً فعلياً)',
        handoff: 'تسليم صريح لمسودة طلب توظيف فقط',
        code: 'الرمز',
        titleEn: 'العنوان (إنجليزي)',
        titleAr: 'العنوان (عربي)',
        quantity: 'الكمية',
        jaProfile: 'ملف هيكل الوظائف',
      }
    : {
        title: 'Workforce Planning',
        subtitle: 'Governed cycles, a frozen baseline, scenarios, and explicit demand. Actual workforce is not the baseline, not the plan, and not approved execution.',
        overview: 'Overview',
        plan: 'Plan',
        scenarios: 'Scenarios',
        demand: 'Demand',
        cost: 'Cost',
        approvals: 'Approvals',
        execution: 'Execution',
        history: 'History',
        refresh: 'Refresh',
        live: 'Live plans',
        drafts: 'Drafts',
        approved: 'Approved scenarios',
        demandCount: 'Demand items',
        emptyPlans: 'No workforce plans yet',
        emptyDemand: 'No planned demand yet — growth, replacement, vacancy, and reduction stay explicit.',
        emptyGap: 'No defined workforce gap. This is not a hidden zero.',
        emptyScenarios: 'No scenarios yet',
        emptyApprovals: 'No approvals yet — approval is not an actual workforce change.',
        emptyExecution: 'No execution handoffs yet',
        emptyHistory: 'No workforce planning history yet',
        emptyHint: 'This is a true empty result — not a load failure.',
        loadError: 'This section could not be loaded. This is not an empty result and not “no workforce gap”.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Workforce Planning is not available. Job Architecture is required.',
        boundaries: 'Actual is not baseline. Baseline is not a scenario. A scenario is not approved execution. Planned headcount is not actual headcount.',
        kwdOnly: 'KWD only. Planned/estimated workforce cost is not finalized payroll cost. Exchange rates are not invented.',
        jaRequired: 'Job Architecture is required. No local role/grade catalog.',
        plannedCost: 'Planned / estimated workforce cost — not finalized payroll cost.',
        createPlan: 'Plan',
        freezeBaseline: 'Freeze baseline (from actual)',
        createScenario: 'Scenario',
        addDemand: 'Explicit demand',
        submit: 'Submit (not execution)',
        approve: 'Approve (not actual change)',
        handoff: 'Explicit draft-requisition handoff only',
        code: 'Code',
        titleEn: 'Title (EN)',
        titleAr: 'Title (AR)',
        quantity: 'Quantity',
        jaProfile: 'Job Architecture profile',
      }
}

export function WorkforcePlanningWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: WorkforcePlanningWorkspaceProps) {
  const { isAr } = useEmployees360Locale()
  const t = copy(isAr)
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<WorkforcePlanningWorkspacePayload | null>(null)
  const [plans, setPlans] = useState<Array<Record<string, unknown>>>([])
  const [scenarios, setScenarios] = useState<Array<Record<string, unknown>>>([])
  const [demand, setDemand] = useState<Array<Record<string, unknown>>>([])
  const [baselineRows, setBaselineRows] = useState<Array<Record<string, unknown>>>([])
  const [approvals, setApprovals] = useState<Array<Record<string, unknown>>>([])
  const [handoffs, setHandoffs] = useState<Array<Record<string, unknown>>>([])
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([])
  const [projection, setProjection] = useState<Record<string, unknown> | null>(null)
  const [cost, setCost] = useState<Record<string, unknown> | null>(null)
  const [actualVsPlan, setActualVsPlan] = useState<Record<string, unknown> | null>(null)
  const [tabError, setTabError] = useState(false)
  const [tabReady, setTabReady] = useState(false)
  const [code, setCode] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [titleAr, setTitleAr] = useState('')
  const [selectedPlan, setSelectedPlan] = useState('')
  const [selectedScenario, setSelectedScenario] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [jaProfileId, setJaProfileId] = useState('')
  const [demandType, setDemandType] = useState('new_headcount')
  const [reasonEn, setReasonEn] = useState('')

  const canManage = permissions.includes('workforce_planning.manage') || permissions.includes('workforce_planning.plan') || role === 'owner'
  const canApprove = permissions.includes('workforce_planning.approve') || permissions.includes('workforce_planning.manage')
  const canExecute = permissions.includes('workforce_planning.execute') || permissions.includes('workforce_planning.manage')
  const canCost = permissions.includes('workforce_planning.cost') || permissions.includes('workforce_planning.manage')
  const managerOnly = String(role || '').toLowerCase() === 'manager'

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      if (managerOnly) {
        const data = await getWorkforcePlanningManager(access)
        setPayload({
          ok: data.ok,
          enabled: data.enabled,
          resource_state: data.resource_state,
          counts: null,
        })
        setDemand(data.demand || [])
        if (data.resource_state === 'unavailable' || data.enabled === false) setUnavailable(true)
      } else {
        const data = await getWorkforcePlanningWorkspace(access)
        setPayload(data)
        if (data.resource_state === 'unavailable' || data.enabled === false) setUnavailable(true)
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
  }, [access, managerOnly, onAccessIssue])

  useEffect(() => {
    void load()
  }, [load])

  const loadTab = useCallback(async () => {
    if (forbidden || unavailable || managerOnly) return
    setTabError(false)
    setTabReady(false)
    try {
      const listed = await getWorkforcePlanningPlans(access)
      setPlans(listed.plans || [])
      if (!selectedPlan && (listed.plans || [])[0]) {
        setSelectedPlan(String((listed.plans || [])[0].plan_id || ''))
      }
      if (selectedPlan) {
        if (tab === 'plan' || tab === 'overview') {
          const base = await getWorkforcePlanningBaseline(access, selectedPlan)
          setBaselineRows(base.rows || [])
        }
        if (tab === 'scenarios' || tab === 'overview' || tab === 'demand' || tab === 'cost') {
          const sc = await getWorkforcePlanningScenarios(access, selectedPlan)
          setScenarios(sc.scenarios || [])
          if (!selectedScenario && (sc.scenarios || [])[0]) {
            setSelectedScenario(String((sc.scenarios || [])[0].scenario_id || ''))
          }
        }
        if (tab === 'demand' || tab === 'overview') {
          const d = await getWorkforcePlanningDemand(access, selectedPlan, selectedScenario || undefined)
          setDemand(d.demand || [])
        }
        if (tab === 'approvals') {
          const a = await getWorkforcePlanningApprovals(access, selectedPlan)
          setApprovals(a.approvals || [])
        }
        if (tab === 'execution') {
          const ex = await getWorkforcePlanningExecution(access, selectedPlan)
          setHandoffs((ex.handoffs as Array<Record<string, unknown>> | undefined) || [])
        }
      }
      if (selectedScenario && (tab === 'scenarios' || tab === 'overview')) {
        const proj = await getWorkforcePlanningProjection(access, selectedScenario)
        setProjection(proj)
        const avp = await getWorkforcePlanningActualVsPlan(access, selectedScenario)
        setActualVsPlan(avp)
      }
      if (selectedScenario && tab === 'cost' && canCost) {
        const c = await getWorkforcePlanningCost(access, selectedScenario)
        setCost(c)
      }
      if (tab === 'history') {
        const h = await getWorkforcePlanningHistory(access, selectedPlan || undefined)
        setHistory(h.history || [])
      }
      setTabReady(true)
    } catch (err) {
      if (err instanceof DashboardApiError && err.status === 403) setForbidden(true)
      else setTabError(true)
    }
  }, [access, canCost, forbidden, managerOnly, selectedPlan, selectedScenario, tab, unavailable])

  useEffect(() => {
    void loadTab()
  }, [loadTab])

  const counts = payload?.counts
  const itemCount = useMemo(() => {
    if (tab === 'plan') return plans.length + baselineRows.length
    if (tab === 'scenarios') return scenarios.length
    if (tab === 'demand') return demand.length
    if (tab === 'cost') return cost ? 1 : 0
    if (tab === 'approvals') return approvals.length
    if (tab === 'execution') return handoffs.length
    if (tab === 'history') return history.length
    if (tab === 'overview') return plans.length || (counts ? 1 : 0)
    return counts ? 1 : 0
  }, [approvals.length, baselineRows.length, cost, counts, demand.length, handoffs.length, history.length, plans.length, scenarios.length, tab])

  const state = resolveListDataState({
    forbidden,
    unavailable,
    loading,
    error: error || tabError,
    itemCount: loading ? 0 : itemCount,
  })

  async function author(path: string, body: Record<string, unknown>) {
    try {
      await postWorkforcePlanningJson(access, path, body)
      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
      await load()
      await loadTab()
    } catch (err) {
      onNotice(err instanceof Error ? err.message : isAr ? 'فشل الحفظ' : 'Save failed', 'error')
    }
  }

  const tabs: Tab[] = managerOnly
    ? ['overview', 'demand']
    : ['overview', 'plan', 'scenarios', 'demand', 'cost', 'approvals', 'execution', 'history']

  return (
    <div className="space-y-6" dir={isAr ? 'rtl' : 'ltr'} data-testid="workforce-planning-workspace">
      <ConfigureInSetupBanner anchor="classic-wave6-workforce-planning" />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t.title}</h1>
          <p className="text-sm text-muted-foreground">{t.subtitle}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t.boundaries}</p>
          <p className="text-xs text-muted-foreground">{t.kwdOnly}</p>
          <p className="text-xs text-muted-foreground">{t.jaRequired}</p>
        </div>
        <Button type="button" variant="outline" onClick={() => void load()}>
          <RefreshCw className="me-2 h-4 w-4" />
          {t.refresh}
        </Button>
      </div>
      <ResourceState
        state={state}
        labels={{ forbidden: t.forbidden, unavailable: t.unavailable, empty: t.emptyHint, error: t.loadError }}
        testId="workforce-planning-workspace-state"
      />
      {!forbidden && !unavailable && !error && (
        <>
          <div className="flex flex-wrap gap-2">
            {tabs.map((id) => (
              <Button key={id} type="button" variant={tab === id ? 'default' : 'outline'} onClick={() => setTab(id)}>
                {t[id]}
              </Button>
            ))}
          </div>
          {tab === 'overview' && counts && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                [t.live, counts.live_plans],
                [t.drafts, counts.draft_plans],
                [t.approved, counts.approved_scenarios],
                [t.demandCount, counts.demand_items],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">{label}</div>
                  <div className="text-2xl font-semibold">{value ?? '—'}</div>
                </div>
              ))}
            </div>
          )}
          {tab === 'overview' && projection && (
            <div className="rounded-lg border p-4 text-sm">
              <div className="font-medium">{isAr ? 'إسقاط الرأس المال البشري (خلفي)' : 'Headcount projection (backend-authoritative)'}</div>
              <div className="text-muted-foreground">
                {String(projection.formula || '')} → {String(projection.planned_headcount ?? '—')}
              </div>
              {actualVsPlan ? (
                <div className="mt-2 text-muted-foreground">
                  {isAr ? 'الفعلي مقابل الخطة' : 'Actual vs plan'}: {String(actualVsPlan.actual_from_canonical ?? '—')} / {String(actualVsPlan.planned ?? '—')}
                </div>
              ) : null}
            </div>
          )}
          {managerOnly && tab === 'demand' && (
            <div className="space-y-2">
              {demand.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyDemand}</p> : null}
              {demand.map((row) => (
                <div key={String(row.demand_id)} className="rounded-lg border p-3 text-sm">
                  <div className="font-medium">{String(row.demand_type)}</div>
                  <div className="text-muted-foreground">{String(row.quantity)} · {String(row.org_unit || '')}</div>
                </div>
              ))}
            </div>
          )}
          {!managerOnly && tab === 'plan' && canManage && (
            <div className="flex flex-wrap gap-2">
              <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.code} />
              <Input value={titleEn} onChange={(e) => setTitleEn(e.target.value)} placeholder={t.titleEn} />
              <Input value={titleAr} onChange={(e) => setTitleAr(e.target.value)} placeholder={t.titleAr} />
              <Button
                type="button"
                onClick={() =>
                  void author('/dashboard/workforce-planning/plans', {
                    code,
                    title_en: titleEn,
                    title_ar: titleAr,
                    currency: 'KWD',
                  })
                }
              >
                {t.createPlan}
              </Button>
              {selectedPlan ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author(`/dashboard/workforce-planning/plans/${selectedPlan}/baseline`, {
                      as_of_date: new Date().toISOString().slice(0, 10),
                    })
                  }
                >
                  {t.freezeBaseline}
                </Button>
              ) : null}
            </div>
          )}
          {!managerOnly && tab === 'plan' && (
            <div className="space-y-2">
              {plans.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyPlans}</p> : null}
              {plans.map((row) => (
                <button
                  key={String(row.plan_id)}
                  type="button"
                  className="block w-full rounded-lg border p-3 text-start text-sm"
                  onClick={() => setSelectedPlan(String(row.plan_id))}
                >
                  <div className="font-medium">{String(row.title_en)} / {String(row.title_ar)}</div>
                  <div className="text-muted-foreground">{String(row.status_label_en)} · {String(row.horizon)} · KWD</div>
                </button>
              ))}
              {baselineRows.length ? (
                <p className="text-xs text-muted-foreground">
                  {isAr ? 'خط الأساس مجمّد ولا يُعاد كتابته من الفعلي اللاحق.' : 'Frozen baseline is not rewritten by later actual workforce changes.'}
                </p>
              ) : null}
            </div>
          )}
          {!managerOnly && tab === 'scenarios' && canManage && selectedPlan && (
            <div className="flex flex-wrap gap-2">
              <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.code} />
              <Input value={titleEn} onChange={(e) => setTitleEn(e.target.value)} placeholder={t.titleEn} />
              <Input value={titleAr} onChange={(e) => setTitleAr(e.target.value)} placeholder={t.titleAr} />
              <Button
                type="button"
                onClick={() =>
                  void author(`/dashboard/workforce-planning/plans/${selectedPlan}/scenarios`, {
                    code,
                    scenario_type: 'base',
                    title_en: titleEn,
                    title_ar: titleAr,
                  })
                }
              >
                {t.createScenario}
              </Button>
            </div>
          )}
          {!managerOnly && tab === 'scenarios' && (
            <div className="space-y-2">
              {scenarios.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyScenarios}</p> : null}
              {scenarios.map((row) => (
                <button
                  key={String(row.scenario_id)}
                  type="button"
                  className="block w-full rounded-lg border p-3 text-start text-sm"
                  onClick={() => setSelectedScenario(String(row.scenario_id))}
                >
                  <div className="font-medium">{String(row.title_en)} / {String(row.title_ar)}</div>
                  <div className="text-muted-foreground">{String(row.type_label_en)} · {String(row.status_label_en)}</div>
                </button>
              ))}
            </div>
          )}
          {!managerOnly && tab === 'demand' && canManage && selectedPlan && selectedScenario && (
            <div className="flex flex-wrap gap-2">
              <Input value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder={t.quantity} />
              <Input value={jaProfileId} onChange={(e) => setJaProfileId(e.target.value)} placeholder={t.jaProfile} />
              <Input value={reasonEn} onChange={(e) => setReasonEn(e.target.value)} placeholder={isAr ? 'السبب' : 'Reason'} />
              <select className="rounded-md border px-2 py-1 text-sm" value={demandType} onChange={(e) => setDemandType(e.target.value)}>
                <option value="new_headcount">{isAr ? 'رأس مال بشري جديد' : 'New headcount'}</option>
                <option value="replacement">{isAr ? 'استبدال' : 'Replacement'}</option>
                <option value="planned_vacancy">{isAr ? 'شاغر مخطط' : 'Planned vacancy'}</option>
                <option value="planned_reduction">{isAr ? 'تخفيض مخطط' : 'Planned reduction'}</option>
                <option value="role_mix_change">{isAr ? 'تغيير مزيج الأدوار' : 'Role-mix change'}</option>
              </select>
              <Button
                type="button"
                onClick={() =>
                  void author('/dashboard/workforce-planning/demand', {
                    plan_id: selectedPlan,
                    scenario_id: selectedScenario,
                    demand_type: demandType,
                    quantity: Number(quantity),
                    ja_profile_id: jaProfileId,
                    reason_en: reasonEn,
                  })
                }
              >
                {t.addDemand}
              </Button>
            </div>
          )}
          {!managerOnly && tab === 'demand' && (
            <div className="space-y-2">
              {demand.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyDemand}</p> : null}
              {demand.map((row) => (
                <div key={String(row.demand_id)} className="rounded-lg border p-3 text-sm">
                  <div className="font-medium">{String(row.type_label_en)} / {String(row.type_label_ar)}</div>
                  <div className="text-muted-foreground">
                    {String(row.quantity)} · {String(row.org_unit || '')} · {t.emptyDemand}
                  </div>
                </div>
              ))}
            </div>
          )}
          {!managerOnly && tab === 'cost' && (
            <div className="rounded-lg border p-4 text-sm">
              <div className="font-medium">{t.plannedCost}</div>
              {canCost && cost ? (
                <div className="text-muted-foreground">{formatKwd(cost.planned_estimated_cost, isAr)}</div>
              ) : (
                <p className="text-muted-foreground">{t.forbidden}</p>
              )}
            </div>
          )}
          {!managerOnly && tab === 'approvals' && canApprove && selectedPlan && selectedScenario && (
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => void author(`/dashboard/workforce-planning/plans/${selectedPlan}/submit`, {})}>
                {t.submit}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  void author('/dashboard/workforce-planning/approve', {
                    plan_id: selectedPlan,
                    scenario_id: selectedScenario,
                    decision: 'approved',
                  })
                }
              >
                {t.approve}
              </Button>
            </div>
          )}
          {!managerOnly && tab === 'approvals' && (
            <div className="space-y-2">
              {approvals.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyApprovals}</p> : null}
              {approvals.map((row) => (
                <div key={String(row.approval_id)} className="rounded-lg border p-3 text-sm">
                  {String(row.decision)} · {String(row.approver_key)}
                </div>
              ))}
            </div>
          )}
          {!managerOnly && tab === 'execution' && canExecute && demand[0] && selectedPlan && selectedScenario && (
            <Button
              type="button"
              onClick={() =>
                void author('/dashboard/workforce-planning/handoffs', {
                  plan_id: selectedPlan,
                  scenario_id: selectedScenario,
                  demand_id: String(demand[0].demand_id),
                })
              }
            >
              {t.handoff}
            </Button>
          )}
          {!managerOnly && tab === 'execution' && (
            <div className="space-y-2">
              {handoffs.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyExecution}</p> : null}
              {handoffs.map((row) => (
                <div key={String(row.handoff_id)} className="rounded-lg border p-3 text-sm">
                  {String(row.target_authority)} · {String(row.status)}
                </div>
              ))}
            </div>
          )}
          {!managerOnly && tab === 'history' && (
            <div className="space-y-2">
              {history.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyHistory}</p> : null}
              {history.map((row, idx) => (
                <div key={`${String(row.action)}-${idx}`} className="rounded-lg border p-3 text-sm">
                  {String(row.action)} · {String(row.entity_type || '')}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
