import { type ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function HrMetricTile({
  label,
  primary,
  unitLabel,
  hint,
  statusLabel,
  current = true,
  onClick,
  srLabel,
  className,
}: {
  label: string
  primary?: ReactNode
  unitLabel?: string
  hint?: string | null
  statusLabel?: string | null
  /** When false, do not present the number as live/current truth. */
  current?: boolean
  onClick?: () => void
  srLabel?: string
  className?: string
}) {
  const inner = (
    <>
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-semantic-mist">{label}</div>
      {current && primary != null ? (
        <div className="mt-3 text-[2.1rem] font-semibold leading-none tracking-[-0.06em] text-semantic-ink">{primary}</div>
      ) : (
        <div className="mt-3 text-sm font-medium leading-6 text-semantic-subtle">{statusLabel || primary || '—'}</div>
      )}
      {unitLabel || hint ? (
        <div className="mt-1.5 text-[11px] font-medium text-semantic-subtle">
          {unitLabel}
          {hint ? `${unitLabel ? ' · ' : ''}${hint}` : ''}
        </div>
      ) : null}
      {current && statusLabel ? (
        <div className="mt-2 text-[11px] text-semantic-mist">{statusLabel}</div>
      ) : null}
      {srLabel ? <span className="sr-only">{srLabel}</span> : null}
    </>
  )

  const classes = cn(
    'min-h-[132px] rounded-[1.35rem] border border-semantic-line bg-semantic-surface-raised p-4 text-start transition-colors duration-150',
    onClick && 'hover:border-semantic-accent/40 hover:bg-semantic-accent-soft/40',
    className,
  )

  if (onClick) {
    return (
      <button className={classes} onClick={onClick} type="button">
        {inner}
      </button>
    )
  }
  return <div className={classes}>{inner}</div>
}
