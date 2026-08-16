import { type HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

type CardProps = HTMLAttributes<HTMLDivElement> & {
  /** board = hiring ops cream; quiet = analytical; glass = legacy soft panel */
  tone?: 'board' | 'quiet' | 'glass'
}

export function Card({ className, tone = 'board', ...props }: CardProps) {
  return (
    <section
      className={cn(
        'p-6',
        tone === 'board' && 'rounded-[var(--radius-wf-panel)] border border-[#e8dfd0]/75 bg-wf-surface shadow-[0_10px_28px_rgba(24,20,15,0.04)]',
        tone === 'quiet' && 'rounded-[var(--radius-wf-card)] border border-line/45 bg-panel/75 shadow-soft',
        tone === 'glass' && 'rounded-[1.6rem] border border-line/60 bg-panel/88 shadow-[0_16px_46px_rgba(24,20,15,0.055)] ring-1 ring-white/55 backdrop-blur-xl',
        className,
      )}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('mb-5 space-y-2 border-b border-line/50 pb-5', className)} {...props} />
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn('text-[17px] font-semibold tracking-[-0.02em] text-text', className)} {...props} />
}

export function CardDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('max-w-2xl text-[13px] leading-6 text-subtle/88', className)} {...props} />
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn(className)} {...props} />
}
