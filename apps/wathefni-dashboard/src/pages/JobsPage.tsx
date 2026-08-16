import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import QRCode from 'qrcode'
import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import { SearchInput } from '@/components/ui/search-input'
import { jobIsExternallyShareable, recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { EmptyState } from '@/pages/shared/primitives'
import { normalizedJobStatus } from '@/pages/shared/format'
import type { PositionsResponse, PositionSummary } from '@/types'

export function jobStatusTone(status: string) {
  if (status === 'open') return 'priority'
  if (status === 'draft') return 'review'
  if (status === 'paused') return 'paused'
  if (status === 'closed') return 'muted'
  return 'muted'
}

export function jobStatusLabel(status: string, locale: RecruitingLocale) {
  if (status === 'open') return recruitingCopy(locale, 'jobsOpen')
  if (status === 'draft') return recruitingCopy(locale, 'jobsDraft')
  if (status === 'paused') return recruitingCopy(locale, 'jobsPaused')
  if (status === 'closed') return recruitingCopy(locale, 'jobsClosed')
  return status
}

export function jobDisplayTitle(job: PositionSummary, locale: RecruitingLocale) {
  if (locale === 'ar') return job.title_ar || job.position_title || job.title || job.position_code
  return job.title_en || job.title || job.position_title || job.position_code
}

export function jobAgeDays(job: PositionSummary) {
  const raw = job.created_at || job.published_at
  if (!raw) return null
  const ms = Date.now() - new Date(raw).getTime()
  if (!Number.isFinite(ms) || ms < 0) return null
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)))
}

export function deadlineIsOverdue(job: PositionSummary) {
  if (!job.application_deadline) return false
  const end = new Date(job.application_deadline).getTime()
  if (!Number.isFinite(end)) return false
  return end < Date.now()
}

/** Capacity column: vacancies → overdue → short deadline → —. */
export function jobCapacityDisplay(job: PositionSummary, locale: RecruitingLocale): { text: string; overdue: boolean } {
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) =>
    recruitingCopy(locale, key, vars)
  if (job.vacancies != null) {
    return {
      text: t('jobsRemaining', { remaining: job.remaining_vacancies ?? 0, total: job.vacancies }),
      overdue: false,
    }
  }
  if (deadlineIsOverdue(job)) {
    return { text: t('jobsDeadlineOverdueLabel'), overdue: true }
  }
  if (job.application_deadline) {
    const raw = String(job.application_deadline)
    const date = new Date(raw)
    if (Number.isFinite(date.getTime())) {
      return {
        text: date.toLocaleDateString(locale === 'ar' ? 'ar' : 'en', { month: 'short', day: 'numeric' }),
        overdue: false,
      }
    }
  }
  return { text: '—', overdue: false }
}

function jobOwnerLabel(job: PositionSummary, locale: RecruitingLocale) {
  if (job.recruiter_name) return job.recruiter_name
  if (job.recruiter_user_id) return recruitingCopy(locale, 'jobsAssigned')
  return '—'
}

function ApplicantsControl({
  job,
  locale,
  title,
  compact,
  onViewCandidates,
}: {
  job: PositionSummary
  locale: RecruitingLocale
  title: string
  compact?: boolean
  onViewCandidates: (job: PositionSummary) => void
}) {
  const apps = Number(job.active_count || 0)
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) =>
    recruitingCopy(locale, key, vars)
  if (apps <= 0) {
    return <span className="text-[#716a5e]">{compact ? '—' : t('jobsNoAppsYet')}</span>
  }
  const label = apps === 1 ? t('jobsAppsOne') : t('jobsAppsMany', { count: apps })
  return (
    <button
      type="button"
      className="font-semibold text-[#23211d] underline-offset-4 hover:underline"
      aria-label={t('jobsViewCandidatesAria', { title })}
      onClick={(event) => {
        event.stopPropagation()
        onViewCandidates(job)
      }}
      onKeyDown={(event) => event.stopPropagation()}
    >
      {compact ? apps : label}
    </button>
  )
}

function rowKeyHandlers(openManage: () => void) {
  return (event: KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      openManage()
    }
  }
}

