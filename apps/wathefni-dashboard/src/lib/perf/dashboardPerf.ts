/**
 * Lightweight dashboard responsiveness instrumentation (Wave 3).
 * Never log personal / candidate / token data — page ids, counts, durations only.
 */

export type DashboardPerfKind =
  | 'interaction_start'
  | 'cached_paint'
  | 'network_complete'
  | 'overview_interactive'
  | 'page_first_load'
  | 'page_cached_return'
  | 'request'
  | 'profiler_commit'

export type DashboardPerfEvent = {
  t: number
  kind: DashboardPerfKind
  name: string
  durMs?: number
  meta?: Record<string, string | number | boolean>
}

const MAX_EVENTS = 200
const events: DashboardPerfEvent[] = []
const counters = {
  requests: 0,
  byName: new Map<string, number>(),
}

let overviewInteractiveAt: number | null = null
const pageFirstLoadAt = new Map<string, number>()
const interactionStarts = new Map<string, number>()

function now() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function push(event: DashboardPerfEvent) {
  events.push(event)
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS)
  if (typeof window !== 'undefined' && (window as any).__WATHEFNI_DASHBOARD_PERF_DEBUG__) {
    // eslint-disable-next-line no-console
    console.debug('[wathefni-perf]', event.kind, event.name, event.durMs ?? '', event.meta || {})
  }
}

export function dashboardPerfReset() {
  events.length = 0
  counters.requests = 0
  counters.byName.clear()
  overviewInteractiveAt = null
  pageFirstLoadAt.clear()
  interactionStarts.clear()
}

export function dashboardPerfMarkInteractionStart(name: string, meta?: DashboardPerfEvent['meta']) {
  const t = now()
  interactionStarts.set(name, t)
  push({ t, kind: 'interaction_start', name, meta })
}

export function dashboardPerfMarkCachedPaint(name: string, meta?: DashboardPerfEvent['meta']) {
  const t = now()
  const start = interactionStarts.get(name)
  push({ t, kind: 'cached_paint', name, durMs: start != null ? Math.round(t - start) : undefined, meta })
}

export function dashboardPerfMarkNetworkComplete(name: string, meta?: DashboardPerfEvent['meta']) {
  const t = now()
  const start = interactionStarts.get(name)
  push({ t, kind: 'network_complete', name, durMs: start != null ? Math.round(t - start) : undefined, meta })
}

export function dashboardPerfMarkOverviewInteractive(meta?: DashboardPerfEvent['meta']) {
  if (overviewInteractiveAt != null) return
  const t = now()
  overviewInteractiveAt = t
  push({ t, kind: 'overview_interactive', name: 'overview', durMs: Math.round(t), meta })
}

export function dashboardPerfMarkPageVisit(page: string, hadCache: boolean) {
  const t = now()
  const first = pageFirstLoadAt.get(page)
  if (first == null) {
    pageFirstLoadAt.set(page, t)
    push({
      t,
      kind: 'page_first_load',
      name: page,
      meta: { hadCache },
    })
    return
  }
  push({
    t,
    kind: 'page_cached_return',
    name: page,
    durMs: Math.round(t - first),
    meta: { hadCache, returnVisit: true },
  })
}

export function dashboardPerfCountRequest(name: string) {
  counters.requests += 1
  counters.byName.set(name, (counters.byName.get(name) || 0) + 1)
  push({ t: now(), kind: 'request', name, meta: { total: counters.requests } })
}

/** React.Profiler onRender — durations only, no PII. */
export function dashboardPerfMarkProfilerCommit(
  name: string,
  meta: { phase: string; actualDurationMs: number; baseDurationMs?: number },
) {
  push({
    t: now(),
    kind: 'profiler_commit',
    name,
    durMs: meta.actualDurationMs,
    meta: {
      phase: meta.phase,
      actualDurationMs: meta.actualDurationMs,
      ...(meta.baseDurationMs != null ? { baseDurationMs: meta.baseDurationMs } : {}),
    },
  })
}

export function dashboardPerfSnapshot() {
  return {
    overviewInteractiveAtMs: overviewInteractiveAt,
    requestCount: counters.requests,
    requestsByName: Object.fromEntries(counters.byName.entries()),
    events: events.slice(),
  }
}

/** Expose read-only snapshot for operators / tests (no PII). */
export function installDashboardPerfGlobals() {
  if (typeof window === 'undefined') return
  ;(window as any).__WATHEFNI_DASHBOARD_PERF__ = {
    snapshot: dashboardPerfSnapshot,
    reset: dashboardPerfReset,
  }
}
