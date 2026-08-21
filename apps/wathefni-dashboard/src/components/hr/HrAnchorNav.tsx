import { cn } from '@/lib/utils'

export type HrAnchorNavItem = {
  id: string
  label: string
}

/**
 * In-page jump nav. Scrolls to existing section ids — does not invent data or totals.
 * Color/opacity only.
 */
export function HrAnchorNav({
  items,
  ariaLabel,
  dir,
  className,
}: {
  items: HrAnchorNavItem[]
  ariaLabel?: string
  dir?: 'ltr' | 'rtl'
  className?: string
}) {
  if (!items.length) return null
  return (
    <nav
      className={cn('flex flex-wrap gap-1.5', className)}
      aria-label={ariaLabel}
      dir={dir}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className="rounded-full border border-semantic-line/70 bg-semantic-surface-raised px-3 py-1 text-[12px] font-semibold text-semantic-subtle transition-colors duration-150 ease-out hover:border-semantic-accent/40 hover:text-semantic-ink"
          onClick={() => {
            document.getElementById(item.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )
}
