/**
 * Probation Surface Wave — HR Web primary operator workspace.
 * Thin client over frozen probation authority. Answers:
 * Who is on probation? What is due? How are they doing? What decision is required?
 */
import { AlertTriangle, CheckCircle2, Clock3, Loader2, RefreshCw, Timer } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input, Select, Textarea } from '@/components/ui/field'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getPosthireProbation,
  getProbationDetail,
  postProbationCreate,
  postProbationExtend,
  postProbationMilestone,
  postProbationRecommend,
  postProbationRemind,
  postProbationTransition,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type ProbationWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type CaseRow = {
  case_id: string
  employee_key: string
  employee_name?: string
  status: string
  probation_start?: string | null
  probation_end?: string | null
  days_to_end?: number | null
  decision_required?: boolean
  needs_attention?: boolean
  progress_percent?: number
  milestones_summary?: { open?: number; overdue?: number; completed?: number; total?: number }
  next_milestone?: { milestone_key?: string; title_en?: string; title_ar?: string; due_on?: string } | null
  row_version?: number
}

type MilestoneRow = {
  milestone_id: string
  milestone_key: string
  title_en?: string
  title_ar?: string
  due_on?: string
  status?: string
  overdue?: boolean
  notes?: string | null
  row_version?: number
}

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'فترة التجربة',
        subtitle: 'من في التجربة؟ ما المستحق؟ كيف أداؤهم؟ أي قرار مطلوب؟',
        filterAttention: 'يحتاج اهتماماً',
        filterActive: 'نشط',
        filterReview: 'مراجعة مستحقة',
        filterConfirmed: 'مثبّت',
        filterExtended: 'ممدّد',
        filterFailed: 'منتهٍ',
        refresh: 'تحديث',
        empty: 'لا توجد حالات تجربة',
        emptyHint: 'تُنشأ الحالات عند التعيين أو يدوياً لموظف نشط',
        detail: 'التفاصيل',
        milestones: 'معالم ٣٠/٦٠/٩٠',
        audit: 'السجل',
        start: 'بداية التجربة',
        end: 'نهاية التجربة',
        decision: 'القرار المطلوب',
        confirm: 'تثبيت',
        extend: 'تمديد',
        fail: 'إنهاء',
        recommend: 'توصية المدير',
        remind: 'تذكير',
        overdue: 'متأخر',
        complete: 'إكمال',
        skip: 'تخطي',
        reason: 'سبب القرار',
        extendDays: 'أيام التمديد',
        create: 'إنشاء حالة',
        employeeKey: 'مفتاح الموظف',
        moduleOff: 'وحدة فترة التجربة غير مفعّلة لهذه الشركة',
        permissionDenied: 'لا تملك صلاحية هذا الإجراء',
        managerNote: 'توصية المدير ليست قرار الموارد البشرية النهائي',
        daysLeft: 'يوم متبقٍ',
        progress: 'التقدم',
      }
    : {
        title: 'Probation',
        subtitle: 'Who is on probation? What is due? How are they doing? What decision is required?',
        filterAttention: 'Needs attention',
        filterActive: 'Active',
        filterReview: 'Review due',
        filterConfirmed: 'Confirmed',
        filterExtended: 'Extended',
        filterFailed: 'Failed',
        refresh: 'Refresh',
        empty: 'No probation cases',
        emptyHint: 'Cases are created on hire or manually for an active employee',
        detail: 'Detail',
        milestones: '30 / 60 / 90 milestones',
        audit: 'History',
        start: 'Probation start',
        end: 'Probation end',
        decision: 'Decision required',
        confirm: 'Confirm',
        extend: 'Extend',
        fail: 'Fail',
        recommend: 'Manager recommend',
        remind: 'Remind',
        overdue: 'Overdue',
        complete: 'Complete',
        skip: 'Skip',
        reason: 'Decision reason',
        extendDays: 'Extend days',
        create: 'Create case',
        employeeKey: 'Employee key',
        moduleOff: 'Probation is not enabled for this company',
        permissionDenied: 'You do not have permission for this action',
        managerNote: 'Manager recommendation is not final HR authority',
        daysLeft: 'days left',
        progress: 'Progress',
      }
}

