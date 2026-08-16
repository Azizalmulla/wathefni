import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'

import { Button } from '@/components/ui/button'
import { useBodyScrollLock, useOverlayFocus } from '@/hooks/useOverlayA11y'
import { cn } from '@/lib/utils'

export type ConfirmOptions = {
  title?: string
  body: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  // Strong (destructive) confirmations are styled in red and used for actions that
  // are hard to reverse (hire, deactivate, disconnect, archive, role/permission
  // changes). Light confirmations are calm/amber and used for external sends,
  // exports, bulk workflow steps — a gentle "just checking" rather than a warning.
  destructive?: boolean
  /** When set, confirm resolves only after a non-empty reason is entered. */
  requireReason?: boolean
  /** Minimum trimmed reason length when requireReason is set (default 1). */
  minReasonLength?: number
  reasonLabel?: string
  reasonPlaceholder?: string
  dir?: 'ltr' | 'rtl'
  /**
   * Optional async work that must finish before the dialog closes.
   * When provided, Confirm stays open (pending) until `run` resolves.
   * On throw, the dialog stays open and shows the error message.
   * Callers that mutate after `await confirm(...)` can keep the legacy pattern.
   */
  run?: (ctx: { reason?: string }) => Promise<void>
}

type PendingConfirm = {
  options: ConfirmOptions
  resolve: (result: { confirmed: boolean; reason?: string }) => void
}

type ConfirmFn = {
  (options: ConfirmOptions): Promise<boolean>
  withReason: (options: ConfirmOptions) => Promise<string | null>
}

const ConfirmContext = createContext<ConfirmFn | null>(null)

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null)

  const confirmWithReason = useCallback((options: ConfirmOptions) => {
    return new Promise<string | null>((resolve) => {
      setPending({
        options: { ...options, requireReason: true },
        resolve: (result) => resolve(result.confirmed ? String(result.reason || '').trim() || null : null),
      })
    })
  }, [])

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setPending({
        options,
        resolve: (result) => resolve(result.confirmed),
      })
    })
  }, []) as ConfirmFn

  confirm.withReason = confirmWithReason

  const settle = useCallback((result: { confirmed: boolean; reason?: string }) => {
    setPending((current) => {
      current?.resolve(result)
      return null
    })
  }, [])

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending ? (
        <ConfirmDialog
          options={pending.options}
          onConfirm={(reason) => settle({ confirmed: true, reason })}
          onCancel={() => settle({ confirmed: false })}
        />
      ) : null}
    </ConfirmContext.Provider>
  )
}

// Returns confirm(options) -> Promise<boolean>. Resolves true when the user
// confirms, false when they cancel or dismiss. Wrap a handler like:
//   if (!(await confirm({ body: '…', destructive: true }))) return
// For required reason: await confirm.withReason({ … }) → string | null
// For keep-open mutations: confirm({ body: '…', run: async () => { await mutate() } })
export function useConfirm() {
  const ctx = useContext(ConfirmContext)
  if (!ctx) {
    throw new Error('useConfirm must be used within a ConfirmProvider')
  }
  return ctx
}

function ConfirmDialog({
  options,
  onConfirm,
  onCancel,
}: {
  options: ConfirmOptions
  onConfirm: (reason?: string) => void
  onCancel: () => void
}) {
  const {
    title,
    body,
    confirmLabel,
    cancelLabel,
    destructive,
    requireReason,
    minReasonLength,
    reasonLabel,
    reasonPlaceholder,
    dir,
    run,
  } = options
  const [working, setWorking] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  useBodyScrollLock(true)
  useOverlayFocus(true, working ? () => undefined : onCancel, panelRef)

  const minLen = Math.max(1, minReasonLength ?? 1)
  const reasonOk = !requireReason || reason.trim().length >= minLen
  const reasonHint =
    requireReason && reason.trim().length > 0 && reason.trim().length < minLen
      ? `Enter at least ${minLen} characters`
      : null

  useEffect(() => {
    if (requireReason) {
      const input = panelRef.current?.querySelector<HTMLTextAreaElement>('textarea')
      input?.focus()
    }
  }, [requireReason])

  const handleConfirm = async () => {
    if (!reasonOk || working) return
    const trimmed = reason.trim()
    setRunError(null)
    if (!run) {
      setWorking(true)
      onConfirm(trimmed)
      return
    }
    setWorking(true)
    try {
      await run({ reason: requireReason ? trimmed : undefined })
      onConfirm(trimmed)
    } catch (err) {
      setWorking(false)
      setRunError(err instanceof Error && err.message ? err.message : 'Something went wrong. Please try again.')
    }
  }

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/35 px-4 backdrop-blur-sm"
      dir={dir}
      onClick={() => (working ? null : onCancel())}
      role="dialog"
      data-interaction-confirm
    >
      <div
        className="w-full max-w-md rounded-[1.6rem] border border-[#e8dfd0] bg-[#fffaf0] p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60"
        onClick={(event) => event.stopPropagation()}
        ref={panelRef}
      >
        <div className="flex items-start gap-3">
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
              destructive ? 'bg-rose-50 text-rose-600' : 'bg-[#fff7e8] text-[#8a5a16]',
            )}
          >
            {destructive ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
          </div>
          <div className="space-y-1">
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-[#23211d]">{title || 'Please confirm'}</p>
            <div className="text-[13px] leading-6 text-[#716a5e]">{body}</div>
          </div>
        </div>
        {requireReason ? (
          <label className="mt-4 block space-y-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#716a5e]">
              {reasonLabel || 'Reason'}
            </span>
            <textarea
              className="min-h-[88px] w-full rounded-xl border border-[#e8dfd0] bg-white/70 px-3 py-2 text-sm text-[#23211d] outline-none focus:border-[#23211d]/40"
              onChange={(event) => setReason(event.target.value)}
              placeholder={reasonPlaceholder || ''}
              value={reason}
              aria-invalid={Boolean(reasonHint)}
              disabled={working}
            />
            {reasonHint ? <span className="text-[12px] text-rose-700">{reasonHint}</span> : null}
          </label>
        ) : null}
        {runError ? <p className="mt-3 text-[13px] text-rose-700" role="alert">{runError}</p> : null}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={working}>
            {cancelLabel || 'Cancel'}
          </Button>
          <Button
            size="sm"
            className={destructive ? 'bg-rose-600 hover:bg-rose-600/90' : undefined}
            onClick={() => void handleConfirm()}
            pending={working}
            disabled={!reasonOk}
          >
            {confirmLabel || (destructive ? 'Confirm' : 'Continue')}
          </Button>
        </div>
      </div>
    </div>
  )
}