function JobMobileCard({
  job,
  locale,
  onSelect,
  onViewCandidates,
}: {
  job: PositionSummary
  locale: RecruitingLocale
  onSelect: (job: PositionSummary) => void
  onViewCandidates: (job: PositionSummary) => void
}) {
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) =>
    recruitingCopy(locale, key, vars)
  const isAr = locale === 'ar'
  const status = normalizedJobStatus(job)
  const title = jobDisplayTitle(job, locale)
  const meta = [job.department, job.location].filter(Boolean).join(' · ')
  const capacity = jobCapacityDisplay(job, locale)
  const owner = jobOwnerLabel(job, locale)
  const Chevron = isAr ? ChevronLeft : ChevronRight
  const openManage = () => onSelect(job)

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={t('jobsOpenRowAria', { title })}
      className="group flex min-h-11 cursor-pointer items-center gap-3 border-b border-[#ddd3c1]/70 px-3 py-3 text-start last:border-b-0 hover:bg-white/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/30"
      onClick={openManage}
      onKeyDown={rowKeyHandlers(openManage)}
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-[#23211d]">{title}</span>
          <Badge tone={jobStatusTone(status)}>{jobStatusLabel(status, locale)}</Badge>
        </div>
        {meta ? <div className="truncate text-xs text-[#716a5e]">{meta}</div> : null}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[#716a5e]">
          <ApplicantsControl job={job} locale={locale} title={title} onViewCandidates={onViewCandidates} />
          {capacity.text !== '—' ? (
            <span className={capacity.overdue ? 'font-medium text-[#9a3412]' : undefined}>{capacity.text}</span>
          ) : null}
          {owner !== '—' ? <span>{owner}</span> : null}
        </div>
      </div>
      <Chevron className="h-4 w-4 shrink-0 text-[#8a8274] opacity-70 group-hover:opacity-100" aria-hidden />
    </div>
  )
}

/** Shared desktop inventory grid — header, rows, and skeletons must match. */
export const JOBS_DESKTOP_GRID_CLASS =
  'grid w-full grid-cols-[minmax(260px,2.2fr)_120px_130px_180px_160px_32px] items-center'

const JOBS_DESKTOP_CELL = 'min-w-0 px-3 py-3 text-start'
const JOBS_DESKTOP_HEADER_CELL =
  'min-w-0 px-3 py-3 text-start text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8a8274]'