function statusTone(status: string): 'success' | 'warning' | 'danger' | 'neutral' | 'info' {
  if (status === 'confirmed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'under_review' || status === 'extended') return 'warning'
  if (status === 'active') return 'info'
  return 'neutral'
}

export function ProbationWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: ProbationWorkspaceProps) {
  void role
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const c = copy(isAr)
  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState<CaseRow[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [filter, setFilter] = useState('attention')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<{
    case?: CaseRow
    milestones?: MilestoneRow[]
    events?: Array<{ event_type?: string; created_at?: string; payload?: Record<string, unknown> }>
    permissions?: { manage?: boolean; decide?: boolean; recommend?: boolean }
  } | null>(null)
  const [reason, setReason] = useState('')
  const [extendDays, setExtendDays] = useState('30')
  const [createKey, setCreateKey] = useState('')
  const [moduleDenied, setModuleDenied] = useState(false)

  const canDecide = permissions.includes('probation.decide')
  const canRecommend = permissions.includes('probation.manage')
  const canManage = permissions.includes('probation.manage')

  const loadQueue = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getPosthireProbation(access, {
        status: filter || undefined,
        limit: 100,
      })
      setRows((res.cases || []) as CaseRow[])
      setCounts((res.counts || {}) as Record<string, number>)
      setModuleDenied(false)
      if (!selectedId && res.cases?.[0]?.case_id) {
        setSelectedId(String(res.cases[0].case_id))
      }
    } catch (error) {
      const issue = accessIssueFromError(error)
      if (issue) onAccessIssue?.(issue)
      if (error instanceof DashboardApiError && String(error.code || '').includes('probation')) {
        setModuleDenied(true)
      } else {
        onNotice(isAr ? 'تعذر تحميل فترة التجربة' : 'Could not load probation', 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [access, filter, isAr, onAccessIssue, onNotice, selectedId])

  const loadDetail = useCallback(
    async (caseId: string) => {
      try {
        const res = await getProbationDetail(access, caseId)
        setDetail(res as typeof detail)
      } catch (error) {
        const issue = accessIssueFromError(error)
        if (issue) onAccessIssue?.(issue)
        onNotice(isAr ? 'تعذر فتح التفاصيل' : 'Could not open detail', 'error')
      }
    },
    [access, isAr, onAccessIssue, onNotice],
  )

  useEffect(() => {
    void loadQueue()
  }, [loadQueue])

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId)
  }, [selectedId, loadDetail])

  const filtered = useMemo(() => rows, [rows])

  async function runSafe(fn: () => Promise<unknown>, okMsg: string) {
    try {
      await fn()
      onNotice(okMsg, 'success')
      await loadQueue()
      if (selectedId) await loadDetail(selectedId)
    } catch (error) {
      const issue = accessIssueFromError(error)
      if (issue) onAccessIssue?.(issue)
      onNotice(error instanceof DashboardApiError ? error.message : c.permissionDenied, 'error')
    }
  }

  if (moduleDenied) {
    return (
      <div className="space-y-4 p-6" dir={isAr ? 'rtl' : 'ltr'}>
        <ConfigureInSetupBanner
          title={isAr ? 'فترة التجربة غير مفعّلة' : 'Probation is not enabled'}
          body={
            isAr
              ? 'فعّل الوحدة واضبط سياسة التجربة والمعالم من وحدة التحكم.'
              : 'Enable the module and configure probation policy and milestones in Setup Console.'
          }
          anchor="classic-wave1-hire-ready"
          locale={isAr ? 'ar' : 'en'}
        />
        <p className="text-sm text-muted-foreground">{c.moduleOff}</p>
      </div>
    )
  }

  const selected = detail?.case

  return (
    <div className="flex h-full min-h-[70vh] flex-col gap-4 p-4 md:p-6" dir={isAr ? 'rtl' : 'ltr'}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Timer className="h-6 w-6" />
            {c.title}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{c.subtitle}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void loadQueue()}>
          <RefreshCw className="me-2 h-4 w-4" />
          {c.refresh}
        </Button>
      </header>

      <div className="flex flex-wrap gap-2">
        {(
          [
            ['attention', c.filterAttention, counts.attention],
            ['active', c.filterActive, counts.active],
            ['under_review', c.filterReview, counts.under_review],
            ['confirmed', c.filterConfirmed, counts.confirmed],
            ['extended', c.filterExtended, counts.extended],
            ['failed', c.filterFailed, counts.failed],
          ] as const
        ).map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={cn(
              'rounded-full border px-3 py-1 text-sm',
              filter === key ? 'border-foreground bg-foreground text-background' : 'border-border',
            )}
          >
            {label}
            {typeof count === 'number' ? ` · ${count}` : ''}
          </button>
        ))}
      </div>

      {canManage && String(role || '') !== 'manager' ? (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border/60 p-3">
          <div className="min-w-[220px] flex-1">
            <label className="mb-1 block text-xs text-muted-foreground">{c.employeeKey}</label>
            <Input value={createKey} onChange={(e) => setCreateKey(e.target.value)} />
          </div>
          <Button
            size="sm"
            disabled={!createKey.trim()}
            onClick={() =>
              void runSafe(
                () => postProbationCreate(access, { employee_key: createKey.trim() }),
                isAr ? 'تم إنشاء الحالة' : 'Case created',
              )
            }
          >
            {c.create}
          </Button>
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(280px,1fr)_minmax(360px,1.4fr)]">
        <section className="overflow-auto rounded-xl border border-border/70">
          {loading ? (
            <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> …
            </div>
          ) : filtered.length === 0 ? (
            <WorkflowEmpty title={c.empty} description={c.emptyHint} />
          ) : (
            <ul className="divide-y divide-border/60">
              {filtered.map((row) => (
                <li key={row.case_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(row.case_id)}
                    className={cn(
                      'flex w-full flex-col gap-1 px-4 py-3 text-start hover:bg-muted/40',
                      selectedId === row.case_id && 'bg-muted/60',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{row.employee_name || row.employee_key}</span>
                      <StatusPill tone={statusTone(row.status)}>{row.status}</StatusPill>
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span>
                        {c.end}: {String(row.probation_end || '').slice(0, 10)}
                        {typeof row.days_to_end === 'number' ? ` · ${row.days_to_end} ${c.daysLeft}` : ''}
                      </span>
                      {row.decision_required ? (
                        <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                          <AlertTriangle className="h-3 w-3" /> {c.decision}
                        </span>
                      ) : null}
                      {(row.milestones_summary?.overdue || 0) > 0 ? (
                        <span className="text-danger">
                          {c.overdue}: {row.milestones_summary?.overdue}
                        </span>
                      ) : null}
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full bg-foreground/70"
                        style={{ width: `${Math.min(100, row.progress_percent || 0)}%` }}
                      />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="overflow-auto rounded-xl border border-border/70 p-4">
          {!selectedId || !selected ? (
            <WorkflowEmpty title={c.detail} description={c.emptyHint} />
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold">{selected.employee_name || selected.employee_key}</h2>
                  <p className="text-sm text-muted-foreground">
                    {c.start}: {String(selected.probation_start || '').slice(0, 10)} · {c.end}:{' '}
                    {String(selected.probation_end || '').slice(0, 10)}
                  </p>
                </div>
                <StatusPill tone={statusTone(selected.status)}>{selected.status}</StatusPill>
              </div>

              {selected.decision_required ? (
                <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                  <div className="mb-2 flex items-center gap-2 font-medium">
                    <AlertTriangle className="h-4 w-4" /> {c.decision}
                  </div>
                  <Textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder={c.reason}
                    className="mb-2"
                  />
                  <div className="mb-2 flex items-center gap-2">
                    <label className="text-xs text-muted-foreground">{c.extendDays}</label>
                    <Input
                      className="w-24"
                      value={extendDays}
                      onChange={(e) => setExtendDays(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canRecommend ? (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            void runSafe(
                              () =>
                                postProbationRecommend(access, selectedId, {
                                  recommendation: 'confirm',
                                  notes: reason || undefined,
                                }),
                              isAr ? 'سُجّلت التوصية' : 'Recommendation recorded',
                            )
                          }
                        >
                          {c.recommend}: {c.confirm}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            void runSafe(
                              () =>
                                postProbationRecommend(access, selectedId, {
                                  recommendation: 'extend',
                                  notes: reason || undefined,
                                  extend_days: Number(extendDays) || 30,
                                }),
                              isAr ? 'سُجّلت التوصية' : 'Recommendation recorded',
                            )
                          }
                        >
                          {c.recommend}: {c.extend}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            void runSafe(
                              () =>
                                postProbationRecommend(access, selectedId, {
                                  recommendation: 'fail',
                                  notes: reason || undefined,
                                }),
                              isAr ? 'سُجّلت التوصية' : 'Recommendation recorded',
                            )
                          }
                        >
                          {c.recommend}: {c.fail}
                        </Button>
                      </>
                    ) : null}
                    {canDecide ? (
                      <>
                        <Button
                          size="sm"
                          onClick={() =>
                            void runSafe(
                              () =>
                                postProbationTransition(access, selectedId, {
                                  to_status: 'confirmed',
                                  decision_reason: reason || 'confirmed',
                                  expected_row_version: selected.row_version,
                                }),
                              isAr ? 'تم التثبيت' : 'Confirmed',
                            )
                          }
                        >
                          <CheckCircle2 className="me-1 h-4 w-4" /> {c.confirm}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            void runSafe(
                              () =>
                                postProbationExtend(access, selectedId, {
                                  extend_days: Number(extendDays) || 30,
                                  decision_reason: reason || 'extended',
                                  expected_row_version: selected.row_version,
                                }),
                              isAr ? 'تم التمديد' : 'Extended',
                            )
                          }
                        >
                          <Clock3 className="me-1 h-4 w-4" /> {c.extend}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() =>
                            void runSafe(
                              () =>
                                postProbationTransition(access, selectedId, {
                                  to_status: 'failed',
                                  decision_reason: reason || 'failed',
                                  expected_row_version: selected.row_version,
                                }),
                              isAr ? 'تم الإنهاء' : 'Failed',
                            )
                          }
                        >
                          {c.fail}
                        </Button>
                      </>
                    ) : null}
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{c.managerNote}</p>
                </div>
              ) : null}

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="font-medium">{c.milestones}</h3>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      void runSafe(
                        () => postProbationRemind(access, selectedId, { locale: isAr ? 'ar' : 'en' }),
                        isAr ? 'أُرسل التذكير' : 'Reminder queued',
                      )
                    }
                  >
                    {c.remind}
                  </Button>
                </div>
                <ul className="space-y-2">
                  {(detail?.milestones || []).map((m) => (
                    <li
                      key={m.milestone_id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/50 px-3 py-2"
                    >
                      <div>
                        <div className="font-medium">
                          {isAr ? m.title_ar || m.title_en : m.title_en || m.milestone_key}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {m.due_on}
                          {m.overdue || m.status === 'overdue' ? ` · ${c.overdue}` : ''}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusPill tone={statusTone(m.status || 'pending')}>{m.status}</StatusPill>
                        {canManage && m.status && ['pending', 'overdue'].includes(m.status) ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void runSafe(
                                  () =>
                                    postProbationMilestone(access, selectedId, m.milestone_key, {
                                      to_status: 'completed',
                                      expected_row_version: m.row_version,
                                    }),
                                  isAr ? 'اكتمل المعلم' : 'Milestone completed',
                                )
                              }
                            >
                              {c.complete}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() =>
                                void runSafe(
                                  () =>
                                    postProbationMilestone(access, selectedId, m.milestone_key, {
                                      to_status: 'skipped',
                                      expected_row_version: m.row_version,
                                    }),
                                  isAr ? 'تم التخطي' : 'Milestone skipped',
                                )
                              }
                            >
                              {c.skip}
                            </Button>
                          </>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="mb-2 font-medium">{c.audit}</h3>
                <ul className="max-h-48 space-y-1 overflow-auto text-xs text-muted-foreground">
                  {(detail?.events || []).map((e, idx) => (
                    <li key={`${e.created_at}-${idx}`}>
                      {String(e.created_at || '').slice(0, 19)} · {e.event_type}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
