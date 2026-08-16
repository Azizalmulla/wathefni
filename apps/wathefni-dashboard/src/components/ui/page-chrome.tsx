import { type HTMLAttributes, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** Compact page intro — density varies by personality; never a forced four-card grid. */
export function PageIntro({
  eyebrow,
  title,
  description,
  density = 'default',
  className,
  dir,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  density?: 'default' | 'compact' | 'quiet'
  className?: string
  dir?: 'ltr' | 'rtl'
  actions?: ReactNode
}) {
  return (
    <div className={cn('flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between', className)} dir={dir}>
      <div>
        {eyebrow ? <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-mist">{eyebrow}</div> : null}
        <h2
          className={cn(
            'font-semibold tracking-[-0.04em] text-text',
            density === 'compact' ? 'mt-1 text-xl' : density === 'quiet' ? 'mt-1 text-2xl' : 'mt-1.5 text-2xl lg:text-[1.65rem]',
          )}
        >
          {title}
        </h2>
        {description ? (
          <p className={cn('text-subtle/90', density === 'compact' ? 'mt-1 text-[13px] leading-5' : 'mt-1.5 max-w-2xl text-[14px] leading-6')}>
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function StatusPill({
  children,
  tone = 'neutral',
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'priority' | 'review' | 'assess' | 'follow' | 'paused' | 'active'
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-[-0.01em]',
        tone === 'neutral' && 'bg-[#eee5d4] text-[#5c554a]',
        (tone === 'success' || tone === 'priority') && 'bg-wf-accent-priority-soft text-wf-accent-priority-ink',
        (tone === 'warning' || tone === 'review') && 'bg-wf-accent-review-soft text-wf-accent-review-ink',
        tone === 'assess' && 'bg-wf-accent-assess-soft text-wf-accent-assess-ink',
        (tone === 'info' || tone === 'follow') && 'bg-wf-accent-follow-soft text-wf-accent-follow-ink',
        tone === 'paused' && 'bg-wf-accent-paused-soft text-wf-accent-paused-ink',
        (tone === 'danger' || tone === 'active') && 'bg-wf-accent-active-soft text-wf-accent-active-ink',
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
}
