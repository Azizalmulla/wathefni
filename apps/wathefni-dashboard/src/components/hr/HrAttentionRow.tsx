import { type ReactNode } from 'react'

import { HrDestinationButton } from '@/components/hr/HrDestinationButton'
import { cn } from '@/lib/utils'

export function HrAttentionRow({
  title,
  detail,
  meta,
  actionLabel,
  onAction,
  disabled,
  className,
}: {
  title: string
  detail?: ReactNode
  meta?: Array<{ label: string; value: string }>
  actionLabel?: string
  onAction?: () => void
  disabled?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex min-h-[60px] flex-col gap-3 rounded-[1.1rem] border border-semantic-line bg-semantic-surface-raised px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold text-semantic-ink">{title}</div>
        {detail ? <div className="mt-0.5 text-xs text-semantic-subtle">{detail}</div> : null}
        {meta?.length ? (
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-semantic-mist">
            {meta.map((item) => (
              <span key={`${item.label}:${item.value}`}>
                {item.label}: {item.value}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      {actionLabel && onAction ? (
        <HrDestinationButton disabled={disabled} onClick={onAction}>
          {actionLabel}
        </HrDestinationButton>
      ) : null}
    </div>
  )
}