function JobDesktopTable({
  positions,
  locale,
  onSelect,
  onViewCandidates,
}: {
  positions: PositionSummary[]
  locale: RecruitingLocale
  onSelect: (job: PositionSummary) => void
  onViewCandidates: (job: PositionSummary) => void
}) {
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) =>
    recruitingCopy(locale, key, vars)
  const isAr = locale === 'ar'
  const Chevron = isAr ? ChevronLeft : ChevronRight

  return (
    <div
      className="hidden w-full text-sm md:block"
      data-testid="jobs-desktop-table"
      role="table"
      aria-label={t('jobsOpeningsList')}
    >
      <div className={`${JOBS_DESKTOP_GRID_CLASS} border-b border-[#ddd3c1]/80`} role="row">
        <div className={JOBS_DESKTOP_HEADER_CELL} role="columnheader">{t('jobsColJob')}</div>
        <div className={JOBS_DESKTOP_HEADER_CELL} role="columnheader">{t('jobsColStatus')}</div>
        <div className={JOBS_DESKTOP_HEADER_CELL} role="columnheader">{t('jobsColApps')}</div>
        <div className={JOBS_DESKTOP_HEADER_CELL} role="columnheader">{t('jobsColCapacity')}</div>
        <div className={JOBS_DESKTOP_HEADER_CELL} role="columnheader">{t('jobsColOwner')}</div>
        <div className="px-0 py-3 text-center" role="columnheader">
          <span className="sr-only">{t('jobsColOpen')}</span>
        </div>
      </div>
      {positions.map((job) => {
        const status = normalizedJobStatus(job)
        const title = jobDisplayTitle(job, locale)
        const meta = [job.department, job.location].filter(Boolean).join(' · ')
        const capacity = jobCapacityDisplay(job, locale)
        const owner = jobOwnerLabel(job, locale)
        const openManage = () => onSelect(job)
        return (
          <div
            key={job.position_code}
            role="button"
            tabIndex={0}
            aria-label={t('jobsOpenRowAria', { title })}
            className={`${JOBS_DESKTOP_GRID_CLASS} cursor-pointer border-b border-[#ddd3c1]/70 last:border-b-0 hover:bg-white/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ink/30`}
            onClick={openManage}
            onKeyDown={rowKeyHandlers(openManage)}
          >
            <div className={JOBS_DESKTOP_CELL} role="cell">
              <div className="truncate font-semibold text-[#23211d]">{title}</div>
              {meta ? <div className="truncate text-xs text-[#716a5e]">{meta}</div> : null}
            </div>
            <div className={JOBS_DESKTOP_CELL} role="cell" data-testid="jobs-status-cell">
              <Badge tone={jobStatusTone(status)}>{jobStatusLabel(status, locale)}</Badge>
            </div>
            <div className={`${JOBS_DESKTOP_CELL} tabular-nums`} role="cell">
              <ApplicantsControl
                job={job}
                locale={locale}
                title={title}
                compact
                onViewCandidates={onViewCandidates}
              />
            </div>
            <div
              className={`${JOBS_DESKTOP_CELL} truncate text-[#716a5e] ${capacity.overdue ? 'font-medium text-[#9a3412]' : ''}`}
              role="cell"
            >
              {capacity.text}
            </div>
            <div className={`${JOBS_DESKTOP_CELL} truncate text-[#716a5e]`} role="cell">
              {owner}
            </div>
            <div className="px-0 py-3 text-center text-[#8a8274]" role="cell" aria-hidden>
              <Chevron className="inline-block h-4 w-4 align-middle" />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function JobsDesktopSkeleton() {
  return (
    <div className="hidden md:block" data-testid="jobs-desktop-skeleton" aria-hidden>
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={`desk-sk-${index}`}
          className={`${JOBS_DESKTOP_GRID_CLASS} animate-pulse border-b border-[#ddd3c1]/50 last:border-b-0`}
        >
          <div className={JOBS_DESKTOP_CELL}>
            <div className="h-4 w-3/5 rounded bg-[#eee5d4]" />
            <div className="mt-2 h-3 w-2/5 rounded bg-[#f3ebe0]" />
          </div>
          <div className={JOBS_DESKTOP_CELL}>
            <div className="h-5 w-16 rounded-full bg-[#eee5d4]" />
          </div>
          <div className={JOBS_DESKTOP_CELL}>
            <div className="h-3 w-8 rounded bg-[#eee5d4]" />
          </div>
          <div className={JOBS_DESKTOP_CELL}>
            <div className="h-3 w-24 rounded bg-[#eee5d4]" />
          </div>
          <div className={JOBS_DESKTOP_CELL}>
            <div className="h-3 w-16 rounded bg-[#eee5d4]" />
          </div>
          <div className="px-0 py-3 text-center">
            <div className="mx-auto h-3 w-3 rounded bg-[#eee5d4]" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function JobsPage({
  canCreateJobs,
  deadlineFilter,
  departmentFilter,
  jobsData,
  loading = false,
  loadingMore,
  locale,
  locationFilter,
  onAssistantCreate,
  onCreate,
  onDeadlineFilterChange,
  onDepartmentFilterChange,
  onLoadMore,
  onLocaleChange,
  onLocationFilterChange,
  onQueryChange,
  onRemainingOnlyChange,
  onSelect,
  onStatusFilterChange,
  onViewCandidates,
  query,
  remainingOnly,
  statusFilter,
  selectedJob,
  onQrDataUrlChange,
}: {
  canCreateJobs: boolean
  deadlineFilter: string
  departmentFilter: string
  jobsData: PositionsResponse | null
  loading?: boolean
  loadingMore: boolean
  locale: RecruitingLocale
  locationFilter: string
  onAssistantCreate: () => void
  onCreate: () => void
  onDeadlineFilterChange: (value: string) => void
  onDepartmentFilterChange: (value: string) => void
  onLoadMore: () => void
  onLocaleChange: (locale: RecruitingLocale) => void
  onLocationFilterChange: (value: string) => void
  onQueryChange: (value: string) => void
  onRemainingOnlyChange: (value: boolean) => void
  onSelect: (job: PositionSummary) => void
  onStatusFilterChange: (value: string) => void
  onViewCandidates: (job: PositionSummary) => void
  query: string
  remainingOnly: boolean
  statusFilter: string
  selectedJob?: PositionSummary | null
  onQrDataUrlChange?: (value: string) => void
}) {
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) =>
    recruitingCopy(locale, key, vars)
  const positions = jobsData?.positions || []
  const totalCount = jobsData?.total_count ?? positions.length
  const summary = jobsData?.summary
  const openCount = summary?.open_positions
  const draftCount = summary?.draft_positions
  const pausedCount = summary?.paused_positions
  const closedCount = summary?.closed_positions
  const showStatusTiles =
    openCount != null || draftCount != null || pausedCount != null || closedCount != null
  // Reserve tile row while first load — avoids filter bar jumping down when counts arrive.
  const showStatusTilesShell = showStatusTiles || loading
  const isSearching = query.trim().length > 0
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false)

  const filtersActive = Boolean(
    statusFilter || departmentFilter || locationFilter || deadlineFilter || remainingOnly,
  )

  useEffect(() => {
    if (departmentFilter || locationFilter || deadlineFilter || remainingOnly) {
      setMoreFiltersOpen(true)
    }
  }, [deadlineFilter, departmentFilter, locationFilter, remainingOnly])

  const departments = useMemo(
    () => Array.from(new Set(positions.map((job) => String(job.department || '').trim()).filter(Boolean))).sort(),
    [positions],
  )
  const locations = useMemo(
    () => Array.from(new Set(positions.map((job) => String(job.location || '').trim()).filter(Boolean))).sort(),
    [positions],
  )

  useEffect(() => {
    if (!onQrDataUrlChange) return
    const setQr = onQrDataUrlChange
    let cancelled = false
    async function renderQr() {
      if (!jobIsExternallyShareable(selectedJob || {})) {
        setQr('')
        return
      }
      const value = selectedJob?.qr_value || selectedJob?.application_link || ''
      if (!value) {
        setQr('')
        return
      }
      const dataUrl = await QRCode.toDataURL(value, { margin: 2, width: 220 })
      if (!cancelled) setQr(dataUrl)
    }
    void renderQr().catch(() => setQr(''))
    return () => {
      cancelled = true
    }
  }, [onQrDataUrlChange, selectedJob])

  const clearFilters = () => {
    onStatusFilterChange('')
    onDepartmentFilterChange('')
    onLocationFilterChange('')
    onDeadlineFilterChange('')
    onRemainingOnlyChange(false)
    onQueryChange('')
  }

  const statusChips: Array<{ value: string; label: string }> = [
    { value: '', label: t('jobsFilterAll') },
    { value: 'open', label: t('jobsOpen') },
    { value: 'draft', label: t('jobsDraft') },
    { value: 'paused', label: t('jobsPaused') },
    { value: 'closed', label: t('jobsClosed') },
  ]

  let listBody: ReactNode
  if (loading && !jobsData) {
    listBody = (
      <div aria-busy="true" aria-label={t('jobsLoadingLabel')}>
        <div className="space-y-0 px-1 md:hidden">
          {Array.from({ length: 5 }).map((_, index) => (
            <div className="animate-pulse border-b border-[#ddd3c1]/50 px-3 py-3 last:border-b-0" key={`sk-${index}`}>
              <div className="h-4 w-2/5 rounded bg-[#eee5d4]" />
              <div className="mt-2 h-3 w-1/3 rounded bg-[#f3ebe0]" />
              <div className="mt-2 h-3 w-1/4 rounded bg-[#f3ebe0]" />
            </div>
          ))}
        </div>
        <JobsDesktopSkeleton />
      </div>
    )
  } else if (positions.length === 0) {
    const emptyText = isSearching
      ? t('jobsEmptySearch', { query: query.trim() })
      : filtersActive
        ? t('jobsEmptyFiltered')
        : t('jobsEmpty')
    listBody = (
      <div className="space-y-3 p-4">
        <EmptyState text={emptyText} />
        {filtersActive || isSearching ? (
          <Button onClick={clearFilters} type="button" variant="secondary">
            {t('jobsClearFilters')}
          </Button>
        ) : canCreateJobs ? (
          <Button onClick={onCreate} type="button">
            <Plus size={16} /> {t('jobsCreate')}
          </Button>
        ) : null}
      </div>
    )
  } else {
    listBody = (
      <>
        <div className="md:hidden" data-testid="jobs-mobile-list" role="list" aria-label={t('jobsOpeningsList')}>
          {positions.map((job) => (
            <div role="listitem" key={job.position_code}>
              <JobMobileCard
                job={job}
                locale={locale}
                onSelect={onSelect}
                onViewCandidates={onViewCandidates}
              />
            </div>
          ))}
        </div>
        <JobDesktopTable
          positions={positions}
          locale={locale}
          onSelect={onSelect}
          onViewCandidates={onViewCandidates}
        />
      </>
    )
  }

  const description = isSearching
    ? t('jobsResultCount', { count: totalCount, query: query.trim() })
    : t('jobsInventoryHint')

  return (
    <div className="space-y-5" dir={locale === 'ar' ? 'rtl' : 'ltr'} data-testid="jobs-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <Button
          disabled={!canCreateJobs}
          onClick={onCreate}
          title={!canCreateJobs ? t('jobsCreateDisabled') : undefined}
          type="button"
        >
          <Plus size={16} /> {t('jobsCreate')}
        </Button>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canCreateJobs} onClick={onAssistantCreate} type="button" variant="ghost">
            {t('jobsCreateAssistant')}
          </Button>
          <Button onClick={() => onLocaleChange(locale === 'ar' ? 'en' : 'ar')} type="button" variant="ghost">
            {t('language')}
          </Button>
        </div>
      </div>

      <section className="rounded-[var(--radius-wf-panel)] bg-wf-surface p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset] sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 px-1">
            <h2 className="text-[15px] font-semibold tracking-[-0.025em] text-[#23211d]">{t('jobsOpeningsList')}</h2>
            <p className="mt-0.5 text-xs text-[#716a5e]">{description}</p>
          </div>
          <div className="w-full sm:max-w-xs">
            <SearchInput onChange={onQueryChange} placeholder={t('jobsSearchPlaceholder')} value={query} />
          </div>
        </div>

        {showStatusTilesShell ? (
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="jobs-status-tiles">
            <button
              type="button"
              className="rounded-[1.1rem] bg-wf-accent-priority-soft px-3 py-3 text-start text-wf-accent-priority-ink transition hover:brightness-[0.98]"
              onClick={() => onStatusFilterChange('open')}
              disabled={!showStatusTiles}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">{t('jobsOpen')}</div>
              <div className={`mt-1 text-xl font-semibold tracking-tight ${!showStatusTiles ? 'animate-pulse text-transparent' : ''}`}>
                {showStatusTiles ? (openCount ?? '—') : '00'}
              </div>
            </button>
            <button
              type="button"
              className="rounded-[1.1rem] bg-wf-accent-review-soft px-3 py-3 text-start text-wf-accent-review-ink transition hover:brightness-[0.98]"
              onClick={() => onStatusFilterChange('draft')}
              disabled={!showStatusTiles}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">{t('jobsDraft')}</div>
              <div className={`mt-1 text-xl font-semibold tracking-tight ${!showStatusTiles ? 'animate-pulse text-transparent' : ''}`}>
                {showStatusTiles ? (draftCount ?? '—') : '00'}
              </div>
            </button>
            <button
              type="button"
              className="rounded-[1.1rem] bg-wf-accent-paused-soft px-3 py-3 text-start text-wf-accent-paused-ink transition hover:brightness-[0.98]"
              onClick={() => onStatusFilterChange('paused')}
              disabled={!showStatusTiles}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">{t('jobsPaused')}</div>
              <div className={`mt-1 text-xl font-semibold tracking-tight ${!showStatusTiles ? 'animate-pulse text-transparent' : ''}`}>
                {showStatusTiles ? (pausedCount ?? '—') : '00'}
              </div>
            </button>
            <button
              type="button"
              className="rounded-[1.1rem] bg-wf-accent-follow-soft px-3 py-3 text-start text-wf-accent-follow-ink transition hover:brightness-[0.98]"
              onClick={() => onStatusFilterChange('closed')}
              disabled={!showStatusTiles}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">{t('jobsClosed')}</div>
              <div className={`mt-1 text-xl font-semibold tracking-tight ${!showStatusTiles ? 'animate-pulse text-transparent' : ''}`}>
                {showStatusTiles ? (closedCount ?? '—') : '00'}
              </div>
            </button>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2 px-1" role="group" aria-label={t('jobsFilterStatus')}>
          {statusChips.map((chip) => {
            const active = statusFilter === chip.value
            return (
              <button
                key={chip.value || 'all'}
                type="button"
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                  active ? 'bg-[#23211d] text-white' : 'bg-[#f8f3e9] text-[#716a5e] hover:bg-[#eee5d4]'
                }`}
                aria-pressed={active}
                onClick={() => onStatusFilterChange(chip.value)}
              >
                {chip.label}
              </button>
            )
          })}
          <button
            type="button"
            className="rounded-full px-3 py-1.5 text-xs font-semibold text-[#716a5e] underline-offset-4 hover:underline"
            aria-expanded={moreFiltersOpen}
            onClick={() => setMoreFiltersOpen((open) => !open)}
          >
            {moreFiltersOpen ? t('jobsHideFilters') : t('jobsMoreFilters')}
          </button>
          {filtersActive || isSearching ? (
            <button
              type="button"
              className="rounded-full px-3 py-1.5 text-xs font-semibold text-[#716a5e] underline-offset-4 hover:underline"
              onClick={clearFilters}
            >
              {t('jobsClearFilters')}
            </button>
          ) : null}
        </div>

        {moreFiltersOpen ? (
          <div className="mt-3 flex flex-wrap gap-2 px-1">
            <select
              className="rounded-xl border border-[#e8dfd0] bg-white px-3 py-2 text-sm"
              onChange={(event) => onDepartmentFilterChange(event.target.value)}
              value={departmentFilter}
              aria-label={t('jobsFilterDepartment')}
            >
              <option value="">{t('jobsFilterDepartment')}</option>
              {departments.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <select
              className="rounded-xl border border-[#e8dfd0] bg-white px-3 py-2 text-sm"
              onChange={(event) => onLocationFilterChange(event.target.value)}
              value={locationFilter}
              aria-label={t('jobsFilterLocation')}
            >
              <option value="">{t('jobsFilterLocation')}</option>
              {locations.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <select
              className="rounded-xl border border-[#e8dfd0] bg-white px-3 py-2 text-sm"
              onChange={(event) => onDeadlineFilterChange(event.target.value)}
              value={deadlineFilter}
              aria-label={t('jobsFilterDeadline')}
            >
              <option value="">{t('jobsFilterDeadline')}: {t('jobsDeadlineAny')}</option>
              <option value="upcoming">{t('jobsDeadlineUpcoming')}</option>
              <option value="overdue">{t('jobsDeadlineOverdue')}</option>
              <option value="none">{t('jobsDeadlineNone')}</option>
            </select>
            <label className="inline-flex items-center gap-2 rounded-xl border border-[#e8dfd0] bg-white px-3 py-2 text-sm">
              <input checked={remainingOnly} onChange={(event) => onRemainingOnlyChange(event.target.checked)} type="checkbox" />
              {t('jobsFilterRemaining')}
            </label>
          </div>
        ) : null}

        <div className="mt-4 overflow-hidden rounded-[1.1rem] border border-[#e8dfd0] bg-[#f8f3e9]/80">
          {listBody}
          {!loading || jobsData ? (
            <LoadMoreBar
              loaded={positions.length}
              loading={loadingMore}
              onLoadMore={onLoadMore}
              total={totalCount}
              showingLabel={t('jobsShowing', { loaded: positions.length, total: totalCount })}
              loadMoreLabel={t('jobsLoadMore')}
              loadingLabel={t('jobsLoadingLabel')}
            />
          ) : null}
        </div>
      </section>
    </div>
  )
}
