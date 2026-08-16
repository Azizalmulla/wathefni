import { useEffect, useRef } from 'react'

import { useDocumentVisible } from '@/lib/query/freshness'

/**
 * Soft background reload for non-TanStack modules (useModuleData).
 * - Pauses while tab hidden
 * - Skips if a reload is already in flight (no overlapping requests)
 * - Does not blank painted content (caller must soft-keep)
 */
export function useVisibilitySoftPoll(reload: () => Promise<void> | void, intervalMs: number, enabled = true) {
  const visible = useDocumentVisible()
  const inFlight = useRef(false)
  const reloadRef = useRef(reload)
  reloadRef.current = reload

  useEffect(() => {
    if (!enabled || !visible || intervalMs <= 0) return
    const tick = async () => {
      if (inFlight.current) return
      if (document.visibilityState !== 'visible') return
      inFlight.current = true
      try {
        await reloadRef.current()
      } finally {
        inFlight.current = false
      }
    }
    const id = window.setInterval(() => {
      void tick()
    }, intervalMs)
    return () => window.clearInterval(id)
  }, [enabled, visible, intervalMs])
}
