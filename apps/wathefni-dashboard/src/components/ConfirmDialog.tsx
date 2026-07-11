import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import { createContext, type ReactNode, useCallback, useContext, useState } from 'react'

import { Button } from '@/components/ui/button'
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
}

type PendingConfirm = {
  options: ConfirmOptions
  resolve: (confirmed: boolean) => void
}

const ConfirmContext = createContext<((options: ConfirmOptions) => Promise<boolean>) | null>(null)

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null)

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => setPending({ options, resolve }))
  }, [])

  const settle = useCallback(
    (confirmed: boolean) => {
      setPending((current) => {
        current?.resolve(confirmed)
        return null
      })
    },
    [],
  )

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending ? (
        <ConfirmDialog
          options={pending.options}
          onConfirm={() => settle(true)}
          onCancel={() => settle(false)}
        />
      ) : null}
    </ConfirmContext.Provider>
  )
}

// Returns confirm(options) -> Promise<boolean>. Resolves true when the user
// confirms, false when they cancel or dismiss. Wrap a handler like:
//   if (!(await confirm({ body: '…', destructive: true }))) return
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
  onConfirm: () => void
  onCancel: () => void
}) {
  const { title, body, confirmLabel, cancelLabel, destructive } = options
  const [working, setWorking] = useState(false)

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/35 px-4 backdrop-blur-sm"
      onClick={() => (working ? null : onCancel())}
    >
      <div
        className="w-full max-w-md rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60"
        onClick={(event) => event.stopPropagation()}
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
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">{title || 'Please confirm'}</p>
            <p className="text-[13px] leading-6 text-subtle/95">{body}</p>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={working}>
            {cancelLabel || 'Cancel'}
          </Button>
          <Button
            size="sm"
            className={destructive ? 'bg-rose-600 hover:bg-rose-600/90' : undefined}
            onClick={() => {
              setWorking(true)
              onConfirm()
            }}
            disabled={working}
          >
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {confirmLabel || (destructive ? 'Confirm' : 'Continue')}
          </Button>
        </div>
      </div>
    </div>
  )
}
