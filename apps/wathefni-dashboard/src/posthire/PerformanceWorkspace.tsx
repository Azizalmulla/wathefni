/**
 * R5B Performance workspace — thin client over frozen Wave 4 C1–C4.
 * Backend remains authoritative for progress, rollup, review status, and ratings.
 * Talent / HiPo / 9-box vocabulary is forbidden here.
 */
import { Loader2, RefreshCw, Target } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/field'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getPerformanceCalibrationDetail,
  getPerformanceCheckIns,
  getPerformanceCycles,
  getPerformanceObjective,
  getPerformanceOkrAlignment,
  getPerformanceReview,
  getPerformanceWorkspace,
  postPerformanceJson,
  type PerformanceWorkspacePayload,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type PerformanceWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'goals' | 'reviews' | 'calibration' | 'development'

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'الأداء',
        subtitle: 'الأهداف والمراجعات والمعايرة والتطوير — دون مواهب أو إمكانات عالية.',
        overview: 'نظرة عامة',
        goals: 'الأهداف',
        reviews: 'المراجعات',
        calibration: 'المعايرة',
        development: 'التطوير',
        refresh: 'تحديث',
        activeCycle: 'الدورة النشطة',
        noActiveCycle: 'لا توجد دورة مراجعة نشطة',
        objectivesOpen: 'أهداف مفتوحة',
        managerPending: 'مراجعات المدير المعلّقة',
        selfPending: 'المراجعات الذاتية المعلّقة',
        checkIns: 'متابعات مفتوحة',
        developmentOpen: 'إجراءات تطوير مفتوحة',
        emptyGoals: 'لا توجد أهداف بعد',
        emptyReviews: 'لا توجد مراجعات بعد',
        emptyCalibration: 'لا توجد جلسات معايرة',
        emptyDevelopment: 'لا توجد إجراءات تطوير',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'الأداء غير متاح لهذه الشركة.',
        talentOff: 'المواهب منفصلة وغير ظاهرة هنا. التقييم العالي لا يعني إمكانات عالية.',
        learningOff: 'التعلم غير مطلوب. إكمال التعلم لا يُغلق التطوير تلقائياً.',
        config: 'السياسات في الإعداد',
        progress: 'التقدم',
        unknownProgress: 'غير محسوب بعد',
        sealed: 'نهائي مختوم',
        preCal: 'قبل المعايرة',
        calibrated: 'بعد المعايرة',
        overdue: 'متأخر',
        upcoming: 'الاستحقاقات القادمة',
        createGoal: 'هدف جديد',
        addKr: 'نتيجة رئيسية',
        activate: 'تفعيل',
        owner: 'المالك',
        okrCycle: 'دورة النتائج الرئيسية',
        noOkrCycle: 'لا توجد دورة نتائج رئيسية نشطة',
        createOkrCycle: 'دورة نتائج رئيسية جديدة',
        showAlignment: 'عرض المحاذاة',
        hideAlignment: 'إخفاء المحاذاة',
        alignmentHint: 'المحاذاة لا تنقل النسبة. تقدّم الابن لا يصبح 70٪ للأب.',
        updateThread: 'تحديث',
        confidence: 'الثقة (اختيارية — ليست تقدماً)',
        addUpdate: 'إضافة تحديث',
        measure: 'المقياس',
        target: 'المستهدف',
        createCycle: 'دورة جديدة',
        launch: 'إطلاق وتجميد اللقطة',
        close: 'إغلاق',
        submitReview: 'إرسال المراجعة',
        rating: 'التقييم',
        rationale: 'المبرر',
        createDev: 'إجراء تطوير',
      }
    : {
        title: 'Performance',
        subtitle: 'Goals, reviews, calibration, and development — not Talent or HiPo.',
        overview: 'Overview',
        goals: 'Goals',
        reviews: 'Reviews',
        calibration: 'Calibration',
        development: 'Development',
        refresh: 'Refresh',
        activeCycle: 'Active cycle',
        noActiveCycle: 'No active review cycle',
        objectivesOpen: 'Open objectives',
        managerPending: 'Pending manager reviews',
        selfPending: 'Pending self-reviews',
        checkIns: 'Open check-ins',
        developmentOpen: 'Open development actions',
        emptyGoals: 'No goals yet',
        emptyReviews: 'No reviews yet',
        emptyCalibration: 'No calibration sessions',
        emptyDevelopment: 'No development actions',
        emptyHint: 'This is a true empty result — not a load failure.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Performance is not available for this company.',
        talentOff: 'Talent is separate and hidden here. A high rating is not HiPo.',
        learningOff: 'Learning is not required. Learning completion does not close development.',
        config: 'Policies live in Setup',
        progress: 'Progress',
        unknownProgress: 'Not computed yet',
        sealed: 'Sealed final',
        preCal: 'Pre-calibration',
        calibrated: 'Calibrated',
        overdue: 'Overdue',
        upcoming: 'Upcoming due dates',
        createGoal: 'New objective',
        addKr: 'Key result',
        activate: 'Activate',
        owner: 'Owner',
        okrCycle: 'OKR cycle',
        noOkrCycle: 'No active OKR cycle',
        createOkrCycle: 'New OKR cycle',
        showAlignment: 'Show alignment',
        hideAlignment: 'Hide alignment',
        alignmentHint: 'Alignment does not inherit scores. A child at 70% does not make the parent 70%.',
        updateThread: 'Update',
        confidence: 'Confidence (optional — not progress)',
        addUpdate: 'Add update',
        measure: 'Measure',
        target: 'Target',
        createCycle: 'New cycle',
        launch: 'Launch and freeze snapshot',
        close: 'Close',
        submitReview: 'Submit review',
        rating: 'Rating',
        rationale: 'Rationale',
        createDev: 'Development action',
      }
}

