import { type HTMLAttributes, type ReactNode } from 'react'

import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'
import { StatusPill } from '@/components/ui/page-chrome'
import { readStoredRecruitingLocale } from '@/lib/dashboardLocale'
import { cn } from '@/lib/utils'

export type Locale = 'en' | 'ar'

export function useEmployees360Locale(): Locale {
  if (typeof document !== 'undefined' && document.documentElement.lang === 'ar') return 'ar'
  return readStoredRecruitingLocale()
}

export function MaskedField({
  label,
  masked = true,
  value,
  revealLabel,
  onReveal,
  className,
}: {
  label: string
  masked?: boolean
  value?: string | null
  revealLabel?: string
  onReveal?: () => void
  className?: string
}) {
  const display = masked ? '••••' : value || '—'
  return (
    <div className={cn('space-y-1', className)}>
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mist">{label}</div>
      <div className="flex items-center gap-2">
        <span className="font-mono text-[13px] tracking-wide text-text">{display}</span>
        {masked && onReveal ? (
          <button type="button" className="text-[12px] font-medium text-wf-ink underline-offset-2 hover:underline" onClick={onReveal}>
            {revealLabel || 'Request unmask'}
          </button>
        ) : null}
      </div>
    </div>
  )
}

export function RecordEpoch({
  epoch,
  locale = 'en',
  className,
}: {
  epoch: 'current' | 'scheduled' | 'historical'
  locale?: Locale
  className?: string
}) {
  const labels = {
    en: { current: 'Current', scheduled: 'Scheduled', historical: 'Historical' },
    ar: { current: 'الحالي', scheduled: 'مجدول', historical: 'تاريخي' },
  } as const
  const tone = epoch === 'current' ? 'priority' : epoch === 'scheduled' ? 'follow' : 'paused'
  return (
    <StatusPill tone={tone} className={className}>
      {labels[locale][epoch]}
    </StatusPill>
  )
}

export function ApprovalStrip({
  state,
  nextApprover,
  locale = 'en',
  className,
}: {
  state: string
  nextApprover?: string | null
  locale?: Locale
  className?: string
}) {
  const isAr = locale === 'ar'
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-2 rounded-[1rem] border border-semantic-line bg-semantic-surface-raised px-3 py-2 text-[13px]',
        className,
      )}
      dir={isAr ? 'rtl' : 'ltr'}
    >
      <StatusPill tone={stateTone(state)}>{state.replace(/_/g, ' ')}</StatusPill>
      {nextApprover ? (
        <span className="text-subtle/90">
          {isAr ? 'التالي:' : 'Next:'} <span className="font-medium text-text">{nextApprover}</span>
        </span>
      ) : (
        <span className="text-subtle/80">{isAr ? 'لا يوجد معتمد تالٍ' : 'No next approver'}</span>
      )}
    </div>
  )
}

function stateTone(state: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  const s = state.toLowerCase()
  if (['applied', 'approved', 'complete', 'resolved'].some((x) => s.includes(x))) return 'success'
  if (['pending', 'submitted', 'needs_information'].some((x) => s.includes(x))) return 'review'
  if (['needs_review', 'conflict', 'stale'].some((x) => s.includes(x))) return 'warning'
  if (['rejected', 'failed', 'blocked'].some((x) => s.includes(x))) return 'danger'
  if (['withdrawn', 'cancelled', 'draft'].some((x) => s.includes(x))) return 'paused'
  return 'info'
}

export function ConflictBanner({
  title,
  detail,
  locale = 'en',
  action,
  className,
}: {
  title?: string
  detail: string
  locale?: Locale
  action?: ReactNode
  className?: string
}) {
  const isAr = locale === 'ar'
  return (
    <div
      className={cn('rounded-[1.1rem] border border-semantic-warning/40 bg-semantic-warning/15 px-4 py-3', className)}
      dir={isAr ? 'rtl' : 'ltr'}
      role="alert"
    >
      <p className="text-[13px] font-semibold text-wf-accent-review-ink">{title || (isAr ? 'تعارض يحتاج مراجعة' : 'Conflict needs review')}</p>
      <p className="mt-1 text-[13px] leading-5 text-wf-accent-review-ink/90">{detail}</p>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  )
}

export function BlockedReason({
  reason,
  missing,
  locale = 'en',
  className,
}: {
  reason: string
  missing?: string[]
  locale?: Locale
  className?: string
}) {
  const isAr = locale === 'ar'
  return (
    <div className={cn('rounded-[1rem] border border-line/60 bg-panel-muted/50 px-3 py-2 text-[13px] text-subtle', className)} dir={isAr ? 'rtl' : 'ltr'}>
      <p className="font-medium text-text">{isAr ? 'محظور' : 'Blocked'}: {reason}</p>
      {missing?.length ? (
        <p className="mt-1 text-[12px]">
          {isAr ? 'مطلوب:' : 'Missing:'} {missing.join(', ')}
        </p>
      ) : null}
    </div>
  )
}

export function WorkflowEmpty({
  title,
  hint,
  icon,
  action,
  className,
}: {
  title: string
  hint?: string
  icon?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 rounded-[var(--radius-wf-panel)] border border-dashed border-semantic-line bg-semantic-surface-raised/70 px-6 py-12 text-center', className)}>
      {icon ? <div className="text-mist">{icon}</div> : null}
      <p className="text-[15px] font-semibold tracking-[-0.02em] text-text">{title}</p>
      {hint ? <p className="max-w-md text-[13px] leading-5 text-subtle/90">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}

export function WorkforceSectionRail({
  sections,
  active,
  onChange,
  locale = 'en',
  className,
}: {
  sections: { id: string; labelEn: string; labelAr: string }[]
  active: string
  onChange: (id: string) => void
  locale?: Locale
  className?: string
}) {
  const isAr = locale === 'ar'
  return (
    <HrSurfaceTabs
      value={active}
      onChange={onChange}
      className={className}
      ariaLabel={isAr ? 'أقسام الهيكل' : 'Organization sections'}
      items={sections.map((s) => ({
        id: s.id,
        label: isAr ? s.labelAr : s.labelEn,
      }))}
    />
  )
}

export function QuietStat({
  label,
  value,
  hint,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { label: string; value: string | number; hint?: string }) {
  return (
    <div className={cn('rounded-[1.1rem] border border-semantic-line/80 bg-semantic-surface px-4 py-3', className)} {...props}>
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mist">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-text">{value}</div>
      {hint ? <div className="mt-0.5 text-[12px] text-subtle/85">{hint}</div> : null}
    </div>
  )
}
