import { Loader2 } from 'lucide-react'
import type { HTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/utils'

type SoftKeepSurfaceProps = HTMLAttributes<HTMLDivElement> & {
  /** Quiet non-reflow strip while soft-refreshing (content already painted). */
  refreshing?: boolean
  refreshingLabel?: string
  /** Genuine first load only — replaces children with coldFallback. */
  cold?: boolean
  coldFallback?: ReactNode
  children: ReactNode
}

/**
 * Soft-keep container: never blanks painted content on refetch.
 * No opacity flash. Updating rail does not remount the body.
 */
export function SoftKeepSurface({
  refreshing = false,
  refreshingLabel = 'Updating…',
  cold = false,
  coldFallback,
  className,
  children,
  ...props
}: SoftKeepSurfaceProps) {
  return (
    <div
      className={cn('relative', className)}
      data-rendering-soft-keep
      data-rendering-updating={refreshing && !cold ? 'true' : undefined}
      aria-busy={refreshing || cold || undefined}
      {...props}
    >
      {refreshing && !cold ? (
        <div
          className="pointer-events-none absolute inset-x-0 top-0 z-10 flex h-0.5 overflow-hidden"
          data-rendering-updating-rail
          aria-hidden
        >
          <span className="block h-full w-1/3 animate-pulse rounded-full bg-wf-accent-follow" />
        </div>
      ) : null}
      {refreshing && !cold ? (
        <p className="sr-only">{refreshingLabel}</p>
      ) : null}
      {cold && coldFallback != null ? coldFallback : children}
    </div>
  )
}

/** Compact inline status for headers — does not reflow primary CTAs. */
export function SoftKeepStatus({
  refreshing,
  label = 'Updating…',
  className,
}: {
  refreshing?: boolean
  label?: string
  className?: string
}) {
  if (!refreshing) return null
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 text-[11px] text-muted', className)}
      data-rendering-soft-status
    >
      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
      {label}
    </span>
  )
}
