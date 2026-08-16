import { type HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

export type BadgeTone =
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'muted'
  | 'priority'
  | 'review'
  | 'assess'
  | 'follow'
  | 'paused'
  | 'active'

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone
}

/** Semantic status/category chip. Prefer named semantic tones over generic success/warning. */
export function Badge({ className, tone = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold leading-none shadow-[0_1px_0_rgba(255,255,255,0.7)_inset]',
        tone === 'default' && 'border-wf-accent-follow/35 bg-wf-accent-follow-soft/90 text-wf-accent-follow-ink',
        (tone === 'success' || tone === 'priority') &&
          'border-wf-accent-priority/45 bg-wf-accent-priority-soft text-wf-accent-priority-ink',
        (tone === 'warning' || tone === 'review') &&
          'border-wf-accent-review/55 bg-wf-accent-review-soft text-wf-accent-review-ink',
        tone === 'assess' && 'border-wf-accent-assess/45 bg-wf-accent-assess-soft text-wf-accent-assess-ink',
        tone === 'follow' && 'border-wf-accent-follow/45 bg-wf-accent-follow-soft text-wf-accent-follow-ink',
        tone === 'paused' && 'border-wf-accent-paused/50 bg-wf-accent-paused-soft text-wf-accent-paused-ink',
        (tone === 'danger' || tone === 'active') &&
          'border-wf-accent-active/40 bg-wf-accent-active-soft text-wf-accent-active-ink',
        tone === 'muted' && 'border-line/70 bg-white/45 text-subtle',
        className,
      )}
      {...props}
    />
  )
}
