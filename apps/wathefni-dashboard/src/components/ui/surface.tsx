import { type HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

/** Flexible surface variants — composition aids, not page templates. */
export type SurfaceTone = 'desk' | 'board' | 'people' | 'quiet' | 'chat' | 'eval'

const toneClass: Record<SurfaceTone, string> = {
  desk: 'rounded-[var(--radius-wf-panel)] bg-wf-surface',
  board: 'rounded-[var(--radius-wf-panel)] border border-[#e8dfd0]/80 bg-wf-surface',
  people: 'rounded-[var(--radius-wf-panel)] border border-line/45 bg-wf-surface/95',
  quiet: 'rounded-[var(--radius-wf-card)] border border-line/40 bg-panel/70',
  chat: 'rounded-[1.75rem] border border-line/40 bg-wf-surface/90',
  eval: 'rounded-[var(--radius-wf-panel)] border border-[#e8dfd0]/70 bg-wf-surface/90',
}

export function Surface({
  tone = 'board',
  className,
  ...props
}: HTMLAttributes<HTMLElement> & { tone?: SurfaceTone }) {
  return <section className={cn(toneClass[tone], className)} {...props} />
}
