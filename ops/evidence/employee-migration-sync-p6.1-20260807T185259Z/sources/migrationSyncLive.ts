/**
 * P6.1 — Live UI refresh for Migration & Sync.
 *
 * Event-driven invalidation across Migration Sync sections + Employees list /
 * open profiles. No new realtime platform: same-tab CustomEvent + optional
 * visibility-gated soft poll while Migration Sync is open (scheduler runs).
 */

import { useEffect, useRef } from 'react'

export const MIGRATION_SYNC_LIVE_EVENT = 'wathefni:migration-sync-live'
export const MIGRATION_SYNC_LIVE_CHANNEL = 'wathefni-migration-sync-live'

/** Soft poll while Connected / Needs Review / History is open (scheduler + other-tab sync). */
export const MIGRATION_SYNC_SOFT_POLL_MS = 30_000

export type MigrationSyncLiveReason =
  | 'sync_completed'
  | 'connection_changed'
  | 'review_resolved'
  | 'lifecycle_resolved'
  | 'import_applied'
  | 'soft_poll'
  | 'visibility'

export type MigrationSyncLiveDetail = {
  reason: MigrationSyncLiveReason
  connection_id?: string | null
  batch_id?: string | null
  employee_keys?: string[]
  at?: string
}

export function emitMigrationSyncLive(detail: MigrationSyncLiveDetail): void {
  if (typeof window === 'undefined') return
  const payload: MigrationSyncLiveDetail = {
    ...detail,
    at: detail.at || new Date().toISOString(),
  }
  window.dispatchEvent(
    new CustomEvent(MIGRATION_SYNC_LIVE_EVENT, {
      detail: payload,
    }),
  )
  // Cross-tab: Migration Sync in one tab can refresh an open employee profile in another.
  try {
    const bc = new BroadcastChannel(MIGRATION_SYNC_LIVE_CHANNEL)
    bc.postMessage(payload)
    bc.close()
  } catch {
    /* BroadcastChannel unavailable — same-tab CustomEvent still works */
  }
}

type SoftRefreshOptions = {
  /** Skip when local editor / dirty form would be clobbered. */
  isDirty?: () => boolean
  /** Debounce overlapping listeners (ms). */
  debounceMs?: number
  /** Soft poll while this surface is mounted (ms). 0 = off. */
  pollMs?: number
  enabled?: boolean
}

/**
 * Subscribe to migration live events (+ optional visibility-gated soft poll).
 * Caller supplies a soft refresh that must not blank the UI or reset filters.
 */
export function useMigrationSyncLiveRefresh(
  onSoftRefresh: (detail: MigrationSyncLiveDetail) => void | Promise<void>,
  options: SoftRefreshOptions = {},
): void {
  const { isDirty, debounceMs = 400, pollMs = 0, enabled = true } = options

  // Stable refs so effect deps stay small and avoid re-subscribe storms.
  const onSoftRefreshRef = useRef(onSoftRefresh)
  const isDirtyRef = useRef(isDirty)
  onSoftRefreshRef.current = onSoftRefresh
  isDirtyRef.current = isDirty

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return

    let timer: ReturnType<typeof setTimeout> | null = null
    let inFlight = false
    let disposed = false

    const run = (detail: MigrationSyncLiveDetail) => {
      if (disposed) return
      if (isDirtyRef.current?.()) return
      if (inFlight) {
        // Coalesce: schedule one follow-up after current finishes.
        if (timer) clearTimeout(timer)
        timer = setTimeout(() => run(detail), debounceMs)
        return
      }
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        void (async () => {
          if (disposed || isDirtyRef.current?.()) return
          inFlight = true
          try {
            await onSoftRefreshRef.current(detail)
          } finally {
            inFlight = false
          }
        })()
      }, debounceMs)
    }

    const onEvent = (ev: Event) => {
      const detail = (ev as CustomEvent<MigrationSyncLiveDetail>).detail
      run(
        detail || {
          reason: 'sync_completed',
        },
      )
    }

    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return
      run({ reason: 'visibility' })
    }

    window.addEventListener(MIGRATION_SYNC_LIVE_EVENT, onEvent)
    document.addEventListener('visibilitychange', onVisibility)

    let bc: BroadcastChannel | null = null
    try {
      bc = new BroadcastChannel(MIGRATION_SYNC_LIVE_CHANNEL)
      bc.onmessage = (msg) => {
        const detail = (msg.data || {}) as MigrationSyncLiveDetail
        run(detail.reason ? detail : { reason: 'sync_completed' })
      }
    } catch {
      bc = null
    }

    let pollTimer: ReturnType<typeof setInterval> | null = null
    if (pollMs > 0) {
      pollTimer = setInterval(() => {
        if (document.visibilityState !== 'visible') return
        run({ reason: 'soft_poll' })
      }, pollMs)
    }

    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      if (pollTimer) clearInterval(pollTimer)
      window.removeEventListener(MIGRATION_SYNC_LIVE_EVENT, onEvent)
      document.removeEventListener('visibilitychange', onVisibility)
      try {
        bc?.close()
      } catch {
        /* ignore */
      }
    }
  }, [enabled, debounceMs, pollMs])
}
