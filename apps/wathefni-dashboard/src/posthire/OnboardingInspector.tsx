/**
 * Onboarding checklist inspector — Leave-style drawer + portal overflow menu.
 * Keeps the Wathefni visual system; avoids inline queue expansion/jump.
 */
import { MoreHorizontal, X } from 'lucide-react'
import {
  type ReactNode,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'

import { Button } from '@/components/ui/button'
import type { OnboardingPrimaryKind } from '@/posthire/onboardingPrimaryAction'

export function OnboardingPrimaryButton({
  kind,
  label,
  busy,
  disabled,
  onClick,
  testId,
}: {
  kind: OnboardingPrimaryKind
  label: string
  busy?: boolean
  disabled?: boolean
  onClick: () => void
  testId?: string
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={kind === 'remind' ? 'secondary' : 'secondary'}
      className="min-w-[7.5rem] justify-center"
      disabled={disabled || busy}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      data-testid={testId || `onboarding-primary-${kind}`}
    >
      {busy ? (
        <span className="inline-flex h-4 w-4 animate-pulse rounded-full bg-current/40" aria-hidden />
      ) : (
        label
      )}
    </Button>
  )
}

export function OnboardingOverflowMenu({
  open,
  onOpenChange,
  children,
  label,
  align = 'end',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
  label: string
  align?: 'start' | 'end'
}) {
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null)

  const updatePosition = () => {
    const el = triggerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const width = 220
    const left = align === 'end' ? rect.right - width : rect.left
    setCoords({
      top: rect.bottom + 6,
      left: Math.max(8, Math.min(left, window.innerWidth - width - 8)),
    })
  }

  useLayoutEffect(() => {
    if (!open) return
    updatePosition()
  }, [open, align])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false)
    }
    const onPointer = (e: MouseEvent) => {
      const t = e.target as Node
      if (menuRef.current?.contains(t) || triggerRef.current?.contains(t)) return
      onOpenChange(false)
    }
    const onScroll = () => onOpenChange(false)
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onPointer)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onPointer)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onScroll)
    }
  }, [open, onOpenChange])

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="rounded-lg p-1.5 text-subtle hover:bg-[#f7f1e6]"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        data-testid="onboarding-more"
        onClick={(e) => {
          e.stopPropagation()
          onOpenChange(!open)
        }}
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open && coords
        ? createPortal(
            <div
              ref={menuRef}
              role="menu"
              data-testid="onboarding-more-menu"
              className="fixed z-[80] w-[220px] rounded-xl border border-[#e8dfd0] bg-[#fffdf8] p-1.5 shadow-[0_18px_40px_rgba(24,20,15,0.18)]"
              style={{ top: coords.top, left: coords.left }}
              onClick={(e) => e.stopPropagation()}
            >
              {children}
            </div>,
            document.body,
          )
        : null}
    </>
  )
}

export function OnboardingDetailDrawer({
  open,
  title,
  subtitle,
  isAr,
  onClose,
  children,
}: {
  open: boolean
  title: string
  subtitle?: string
  isAr?: boolean
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/25 backdrop-blur-[2px]"
      onClick={onClose}
      data-testid="onboarding-detail-drawer"
    >
      <aside
        className="flex h-full w-full max-w-lg flex-col border-s border-[#e8dfd0] bg-[#fffdf8]/98 shadow-[-20px_0_60px_rgba(24,20,15,0.18)]"
        dir={isAr ? 'rtl' : 'ltr'}
        lang={isAr ? 'ar' : 'en'}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[#e8dfd0] px-5 py-4">
          <div className="min-w-0 space-y-1">
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">{title}</p>
            {subtitle ? <p className="text-[12px] text-subtle/85">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            className="rounded-full p-1.5 text-subtle hover:bg-[#f7f1e6]"
            onClick={onClose}
            aria-label={isAr ? 'إغلاق' : 'Close'}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </div>,
    document.body,
  )
}
