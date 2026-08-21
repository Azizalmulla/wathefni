import { useEffect, useState } from 'react'

/** True when the document tab is visible (SSR-safe default true). */
export function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(() =>
    typeof document === 'undefined' ? true : document.visibilityState === 'visible',
  )
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState === 'visible')
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])
  return visible
}

/**
 * TanStack `refetchInterval` that pauses while the tab is hidden.
 * Returns `false` when hidden so in-flight soft-keep content stays and no
 * overlapping background polls accumulate.
 */
export function useVisibilityRefetchInterval(ms: number, enabled = true): number | false {
  const visible = useDocumentVisible()
  if (!enabled || !visible) return false
  return ms
}

/** Operational queue freshness intervals (Wave 1b — low-risk RQ only). */
export const FRESHNESS_MS = {
  workQueue: 60_000,
  calendarEvents: 60_000,
  calendarOverview: 90_000,
  notifications: 60_000,
  applications: 90_000,
  interviews: 60_000,
  jobs: 120_000,
  assessments: 90_000,
  actionInbox: 60_000,
  /** Inbound employee work for Leave / Onboarding / Compliance / ESS. */
  inboundQueue: 60_000,
  intelligenceOverview: 90_000,
} as const
