/**
 * R5I Compensation Planning workspace — thin client over frozen Wave 6 C6.
 * Plan ≠ salary change ≠ payroll application ≠ paid. Eligible ≠ increase.
 * Grade ≠ salary band. Recommendation ≠ approval. Finalized ≠ applied.
 */
import { Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getCompensationPlanningApprovals,
  getCompensationPlanningCycles,
  getCompensationPlanningFinalized,
  getCompensationPlanningHandoffs,
  getCompensationPlanningHistory,
  getCompensationPlanningManager,
  getCompensationPlanningRecommendations,
  getCompensationPlanningWorksheet,
  getCompensationPlanningWorkspace,
  postCompensationPlanningJson,
  type CompensationPlanningWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type CompensationPlanningWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'worksheet' | 'calibration' | 'approvals' | 'finalized' | 'history'

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
        title: 'تخطيط التعويضات',
        subtitle: 'دورة محكومة وأهلية مجمّدة ونطاقات مرتبطة بهيكل الوظائف. الخطة ليست تغييراً في الراتب وليست رواتب وليست دفعاً.',
        overview: 'نظرة عامة',
        worksheet: 'ورقة التخطيط',
        calibration: 'المعايرة',
        approvals: 'الاعتمادات',
        finalized: 'النهائي',
        history: 'السجل',
        refresh: 'تحديث',
        live: 'دورات مباشرة',
        drafts: 'مسودات',
        finalizedCount: 'دورات نهائية',
        pending: 'اعتمادات تحتاج انتباهاً',
        emptyCycles: 'لا توجد دورات تعويضات بعد',
        emptyWorksheet: 'لا توجد صفوف أهلية بعد — الأهلية ليست زيادة.',
        emptyCalibration: 'لا توجد توصيات للمعايرة بعد',
        emptyApprovals: 'لا توجد اعتمادات بعد',
        emptyFinalized: 'لا توجد قرارات نهائية بعد — النهائي ليس تطبيقاً.',
        emptyHistory: 'لا يوجد سجل بعد',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        loadError: 'تعذر تحميل هذا القسم. هذه ليست نتيجة فارغة.',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'تخطيط التعويضات غير متاح. هيكل الوظائف إلزامي.',
        boundaries: 'الخطة ليست تغييراً في الراتب. الأهلية ليست زيادة. الدرجة ليست نطاقاً. التوصية ليست اعتماداً. النهائي ليس تطبيقاً.',
        kwdOnly: 'العملة دينار كويتي فقط. لا يوجد تحويل عملات.',
        createCycle: 'دورة',
        launch: 'إطلاق (تجميد الأهلية)',
        recommend: 'توصية (ليست اعتماداً)',
        calibrate: 'معايرة (الأصل محفوظ)',
        approve: 'اعتماد (ليس راتباً)',
        finalize: 'إنهاء (ليس تطبيقاً)',
        handoff: 'تسليم صريح',
        code: 'الرمز',
        titleEn: 'العنوان (إنجليزي)',
        titleAr: 'العنوان (عربي)',
        employeeKey: 'مفتاح الموظف',
        amount: 'المبلغ (د.ك)',
        jaRequired: 'هيكل الوظائف إلزامي. لا درجات محلية.',
      }
    : {
        title: 'Compensation Planning',
        subtitle: 'Governed cycles, frozen eligibility, and JA-linked bands. A plan is not a salary change, not payroll, and not payment.',
        overview: 'Overview',
        worksheet: 'Worksheet',
        calibration: 'Calibration',
        approvals: 'Approvals',
        finalized: 'Finalized',
        history: 'History',
        refresh: 'Refresh',
        live: 'Live cycles',
        drafts: 'Drafts',
        finalizedCount: 'Finalized cycles',
        pending: 'Approvals needing attention',
        emptyCycles: 'No compensation cycles yet',
        emptyWorksheet: 'No eligible rows yet — eligible is not an increase.',
        emptyCalibration: 'No recommendations to calibrate yet',
        emptyApprovals: 'No approvals yet',
        emptyFinalized: 'No finalized decisions yet — finalized is not applied.',
        emptyHistory: 'No compensation history yet',
        emptyHint: 'This is a true empty result — not a load failure.',
        loadError: 'This section could not be loaded. This is not an empty result.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Compensation Planning is not available. Job Architecture is required.',
        boundaries: 'A plan is not a salary change. Eligible is not an increase. Grade is not a salary band. A recommendation is not an approval. Finalized is not applied.',
        kwdOnly: 'KWD only. Exchange rates are not invented.',
        createCycle: 'Cycle',
        launch: 'Launch (freeze eligibility)',
        recommend: 'Recommend (not approval)',
        calibrate: 'Calibrate (original preserved)',
        approve: 'Approve (not salary)',
        finalize: 'Finalize (not applied)',
        handoff: 'Explicit handoff',
        code: 'Code',
        titleEn: 'Title (EN)',
        titleAr: 'Title (AR)',
        employeeKey: 'Employee key',
        amount: 'Amount (KWD)',
        jaRequired: 'Job Architecture is required. No local grades.',
      }
}

