import { type HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        'rounded-[1.6rem] border border-line/60 bg-panel/88 p-6 shadow-[0_16px_46px_rgba(24,20,15,0.055)] ring-1 ring-white/55 backdrop-blur-xl',
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
