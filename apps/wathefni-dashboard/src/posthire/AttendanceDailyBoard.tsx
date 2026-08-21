/**
 * Bilingual daily attendance board (attention strip + table + day detail).
 * Wave 1: view + resolve-into-Ops only — no board Correct / Mark absent.
 */
import { CalendarDays, ChevronDown, Clock } from 'lucide-react'
import { Fragment, type ReactNode, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusPill } from '@/components/ui/page-chrome'
import { BlockedReason, useEmployees360Locale } from '@/posthire/employees360/chrome'
import {
  attendanceLifeState,
  formatMinutes,
  lifeStateLabel,
  lifeStateTone,
  payrollExclusionReason,
  type AttendanceLifeState,
} from '@/posthire/attendanceUx'
import type { PosthireAttendanceRow } from '@/types'
import { cn } from '@/lib/utils'

function formatDate(value: string | null | undefined, locale: 'en' | 'ar'): string {
  if (!value) return '—'
  try {
    return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString(locale === 'ar' ? 'ar-KW' : 'en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return String(value).slice(0, 10)
  }
}

function formatClock(value: string | null | undefined): string {
  if (!value) return '—'
  const s = String(value)
  if (s.includes('T')) return s.slice(11, 16) || s
  if (s.length >= 5 && s.includes(':')) return s.slice(0, 5)
  return s
}

function sessionSummary(row: PosthireAttendanceRow, locale: 'en' | 'ar'): string {
  const sessions = (row.metadata?.sessions || []) as Array<Record<string, unknown>>
  if (!sessions.length) {
    const inAt = formatClock(row.check_in_at)
    const outAt = formatClock(row.check_out_at)
    if (inAt === '—' && outAt === '—') return locale === 'ar' ? 'لا جلسات' : 'No sessions'
    return `${inAt} → ${outAt}`
  }
  return sessions
    .map((s, i) => {
      const a = formatClock(String(s.check_in_at || ''))
      const b = formatClock(String(s.check_out_at || ''))
      return locale === 'ar' ? `جلسة ${i + 1}: ${a} → ${b}` : `S${i + 1}: ${a} → ${b}`
    })
    .join(' · ')
}

const NEEDS_EXCEPTION: AttendanceLifeState[] = ['needs_review', 'incomplete', 'disputed', 'absent']

function rowNeedsResolve(row: PosthireAttendanceRow): boolean {
  return NEEDS_EXCEPTION.includes(attendanceLifeState(row))
}

const labels = {
  en: {
    present: 'Present',
    late: 'Late',
    absent: 'Absent',
    review: 'Needs attention',
    excluded: 'Payroll excluded',
    employee: 'Employee',
    date: 'Date',
    scheduled: 'Scheduled',
    actual: 'Actual',
    worked: 'Worked',
    lateEarly: 'Late / early',
    state: 'State',
    action: 'Action',
    expand: 'Day detail',
    collapse: 'Hide',
    resolve: 'Resolve',
    empty: 'No attendance records for this range',
    emptyHint: 'Attendance appears once check-ins are captured against shifts. Try a wider range.',
    sessions: 'Sessions',
    breaks: 'Breaks',
    payroll: 'Payroll',
    version: 'Version',
    attention: 'Attention',
    attentionHint: 'Exceptions resolve through Ops — request, dual review, then apply.',
    records: 'records',
  },
  ar: {
    present: 'حاضر',
    late: 'تأخير',
    absent: 'غياب',
    review: 'يحتاج متابعة',
    excluded: 'مستبعد من الرواتب',
    employee: 'الموظف',
    date: 'التاريخ',
    scheduled: 'المجدول',
    actual: 'الفعلي',
    worked: 'العمل',
    lateEarly: 'تأخير / انصراف مبكر',
    state: 'الحالة',
    action: 'إجراء',
    expand: 'تفاصيل اليوم',
    collapse: 'إخفاء',
    resolve: 'متابعة',
    empty: 'لا سجلات حضور لهذا النطاق',
    emptyHint: 'يظهر الحضور بعد تسجيل الدخول وفق الورديات. جرّب نطاقاً أوسع.',
    sessions: 'الجلسات',
    breaks: 'الاستراحات',
    payroll: 'الرواتب',
    version: 'الإصدار',
    attention: 'يتطلب متابعة',
    attentionHint: 'تُحل الاستثناءات عبر العمليات — طلب، اعتماد مزدوج، ثم تطبيق.',
    records: 'سجل',
  },
} as const

/** Compact attention strip — replaces oversized NextAction + multi-card metrics. */
export function AttendanceAttentionStrip({
  rows,
  exceptionCount,
}: {
  rows: PosthireAttendanceRow[]
  exceptionCount?: number
}) {
  const locale = useEmployees360Locale()
  const t = labels[locale]
  const stats = useMemo(() => {
    let present = 0
    let late = 0
    let absent = 0
    let review = 0
    let excluded = 0
    for (const row of rows) {
      const life = attendanceLifeState(row)
      if (life === 'absent') absent += 1
      else if (life === 'needs_review' || life === 'incomplete' || life === 'disputed') review += 1
      else if (Number(row.late_minutes || 0) > 0) late += 1
      else present += 1
      if (payrollExclusionReason(row, locale)) excluded += 1
    }
    return { present, late, absent, review, excluded }
  }, [rows, locale])

  const attention = Math.max(stats.review + stats.absent, exceptionCount ?? 0)

  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[1.05rem] border border-semantic-line bg-semantic-surface-raised/90 px-4 py-3"
      data-testid="attendance-attention-strip"
      dir={locale === 'ar' ? 'rtl' : 'ltr'}
    >
      <div className="min-w-0">
        <p className="text-[13px] font-semibold text-text">
          {attention
            ? locale === 'ar'
              ? `${attention} ${t.attention}`
              : `${attention} need${attention === 1 ? 's' : ''} attention`
            : locale === 'ar'
              ? 'لا استثناءات ظاهرة'
              : 'No exceptions in view'}
        </p>
        <p className="text-[12px] text-subtle/85">{t.attentionHint}</p>
      </div>
      <div className="ms-auto flex flex-wrap gap-x-3 gap-y-1 text-[12px] tabular-nums text-subtle/80">
        <span>
          {t.present} {stats.present}
        </span>
        <span>
          {t.late} {stats.late}
        </span>
        <span>
          {t.absent} {stats.absent}
        </span>
        <span>
          {t.review} {stats.review}
        </span>
        {stats.excluded ? (
          <span>
            {t.excluded} {stats.excluded}
          </span>
        ) : null}
      </div>
    </div>
  )
}

