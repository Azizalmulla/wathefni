import { type ButtonHTMLAttributes, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

type HrDestinationButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  size?: 'sm' | 'md'
}

/**
 * Navigates a backend destination. Never computes a cohort or total.
 * Color/opacity only — no hover translate or decorative shadow.
 */
export function HrDestinationButton({
  children,
  className,
  size = 'sm',
  type = 'button',
  ...props
}: HrDestinationButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full bg-semantic-ink font-semibold text-white transition-colors duration-150 ease-out',
        'hover:bg-semantic-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-semantic-accent',
        'disabled:pointer-events-none disabled:opacity-50',
        size === 'sm' ? 'h-8 px-3 text-xs' : 'h-9 px-4 text-sm',
        className,
      )}
      type={type}
      {...props}
    >
      {children}
    </button>
  )
}