export function PerformanceWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: PerformanceWorkspaceProps) {
  const isAr = useEmployees360Locale() === 'ar'
  const t = copy(isAr)
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<PerformanceWorkspacePayload | null>(null)

  const canCalibrate = hasActorPermission(permissions, 'performance.calibrate')
  const canManage = hasActorPermission(permissions, 'performance.manage')
  const managerOnly = String(role || '').toLowerCase() === 'manager'

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      const data = await getPerformanceWorkspace(access)
      setPayload(data)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      if (err instanceof DashboardApiError) {
        if (err.status === 403) {
          const code = String((err.body as { error?: string } | undefined)?.error || '')
          if (code.includes('permission') || code.includes('forbidden')) setForbidden(true)
          else setUnavailable(true)
        } else if (err.status === 404) {
          setUnavailable(true)
        } else {
          setError(true)
        }
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

  const counts = payload?.counts
  const state = resolveListDataState({
    forbidden,
    unavailable,
    loading,
    error,
    itemCount: counts ? 1 : 0,
  })

  const tabs = useMemo(() => {
    const items: Array<{ id: Tab; label: string }> = [
      { id: 'overview', label: t.overview },
      { id: 'goals', label: t.goals },
      { id: 'reviews', label: t.reviews },
      { id: 'development', label: t.development },
    ]
    if (canCalibrate && !managerOnly) items.splice(3, 0, { id: 'calibration', label: t.calibration })
    return items
  }, [canCalibrate, managerOnly, t])

  return (
    <div dir={isAr ? 'rtl' : 'ltr'} lang={isAr ? 'ar' : 'en'} className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            <h2 className="text-xl font-semibold">{t.title}</h2>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t.subtitle}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="ms-2">{t.refresh}</span>
        </Button>
      </div>

      <ConfigureInSetupBanner anchor="classic-wave4-performance" />

      {state !== 'ready' ? (
        <ResourceState
          kind={state === 'empty' ? 'empty' : state}
          locale={isAr ? 'ar' : 'en'}
          title={forbidden ? t.forbidden : unavailable ? t.unavailable : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="performance-workspace-state"
        />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {tabs.map((item) => (
              <Button
                key={item.id}
                type="button"
                size="sm"
                variant={tab === item.id ? 'default' : 'outline'}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </Button>
            ))}
          </div>

          {tab === 'overview' ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-border/70 p-4">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">{t.okrCycle}</div>
                {payload?.active_okr_cycle ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <div className="font-medium">
                      {isAr
                        ? payload.active_okr_cycle.name_ar || payload.active_okr_cycle.name_en
                        : payload.active_okr_cycle.name_en}
                    </div>
                    <StatusPill>{String(payload.active_okr_cycle.status || '')}</StatusPill>
                  </div>
                ) : (
                  <div className="mt-2 text-sm text-muted-foreground">{t.noOkrCycle}</div>
                )}
              </div>
              <div className="rounded-xl border border-border/70 p-4">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">{t.activeCycle}</div>
                {payload?.active_cycle ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <div className="font-medium">
                      {isAr
                        ? payload.active_cycle.name_ar || payload.active_cycle.name_en
                        : payload.active_cycle.name_en}
                    </div>
                    <StatusPill>{String(payload.active_cycle.status || '')}</StatusPill>
                  </div>
                ) : (
                  <div className="mt-2 text-sm text-muted-foreground">{t.noActiveCycle}</div>
                )}
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {[
                  [t.objectivesOpen, counts?.objectives_open],
                  [t.managerPending, counts?.manager_reviews_pending],
                  [t.selfPending, counts?.self_reviews_pending],
                  [t.overdue, counts?.overdue_reviews],
                  [t.checkIns, counts?.open_check_ins],
                  [t.developmentOpen, counts?.open_development_actions],
                ].map(([label, value]) => (
                  <div key={String(label)} className="rounded-xl border border-border/70 p-4">
                    <div className="text-xs text-muted-foreground">{label}</div>
                    <div className="mt-1 text-2xl font-semibold">{value ?? '—'}</div>
                  </div>
                ))}
              </div>
              {payload?.upcoming && (payload.upcoming.due_self || payload.upcoming.due_manager) ? (
                <div className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
                  {t.upcoming}: {String(payload.upcoming.due_self || '—')} / {String(payload.upcoming.due_manager || '—')}
                </div>
              ) : null}
              <p className="text-sm text-muted-foreground">{t.talentOff}</p>
              <p className="text-sm text-muted-foreground">{t.learningOff}</p>
            </div>
          ) : null}

          {tab === 'goals' ? (
            <GoalsPane
              access={access}
              isAr={isAr}
              t={t}
              onNotice={onNotice}
              canManage={canManage}
              canAdminCycles={canManage && !managerOnly}
            />
          ) : null}
          {tab === 'reviews' ? (
            <ReviewsPane
              access={access}
              isAr={isAr}
              t={t}
              onNotice={onNotice}
              canManage={canManage && !managerOnly}
            />
          ) : null}
          {tab === 'calibration' && canCalibrate && !managerOnly ? (
            <CalibrationPane access={access} isAr={isAr} t={t} />
          ) : null}
          {tab === 'development' ? (
            <DevelopmentPane access={access} isAr={isAr} t={t} onNotice={onNotice} canManage={canManage} />
          ) : null}
        </>
      )}
    </div>
  )
}