/** @deprecated Prefer AttendanceAttentionStrip — kept for any external import. */
export function AttendanceOverviewStats({ rows }: { rows: PosthireAttendanceRow[] }) {
  return <AttendanceAttentionStrip rows={rows} />
}

export function AttendanceDailyTable({
  rows,
  canManage,
  onResolve,
  emptyAction,
}: {
  rows: PosthireAttendanceRow[]
  canManage: boolean
  /** Wave 1: route board exceptions into Ops — no board mutations. */
  onResolve?: (row: PosthireAttendanceRow) => void
  emptyAction?: ReactNode
}) {
  const locale = useEmployees360Locale()
  const t = labels[locale]
  const isAr = locale === 'ar'
  const [expanded, setExpanded] = useState<string | null>(null)

  if (rows.length === 0) {
    return (
      <div className="rounded-[1.2rem] border border-semantic-line bg-semantic-surface-raised px-5 py-10 text-center" dir={isAr ? 'rtl' : 'ltr'}>
        <CalendarDays className="mx-auto h-5 w-5 text-mist" />
        <p className="mt-3 text-[15px] font-semibold text-text">{t.empty}</p>
        <p className="mt-1 text-[13px] text-subtle/90">{t.emptyHint}</p>
        {emptyAction}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-[1.1rem] border border-semantic-line" dir={isAr ? 'rtl' : 'ltr'} data-testid="attendance-daily-table">
      <table className="w-full min-w-[860px] text-start text-[13px]">
        <thead className="bg-semantic-accent-soft/50 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
          <tr>
            <th className="px-4 py-3 font-medium">{t.employee}</th>
            <th className="px-4 py-3 font-medium">{t.date}</th>
            <th className="px-4 py-3 font-medium">{t.scheduled}</th>
            <th className="px-4 py-3 font-medium">{t.actual}</th>
            <th className="px-4 py-3 font-medium">{t.worked}</th>
            <th className="px-4 py-3 font-medium">{t.lateEarly}</th>
            <th className="px-4 py-3 font-medium">{t.state}</th>
            <th className="px-4 py-3 text-end font-medium">{t.action}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-semantic-line/80">
          {rows.map((row, idx) => {
            const rowKey = row.attendance_id || `${row.employee_key}-${idx}`
            const life = attendanceLifeState(row)
            const meta = row.metadata || {}
            const worked = formatMinutes(Number(meta.worked_minutes ?? 0), locale)
            const late = Number(row.late_minutes || 0)
            const early = Number(row.early_leave_minutes ?? meta.early_leave_minutes ?? 0)
            const scheduled = `${formatClock(row.scheduled_start)} – ${formatClock(row.scheduled_end)}`
            const actual = `${formatClock(row.check_in_at)} → ${formatClock(row.check_out_at)}`
            const exclusion = payrollExclusionReason(row, locale)
            const isOpen = expanded === rowKey
            const needsResolve = rowNeedsResolve(row)
            return (
              <Fragment key={rowKey}>
                <tr className="hover:bg-white/70" data-testid="attendance-board-row" data-employee-key={row.employee_key || ''}>
                  <td className="px-4 py-3 font-semibold text-text">{row.employee_name || row.employee_key || '—'}</td>
                  <td className="px-4 py-3 text-subtle/90">{formatDate(row.attendance_date, locale)}</td>
                  <td className="px-4 py-3 text-subtle/90">{scheduled}</td>
                  <td className="px-4 py-3 text-subtle/90">{actual}</td>
                  <td className="px-4 py-3 text-subtle/90">{worked}</td>
                  <td className="px-4 py-3 text-subtle/90">
                    {late > 0 ? <span className="text-rose-700">+{late}m</span> : null}
                    {late > 0 && early > 0 ? ' · ' : null}
                    {early > 0 ? <span className="text-amber-800">-{early}m</span> : null}
                    {!late && !early ? '—' : null}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StatusPill tone={lifeStateTone(life)}>{lifeStateLabel(life, locale)}</StatusPill>
                      {exclusion ? (
                        <Badge tone="warning" className="text-[10px]">
                          {t.excluded}
                        </Badge>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-end">
                    <div className="flex flex-wrap items-center justify-end gap-1.5">
                      <Button variant="ghost" size="sm" onClick={() => setExpanded(isOpen ? null : rowKey)}>
                        <ChevronDown className={cn('h-3.5 w-3.5 transition', isOpen && 'rotate-180')} />
                        {isOpen ? t.collapse : t.expand}
                      </Button>
                      {canManage && needsResolve && onResolve ? (
                        <Button size="sm" variant="secondary" onClick={() => onResolve(row)}>
                          {t.resolve}
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
                {isOpen ? (
                  <tr className="bg-semantic-surface-raised/90">
                    <td colSpan={8} className="px-4 py-4">
                      <div className="grid gap-3 lg:grid-cols-2">
                        <div className="rounded-[1rem] border border-semantic-line bg-white px-3 py-3">
                          <p className="text-[12px] font-semibold text-mist">{t.sessions}</p>
                          <p className="mt-1 text-[13px] text-text">{sessionSummary(row, locale)}</p>
                          <p className="mt-3 text-[12px] font-semibold text-mist">{t.breaks}</p>
                          <p className="mt-1 text-[13px] text-text">
                            {((meta.breaks as unknown[]) || []).length
                              ? `${(meta.breaks as unknown[]).length} ${locale === 'ar' ? 'استراحة' : 'break(s)'}`
                              : '—'}
                          </p>
                          {meta.projection_version != null ? (
                            <p className="mt-3 text-[12px] text-subtle">
                              {t.version}: {String(meta.projection_version)}
                            </p>
                          ) : null}
                        </div>
                        <div className="space-y-2">
                          <p className="text-[12px] font-semibold text-mist">{t.payroll}</p>
                          {exclusion ? (
                            <BlockedReason locale={locale} reason={exclusion} />
                          ) : (
                            <p className="rounded-[1rem] border border-semantic-success/40 bg-semantic-success-soft px-3 py-2 text-[13px] text-semantic-success-ink">
                              {locale === 'ar' ? 'مؤهل لكشف الرواتب عند الاعتماد.' : 'Eligible for Payroll when approved.'}
                            </p>
                          )}
                          {canManage && needsResolve && onResolve ? (
                            <Button size="sm" className="mt-2" onClick={() => onResolve(row)}>
                              {t.resolve}
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function AttendanceRangeCard({
  title,
  description,
  children,
  actions,
}: {
  title: string
  description: string
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <Card className="border-semantic-line bg-semantic-surface-raised">
      <CardHeader className="flex flex-col gap-3">
        <div className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-[17px]">
              <Clock className="h-4 w-4 text-mist" />
              {title}
            </CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          {actions}
        </div>
        {children}
      </CardHeader>
    </Card>
  )
}
