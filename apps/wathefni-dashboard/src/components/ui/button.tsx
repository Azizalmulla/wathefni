import { Loader2 } from 'lucide-react'
import { type ButtonHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'secondary' | 'ghost'
  size?: 'sm' | 'md'
  /** Local pending: disables the control, keeps width stable, exposes aria-busy. */
  pending?: boolean
}

export function Button({
  className,
  variant = 'default',
  size = 'md',
  pending = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      aria-busy={pending || undefined}
      disabled={disabled || pending}
      className={cn(
        'relative inline-flex items-center justify-center gap-2 rounded-full font-semibold tracking-[-0.01em] transition duration-200 ease-out disabled:pointer-events-none disabled:opacity-50',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#c89445]',
        size === 'sm' ? 'h-9 px-3.5 text-sm' : 'h-11 px-5 text-sm',
        variant === 'default' && 'bg-[linear-gradient(180deg,#24211d_0%,#11100e_100%)] text-white shadow-[0_12px_28px_rgba(24,20,15,0.18)] hover:-translate-y-0.5 hover:shadow-[0_16px_36px_rgba(24,20,15,0.22),0_0_0_1px_rgba(200,148,69,0.12)] active:translate-y-0 active:shadow-soft',
        variant === 'secondary' && 'border border-white/70 bg-panel/80 text-text shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_22px_rgba(24,20,15,0.05)] hover:-translate-y-0.5 hover:border-[#c89445]/25 hover:bg-white/90 hover:shadow-[0_14px_30px_rgba(24,20,15,0.08)] active:translate-y-0',
        variant === 'ghost' && 'text-subtle hover:bg-[#f4e7cf]/45 hover:text-text active:bg-panel-muted',
        className,
      )}
      {...props}
    >
      {/* Overlay spinner — children stay mounted so pending never changes button width. */}
      {pending ? (
        <Loader2 className="pointer-events-none absolute h-4 w-4 animate-spin" aria-hidden="true" data-button-pending-slot />
      ) : null}
      <span className={cn('inline-flex items-center justify-center gap-2', pending && 'opacity-0')}>{children}</span>
    </button>
  )
}
