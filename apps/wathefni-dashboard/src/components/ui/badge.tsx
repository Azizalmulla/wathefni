import { type HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'muted'
}

export function Badge({ className, tone = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold leading-none shadow-[0_1px_0_rgba(255,255,255,0.7)_inset]',
        tone === 'default' && 'border-slate-200/75 bg-slate-50/70 text-slate-700',
        tone === 'success' && 'border-emerald-200/70 bg-emerald-50/75 text-emerald-800',
        tone === 'warning' && 'border-[#e2bd78]/75 bg-[#fff7e8]/80 text-[#8a5a16]',
        tone === 'danger' && 'border-rose-200/75 bg-rose-50/75 text-rose-800',
        tone === 'muted' && 'border-line/70 bg-white/45 text-subtle',
        className,
      )}
      {...props}
    />
  )
}
