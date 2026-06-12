import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, AlertTriangle, Download, Loader2, RotateCcw, Search, ShieldAlert } from 'lucide-react'

import { DashboardApiError, downloadCompanyActivityCsv, getCompanyActivity } from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import type { ActivityActorOption, ActivityItem, ActivityResponse, DashboardAccess } from '@/types'

const PAGE_SIZE = 50

// Categories that get a calm "sensitive" highlight are driven by the backend
// `sensitive` flag on each row; this just maps category -> badge tone.
const CATEGORY_TONE: Record<string, 'default' | 'success' | 'warning' | 'danger' | 'muted'> = {
  Payroll: 'warning',
  Leave: 'default',
  Employees: 'default',
  'Team & Access': 'warning',
  Documents: 'default',
  Compliance: 'default',
  Candidates: 'default',
}

type Filters = {
  start_date: string
  end_date: string
  actor: string
  category: string
  q: string
}

const EMPTY_FILTERS: Filters = { start_date: '', end_date: '', actor: '', category: 'all', q: '' }

function formatWhen(at: string | null): string {
  if (!at) return '—'
  const date = new Date(at)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function actorOptionLabel(actor: ActivityActorOption): string {
  const name = actor.name?.trim()
  if (name) return actor.role_label ? `${name} · ${actor.role_label}` : name
  return actor.email || 'Team member'
}

export function ActivityLog({
  access,
  onAccessIssue,
}: {
  access: DashboardAccess
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [items, setItems] = useState<ActivityItem[]>([])
  const [meta, setMeta] = useState<{ total: number; hasMore: boolean; actors: ActivityActorOption[]; categories: string[] } | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)
  const [permissionDenied, setPermissionDenied] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [debouncedQuery, setDebouncedQuery] = useState('')

  // Debounce the free-text search so we don't fire a request per keystroke.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedQuery(filters.q.trim()), 350)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [filters.q])

  const apiFilters = useMemo(
    () => ({
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
      actor: filters.actor || undefined,
      category: filters.category,
      q: debouncedQuery || undefined,
    }),
    [filters.start_date, filters.end_date, filters.actor, filters.category, debouncedQuery],
  )

  const load = useCallback(
    async (nextOffset: number, append: boolean) => {
      if (append) setLoadingMore(true)
      else setLoading(true)
      setError('')
      try {
        const response: ActivityResponse = await getCompanyActivity(access, {
          ...apiFilters,
          limit: PAGE_SIZE,
          offset: nextOffset,
        })
        setItems((current) => (append ? [...current, ...response.items] : response.items))
        setMeta({
          total: response.total,
          hasMore: response.has_more,
          actors: response.actors || [],
          categories: response.categories || [],
        })
        setOffset(nextOffset)
        setPermissionDenied(false)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return
        }
        if (err instanceof DashboardApiError && err.status === 403) {
          setPermissionDenied(true)
          setItems([])
          setMeta(null)
          return
        }
        setError('We couldn’t load the activity log right now. Please try again.')
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [access, apiFilters, onAccessIssue],
  )

  useEffect(() => {
    void load(0, false)
  }, [load])

  const filtersActive = Boolean(
    filters.start_date || filters.end_date || filters.actor || (filters.category && filters.category !== 'all') || filters.q,
  )

  async function exportCsv() {
    setExporting(true)
    setError('')
    try {
      await downloadCompanyActivityCsv(access, apiFilters)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError('We couldn’t export the activity log. Please try again.')
    } finally {
      setExporting(false)
    }
  }

  if (permissionDenied) {
    return (
      <Card>
        <CardContent className="flex items-start gap-3 py-6 text-sm text-subtle">
          <ShieldAlert className="mt-0.5 shrink-0 text-subtle" size={18} />
          <div>
            <div className="font-medium text-text">Activity is visible to Owners and HR Managers</div>
            <p className="mt-1 leading-6">Ask a company Owner or HR Manager if you need to review who did what.</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity size={18} /> Company activity
              </CardTitle>
              <CardDescription>
                A read-only record of who did what across your workspace. Sensitive actions are highlighted.
              </CardDescription>
            </div>
            <Button onClick={() => void exportCsv()} type="button" variant="secondary" disabled={exporting || loading}>
              {exporting ? <Loader2 className="animate-spin" size={16} /> : <Download size={16} />} Export CSV
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Filters */}
          <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1fr_auto]">
            <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
              From
              <Input type="date" value={filters.start_date} onChange={(e) => setFilters((f) => ({ ...f, start_date: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
              To
              <Input type="date" value={filters.end_date} onChange={(e) => setFilters((f) => ({ ...f, end_date: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
              Person
              <Select value={filters.actor} onChange={(e) => setFilters((f) => ({ ...f, actor: e.target.value }))}>
                <option value="">Everyone</option>
                {(meta?.actors || []).map((actor) => (
                  <option key={actor.user_id || actor.email || actorOptionLabel(actor)} value={actor.user_id || actor.email || ''}>
                    {actorOptionLabel(actor)}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
              Category
              <Select value={filters.category} onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}>
                <option value="all">All categories</option>
                {(meta?.categories || []).map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
              Search
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subtle/70" size={15} />
                <Input
                  className="w-full pl-9"
                  placeholder="Find an activity…"
                  value={filters.q}
                  onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                />
              </div>
            </label>
          </div>
          {filtersActive ? (
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-subtle">
                {meta ? `${meta.total} matching ${meta.total === 1 ? 'activity' : 'activities'}` : ''}
              </span>
              <button
                type="button"
                onClick={() => setFilters(EMPTY_FILTERS)}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-subtle underline-offset-2 hover:text-text hover:underline"
              >
                <RotateCcw size={13} /> Clear filters
              </button>
            </div>
          ) : null}

          {error ? (
            <div className="flex items-start gap-2 rounded-2xl border border-rose-200/70 bg-rose-50/70 px-4 py-2.5 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 shrink-0" size={16} /> <span>{error}</span>
            </div>
          ) : null}

          {/* Feed */}
          {loading ? (
            <div className="flex items-center gap-2 py-8 text-sm text-subtle">
              <Loader2 className="animate-spin" size={16} /> Loading activity…
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-2xl border border-line/60 bg-white/45 px-4 py-10 text-center">
              <Activity className="mx-auto mb-2 text-subtle/70" size={20} />
              <div className="text-sm font-medium text-text">
                {filtersActive ? 'No activity matches these filters' : 'No activity recorded yet'}
              </div>
              <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-subtle">
                {filtersActive
                  ? 'Try widening the date range or clearing filters.'
                  : 'As your team approves leave, runs payroll, updates employees, and more, it will appear here.'}
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-line/55">
              <ul className="divide-y divide-line/45">
                {items.map((item) => (
                  <li key={item.id} className="flex items-start gap-3 bg-white/45 px-4 py-3 hover:bg-white/65">
                    <span
                      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.sensitive ? 'bg-[#c89445]' : 'bg-subtle/35'}`}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm text-text">{item.summary}</span>
                        {item.sensitive ? <Badge tone="warning">Sensitive</Badge> : null}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-subtle">
                        <Badge tone={CATEGORY_TONE[item.category] || 'muted'}>{item.category}</Badge>
                        <span>{formatWhen(item.at)}</span>
                        {item.actor.role_label ? <span>· {item.actor.role_label}</span> : null}
                        {item.status && item.status !== 'completed' ? <span>· {item.status}</span> : null}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {meta?.hasMore && !loading ? (
            <div className="flex justify-center pt-1">
              <Button onClick={() => void load(offset + PAGE_SIZE, true)} type="button" variant="secondary" disabled={loadingMore}>
                {loadingMore ? <Loader2 className="animate-spin" size={16} /> : null}
                Load more
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
