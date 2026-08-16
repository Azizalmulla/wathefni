/**
 * Wathefni Rendering Stability Wave 2 — shared contract helpers.
 *
 * Rules (UX only — no authority / layout redesign):
 * 1. Keep previous content visible while new data loads.
 * 2. Skeletons only on genuine first load (`!data`).
 * 3. Quiet, non-reflow pending indicators for refresh.
 * 4. Latest request wins (requestId / AbortSignal).
 * 5. Preserve filters, tabs, ranges, scroll, focus, selection, open drawers.
 * 6. No opacity flashes or full-section remount keys for refetch.
 */

export function isColdLoad(hasData: boolean, isPending: boolean): boolean {
  return isPending && !hasData
}

export function isSoftRefreshing(hasData: boolean, isFetching: boolean): boolean {
  return isFetching && hasData
}
