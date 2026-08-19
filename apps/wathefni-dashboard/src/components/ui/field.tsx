import { type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-11 rounded-2xl border border-white/70 bg-white/60 px-3.5 text-start text-sm text-text shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_22px_rgba(24,20,15,0.04)] placeholder:text-subtle/55',
        'outline-none transition duration-200 focus:border-[#c89445]/45 focus:bg-panel focus:ring-4 focus:ring-[#c89445]/15',
        className,
      )}
      {...props}
    />
  )
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'h-11 rounded-2xl border border-white/70 bg-white/60 px-3.5 text-start text-sm text-text shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_22px_rgba(24,20,15,0.04)] outline-none',
        'transition duration-200 focus:border-[#c89445]/45 focus:bg-panel focus:ring-4 focus:ring-[#c89445]/15',
        className,
      )}
      {...props}
    />
  )
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'min-h-24 rounded-2xl border border-white/70 bg-white/60 px-3.5 py-3 text-start text-sm text-text shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_22px_rgba(24,20,15,0.04)] placeholder:text-subtle/55',
        'outline-none transition duration-200 focus:border-[#c89445]/45 focus:bg-panel focus:ring-4 focus:ring-[#c89445]/15',
        className,
      )}
      {...props}
    />
  )
}
