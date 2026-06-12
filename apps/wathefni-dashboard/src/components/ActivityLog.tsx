import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Briefcase,
  CalendarClock,
  ClipboardCheck,
  Clock,
  Download,
  FileText,
  type LucideIcon,
  Loader2,
  MessageSquare,
  Plane,
  RotateCcw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Users,
  Wallet,
} from 'lucide-react'

import { DashboardApiError, downloadCompanyActivityCsv, getCompanyActivity } from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import type { ActivityActorOption, ActivityItem, ActivityResponse, DashboardAccess } from '@/types'

const PAGE_SIZE = 50

// Each category gets a quiet icon + colour so the feed reads like a timeline
// instead of one flat list. The icon is the primary visual cue per row.
const CATEGORY_META: Record<string, { Icon: LucideIcon; chip: string }> = {
  Employees: { Icon: Users, chip: 'bg-slate-100 text-slate-700' },
  Documents: { Icon: FileText, chip: 'bg-slate-100 text-slate-700' },
  Compliance: { Icon: FileText, chip: 'bg-slate-100 text-slate-700' },
  Leave: { Icon: Plane, chip: 'bg-sky-100 text-sky-700' },
  Payroll: { Icon: Wallet, chip: 'bg-[#f7e7c6] text-[#8a5a16]' },
  Attendance: { Icon: Clock, chip: 'bg-slate-100 text-slate-700' },
  Shifts: { Icon: CalendarClock, chip: 'bg-violet-100 text-violet-700' },
  Candidates: { Icon: Briefcase, chip: 'bg-indigo-100 text-indigo-700' },
  Onboarding: { Icon: ClipboardCheck, chip: 'bg-emerald-100 text-emerald-700' },
  'Team & Access': { Icon: ShieldCheck, chip: 'bg-[#f7e7c6] text-[#8a5a16]' },
  Other: { Icon: MessageSquare, chip: 'bg-slate-100 text-slate-600' },
}

function categoryMeta(category: string) {
  return CATEGORY_META[category] || { Icon: Activity, chip: 'bg-slate-100 text-slate-600' }
}

// Raw backend run states -> HR-friendly outcome labels. `completed` (and empty)
// are intentionally not shown — the activity already happened.
const STATUS_LABELS: Record<string, { label: string; tone: 'success' | 'warning' | 'danger' | 'muted' }> = {
  failed: { label: 'Failed', tone: 'danger' },
  needs_confirmation: { label: 'Needs confirmation', tone: 'warning' },
  needs_clarification: { label: 'Needs clarification', tone: 'warning' },
  needs_backend_tool: { label: 'In progress', tone: 'muted' },
  partial: { label: 'Partly done', tone: 'muted' },
  candidate_ambiguous: { label: 'Candidate unclear', tone: 'warning' },
  candidate_not_found: { label: 'Candidate not found', tone: 'warning' },
  needs_candidate_reference: { label: 'Needs a candidate', tone: 'warning' },
}

function statusMeta(status: string | null | undefined) {
  if (!status || status === 'completed') return null
  const known = STATUS_LABELS[status]
  if (known) return known
  const label = status.replace(/[_\s]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  return { label, tone: 'muted' as const }
}

type Filters = {
  start_date: string
  end_date: string
  actor: string
  category: string
  q: string
}

const EMPTY_FILTERS: Filters = { start_date: '', end_date: '', actor: '', category: 'all', q: '' }

function startOfDay(date: Date): Date {
  const out = new Date(date)
  out.setHours(0, 0, 0, 0)
  return out
}

// Group key + heading for a timestamp: Today / Yesterday / a weekday (this week)
// / an exact date for older entries.
function dateGroup(at: string | null): { key: string; label: string } {
  if (!at) return { key: 'unknown', label: 'Earlier' }
  const date = new Date(at)
  if (Number.isNaN(date.getTime())) return { key: 'unknown', label: 'Earlier' }
  const today = startOfDay(new Date())
  const that = startOfDay(date)
  const diffDays = Math.round((today.getTime() - that.getTime()) / 86_400_000)
  const dayKey = that.toISOString().slice(0, 10)
  if (diffDays <= 0) return { key: 'today', label: 'Today' }
  if (diffDays === 1) return { key: 'yesterday', label: 'Yesterday' }
  if (diffDays < 7) return { key: dayKey, label: date.toLocaleDateString(undefined, { weekday: 'long' }) }
  return {
    key: dayKey,
    label: date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }),
  }
}

function formatTime(at: string | null): string {
  if (!at) return '—'
  const date = new Date(at)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
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

  // Items arrive newest-first, so grouping in order yields date sections in the
  // right order and "Load more" simply extends the trailing (older) groups.
  const groups = useMemo(() => {
    const out: { key: string; label: string; items: ActivityItem[] }[] = []
    const index = new Map<string, number>()
    for (const item of items) {
      const { key, label } = dateGroup(item.at)
      let i = index.get(key)
      if (i === undefined) {
        i = out.length
        index.set(key, i)
        out.push({ key, label, items: [] })
      }
      out[i].items.push(item)
    }
    return out
  }, [items])

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
                A read-only timeline of who did what across your workspace. Sensitive actions are highlighted.
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

          {/* Timeline */}
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
            <div className="space-y-5">
              {groups.map((group) => (
                <section key={group.key}>
                  <div className="mb-2 flex items-center gap-3">
                    <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{group.label}</h3>
                    <span className="h-px flex-1 bg-line/55" />
                    <span className="text-[11px] text-subtle/70">{group.items.length}</span>
                  </div>
                  <ul className="overflow-hidden rounded-2xl border border-line/55 divide-y divide-line/40">
                    {group.items.map((item) => {
                      const { Icon, chip } = categoryMeta(item.category)
                      const status = statusMeta(item.status)
                      return (
                        <li
                          key={item.id}
                          className={cn(
                            'flex items-start gap-3 px-4 py-3 transition-colors',
                            item.sensitive
                              ? 'border-l-2 border-l-[#c89445] bg-[#fffaf0] hover:bg-[#fff6e6]'
                              : 'bg-white/45 hover:bg-white/70',
                          )}
                        >
                          <span className={cn('mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full', chip)} aria-hidden>
                            <Icon size={16} />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                              <span className="text-sm font-medium text-text">{item.summary}</span>
                              {item.sensitive ? <Badge tone="warning">Sensitive</Badge> : null}
                              {status ? <Badge tone={status.tone}>{status.label}</Badge> : null}
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[12px] text-subtle">
                              <span className="font-medium text-subtle/90">{item.category}</span>
                              <span aria-hidden>·</span>
                              <span>{formatTime(item.at)}</span>
                              {item.actor.role_label ? (
                                <>
                                  <span aria-hidden>·</span>
                                  <span>{item.actor.role_label}</span>
                                </>
                              ) : null}
                            </div>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              ))}
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
