import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'

// Shared pagination footer for dashboard list views. Renders a calm
// "Showing X of Y · Load more" row only when there is more to fetch, so small
// companies (everything fits on the first page) see nothing at all. Reused
// across modules so pagination looks and behaves identically everywhere.
export function LoadMoreBar({
  loaded,
  total,
  loading,
  onLoadMore,
  noun = 'item',
  showingLabel,
  loadMoreLabel,
  loadingLabel,
}: {
  loaded: number
  total: number
  loading: boolean
  onLoadMore: () => void
  noun?: string
  /** Pre-interpolated label; falls back to English "Showing X of Y nouns". */
  showingLabel?: string
  loadMoreLabel?: string
  loadingLabel?: string
}) {
  const hasMore = loaded < total
  if (!hasMore && total <= loaded) return null
  const showing =
    showingLabel
    || `Showing ${loaded} of ${total} ${noun}${total === 1 ? '' : 's'}`
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line/45 px-4 py-3 text-[12.5px] text-subtle/85">
      <span className="tabular-nums">{showing}</span>
      {hasMore ? (
        <Button variant="secondary" size="sm" disabled={loading} onClick={onLoadMore}>
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> {loadingLabel || 'Loading…'}
            </>
          ) : (
            loadMoreLabel || 'Load more'
          )}
        </Button>
      ) : null}
    </div>
  )
}
