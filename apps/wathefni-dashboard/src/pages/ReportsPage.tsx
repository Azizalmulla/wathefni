import { Profiler as ReactProfiler, useCallback, useEffect } from 'react'
import { Download, Loader2 } from 'lucide-react'

import {
  dashboardPerfMarkInteractionStart,
  dashboardPerfMarkNetworkComplete,
  dashboardPerfMarkProfilerCommit,
} from '@/lib/perf/dashboardPerf'
import { type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/pages/shared/primitives'
import type { PrehireReportsResponse } from '@/types'

function reportsCopy(locale: RecruitingLocale | undefined, key: string): string {
  const isAr = locale === 'ar'
  const en: Record<string, string> = {
    overview: 'Overview',
    overview_sub: 'Current hiring snapshot for leadership.',
    breakdowns: 'Breakdowns',
    breakdowns_sub: 'Current counts by stage, role, assessment, and interview.',
    exports: 'Exports',
    exports_sub: 'Download leadership spreadsheets. Each export declares its unit and whether it is current or historical.',
    open_roles: 'Open roles',
    active_applications: 'Active applications',
    ready_for_review: 'Ready for review',
    interview_debt: 'Candidates needing interview scheduling',
    assessment_pending: 'Assessments needing action',
    followups: 'Current follow-ups',
    stage: 'Applications by current stage',
    role: 'Active applications by role',
    assessment_status: 'Assessment status',
    interview_status: 'Interview status',
    candidates_export: 'Candidate applications',
    roles_export: 'Roles',
    assessments_export: 'Assessments',
    interviews_export: 'Interviews',
    followups_export: 'Current follow-ups',
    delivery_export: 'Delivery failure history',
    current: 'Current',
    history: 'Historical',
    application: 'application',
    role_unit: 'role',
    attempt: 'attempt',
    interview: 'interview',
    event: 'event',
    records: 'records',
    download: 'Download',
    downloads_disabled: 'Downloads are disabled for your current role.',
    loading: 'Loading reports…',
    refreshing: 'Refreshing reports…',
    empty: 'Reports will appear here once loaded.',
    error: 'Reports could not be loaded. Try refresh.',
    partial: 'Some report metrics could not be refreshed. Shown numbers may be incomplete.',
    no_stages: 'No application stages to report.',
    no_roles: 'No active role counts to report.',
    no_assessments: 'No assessments to report.',
    no_interviews: 'No interviews to report.',
    more: 'more — see the full export for details.',
  }
  const ar: Record<string, string> = {
    overview: 'نظرة عامة',
    overview_sub: 'لمحة حالية عن التوظيف للقيادة.',
    breakdowns: 'التفصيلات',
    breakdowns_sub: 'العدادات الحالية حسب المرحلة والوظيفة والتقييم والمقابلة.',
    exports: 'التصدير',
    exports_sub: 'تنزيل جداول القيادة. كل تصدير يوضح الوحدة وما إذا كان حالياً أو تاريخياً.',
    open_roles: 'الوظائف المفتوحة',
    active_applications: 'الطلبات النشطة',
    ready_for_review: 'جاهز للمراجعة',
    interview_debt: 'مرشحون يحتاجون جدولة مقابلة',
    assessment_pending: 'تقييمات تحتاج إجراء',
    followups: 'المتابعات الحالية',
    stage: 'الطلبات حسب المرحلة الحالية',
    role: 'الطلبات النشطة حسب الوظيفة',
    assessment_status: 'حالة التقييم',
    interview_status: 'حالة المقابلة',
    candidates_export: 'طلبات المرشحين',
    roles_export: 'الوظائف',
    assessments_export: 'التقييمات',
    interviews_export: 'المقابلات',
    followups_export: 'المتابعات الحالية',
    delivery_export: 'سجل فشل التسليم',
    current: 'حالي',
    history: 'تاريخي',
    application: 'طلب',
    role_unit: 'وظيفة',
    attempt: 'محاولة',
    interview: 'مقابلة',
    event: 'حدث',
    records: 'سجلات',
    download: 'تنزيل',
    downloads_disabled: 'التنزيلات غير متاحة لدورك الحالي.',
    loading: 'جاري تحميل التقارير…',
    refreshing: 'جاري تحديث التقارير…',
    empty: 'ستظهر التقارير هنا بعد التحميل.',
    error: 'تعذّر تحميل التقارير. حاول التحديث.',
    partial: 'تعذّر تحديث بعض مقاييس التقارير. الأرقام المعروضة قد تكون غير مكتملة.',
    no_stages: 'لا مراحل طلبات للعرض.',
    no_roles: 'لا أعداد وظائف نشطة للعرض.',
    no_assessments: 'لا تقييمات للعرض.',
    no_interviews: 'لا مقابلات للعرض.',
    more: 'المزيد — راجع التصدير الكامل للتفاصيل.',
  }
  return (isAr ? ar : en)[key] || en[key] || key
}

function metricValue(metrics: PrehireReportsResponse['metrics'] | undefined, key: string): number {
  const list = metrics?.metrics || []
  const found = list.find((item) => item.key === key)
  if (!found) return 0
  if (typeof found.value === 'number') return found.value
  return 0
}

function ReportsProfiler({ id, children }: { id: string; children: React.ReactNode }) {
  const onRender = useCallback(
    (
      profilerId: string,
      phase: 'mount' | 'update' | 'nested-update',
      actualDuration: number,
      baseDuration: number,
    ) => {
      dashboardPerfMarkProfilerCommit(`reports:${profilerId}`, {
        phase,
        actualDurationMs: Math.round(actualDuration),
        baseDurationMs: Math.round(baseDuration),
      })
    },
    [],
  )
  return (
    <ReactProfiler id={id} onRender={onRender}>
      {children}
    </ReactProfiler>
  )
}

export function ReportsPage({
  assessmentEnabled,
  canExportReports,
  interviewsEnabled = true,
  locale = 'en',
  onExportAssessments,
  onExportCandidates,
  onExportFollowUps,
  onExportDeliveryHistory,
  onExportInterviews,
  onExportRoles,
  refreshing = false,
  reports,
  reportsError = false,
}: {
  assessmentEnabled: boolean
  canExportReports: boolean
  interviewsEnabled?: boolean
  locale?: RecruitingLocale
  onExportAssessments: () => void
  onExportCandidates: () => void
  onExportFollowUps: () => void
  onExportDeliveryHistory: () => void
  onExportInterviews: () => void
  onExportRoles: () => void
  refreshing?: boolean
  reports: PrehireReportsResponse | null
  reportsError?: boolean
}) {
  const isAr = locale === 'ar'
  const summary = reports?.summary
  const exports = reports?.exports
  const breakdowns = reports?.breakdowns
  const overview = reports?.overview
  const metrics = reports?.metrics
  const partial = Boolean(reports?.partial || reports?.error)

  useEffect(() => {
    dashboardPerfMarkInteractionStart('reports_page_load', { hasData: Boolean(reports) })
    dashboardPerfMarkNetworkComplete('reports_page_load', { hasData: Boolean(reports) })
  }, [reports])

  useEffect(() => {
    if (!refreshing) return
    dashboardPerfMarkInteractionStart('reports_refresh', {})
  }, [refreshing])

  useEffect(() => {
    if (refreshing) return
    dashboardPerfMarkNetworkComplete('reports_refresh', { hasData: Boolean(reports) })
  }, [refreshing, reports])

  if (!reports && refreshing) {
    return (
      <div className="space-y-4" data-testid="reports-skeleton" dir={isAr ? 'rtl' : 'ltr'}>
        <div className="h-24 animate-pulse rounded-[1.4rem] bg-white/55" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="h-28 animate-pulse rounded-[1.4rem] bg-white/55" />
          <div className="h-28 animate-pulse rounded-[1.4rem] bg-white/55" />
          <div className="h-28 animate-pulse rounded-[1.4rem] bg-white/55" />
          <div className="h-28 animate-pulse rounded-[1.4rem] bg-white/55" />
        </div>
        <div className="h-48 animate-pulse rounded-[1.4rem] bg-white/55" />
      </div>
    )
  }
  if (reportsError && !reports) {
    return <EmptyState text={reportsCopy(locale, 'error')} />
  }
  if (!reports) {
    return (
      <div className="space-y-4" data-testid="reports-skeleton" dir={isAr ? 'rtl' : 'ltr'}>
        <div className="h-24 animate-pulse rounded-[1.4rem] bg-white/55" />
        <div className="h-48 animate-pulse rounded-[1.4rem] bg-white/55" />
      </div>
    )
  }

  const openRoles = overview?.open_roles ?? metricValue(metrics, 'open_roles')
  const activeApplications = overview?.active_applications ?? metricValue(metrics, 'active_applications')
  const readyForReview = overview?.ready_for_review ?? metricValue(metrics, 'ready_for_review') ?? summary?.ready_for_review ?? 0
  const interviewDebt =
    overview?.interview_scheduling_debt ?? metricValue(metrics, 'interview_scheduling_debt') ?? summary?.interview_scheduling_debt ?? 0
  const assessmentPending =
    overview?.assessment_pending ?? metricValue(metrics, 'assessment_pending') ?? summary?.assessment_pending ?? 0
  const followupsCurrent = overview?.followups_current ?? metricValue(metrics, 'followups_current') ?? summary?.followups ?? 0
  const deliveryHistory =
    exports?.followup_delivery_history_rows ?? metricValue(metrics, 'delivery_failure_history') ?? summary?.followup_delivery_events ?? 0

  const stageRows = metrics?.breakdowns?.applications_by_stage || breakdowns?.applications_by_stage || []
  const roleRows = (metrics?.breakdowns?.applications_by_role || breakdowns?.candidates_by_role || []).filter(
    (row) => Number(row.count || 0) > 0,
  )
  const assessmentRows = breakdowns?.assessment_status || metrics?.breakdowns?.assessment_status || []
  const interviewRows = breakdowns?.interview_status || metrics?.breakdowns?.interview_status || []

  const exportCards = [
    {
      key: 'candidates',
      label: reportsCopy(locale, 'candidates_export'),
      unit: reportsCopy(locale, 'application'),
      scope: 'current' as const,
      count: exports?.candidate_rows || 0,
      onExport: onExportCandidates,
    },
    {
      key: 'roles',
      label: reportsCopy(locale, 'roles_export'),
      unit: reportsCopy(locale, 'role_unit'),
      scope: 'current' as const,
      count: exports?.role_rows || 0,
      onExport: onExportRoles,
    },
    ...(assessmentEnabled
      ? [
          {
            key: 'assessments',
            label: reportsCopy(locale, 'assessments_export'),
            unit: reportsCopy(locale, 'attempt'),
            scope: 'current' as const,
            count: exports?.assessment_rows || 0,
            onExport: onExportAssessments,
          },
        ]
      : []),
    ...(interviewsEnabled
      ? [
          {
            key: 'interviews',
            label: reportsCopy(locale, 'interviews_export'),
            unit: reportsCopy(locale, 'interview'),
            scope: 'current' as const,
            count: exports?.interview_rows || 0,
            onExport: onExportInterviews,
          },
        ]
      : []),
    {
      key: 'followups',
      label: reportsCopy(locale, 'followups_export'),
      unit: reportsCopy(locale, 'application'),
      scope: 'current' as const,
      count: exports?.followup_rows ?? followupsCurrent,
      onExport: onExportFollowUps,
    },
    {
      key: 'followup_delivery_history',
      label: reportsCopy(locale, 'delivery_export'),
      unit: reportsCopy(locale, 'event'),
      scope: 'history' as const,
      count: deliveryHistory,
      onExport: onExportDeliveryHistory,
    },
  ]

  function wrapExport(key: string, action: () => void) {
    return () => {
      dashboardPerfMarkInteractionStart('reports_export', { type: key })
      action()
      dashboardPerfMarkNetworkComplete('reports_export', { type: key })
    }
  }

  return (
    <div className="space-y-8" dir={isAr ? 'rtl' : 'ltr'}>
      {refreshing ? (
        <div className="flex items-center gap-2 text-xs text-subtle">
          <Loader2 className="animate-spin" size={14} /> {reportsCopy(locale, 'refreshing')}
        </div>
      ) : null}
      {partial ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {reportsCopy(locale, 'partial')}
        </div>
      ) : null}

      <ReportsProfiler id="overview">
        <section className="space-y-4">
          <header>
            <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-[#23211d]">{reportsCopy(locale, 'overview')}</h2>
            <p className="mt-1 text-sm text-[#716a5e]">{reportsCopy(locale, 'overview_sub')}</p>
          </header>
          <div className="overflow-hidden rounded-[1.45rem] border border-[#e8dfd0]/80 bg-[#fffaf0]/90 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset]">
            <div className="grid md:grid-cols-2 xl:grid-cols-3">
              <QuietMetric accent="priority" label={reportsCopy(locale, 'open_roles')} value={`${openRoles}`} />
              <QuietMetric accent="follow" label={reportsCopy(locale, 'active_applications')} value={`${activeApplications}`} />
              <QuietMetric accent="review" label={reportsCopy(locale, 'ready_for_review')} value={`${readyForReview}`} />
              {interviewsEnabled ? <QuietMetric accent="review" label={reportsCopy(locale, 'interview_debt')} value={`${interviewDebt}`} /> : null}
              {assessmentEnabled ? <QuietMetric accent="assess" label={reportsCopy(locale, 'assessment_pending')} value={`${assessmentPending}`} /> : null}
              <QuietMetric accent="follow" label={reportsCopy(locale, 'followups')} value={`${followupsCurrent}`} />
            </div>
          </div>
        </section>
      </ReportsProfiler>

      <ReportsProfiler id="breakdowns">
        <section className="space-y-4">
          <header>
            <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-[#23211d]">{reportsCopy(locale, 'breakdowns')}</h2>
            <p className="mt-1 text-sm text-[#716a5e]">{reportsCopy(locale, 'breakdowns_sub')}</p>
          </header>
          <div className="rounded-[1.45rem] border border-[#e8dfd0]/80 bg-[#fffaf0]/90 p-5 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset] sm:p-6">
            <div className="grid gap-8 lg:grid-cols-2">
              <ReportBreakdown emptyText={reportsCopy(locale, 'no_stages')} locale={locale} rows={stageRows} title={reportsCopy(locale, 'stage')} />
              {assessmentEnabled ? (
                <ReportBreakdown
                  emptyText={reportsCopy(locale, 'no_assessments')}
                  locale={locale}
                  rows={assessmentRows}
                  title={reportsCopy(locale, 'assessment_status')}
                />
              ) : null}
              {interviewsEnabled ? (
                <ReportBreakdown
                  emptyText={reportsCopy(locale, 'no_interviews')}
                  locale={locale}
                  rows={interviewRows}
                  title={reportsCopy(locale, 'interview_status')}
                />
              ) : null}
              <ReportBreakdown emptyText={reportsCopy(locale, 'no_roles')} locale={locale} rows={roleRows} title={reportsCopy(locale, 'role')} />
            </div>
          </div>
        </section>
      </ReportsProfiler>

      <ReportsProfiler id="exports">
        <section className="space-y-4">
          <header>
            <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-[#23211d]">{reportsCopy(locale, 'exports')}</h2>
            <p className="mt-1 text-sm text-[#716a5e]">{reportsCopy(locale, 'exports_sub')}</p>
          </header>
          <div className="rounded-[1.45rem] border border-[#e8dfd0]/80 bg-[#fffaf0]/90 px-5 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset] sm:px-6">
            <div className="divide-y divide-[#e8dfd0]/70">
              {exportCards.map((card) => (
                <ExportCard
                  count={card.count}
                  description={`${card.scope === 'history' ? reportsCopy(locale, 'history') : reportsCopy(locale, 'current')} · ${card.unit}`}
                  disabled={!canExportReports}
                  key={card.key}
                  label={card.label}
                  locale={locale}
                  onExport={wrapExport(card.key, card.onExport)}
                />
              ))}
              {!canExportReports ? (
                <div className="py-4 text-sm leading-6 text-[#716a5e]">
                  {reportsCopy(locale, 'downloads_disabled')}
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </ReportsProfiler>
    </div>
  )
}

function QuietMetric({
  label,
  value,
  accent = 'follow',
}: {
  label: string
  value?: string | null
  accent?: 'priority' | 'review' | 'assess' | 'follow'
}) {
  const mark =
    accent === 'priority'
      ? 'bg-wf-accent-priority'
      : accent === 'review'
        ? 'bg-wf-accent-review'
        : accent === 'assess'
          ? 'bg-wf-accent-assess'
          : 'bg-wf-accent-follow'
  return (
    <div className="border-b border-[#e8dfd0]/70 p-4 last:border-b-0 md:border-e md:odd:[&:nth-last-child(-n+2)]:border-b-0 xl:border-b xl:[&:nth-child(3n)]:border-e-0 xl:[&:nth-last-child(-n+3)]:border-b-0">
      <div className="flex items-start gap-2.5">
        <span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${mark}`} />
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a8274]">{label}</div>
          <div className="mt-1.5 break-words text-[1.65rem] font-semibold tracking-[-0.04em] text-[#23211d]">{value || '—'}</div>
        </div>
      </div>
    </div>
  )
}

export function ReportBreakdown({
  emptyText,
  locale,
  rows,
  title,
}: {
  emptyText: string
  locale?: RecruitingLocale
  rows: Array<{ label: string; count: number }>
  title: string
}) {
  const shown = rows.slice(0, 8)
  const remaining = rows.length - shown.length
  return (
    <div className="min-w-0">
      <div className="pb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a8274]">{title}</div>
      <div className="space-y-0">
        {rows.length ? (
          shown.map((row) => (
            <div
              className="flex items-center justify-between gap-3 border-b border-[#e8dfd0]/55 py-2.5 text-sm last:border-0"
              key={row.label}
            >
              <span className="min-w-0 truncate text-[#716a5e]">{row.label}</span>
              <span className="inline-flex h-6 min-w-6 shrink-0 items-center justify-center rounded-full bg-[#23211d] px-2 text-[11px] font-semibold text-white">
                {row.count}
              </span>
            </div>
          ))
        ) : (
          <div className="py-2 text-sm text-[#716a5e]">{emptyText}</div>
        )}
        {remaining > 0 ? (
          <div className="pt-2 text-xs text-[#8a8274]">
            +{remaining} {reportsCopy(locale, 'more')}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function ExportCard({
  count,
  description,
  disabled,
  label,
  locale,
  onExport,
}: {
  count: number
  description: string
  disabled?: boolean
  label: string
  locale?: RecruitingLocale
  onExport: () => void | Promise<void>
}) {
  return (
    <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="font-semibold text-text">{label}</div>
        <div className="mt-0.5 text-sm leading-6 text-subtle">{description}</div>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="inline-flex h-6 min-w-6 shrink-0 items-center justify-center rounded-full bg-[#23211d] px-2 text-[11px] font-semibold text-white">
          {count}
        </span>
        <Button disabled={disabled} onClick={onExport} size="sm" variant="secondary">
          <Download size={16} /> {reportsCopy(locale, 'download')}
        </Button>
      </div>
    </div>
  )
}

/** @deprecated kept for tests importing metricValue from this module */
export { metricValue }
