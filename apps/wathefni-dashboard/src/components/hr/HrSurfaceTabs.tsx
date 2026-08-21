import { type ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type HrSurfaceTabItem<T extends string> = {
  id: T
  label: string
  count?: number
  testId?: string
  title?: string
  /** Extra data-* for existing contracts (e.g. data-surface). */
  dataAttrs?: Record<string, string>
}

/**
 * URL-friendly surface tabs. Color/opacity only — no hover translate or shadow.
 * Does not compute totals; optional `count` is caller-supplied (backend or list length).
 */
export function HrSurfaceTabs<T extends string>({
  value,
  onChange,
  items,
  ariaLabel,
  testId,
  className,
  trailing,
}: {
  value: T
  onChange: (id: T) => void
  items: Array<HrSurfaceTabItem<T>>
  ariaLabel?: string
  testId?: string
  className?: string
  trailing?: ReactNode
}) {
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <div
        className="inline-flex w-fit max-w-full flex-wrap items-center gap-0.5 rounded-[0.75rem] bg-semantic-ink/[0.05] p-0.5"
        role="tablist"
        aria-label={ariaLabel}
        data-testid={testId}
      >
        {items.map((item) => {
          const selected = value === item.id
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              data-surface={item.id}
              data-testid={item.testId}
              title={item.title}
              {...item.dataAttrs}
              className={cn(
                'rounded-[0.6rem] px-3.5 py-1.5 text-[12px] font-semibold transition-colors duration-150 ease-out',
                selected ? 'bg-semantic-ink text-white' : 'text-semantic-subtle hover:text-semantic-ink',
              )}
              onClick={() => onChange(item.id)}
            >
              {item.label}
              {typeof item.count === 'number' ? <span className="ms-1 opacity-80">({item.count})</span> : null}
            </button>
          )
        })}
      </div>
      {trailing}
    </div>
  )
}
