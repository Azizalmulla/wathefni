import type { LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { compactNumber } from '@/lib/utils'

export function MetricGrid({
  metrics,
}: {
  metrics: Array<{
    label: string
    value: number | string | undefined
    icon: LucideIcon
    onClick?: () => void
  }>
}) {
  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
      {metrics.map((metric) => {
        const Icon = metric.icon
        const interactive = typeof metric.onClick === 'function'
        const Tag = interactive ? 'button' : 'section'
        return (
          <Tag
            className={`rounded-[1.35rem] border border-line/55 bg-panel/70 p-4 text-start shadow-[0_10px_28px_rgba(24,20,15,0.035)]${interactive ? ' cursor-pointer transition hover:border-line' : ''}`}
            key={metric.label}
            onClick={metric.onClick}
            type={interactive ? 'button' : undefined}
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle">{metric.label}</div>
                <div className="mt-2 text-2xl font-semibold tracking-tight">{compactNumber(metric.value)}</div>
              </div>
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-2xl border border-line/55 bg-white/45 text-slate">
                <Icon size={18} />
              </div>
            </div>
          </Tag>
        )
      })}
    </section>
  )
}

export function ScoreBreakdown({ label, max, value }: { label: string; max: number; value: number }) {
  const width = Math.max(4, Math.min(100, (Number(value || 0) / max) * 100))
  return (
    <div className="rounded-2xl border border-white/70 bg-white/50 p-3 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_20px_rgba(24,20,15,0.035)]">
      <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-subtle">
        <span>{label}</span>
        <span>
          {Math.round(value)}/{max}
        </span>
      </div>
      <div className="mt-2 h-1.5 rounded-full bg-panel-muted">
        <div className="h-1.5 rounded-full bg-ink" style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

export function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="rounded-2xl border border-line/55 bg-white/32 p-3.5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle">{label}</div>
      <div className="mt-1.5 break-words text-sm font-medium text-text">{value || '—'}</div>
    </div>
  )
}

export function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[1.5rem] border border-dashed border-line/75 bg-white/28 p-5 text-sm leading-6 text-subtle">
      <div className="flex items-center gap-2 font-medium text-text">
        <span className="h-1.5 w-1.5 rounded-full bg-[#c89445]" />
        <span className="max-w-2xl">{text}</span>
      </div>
    </div>
  )
}

export { Badge }