export function CompensationPlanningWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: CompensationPlanningWorkspaceProps) {
  const isAr = useEmployees360Locale() === 'ar'
  const t = copy(isAr)
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<CompensationPlanningWorkspacePayload | null>(null)
  const [cycles, setCycles] = useState<Array<Record<string, unknown>>>([])
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([])
  const [recommendations, setRecommendations] = useState<Array<Record<string, unknown>>>([])
  const [approvals, setApprovals] = useState<Array<Record<string, unknown>>>([])
  const [decisions, setDecisions] = useState<Array<Record<string, unknown>>>([])
  const [handoffs, setHandoffs] = useState<Array<Record<string, unknown>>>([])
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([])
  const [tabError, setTabError] = useState(false)
  const [tabReady, setTabReady] = useState(false)
  const [code, setCode] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [titleAr, setTitleAr] = useState('')
  const [selectedCycle, setSelectedCycle] = useState('')
  const [employeeKey, setEmployeeKey] = useState('')
  const [amount, setAmount] = useState('')
  const [originalRecId, setOriginalRecId] = useState('')
  const [decisionId, setDecisionId] = useState('')

  const canManage = hasActorPermission(permissions, 'comp_planning.manage')
  const canRecommend = hasActorPermission(permissions, 'comp_planning.recommend') || canManage
  const canCalibrate = hasActorPermission(permissions, 'comp_planning.calibrate') || canManage
  const canApprove = hasActorPermission(permissions, 'comp_planning.approve') || canManage
  const canFinalize = hasActorPermission(permissions, 'comp_planning.finalize') || canManage
  const managerOnly = String(role || '').toLowerCase() === 'manager'

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      if (managerOnly) {
        const data = await getCompensationPlanningManager(access)
        setPayload({
          ok: data.ok,
          enabled: data.enabled,
          resource_state: data.resource_state,
          counts: null,
        })
        setRows(data.rows || [])
        if (data.resource_state === 'unavailable' || data.enabled === false) setUnavailable(true)
      } else {
        const data = await getCompensationPlanningWorkspace(access)
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
      if (tab === 'overview' || tab === 'worksheet' || tab === 'calibration' || tab === 'approvals' || tab === 'finalized') {
        const data = await getCompensationPlanningCycles(access)
        setCycles(data.cycles || [])
        if (!selectedCycle && (data.cycles || [])[0]) {
          setSelectedCycle(String((data.cycles || [])[0].cycle_id || ''))
        }
      }
      if (selectedCycle && (tab === 'worksheet' || tab === 'overview')) {
        const data = await getCompensationPlanningWorksheet(access, selectedCycle)
        setRows(data.rows || [])
      }
      if (selectedCycle && tab === 'calibration') {
        const data = await getCompensationPlanningRecommendations(access, selectedCycle)
        setRecommendations(data.recommendations || [])
      }
      if (selectedCycle && tab === 'approvals') {
        const data = await getCompensationPlanningApprovals(access, selectedCycle)
        setApprovals(data.approvals || [])
      }
      if (selectedCycle && tab === 'finalized') {
        const [fin, hand] = await Promise.all([
          getCompensationPlanningFinalized(access, selectedCycle),
          getCompensationPlanningHandoffs(access, selectedCycle),
        ])
        setDecisions(fin.decisions || [])
        setHandoffs(hand.handoffs || [])
      }
      if (tab === 'history') {
        const data = await getCompensationPlanningHistory(access, selectedCycle || undefined)
        setHistory(data.history || [])
      }
      setTabReady(true)
    } catch (err) {
      if (err instanceof DashboardApiError && err.status === 403) setForbidden(true)
      else setTabError(true)
    }
  }, [access, forbidden, managerOnly, selectedCycle, tab, unavailable])

  useEffect(() => {
    void loadTab()
  }, [loadTab])

  const counts = payload?.counts
  const itemCount = useMemo(() => {
    if (tab === 'worksheet') return rows.length
    if (tab === 'calibration') return recommendations.length
    if (tab === 'approvals') return approvals.length
    if (tab === 'finalized') return decisions.length + handoffs.length
    if (tab === 'history') return history.length
    if (tab === 'overview') return cycles.length || (counts ? 1 : 0)
    return counts ? 1 : 0
  }, [approvals.length, counts, cycles.length, decisions.length, handoffs.length, history.length, recommendations.length, rows.length, tab])

  const state = resolveListDataState({
    forbidden,
    unavailable,
    loading,
    error,
    itemCount: loading ? 0 : itemCount,
  })

  async function author(path: string, body: Record<string, unknown>) {
    try {
      await postCompensationPlanningJson(access, path, body)
      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
      await load()
      await loadTab()
    } catch (err) {
      onNotice(err instanceof Error ? err.message : isAr ? 'فشل الحفظ' : 'Save failed', 'error')
    }
  }

  const tabs: Tab[] = managerOnly
    ? ['overview', 'worksheet']
    : ['overview', 'worksheet', 'calibration', 'approvals', 'finalized', 'history']

  return (
    <div className="space-y-6" dir={isAr ? 'rtl' : 'ltr'} data-testid="compensation-planning-workspace">
      <ConfigureInSetupBanner anchor="classic-wave6-comp-planning" />
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
                  ? t.emptyCycles
                  : state === 'error'
                    ? t.loadError
                    : undefined
          }
          detail={state === 'empty' ? t.emptyHint : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="compensation-planning-workspace-state"
        />
      ) : (
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
                [t.live, counts.live_cycles],
                [t.drafts, counts.draft_cycles],
                [t.finalizedCount, counts.finalized_cycles],
                [t.pending, counts.approvals_needing_attention],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">{label}</div>
                  <div className="text-2xl font-semibold">{value ?? '—'}</div>
                </div>
              ))}
            </div>
          )}
          {tab === 'overview' && payload?.budget_usage && (
            <div className="rounded-lg border p-4 text-sm">
              <div className="font-medium">{isAr ? 'استخدام الميزانية (خلفي)' : 'Budget usage (backend-authoritative)'}</div>
              <div className="text-muted-foreground">
                {formatKwd(payload.budget_usage.recommended, isAr)} / {formatKwd(payload.budget_usage.allocated, isAr)}
              </div>
            </div>
          )}
          {managerOnly && tab === 'worksheet' && (
            <div className="space-y-2">
              {rows.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyWorksheet}</p> : null}
              {rows.map((row) => (
                <div key={String(row.employee_key)} className="rounded-lg border p-3 text-sm">
                  <div className="font-medium">{String(row.employee_key)}</div>
                  <div className="text-muted-foreground">
                    {formatKwd(row.current_base, isAr)} · {t.emptyWorksheet}
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === 'overview' && !managerOnly && (
            <div className="space-y-4">
              {canManage && (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.code} />
                  <Input value={titleEn} onChange={(e) => setTitleEn(e.target.value)} placeholder={t.titleEn} />
                  <Input value={titleAr} onChange={(e) => setTitleAr(e.target.value)} placeholder={t.titleAr} />
                  <Button
                    type="button"
                    onClick={() =>
                      void author('/dashboard/compensation-planning/cycles', {
                        code,
                        title_en: titleEn,
                        title_ar: titleAr,
                        currency: 'KWD',
                      })
                    }
                  >
                    {t.createCycle}
                  </Button>
                </div>
              )}
              {tabError ? (
                <ResourceState
                  kind="error"
                  locale={isAr ? 'ar' : 'en'}
                  title={t.loadError}
                  onRetry={() => void loadTab()}
                  testId="compensation-planning-tab-state"
                />
              ) : null}
              {tabReady && cycles.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyCycles}</p> : null}
              {cycles.map((row) => (
                <div key={String(row.cycle_id)} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
                  <div>
                    <div className="font-medium">{isAr ? String(row.title_ar || row.title_en) : String(row.title_en || row.title_ar)}</div>
                    <div className="text-xs text-muted-foreground">
                      {String(isAr ? row.status_label_ar : row.status_label_en)} · KWD
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" onClick={() => { setSelectedCycle(String(row.cycle_id)); setTab('worksheet') }}>
                      {t.worksheet}
                    </Button>
                    {canManage && row.status === 'draft' ? (
                      <Button type="button" onClick={() => void author(`/dashboard/compensation-planning/cycles/${row.cycle_id}/launch`, { population: [] })}>
                        {t.launch}
                      </Button>
                    ) : null}
                    {canFinalize && (row.status === 'launched' || row.status === 'calibrating') ? (
                      <Button type="button" variant="outline" onClick={() => void author(`/dashboard/compensation-planning/cycles/${row.cycle_id}/finalize`, {})}>
                        {t.finalize}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === 'worksheet' && !managerOnly && (
            <div className="space-y-4">
              {canRecommend && selectedCycle ? (
                <div className="grid gap-2 sm:grid-cols-3">
                  <Input value={employeeKey} onChange={(e) => setEmployeeKey(e.target.value)} placeholder={t.employeeKey} />
                  <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={t.amount} />
                  <Button
                    type="button"
                    onClick={() =>
                      void author('/dashboard/compensation-planning/recommendations', {
                        cycle_id: selectedCycle,
                        employee_key: employeeKey,
                        recommendation_type: 'merit_increase',
                        amount: Number(amount),
                        rationale: 'worksheet',
                      })
                    }
                  >
                    {t.recommend}
                  </Button>
                </div>
              ) : null}
              {tabReady && rows.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyWorksheet}</p> : null}
              {rows.map((row) => (
                <div key={String(row.employee_key)} className="rounded-lg border p-3 text-sm">
                  <div className="font-medium">{String(row.employee_key)}</div>
                  <div className="text-muted-foreground">
                    {formatKwd(row.current_base, isAr)} · JA {String(row.ja_grade_id || '—')} · {t.emptyWorksheet}
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === 'calibration' && !managerOnly && (
            <div className="space-y-4">
              {canCalibrate && selectedCycle ? (
                <div className="grid gap-2 sm:grid-cols-3">
                  <Input value={originalRecId} onChange={(e) => setOriginalRecId(e.target.value)} placeholder="original recommendation id" />
                  <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={t.amount} />
                  <Button
                    type="button"
                    onClick={() =>
                      void author('/dashboard/compensation-planning/calibrate', {
                        cycle_id: selectedCycle,
                        original_recommendation_id: originalRecId,
                        amount: Number(amount),
                        rationale: 'calibration',
                      })
                    }
                  >
                    {t.calibrate}
                  </Button>
                </div>
              ) : null}
              {tabReady && recommendations.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyCalibration}</p> : null}
              {recommendations.map((row) => (
                <div key={String(row.recommendation_id)} className="rounded-lg border p-3 text-sm">
                  <div className="font-medium">{String(row.layer)} · {formatKwd(row.amount, isAr)}</div>
                  <div className="text-muted-foreground">{String(row.employee_key)} · {String(row.actor_key)}</div>
                </div>
              ))}
            </div>
          )}
          {tab === 'approvals' && !managerOnly && (
            <div className="space-y-4">
              {canApprove && selectedCycle ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input value={originalRecId} onChange={(e) => setOriginalRecId(e.target.value)} placeholder="recommendation id" />
                  <Button
                    type="button"
                    onClick={() =>
                      void author('/dashboard/compensation-planning/approve', {
                        cycle_id: selectedCycle,
                        recommendation_id: originalRecId,
                        decision: 'approved',
                      })
                    }
                  >
                    {t.approve}
                  </Button>
                </div>
              ) : null}
              {tabReady && approvals.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyApprovals}</p> : null}
              {approvals.map((row) => (
                <div key={String(row.approval_id)} className="rounded-lg border p-3 text-sm">
                  {String(row.decision)} · {String(row.approver_key)}
                </div>
              ))}
            </div>
          )}
          {tab === 'finalized' && !managerOnly && (
            <div className="space-y-4">
              {canManage && selectedCycle ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input value={decisionId} onChange={(e) => setDecisionId(e.target.value)} placeholder="decision id" />
                  <Button
                    type="button"
                    onClick={() =>
                      void author('/dashboard/compensation-planning/handoffs', {
                        cycle_id: selectedCycle,
                        decision_id: decisionId,
                        target_authority: 'employment_change_c1',
                      })
                    }
                  >
                    {t.handoff}
                  </Button>
                </div>
              ) : null}
              {tabReady && decisions.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyFinalized}</p> : null}
              {decisions.map((row) => (
                <div key={String(row.decision_id)} className="rounded-lg border p-3 text-sm">
                  {String(row.employee_key)} · {formatKwd(row.approved_amount, isAr)} · {isAr ? 'النهائي ليس تطبيقاً' : 'finalized ≠ applied'}
                </div>
              ))}
              {handoffs.map((row) => (
                <div key={String(row.handoff_id)} className="rounded-lg border p-3 text-sm">
                  {String(row.target_authority)} · {isAr ? 'التسليم ليس تنفيذاً' : 'handoff ≠ execution'}
                </div>
              ))}
            </div>
          )}
          {tab === 'history' && !managerOnly && (
            <div className="space-y-2">
              {tabReady && history.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyHistory}</p> : null}
              {history.map((row, idx) => (
                <div key={String(row.audit_id || idx)} className="rounded-lg border p-3 text-sm">
                  {String(row.action)} · {String(row.entity_type)} · {String(row.created_at || '')}
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
    </div>
  )
}
