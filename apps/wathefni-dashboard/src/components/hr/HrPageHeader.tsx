import { type ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function HrPageHeader({
  eyebrow,
  title,
  description,
  actions,
  dir,
  className,
  titleAs = 'h1',
  density = 'hero',
}: {
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
  dir?: 'ltr' | 'rtl'
  className?: string
  titleAs?: 'h1' | 'h2'
  /** `hero` is Overview home. `page` is operational modules under the same hierarchy. */
  density?: 'hero' | 'page'
}) {
  const TitleTag = titleAs
  return (
    <header
      className={cn(
        'flex flex-col gap-3 px-1 pb-1 pt-1 text-start sm:flex-row sm:items-start sm:justify-between',
        density === 'page' && 'border-b border-semantic-line/40 pb-5',
        className,
      )}
      dir={dir}
    >
      <div className="max-w-2xl">
        {eyebrow ? (
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-semantic-mist">{eyebrow}</div>
        ) : null}
        <TitleTag
          className={cn(
            'font-semibold leading-none text-semantic-ink',
            density === 'hero'
              ? 'mt-2 text-[2rem] tracking-[-0.055em] sm:text-[2.4rem]'
              : 'mt-2 text-[1.65rem] tracking-[-0.04em] sm:text-[1.9rem] lg:text-[2.1rem]',
          )}
        >
          {title}
        </TitleTag>
        {description ? <div className="mt-2 text-sm text-semantic-subtle">{description}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  )
}
