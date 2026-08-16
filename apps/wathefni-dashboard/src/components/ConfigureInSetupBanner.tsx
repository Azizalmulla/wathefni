import type { ReactNode } from 'react'

import { ArrowUpRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import { setupConsoleHref } from '@/lib/setupConsoleOwnership'

/** Read-only summary + deep link when an operational screen must not edit company policy. */
export function ConfigureInSetupBanner({
  title,
  body,
  anchor,
  locale = 'en',
  className,
  children,
}: {
  title: string
  body: string
  anchor?: string
  locale?: 'en' | 'ar'
  className?: string
  children?: ReactNode
}) {
  const href = setupConsoleHref(anchor)
  const cta = locale === 'ar' ? 'الإعداد في وحدة التحكم' : 'Configure in Setup Console'
  return (
    <div
      role="note"
      className={cn(
        'rounded-2xl border border-sky-200/70 bg-sky-50/50 px-4 py-3 text-sm leading-6 text-sky-950',
        className,
      )}
      data-ownership-banner="setup_console"
    >
      <p className="font-medium text-text">{title}</p>
      <p className="mt-1 text-subtle">{body}</p>
      <a
        href={href}
        className="mt-2 inline-flex items-center gap-1 font-medium text-accent underline-offset-2 hover:underline"
        data-testid="configure-in-setup-console"
      >
        {cta}
        <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
      </a>
      {children}
    </div>
  )
}

export function ConfigureInOpsLink({
  href,
  label,
  className,
}: {
  href: string
  label: string
  className?: string
}) {
  return (
    <a
      href={href}
      className={cn(
        'inline-flex items-center gap-1 text-sm font-medium text-accent underline-offset-2 hover:underline',
        className,
      )}
      data-testid="configure-in-ops"
    >
      {label}
      <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
    </a>
  )
}