function GoalsPane({
  access,
  isAr,
  t,
  onNotice,
  canManage,
  canAdminCycles,
}: {
  access: DashboardAccess
  isAr: boolean
  t: ReturnType<typeof copy>
  onNotice: NoticeFn
  canManage: boolean
  canAdminCycles: boolean
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailError, setDetailError] = useState(false)
  const [title, setTitle] = useState('')
  const [owner, setOwner] = useState('')
  const [krTitle, setKrTitle] = useState('')
  const [measureName, setMeasureName] = useState('')
  const [target, setTarget] = useState('100')
  const [busy, setBusy] = useState(false)
  const [cycleId, setCycleId] = useState('')
  const [cycleName, setCycleName] = useState('')
  const [showTree, setShowTree] = useState(false)
  const [tree, setTree] = useState<Array<Record<string, unknown>>>([])
  const [updateText, setUpdateText] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { getPerformanceObjectives, getPerformanceOkrCycles } = await import('@/lib/api')
      const [data, cycles] = await Promise.all([getPerformanceObjectives(access), getPerformanceOkrCycles(access)])
      setRows(data.objectives || [])
      const active = (cycles.cycles || []).find((c) => String(c.status) === 'active') || (cycles.cycles || [])[0]
      if (active?.cycle_id) setCycleId(String(active.cycle_id))
    } catch {
      setError(true)
      onNotice(isAr ? 'تعذّر تحميل الأهداف' : 'Could not load goals', 'error')
    } finally {
      setLoading(false)
    }
  }, [access, isAr, onNotice])

  useEffect(() => {
    void load()
  }, [load])

  const open = async (id: string) => {
    setOpenId(id)
    setDetailError(false)
    try {
      setDetail(await getPerformanceObjective(access, id))
    } catch {
      setDetailError(true)
      onNotice(isAr ? 'تعذّر تحميل التفاصيل' : 'Could not load objective', 'error')
    }
  }

  const create = async () => {
    if (!title.trim() || !owner.trim()) return
    setBusy(true)
    try {
      await postPerformanceJson(access, '/dashboard/performance/objectives', {
        title_en: title.trim(),
        title_ar: isAr ? title.trim() : undefined,
        owner_employee_key: owner.trim(),
        scope: 'individual',
        cycle_id: cycleId || undefined,
        reason: 'create objective',
      })
      setTitle('')
      await load()
      onNotice(isAr ? 'تم إنشاء الهدف' : 'Objective created', 'success')
    } catch {
      onNotice(isAr ? 'تعذّر إنشاء الهدف' : 'Could not create objective', 'error')
    } finally {
      setBusy(false)
    }
  }

  const addKr = async () => {
    if (!openId || !krTitle.trim() || !measureName.trim()) return
    setBusy(true)
    try {
      const measure = await postPerformanceJson<{ measure?: { measure_id?: string } }>(
        access,
        '/dashboard/performance/measures',
        {
          name_en: measureName.trim(),
          unit: 'count',
          direction: 'higher_is_better',
          target: Number(target) || 100,
          reason: 'create measure',
        },
      )
      await postPerformanceJson(access, `/dashboard/performance/objectives/${openId}/key-results`, {
        title_en: krTitle.trim(),
        measure_id: String(measure.measure?.measure_id || ''),
        weight: 1,
        reason: 'add key result',
      })
      setKrTitle('')
      await open(openId)
      await load()
    } catch {
      onNotice(isAr ? 'تعذّر إضافة النتيجة' : 'Could not add key result', 'error')
    } finally {
      setBusy(false)
    }
  }

  const state = resolveListDataState({ loading, error, itemCount: rows.length || (canManage ? 1 : 0) })
  if (state === 'loading' || state === 'error') {
    return (
      <ResourceState
        kind={state}
        locale={isAr ? 'ar' : 'en'}
        onRetry={() => void load()}
        retrying={loading}
      />
    )
  }
  const krs = (detail?.key_results || []) as Array<Record<string, unknown>>
  const updates = (detail?.updates || []) as Array<Record<string, unknown>>
  const history = (detail?.operating_history || {}) as Record<string, unknown>
  return (
    <div className="space-y-4">
      {canAdminCycles ? (
        <div className="grid gap-2 rounded-xl border border-border/70 p-4 sm:grid-cols-3">
          <Input value={cycleName} onChange={(e) => setCycleName(e.target.value)} placeholder={t.createOkrCycle} />
          <Button
            type="button"
            disabled={busy || !cycleName.trim()}
            onClick={() => {
              void (async () => {
                setBusy(true)
                try {
                  const created = await postPerformanceJson<{ cycle?: { cycle_id?: string } }>(
                    access,
                    '/dashboard/performance/okr-cycles',
                    {
                      name_en: cycleName.trim(),
                      name_ar: isAr ? cycleName.trim() : undefined,
                      period_start: '2026-07-01',
                      period_end: '2026-09-30',
                      scope: 'company',
                      reason: 'create okr cycle',
                    },
                  )
                  const id = String(created.cycle?.cycle_id || '')
                  if (id) {
                    await postPerformanceJson(access, `/dashboard/performance/okr-cycles/${id}/activate`, {
                      reason: 'activate okr cycle',
                    })
                    setCycleId(id)
                  }
                  setCycleName('')
                  onNotice(isAr ? 'تم إنشاء دورة النتائج الرئيسية' : 'OKR cycle created', 'success')
                } catch {
                  onNotice(isAr ? 'تعذّر إنشاء الدورة' : 'Could not create OKR cycle', 'error')
                } finally {
                  setBusy(false)
                }
              })()
            }}
          >
            {t.createOkrCycle}
          </Button>
          {cycleId ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setShowTree((v) => !v)
                if (!showTree) {
                  void getPerformanceOkrAlignment(access, cycleId)
                    .then((data) => setTree((data.tree as Array<Record<string, unknown>>) || []))
                    .catch(() => onNotice(isAr ? 'تعذّر تحميل المحاذاة' : 'Could not load alignment', 'error'))
                }
              }}
            >
              {showTree ? t.hideAlignment : t.showAlignment}
            </Button>
          ) : null}
        </div>
      ) : null}
      {showTree ? (
        <div className="rounded-xl border border-border/70 p-4 text-sm">
          <p className="mb-2 text-muted-foreground">{t.alignmentHint}</p>
          {tree.length === 0 ? (
            <div className="text-muted-foreground">{t.emptyGoals}</div>
          ) : (
            tree.map((node) => (
              <div key={String(node.objective_id)} className="mb-2">
                <div className="font-medium">
                  {isAr ? String(node.title_ar || node.title_en || '') : String(node.title_en || '')} ·{' '}
                  {String(node.scope || '')}
                </div>
                {((node.children || []) as Array<Record<string, unknown>>).map((child) => (
                  <div key={String(child.objective_id)} className="ps-4 text-muted-foreground">
                    {isAr ? String(child.title_ar || child.title_en || '') : String(child.title_en || '')} ·{' '}
                    {String(child.scope || '')}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      ) : null}
      {canManage ? (
        <div className="grid gap-2 rounded-xl border border-border/70 p-4 sm:grid-cols-3">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t.createGoal} />
          <Input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder={t.owner} />
          <Button type="button" disabled={busy} onClick={() => void create()}>
            {t.createGoal}
          </Button>
        </div>
      ) : null}
      {rows.length === 0 ? (
        <ResourceState kind="empty" locale={isAr ? 'ar' : 'en'} title={t.emptyGoals} detail={t.emptyHint} />
      ) : (
        rows.map((row) => {
          const rollup = (row.rollup || {}) as Record<string, unknown>
          const pct = rollup.progress_pct
          const id = String(row.objective_id)
          return (
            <div key={id} className="rounded-xl border border-border/70 p-4">
              <button type="button" className="w-full text-start" onClick={() => void open(id)}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium">
                    {isAr ? String(row.title_ar || row.title_en || '') : String(row.title_en || '')}
                  </div>
                  <StatusPill>{String(row.status || '')}</StatusPill>
                </div>
                <div className="mt-2 text-sm text-muted-foreground">
                  {t.progress}: {pct == null ? t.unknownProgress : `${pct}%`}
                </div>
              </button>
              {openId === id && detailError ? (
                <div className="mt-3">
                  <ResourceState kind="error" locale={isAr ? 'ar' : 'en'} />
                </div>
              ) : null}
              {openId === id && detail ? (
                <div className="mt-3 space-y-2 border-t border-border/60 pt-3">
                  {krs.map((kr) => (
                    <div key={String(kr.key_result_id)} className="text-sm">
                      {String(kr.title_en || '')} · {String(kr.unit || '')} · {t.target} {String(kr.target ?? '')}
                    </div>
                  ))}
                  {canManage && String(row.status) === 'draft' ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void postPerformanceJson(access, `/dashboard/performance/objectives/${id}/activate`, {
                          reason: 'activate',
                        }).then(() => load())
                      }
                    >
                      {t.activate}
                    </Button>
                  ) : null}
                  {canManage ? (
                    <div className="grid gap-2 sm:grid-cols-4">
                      <Input value={krTitle} onChange={(e) => setKrTitle(e.target.value)} placeholder={t.addKr} />
                      <Input value={measureName} onChange={(e) => setMeasureName(e.target.value)} placeholder={t.measure} />
                      <Input value={target} onChange={(e) => setTarget(e.target.value)} placeholder={t.target} />
                      <Button type="button" size="sm" disabled={busy} onClick={() => void addKr()}>
                        {t.addKr}
                      </Button>
                    </div>
                  ) : null}
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">{t.updateThread}</div>
                    {updates.map((item) => (
                      <div key={String(item.update_id)} className="text-sm text-muted-foreground">
                        {String(item.update_text || '')}
                        {item.confidence ? ` · ${t.confidence}: ${String(item.confidence)}` : ''}
                      </div>
                    ))}
                    <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                      <Input value={updateText} onChange={(e) => setUpdateText(e.target.value)} placeholder={t.addUpdate} />
                      <Button
                        type="button"
                        size="sm"
                        disabled={busy || !updateText.trim()}
                        onClick={() => {
                          void (async () => {
                            setBusy(true)
                            try {
                              await postPerformanceJson(access, `/dashboard/performance/objectives/${id}/updates`, {
                                subject_type: 'objective',
                                subject_id: id,
                                update_text: updateText.trim(),
                                cycle_id: cycleId || undefined,
                                reason: 'okr update',
                              })
                              setUpdateText('')
                              await open(id)
                            } catch {
                              onNotice(isAr ? 'تعذّر التحديث' : 'Could not add update', 'error')
                            } finally {
                              setBusy(false)
                            }
                          })()
                        }}
                      >
                        {t.addUpdate}
                      </Button>
                    </div>
                    {Array.isArray(history.alignment_events) && history.alignment_events.length > 0 ? (
                      <p className="text-xs text-muted-foreground">{t.alignmentHint}</p>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          )
        })
      )}
    </div>
  )
}

function ReviewsPane({
  access,
  isAr,
  t,
  onNotice,
  canManage,
}: {
  access: DashboardAccess
  isAr: boolean
  t: ReturnType<typeof copy>
  onNotice: NoticeFn
  canManage: boolean
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([])
  const [cycles, setCycles] = useState<Array<Record<string, unknown>>>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailError, setDetailError] = useState(false)
  const [cycleName, setCycleName] = useState('')
  const [rating, setRating] = useState('3')
  const [rationale, setRationale] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { getPerformanceReviews } = await import('@/lib/api')
      const [reviews, cycleData] = await Promise.all([getPerformanceReviews(access), getPerformanceCycles(access)])
      setRows(reviews.reviews || [])
      setCycles(cycleData.cycles || [])
    } catch {
      setError(true)
      onNotice(isAr ? 'تعذّر تحميل المراجعات' : 'Could not load reviews', 'error')
    } finally {
      setLoading(false)
    }
  }, [access, isAr, onNotice])

  useEffect(() => {
    void load()
  }, [load])

  const createCycle = async () => {
    if (!cycleName.trim()) return
    setBusy(true)
    try {
      const today = new Date()
      const start = today.toISOString().slice(0, 10)
      const end = new Date(today.getTime() + 60 * 86400000).toISOString().slice(0, 10)
      const scale = await postPerformanceJson<{ scale?: { scale_id?: string } }>(access, '/dashboard/performance/scales', {
        name_en: '4pt',
        points: [{ value: 1 }, { value: 2 }, { value: 3 }, { value: 4 }],
        reason: 'create scale',
      })
      const tmpl = await postPerformanceJson<{ template?: { template_id?: string } }>(
        access,
        '/dashboard/performance/templates',
        { name_en: cycleName.trim(), include_goals: true, include_competencies: false, reason: 'create template' },
      )
      await postPerformanceJson(access, '/dashboard/performance/cycles', {
        name_en: cycleName.trim(),
        period_start: start,
        period_end: end,
        template_id: String(tmpl.template?.template_id || ''),
        scale_id: String(scale.scale?.scale_id || ''),
        review_360_enabled: true,
        anonymity_enabled: true,
        min_respondent_threshold: 3,
        due_self: end,
        due_manager: end,
        reason: 'create cycle',
      })
      setCycleName('')
      await load()
    } catch {
      onNotice(isAr ? 'تعذّر إنشاء الدورة' : 'Could not create cycle', 'error')
    } finally {
      setBusy(false)
    }
  }

  const state = resolveListDataState({ loading, error, itemCount: rows.length + cycles.length || (canManage ? 1 : 0) })
  if (state === 'loading' || state === 'error') {
    return (
      <ResourceState kind={state} locale={isAr ? 'ar' : 'en'} onRetry={() => void load()} retrying={loading} />
    )
  }
  const layers = ((detail?.layers as Record<string, unknown> | undefined)?.layers || {}) as Record<string, unknown>
  return (
    <div className="space-y-4">
      {canManage ? (
        <div className="grid gap-2 rounded-xl border border-border/70 p-4 sm:grid-cols-3">
          <Input value={cycleName} onChange={(e) => setCycleName(e.target.value)} placeholder={t.createCycle} />
          <Button type="button" disabled={busy} onClick={() => void createCycle()}>
            {t.createCycle}
          </Button>
        </div>
      ) : null}
      {cycles.map((cycle) => (
        <div key={String(cycle.cycle_id)} className="rounded-xl border border-border/70 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-medium">
              {isAr ? String(cycle.name_ar || cycle.name_en || '') : String(cycle.name_en || '')}
            </div>
            <StatusPill>{String(cycle.status || '')}</StatusPill>
          </div>
          {canManage && String(cycle.status) === 'draft' ? (
            <ConfigureCycleForm
              access={access}
              cycleId={String(cycle.cycle_id)}
              isAr={isAr}
              onDone={() => void load()}
              onNotice={onNotice}
            />
          ) : null}
          {canManage && String(cycle.status) === 'configured' ? (
            <Button
              type="button"
              size="sm"
              className="mt-2"
              disabled={busy}
              onClick={() =>
                void postPerformanceJson(access, `/dashboard/performance/cycles/${cycle.cycle_id}/launch`, {
                  reason: 'launch',
                }).then(() => load())
              }
            >
              {t.launch}
            </Button>
          ) : null}
          {canManage && ['launched', 'in_progress', 'calibration_ready'].includes(String(cycle.status)) ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-2"
              disabled={busy}
              onClick={() =>
                void postPerformanceJson(access, `/dashboard/performance/cycles/${cycle.cycle_id}/close`, {
                  reason: 'close',
                }).then(() => load())
              }
            >
              {t.close}
            </Button>
          ) : null}
        </div>
      ))}
      {rows.length === 0 ? (
        <ResourceState kind="empty" locale={isAr ? 'ar' : 'en'} title={t.emptyReviews} detail={t.emptyHint} />
      ) : (
        rows.map((row) => {
          const id = String(row.review_id)
          const pending = ['not_started', 'draft'].includes(String(row.status))
          return (
            <div key={id} className="rounded-xl border border-border/70 p-4">
              <button type="button" className="w-full text-start" onClick={() => {
                setOpenId(id)
                setDetailError(false)
                void getPerformanceReview(access, id)
                  .then(setDetail)
                  .catch(() => setDetailError(true))
              }}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium">
                    {isAr ? String(row.cycle_name_ar || row.cycle_name_en || '') : String(row.cycle_name_en || '')}
                  </div>
                  <StatusPill>{`${row.reviewer_role} · ${row.status}`}</StatusPill>
                </div>
                <div className="mt-1 text-sm text-muted-foreground">{String(row.subject_employee_key || '')}</div>
              </button>
              {openId === id && detailError ? (
                <div className="mt-3">
                  <ResourceState kind="error" locale={isAr ? 'ar' : 'en'} />
                </div>
              ) : null}
              {openId === id && detail ? (
                <div className="mt-3 space-y-2 border-t border-border/60 pt-3 text-sm text-muted-foreground">
                  <div>self {String((layers.self as Record<string, unknown> | undefined)?.overall_rating_value ?? '—')}</div>
                  <div>manager {String((layers.manager as Record<string, unknown> | undefined)?.overall_rating_value ?? '—')}</div>
                  <div>final {String((layers.final as Record<string, unknown> | undefined)?.overall_rating_value ?? '—')}</div>
                  {pending ? (
                    <div className="grid gap-2 sm:grid-cols-3">
                      <Input value={rating} onChange={(e) => setRating(e.target.value)} placeholder={t.rating} />
                      <Textarea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder={t.rationale} />
                      <Button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setBusy(true)
                          void postPerformanceJson(access, `/dashboard/performance/reviews/${id}/submit`, {
                            overall_rating_value: Number(rating) || 3,
                            rationale: rationale.trim() || 'Submitted from HR Web',
                            expected_version: (detail.review as Record<string, unknown> | undefined)?.row_version,
                          })
                            .then(() => load())
                            .catch(() => onNotice(isAr ? 'تعذّر الإرسال' : 'Could not submit', 'error'))
                            .finally(() => setBusy(false))
                        }}
                      >
                        {t.submitReview}
                      </Button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        })
      )}
    </div>
  )
}

function ConfigureCycleForm({
  access,
  cycleId,
  isAr,
  onDone,
  onNotice,
}: {
  access: DashboardAccess
  cycleId: string
  isAr: boolean
  onDone: () => void
  onNotice: NoticeFn
}) {
  const [emp, setEmp] = useState('')
  const [empPhone, setEmpPhone] = useState('')
  const [mgr, setMgr] = useState('')
  const [mgrPhone, setMgrPhone] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-5">
      <Input value={emp} onChange={(e) => setEmp(e.target.value)} placeholder={isAr ? 'الموظف' : 'Employee key'} />
      <Input value={empPhone} onChange={(e) => setEmpPhone(e.target.value)} placeholder={isAr ? 'هاتف الموظف' : 'Employee phone'} />
      <Input value={mgr} onChange={(e) => setMgr(e.target.value)} placeholder={isAr ? 'المدير' : 'Manager key'} />
      <Input value={mgrPhone} onChange={(e) => setMgrPhone(e.target.value)} placeholder={isAr ? 'هاتف المدير' : 'Manager phone'} />
      <Button
        type="button"
        size="sm"
        disabled={busy || !emp.trim()}
        onClick={() => {
          setBusy(true)
          void postPerformanceJson(access, `/dashboard/performance/cycles/${cycleId}/configure`, {
            participants: [
              {
                employee_key: emp.trim(),
                employee_phone: empPhone.trim() || undefined,
                manager_employee_key: mgr.trim() || undefined,
                manager_phone: mgrPhone.trim() || undefined,
              },
            ],
            reason: 'configure cycle',
          })
            .then(onDone)
            .catch(() => onNotice(isAr ? 'تعذّر التهيئة' : 'Could not configure cycle', 'error'))
            .finally(() => setBusy(false))
        }}
      >
        {isAr ? 'تهيئة' : 'Configure'}
      </Button>
    </div>
  )
}

function CalibrationPane({
  access,
  isAr,
  t,
}: {
  access: DashboardAccess
  isAr: boolean
  t: ReturnType<typeof copy>
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([])
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailError, setDetailError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    try {
      const { getPerformanceCalibration } = await import('@/lib/api')
      const data = await getPerformanceCalibration(access)
      setRows(data.sessions || [])
    } catch (err) {
      if (err instanceof DashboardApiError && err.status === 403) setForbidden(true)
      else setError(true)
    } finally {
      setLoading(false)
    }
  }, [access])

  useEffect(() => {
    void load()
  }, [load])

  const state = resolveListDataState({ forbidden, loading, error, itemCount: rows.length })
  if (state !== 'ready') {
    return (
      <ResourceState
        kind={state}
        locale={isAr ? 'ar' : 'en'}
        title={state === 'empty' ? t.emptyCalibration : undefined}
        onRetry={() => void load()}
        retrying={loading}
      />
    )
  }
  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <button
          type="button"
          key={String(row.session_id)}
          className={cn('w-full rounded-xl border border-border/70 p-4 text-start')}
          onClick={() => {
            setDetailError(false)
            void getPerformanceCalibrationDetail(access, String(row.session_id))
              .then(setDetail)
              .catch(() => setDetailError(true))
          }}
        >
          <div className="font-medium">{isAr ? String(row.name_ar || row.name_en || '') : String(row.name_en || '')}</div>
          <div className="mt-1 flex flex-wrap gap-2 text-sm text-muted-foreground">
            <StatusPill>{String(row.status || '')}</StatusPill>
            <span>{t.preCal}</span>
            <span>/</span>
            <span>{t.calibrated}</span>
            {String(row.status) === 'locked' || String(row.status) === 'published' ? <span>{t.sealed}</span> : null}
          </div>
        </button>
      ))}
      {detailError ? <ResourceState kind="error" locale={isAr ? 'ar' : 'en'} /> : null}
      {detail ? (
        <div className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          <div>
            {t.preCal} ≠ {t.calibrated} · {t.sealed}: {String((detail.session as Record<string, unknown> | undefined)?.status || '')}
          </div>
          {((detail.results || []) as Array<Record<string, unknown>>).map((item) => (
            <div key={String(item.subject_employee_key)}>
              {String(item.subject_employee_key)} · pre {String(item.pre_calibration_value ?? '—')} · cal {String(item.calibrated_value ?? item.final_value ?? '—')}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function DevelopmentPane({
  access,
  isAr,
  t,
  onNotice,
  canManage,
}: {
  access: DashboardAccess
  isAr: boolean
  t: ReturnType<typeof copy>
  onNotice: NoticeFn
  canManage: boolean
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([])
  const [checkIns, setCheckIns] = useState<Array<Record<string, unknown>>>([])
  const [emp, setEmp] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { getPerformanceDevelopment } = await import('@/lib/api')
      const [data, ci] = await Promise.all([getPerformanceDevelopment(access), getPerformanceCheckIns(access)])
      setRows(data.items || [])
      setCheckIns(ci.check_ins || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [access])

  useEffect(() => {
    void load()
  }, [load])

  const state = resolveListDataState({
    loading,
    error,
    itemCount: rows.length + checkIns.length || (canManage ? 1 : 0),
  })
  if (state === 'loading' || state === 'error') {
    return (
      <ResourceState kind={state} locale={isAr ? 'ar' : 'en'} onRetry={() => void load()} retrying={loading} />
    )
  }
  return (
    <div className="space-y-3">
      {canManage ? (
        <div className="grid gap-2 rounded-xl border border-border/70 p-4 sm:grid-cols-3">
          <Input value={emp} onChange={(e) => setEmp(e.target.value)} placeholder={t.owner} />
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t.createDev} />
          <Button
            type="button"
            disabled={busy}
            onClick={() => {
              setBusy(true)
              void postPerformanceJson<{ plan?: { plan_id?: string } }>(access, '/dashboard/performance/development/plans', {
                employee_key: emp.trim(),
                title_en: title.trim(),
                reason: 'create development plan',
              })
                .then((plan) =>
                  postPerformanceJson(access, '/dashboard/performance/development/actions', {
                    plan_id: String(plan.plan?.plan_id || ''),
                    title_en: title.trim(),
                    reason: 'create development action',
                  }),
                )
                .then(() => {
                  setTitle('')
                  return load()
                })
                .catch(() => onNotice(isAr ? 'تعذّر إنشاء التطوير' : 'Could not create development', 'error'))
                .finally(() => setBusy(false))
            }}
          >
            {t.createDev}
          </Button>
        </div>
      ) : null}
      {checkIns.map((row) => (
        <div key={String(row.check_in_id)} className="rounded-xl border border-border/70 p-4">
          <div className="font-medium">{t.checkIns}</div>
          <div className="text-sm text-muted-foreground">
            {String(row.employee_key || '')} · {String(row.status || '')}
          </div>
        </div>
      ))}
      {rows.length === 0 ? (
        <ResourceState kind="empty" locale={isAr ? 'ar' : 'en'} title={t.emptyDevelopment} detail={t.emptyHint} />
      ) : (
        rows.map((row, idx) => (
          <div key={String(row.action_id || row.plan_id || idx)} className="rounded-xl border border-border/70 p-4">
            <div className="font-medium">
              {isAr
                ? String(row.action_title_ar || row.title_ar || row.action_title_en || row.title_en || '')
                : String(row.action_title_en || row.title_en || '')}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">{String(row.action_status || row.status || '')}</div>
          </div>
        ))
      )}
      <p className="text-sm text-muted-foreground">{t.learningOff}</p>
    </div>
  )
}
