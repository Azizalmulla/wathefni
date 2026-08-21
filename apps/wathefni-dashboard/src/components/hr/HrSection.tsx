import { type ReactNode } from 'react'

import { SoftKeepSurface } from '@/components/ui/SoftKeepSurface'
import { cn } from '@/lib/utils'

export function HrSection({
  title,
  description,
  trailing,
  children,
  refreshing = false,
  refreshingLabel,
  cold = false,
  coldFallback,
  dir,
  className,
  testId,
}: {
  title?: string
  description?: string
  trailing?: ReactNode
  children: ReactNode
  refreshing?: boolean
  refreshingLabel?: string
  cold?: boolean
  coldFallback?: ReactNode
  dir?: 'ltr' | 'rtl'
  className?: string
  testId?: string
}) {
  return (
    <section
      className={cn('rounded-[1.55rem] bg-semantic-surface p-4 sm:p-5', className)}
      data-testid={testId}
      dir={dir}
    >
      {title || trailing ? (
        <div className="flex flex-wrap items-start justify-between gap-3 px-1 pb-3">
          <div className="min-w-0">
            {title ? (
              <h3 className="text-[15px] font-semibold tracking-[-0.025em] text-semantic-ink">{title}</h3>
            ) : null}
            {description ? <p className="mt-0.5 text-xs text-semantic-subtle">{description}</p> : null}
          </div>
          {trailing ? <div className="flex flex-wrap items-center gap-2">{trailing}</div> : null}
        </div>
      ) : null}
      <SoftKeepSurface cold={cold} coldFallback={coldFallback} refreshing={refreshing} refreshingLabel={refreshingLabel}>
        {children}
      </SoftKeepSurface>
    </section>
  )
}
