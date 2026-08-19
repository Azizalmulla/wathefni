import { type ReactNode, useEffect, useId, useRef, useState } from 'react'

import { CandidateTableRow, CandidateViewPills } from '@/components/candidates/CandidatesTable'
import { HeldIntakeReviewCard } from '@/components/candidates/HeldIntakeReviewCard'
import {
  ClassificationFilterBar,
  DEFAULT_CLASSIFICATION_FILTERS,
  type ClassificationFiltersState,
  type TaxonomyDimension,
} from '@/components/candidates/ClassificationFilters'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import { useBodyScrollLock, useOverlayFocus } from '@/hooks/useOverlayA11y'
import type { AccessIssue } from '@/lib/access'
import {
  applyCandidateFilterUpdate,
  clearCandidateAdvancedFilters,
} from '@/lib/candidateFilterAuthority'
import {
  buildCandidateFilterChips,
  classificationActiveCount,
  type CandidateFilterChip,
} from '@/lib/candidateFilterChips'
import {
  aggregateCandidatesForList,
  CANDIDATE_LIST_PERSON_PAGE_SIZE,
  CANDIDATE_LIST_STAGE_FILTERS,
  candidateListFooterLabel,
} from '@/lib/candidatesListPresentation'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { cn } from '@/lib/utils'
import { EmptyState } from '@/pages/shared/primitives'
import { ResourceState } from '@/pages/shared/dataState'
import type { ApplicationSummary, CandidateFilters, DashboardAccess, PositionSummary } from '@/types'

export function candidateAdvancedFilterCount(filters: CandidateFilters) {
  return [
    filters.cvStatus,
    filters.assessmentStatus,
    filters.interviewStatus,
    filters.followUp,
    filters.reviewStatus,
    filters.activityFrom,
    filters.activityTo,
    filters.sourceChannel,
    filters.recruiterOwner,
    filters.cvProcessingState,
    filters.receivedFrom,
    filters.receivedTo,
    filters.hasGroundedEmail,
    filters.hasGroundedPhone,
    filters.factCompleteness,
    filters.departmentIntakeTag,
    filters.sort && filters.sort !== 'newest' ? filters.sort : '',
  ].filter(Boolean).length
}

function FilterChip({
  chip,
  onRemove,
}: {
  chip: CandidateFilterChip
  onRemove: () => void
}) {
  return (
    <button
      className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-[#c89445]/35 bg-[#f7f1e7]/90 px-3 py-1.5 text-xs font-semibold text-text shadow-[0_1px_0_rgba(255,255,255,0.75)_inset] transition hover:border-[#c89445]/55 hover:bg-white"
      data-testid={`candidate-filter-chip-${chip.id}`}
      onClick={onRemove}
      type="button"
    >
      <span className="truncate">{chip.label}</span>
      <span aria-hidden="true" className="text-mist">×</span>
      <span className="sr-only">Remove</span>
    </button>
  )
}

function SpecialistFiltersForm({
  assessmentEnabled,
  classificationDeprecatedNodes,
  classificationDimensions,
  classificationEnabled,
  classificationFilters,
  classificationTaxonomyError = false,
  classificationTaxonomyLoading = false,
  filters,
  locale,
  onClassificationFiltersChange,
  onRetryClassificationTaxonomy,
  updateFilter,
  unifiedEnabled,
}: {
  assessmentEnabled: boolean
  classificationDeprecatedNodes: Array<{ node_id: string; message?: string }>
  classificationDimensions: TaxonomyDimension[]
  classificationEnabled: boolean
  classificationFilters: ClassificationFiltersState
  classificationTaxonomyError?: boolean
  classificationTaxonomyLoading?: boolean
  filters: CandidateFilters
  locale: RecruitingLocale
  onClassificationFiltersChange?: (next: ClassificationFiltersState) => void
  onRetryClassificationTaxonomy?: () => void
  updateFilter: (key: keyof CandidateFilters, value: string) => void
  unifiedEnabled: boolean
}) {
  return (
    <div className="space-y-4" data-testid="candidates-specialist-filters">
      <ClassificationFilterBar
        deprecatedNodes={classificationDeprecatedNodes}
        dimensions={classificationDimensions}
        enabled={Boolean(unifiedEnabled && classificationEnabled)}
        locale={locale === 'ar' ? 'ar' : 'en'}
        onChange={(next) => onClassificationFiltersChange?.(next)}
        onRetryTaxonomy={onRetryClassificationTaxonomy}
        taxonomyError={classificationTaxonomyError}
        taxonomyLoading={classificationTaxonomyLoading}
        value={classificationFilters}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'المصدر' : 'Source'}</span>
          <Select onChange={(event) => updateFilter('sourceChannel', event.target.value)} value={filters.sourceChannel}>
            <option value="">{locale === 'ar' ? 'أي مصدر' : 'Any source'}</option>
            <option value="email">{locale === 'ar' ? 'البريد الإلكتروني' : 'Email'}</option>
            <option value="whatsapp">{locale === 'ar' ? 'واتساب' : 'WhatsApp'}</option>
            <option value="bulk">{locale === 'ar' ? 'رفع يدوي' : 'Manual upload'}</option>
            <option value="dashboard">{locale === 'ar' ? 'رفع يدوي' : 'Manual upload'}</option>
          </Select>
        </label>
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'حالة السيرة' : 'CV status'}</span>
          <Select onChange={(event) => updateFilter('cvStatus', event.target.value)} value={filters.cvStatus}>
            <option value="">{locale === 'ar' ? 'الطلبات مع سيرة ذاتية' : 'Applications with CVs'}</option>
            <option value="with_cv">{locale === 'ar' ? 'تم استلام السيرة' : 'CV received'}</option>
            <option value="incomplete">{locale === 'ar' ? 'بدأ بدون سيرة' : 'Started but no CV'}</option>
            <option value="all">{locale === 'ar' ? 'كل الطلبات' : 'All applications'}</option>
          </Select>
        </label>
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'الاستلام من' : 'Received from'}</span>
          <Input onChange={(event) => updateFilter('receivedFrom', event.target.value)} type="date" value={filters.receivedFrom} />
        </label>
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'الاستلام إلى' : 'Received to'}</span>
          <Input onChange={(event) => updateFilter('receivedTo', event.target.value)} type="date" value={filters.receivedTo} />
        </label>
        {assessmentEnabled ? (
          <label className="space-y-1 text-xs font-medium text-subtle">
            <span>{locale === 'ar' ? 'التقييم' : 'Assessment'}</span>
            <Select onChange={(event) => updateFilter('assessmentStatus', event.target.value)} value={filters.assessmentStatus}>
              <option value="">{locale === 'ar' ? 'أي تقييم' : 'Any assessment status'}</option>
              <option value="awaiting">{locale === 'ar' ? 'بانتظار التقييم' : 'Awaiting assessment'}</option>
              <option value="none">{locale === 'ar' ? 'لا تقييم بعد' : 'No assessment yet'}</option>
              <option value="pending">{locale === 'ar' ? 'قيد الانتظار' : 'Pending'}</option>
              <option value="started">{locale === 'ar' ? 'بدأ' : 'Started'}</option>
              <option value="completed">{locale === 'ar' ? 'مكتمل' : 'Completed'}</option>
              <option value="expired">{locale === 'ar' ? 'منتهي' : 'Expired'}</option>
            </Select>
          </label>
        ) : null}
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'المقابلة' : 'Interview'}</span>
          <Select onChange={(event) => updateFilter('interviewStatus', event.target.value)} value={filters.interviewStatus}>
            <option value="">{locale === 'ar' ? 'أي مقابلة' : 'Any interview status'}</option>
            <option value="none">{locale === 'ar' ? 'لا مقابلة بعد' : 'No interview yet'}</option>
            <option value="scheduled">{locale === 'ar' ? 'مجدولة' : 'Scheduled'}</option>
            <option value="completed">{locale === 'ar' ? 'مكتملة' : 'Completed'}</option>
            <option value="no_show">{locale === 'ar' ? 'لم يحضر' : 'No-show'}</option>
            <option value="cancelled">{locale === 'ar' ? 'ملغاة' : 'Cancelled'}</option>
          </Select>
        </label>
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'المتابعة' : 'Follow-up'}</span>
          <Select onChange={(event) => updateFilter('followUp', event.target.value)} value={filters.followUp}>
            <option value="">{locale === 'ar' ? 'أي متابعة' : 'Any follow-up status'}</option>
            <option value="needed">{locale === 'ar' ? 'يحتاج متابعة' : 'Follow-up needed'}</option>
          </Select>
        </label>
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'الترتيب' : 'Sort'}</span>
          <Select onChange={(event) => updateFilter('sort', event.target.value)} value={filters.sort}>
            <option value="newest">{locale === 'ar' ? 'الأحدث أولاً' : 'Newest first'}</option>
            <option value="last_activity">{locale === 'ar' ? 'آخر نشاط' : 'Last activity'}</option>
            <option value="ready_for_review">{locale === 'ar' ? 'جاهز للمراجعة أولاً' : 'Ready for review first'}</option>
            {assessmentEnabled ? <option value="assessment_complete">{locale === 'ar' ? 'التقييم المكتمل أولاً' : 'Assessment complete first'}</option> : null}
            <option value="ranking_score">{locale === 'ar' ? 'درجة الترتيب إن وجدت' : 'Ranking score if available'}</option>
          </Select>
        </label>
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'مسؤول التوظيف' : 'Recruiter'}</span>
          <Select onChange={(event) => updateFilter('recruiterOwner', event.target.value)} value={filters.recruiterOwner}>
            <option value="">{locale === 'ar' ? 'أي مسؤول توظيف' : 'Any recruiter'}</option>
            <option value="unassigned">{locale === 'ar' ? 'غير معيّن' : 'Unassigned'}</option>
          </Select>
        </label>
        <label className="space-y-1 text-xs font-medium text-subtle">
          <span>{locale === 'ar' ? 'معالجة السيرة' : 'CV processing'}</span>
          <Select onChange={(event) => updateFilter('cvProcessingState', event.target.value)} value={filters.cvProcessingState}>
            <option value="">{locale === 'ar' ? 'أي معالجة للسيرة' : 'Any CV processing'}</option>
            <option value="ready">{locale === 'ar' ? 'جاهز' : 'Ready'}</option>
            <option value="partial">{locale === 'ar' ? 'جزئي' : 'Partial'}</option>
            <option value="failed">{locale === 'ar' ? 'فشل' : 'Failed'}</option>
          </Select>
        </label>
      </div>
    </div>
  )
}

function CandidatesFilterOverlay({
  advancedCount,
  assessmentEnabled,
  classificationDeprecatedNodes,
  classificationDimensions,
  classificationEnabled,
  classificationFilters,
  classificationTaxonomyError = false,
  classificationTaxonomyLoading = false,
  filters,
  locale,
  onClearAll,
  onClose,
  onClassificationFiltersChange,
  onRetryClassificationTaxonomy,
  open,
  updateFilter,
  unifiedEnabled,
}: {
  advancedCount: number
  assessmentEnabled: boolean
  classificationDeprecatedNodes: Array<{ node_id: string; message?: string }>
  classificationDimensions: TaxonomyDimension[]
  classificationEnabled: boolean
  classificationFilters: ClassificationFiltersState
  classificationTaxonomyError?: boolean
  classificationTaxonomyLoading?: boolean
  filters: CandidateFilters
  locale: RecruitingLocale
  onClearAll: () => void
  onClose: () => void
  onClassificationFiltersChange?: (next: ClassificationFiltersState) => void
  onRetryClassificationTaxonomy?: () => void
  open: boolean
  updateFilter: (key: keyof CandidateFilters, value: string) => void
  unifiedEnabled: boolean
}) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  useBodyScrollLock(open)
  useOverlayFocus(open, onClose, panelRef)
  if (!open) return null

  const title = locale === 'ar' ? 'المرشحات' : 'Filters'
  const subtitle = locale === 'ar'
    ? (advancedCount ? `${advancedCount} مرشّح نشط` : 'لا مرشحات متخصصة نشطة')
    : (advancedCount ? `${advancedCount} active` : 'No specialist filters active')

  return (
    <div
      aria-labelledby={titleId}
      aria-modal="true"
      className="fixed inset-0 z-50 flex justify-end bg-ink/35 p-0 md:p-3"
      data-testid="candidates-filter-overlay"
      dir={locale === 'ar' ? 'rtl' : 'ltr'}
      onClick={onClose}
      role="dialog"
    >
      {/* Mobile: full-height sheet. Desktop: side drawer. */}
      <div
        className={cn(
          'flex h-full w-full flex-col bg-[#fbf7f0] shadow-[0_24px_80px_rgba(24,20,15,0.28)]',
          'md:ms-auto md:h-full md:max-w-md md:rounded-[1.75rem] md:border md:border-white/70',
        )}
        data-testid="candidates-filter-panel"
        data-variant="drawer-or-sheet"
        onClick={(event) => event.stopPropagation()}
        ref={panelRef}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line/50 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold tracking-[-0.03em] text-text" id={titleId}>
              {title}
            </h2>
            <p className="mt-0.5 text-sm text-subtle">{subtitle}</p>
          </div>
          <Button onClick={onClose} size="sm" type="button" variant="ghost">
            {locale === 'ar' ? 'إغلاق' : 'Close'}
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <SpecialistFiltersForm
            assessmentEnabled={assessmentEnabled}
            classificationDeprecatedNodes={classificationDeprecatedNodes}
            classificationDimensions={classificationDimensions}
            classificationEnabled={classificationEnabled}
            classificationFilters={classificationFilters}
            classificationTaxonomyError={classificationTaxonomyError}
            classificationTaxonomyLoading={classificationTaxonomyLoading}
            filters={filters}
            locale={locale}
            onClassificationFiltersChange={onClassificationFiltersChange}
            onRetryClassificationTaxonomy={onRetryClassificationTaxonomy}
            updateFilter={updateFilter}
            unifiedEnabled={unifiedEnabled}
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line/50 px-5 py-4">
          <Button
            data-testid="candidates-clear-all-filters"
            disabled={advancedCount === 0}
            onClick={onClearAll}
            size="sm"
            type="button"
            variant="secondary"
          >
            {locale === 'ar' ? 'مسح الكل' : 'Clear all'}
          </Button>
          <Button onClick={onClose} size="sm" type="button">
            {locale === 'ar' ? 'تم' : 'Done'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function CandidatesPage({
  access,
  applications,
  assessmentEnabled,
  attentionBanner,
  busy,
  filters,
  importButton,
  locale,
  listError = false,
  listLoading = false,
  onLocale,
  onRetryList,
  onSaveView,
  onSelect,
  onSelectSavedView,
  onAccessIssue,
  onHeldChanged,
  heldReloadKey = 0,
  positions,
  query,
  savedViews,
  setFilters,
  setQuery,
  setStatus,
  status,
  unifiedEnabled = true,
  classificationEnabled = false,
  classificationFilters = DEFAULT_CLASSIFICATION_FILTERS,
  classificationDimensions = [],
  classificationDeprecatedNodes = [],
  classificationTaxonomyError = false,
  classificationTaxonomyLoading = false,
  onClassificationFiltersChange,
  onRetryClassificationTaxonomy,
  showRestrictedView = false,
  hasMoreApplications = false,
  loadingMoreApplications = false,
  onLoadMoreApplications,
  serverApplicationTotal = 0,
}: {
  access?: DashboardAccess
  applications: ApplicationSummary[]
  assessmentEnabled: boolean
  attentionBanner?: ReactNode
  busy: boolean
  filters: CandidateFilters
  importButton?: ReactNode
  locale: RecruitingLocale
  listError?: boolean
  listLoading?: boolean
  onLocale: () => void
  onRetryList?: () => void
  onSaveView: (name: string) => Promise<void>
  onSelect: (application: ApplicationSummary) => void
  onSelectSavedView: (view: { view_id: string; name: string; filters: Record<string, unknown> }) => void
  onAccessIssue?: (issue: AccessIssue) => void
  onHeldChanged?: () => void
  heldReloadKey?: number
  positions: PositionSummary[]
  query: string
  savedViews: Array<{ view_id: string; name: string; filters: Record<string, unknown> }>
  setFilters: (value: CandidateFilters | ((current: CandidateFilters) => CandidateFilters)) => void
  setQuery: (value: string) => void
  setStatus: (value: string) => void
  status: string
  offset?: number
  total?: number
  onPage?: (offset: number) => void
  unifiedEnabled?: boolean
  classificationEnabled?: boolean
  classificationFilters?: ClassificationFiltersState
  classificationDimensions?: TaxonomyDimension[]
  classificationDeprecatedNodes?: Array<{ node_id: string; message?: string }>
  classificationTaxonomyError?: boolean
  classificationTaxonomyLoading?: boolean
  onClassificationFiltersChange?: (next: ClassificationFiltersState) => void
  onRetryClassificationTaxonomy?: () => void
  showRestrictedView?: boolean
  hasMoreApplications?: boolean
  loadingMoreApplications?: boolean
  onLoadMoreApplications?: () => void
  serverApplicationTotal?: number
}) {
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [showSavedViews, setShowSavedViews] = useState(false)
  const [saveViewName, setSaveViewName] = useState('')
  const [personOffset, setPersonOffset] = useState(0)
  const activeMoreFilterCount = candidateAdvancedFilterCount(filters)
  const classCount = classificationEnabled ? classificationActiveCount(classificationFilters) : 0
  const advancedCount = activeMoreFilterCount + classCount
  const chips = buildCandidateFilterChips({
    filters,
    locale,
    classificationEnabled,
    classificationFilters,
  })
  const people = aggregateCandidatesForList(applications)
  const pageSize = CANDIDATE_LIST_PERSON_PAGE_SIZE
  const safeOffset = people.length ? Math.min(personOffset, Math.max(0, people.length - (people.length % pageSize || pageSize))) : 0
  const pageStart = Math.min(safeOffset, Math.max(0, people.length - 1))
  const alignedOffset = Math.floor(pageStart / pageSize) * pageSize
  const pagePeople = people.slice(alignedOffset, alignedOffset + pageSize)
  const updateFilter = (key: keyof CandidateFilters, value: string) => {
    setPersonOffset(0)
    setFilters((current) => applyCandidateFilterUpdate(current, key, value))
  }
  const clearAllSpecialistFilters = () => {
    setPersonOffset(0)
    setFilters((current) => clearCandidateAdvancedFilters(current))
    onClassificationFiltersChange?.(DEFAULT_CLASSIFICATION_FILTERS)
  }
  const removeChip = (chip: CandidateFilterChip) => {
    setPersonOffset(0)
    if (chip.id === 'classification') {
      onClassificationFiltersChange?.(DEFAULT_CLASSIFICATION_FILTERS)
      return
    }
    if (chip.id === 'overviewCohort') {
      setFilters((current) => ({
        ...current,
        overviewCohort: '',
        action: '',
        cohortKey: '',
      }))
      return
    }
    if (chip.filterKey === 'sort') {
      updateFilter('sort', 'newest')
      return
    }
    if (chip.filterKey) updateFilter(chip.filterKey, '')
  }
  const searchPlaceholder = locale === 'ar' ? 'بحث عن مرشح' : 'Search candidates'
  const filtersLabel = locale === 'ar'
    ? (advancedCount ? `مرشحات (${advancedCount})` : 'مرشحات')
    : (advancedCount ? `Filters (${advancedCount})` : 'Filters')
  const viewDirty = Boolean(
    query.trim()
    || status
    || filters.position
    || (filters.view && filters.view !== 'all')
    || advancedCount,
  )
  const showSaveViewControls = viewDirty || savedViews.length > 0 || showSavedViews

  useEffect(() => {
    if (!showRestrictedView && filters.view === 'restricted') {
      setFilters((current) => ({ ...current, view: 'all' }))
      setPersonOffset(0)
    }
  }, [showRestrictedView, filters.view, setFilters])

  return (
    <div
      aria-busy={busy || undefined}
      className="space-y-6"
      data-testid="unified-candidates-page"
      dir={locale === 'ar' ? 'rtl' : 'ltr'}
    >
      {attentionBanner}
      {access && importButton ? (
        <HeldIntakeReviewCard
          access={access}
          applications={applications}
          locale={locale}
          onAccessIssue={onAccessIssue}
          onChanged={() => onHeldChanged?.()}
          onOpenCandidate={(appKey) => {
            const match = applications.find((row) => row.app_key === appKey)
            if (match) onSelect(match)
          }}
          positions={positions}
          reloadKey={heldReloadKey}
        />
      ) : null}
      <Card className="[&_tbody_tr]:min-h-[3.25rem]" tone="board">
        <CardHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle>{recruitingCopy(locale, 'candidateList')}</CardTitle>
                <CardDescription>
                  {locale === 'ar'
                    ? 'اطّلع على خبرة كل مرشح، والوظيفة المرتبطة به، ومرحلة التوظيف الحالية.'
                    : 'See each candidate’s expertise, job, and current hiring stage.'}
                </CardDescription>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button onClick={onLocale} size="sm" type="button" variant="secondary">
                  {recruitingCopy(locale, 'language')}
                </Button>
                {importButton}
              </div>
            </div>

            {unifiedEnabled ? (
              <CandidateViewPills
                locale={locale}
                onChange={(view) => updateFilter('view', view)}
                showRestricted={showRestrictedView}
                value={!showRestrictedView && filters.view === 'restricted' ? 'all' : (filters.view || 'all')}
              />
            ) : null}

            {/* Default bar: Search, Job, Stage, Filters (N) */}
            <div
              className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center"
              data-testid="candidates-default-filter-bar"
            >
              <Input
                className="w-full lg:max-w-xs"
                onChange={(event) => {
                  setPersonOffset(0)
                  setQuery(event.target.value)
                }}
                placeholder={searchPlaceholder}
                value={query}
              />
              <Select onChange={(event) => updateFilter('position', event.target.value)} value={filters.position}>
                <option value="">{locale === 'ar' ? 'كل الوظائف' : 'All jobs'}</option>
                {positions.map((position) => (
                  <option key={position.position_code} value={position.position_code}>
                    {position.position_title || position.position_code}
                  </option>
                ))}
              </Select>
              <Select
                onChange={(event) => {
                  setPersonOffset(0)
                  setStatus(event.target.value)
                }}
                value={status}
              >
                {CANDIDATE_LIST_STAGE_FILTERS.map((item) => (
                  <option key={item.value || 'all'} value={item.value}>
                    {locale === 'ar' ? item.ar : item.en}
                  </option>
                ))}
              </Select>
              <Button
                aria-expanded={filtersOpen}
                data-testid="candidates-open-filters"
                onClick={() => setFiltersOpen(true)}
                type="button"
                variant="secondary"
              >
                {filtersLabel}
              </Button>
              {showSaveViewControls ? (
                <Button
                  onClick={() => setShowSavedViews((value) => !value)}
                  size="sm"
                  type="button"
                  variant="secondary"
                >
                  {locale === 'ar'
                    ? (viewDirty ? 'حفظ هذا العرض' : 'العروض المحفوظة')
                    : (viewDirty ? 'Save this view' : 'Saved views')}
                </Button>
              ) : null}
            </div>

            {/* Active context chips — stay visible with drawer open or closed */}
            {chips.length ? (
              <div className="flex flex-wrap items-center gap-2" data-testid="candidates-active-filter-chips">
                {chips.map((chip) => (
                  <FilterChip chip={chip} key={chip.id} onRemove={() => removeChip(chip)} />
                ))}
                <Button
                  data-testid="candidates-clear-all-chips"
                  onClick={clearAllSpecialistFilters}
                  size="sm"
                  type="button"
                  variant="ghost"
                >
                  {locale === 'ar' ? 'مسح الكل' : 'Clear all'}
                </Button>
              </div>
            ) : null}

            {showSavedViews && showSaveViewControls ? (
              <div className="flex flex-wrap items-center gap-2" data-testid="candidates-save-view-panel">
                {viewDirty ? (
                  <>
                    <Input
                      className="w-48"
                      onChange={(event) => setSaveViewName(event.target.value)}
                      placeholder={locale === 'ar' ? 'اسم العرض…' : 'Name this view…'}
                      value={saveViewName}
                    />
                    <Button
                      disabled={!saveViewName.trim()}
                      onClick={() => {
                        void onSaveView(saveViewName.trim()).then(() => {
                          setSaveViewName('')
                          setShowSavedViews(false)
                        })
                      }}
                      size="sm"
                      type="button"
                      variant="secondary"
                    >
                      {locale === 'ar' ? 'حفظ' : 'Save'}
                    </Button>
                  </>
                ) : null}
                {savedViews.map((view) => (
                  <Button key={view.view_id} onClick={() => onSelectSavedView(view)} size="sm" type="button" variant="ghost">
                    {view.name}
                  </Button>
                ))}
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          {listLoading ? (
            <div className="space-y-3" data-testid="candidates-list-skeleton" aria-busy="true">
              <div className="h-12 animate-pulse rounded-2xl bg-white/55" />
              <div className="h-12 animate-pulse rounded-2xl bg-white/55" />
              <div className="h-12 animate-pulse rounded-2xl bg-white/55" />
              <div className="h-40 animate-pulse rounded-2xl bg-white/55" />
            </div>
          ) : listError ? (
            <ResourceState
              kind="error"
              locale={locale === 'ar' ? 'ar' : 'en'}
              title={locale === 'ar' ? 'تعذّر تحميل المرشحين' : 'Could not load candidates'}
              onRetry={onRetryList}
              retrying={busy}
              testId="candidates-list-error"
            />
          ) : pagePeople.length === 0 ? (
            <EmptyState
              text={
                locale === 'ar'
                  ? 'لا يوجد مرشحون مطابقون للمرشحات الحالية. جرّب مسح المرشحات أو مشاركة رابط التقديم لوظيفة.'
                  : 'No candidates match the current filters. Try clearing filters, or share a job’s application link to start receiving applicants.'
              }
            />
          ) : (
            <>
              <div className="overflow-x-auto rounded-[1.35rem] border border-line/55 bg-panel/75 shadow-[0_10px_30px_rgba(24,20,15,0.035)]">
                <table className="w-full min-w-[720px] text-start text-sm">
                  <thead className="bg-[#f7f1e7]/72 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                    <tr>
                      <th className="px-4 py-3">{locale === 'ar' ? 'المرشح' : 'Candidate'}</th>
                      <th className="px-4 py-3">{locale === 'ar' ? 'الخبرة' : 'Expertise'}</th>
                      <th className="px-4 py-3">{locale === 'ar' ? 'الوظيفة' : 'Job'}</th>
                      <th className="px-4 py-3">{locale === 'ar' ? 'المرحلة' : 'Stage'}</th>
                      <th className="px-4 py-3">{locale === 'ar' ? 'الاستلام' : 'Received'}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/45 bg-panel/42">
                    {pagePeople.map((person) => (
                      <CandidateTableRow
                        key={person.listKey}
                        locale={locale}
                        onSelect={onSelect}
                        person={person}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-subtle">
                <span data-testid="candidates-list-footer">
                  {candidateListFooterLabel(people.length, alignedOffset, pageSize, locale)}
                  {serverApplicationTotal > applications.length
                    ? (locale === 'ar'
                      ? ` · محمّل ${applications.length} من ${serverApplicationTotal} طلباً`
                      : ` · loaded ${applications.length} of ${serverApplicationTotal} applications`)
                    : null}
                </span>
                <div className="flex gap-2">
                  <Button
                    disabled={alignedOffset <= 0}
                    onClick={() => setPersonOffset(Math.max(0, alignedOffset - pageSize))}
                    size="sm"
                    variant="secondary"
                  >
                    {locale === 'ar' ? 'السابق' : 'Previous'}
                  </Button>
                  <Button
                    disabled={
                      alignedOffset + pageSize >= people.length && !hasMoreApplications
                      || loadingMoreApplications
                    }
                    onClick={() => {
                      if (alignedOffset + pageSize < people.length) {
                        setPersonOffset(alignedOffset + pageSize)
                        return
                      }
                      if (hasMoreApplications) onLoadMoreApplications?.()
                    }}
                    size="sm"
                    variant="secondary"
                  >
                    {loadingMoreApplications
                      ? (locale === 'ar' ? 'جاري التحميل…' : 'Loading…')
                      : alignedOffset + pageSize >= people.length && hasMoreApplications
                        ? (locale === 'ar' ? 'تحميل المزيد' : 'Load more')
                        : (locale === 'ar' ? 'التالي' : 'Next')}
                  </Button>
                </div>
              </div>
              {hasMoreApplications ? (
                <LoadMoreBar
                  loaded={applications.length}
                  loading={loadingMoreApplications}
                  noun="application"
                  onLoadMore={() => onLoadMoreApplications?.()}
                  total={Math.max(serverApplicationTotal, applications.length)}
                />
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      <CandidatesFilterOverlay
        advancedCount={advancedCount}
        assessmentEnabled={assessmentEnabled}
        classificationDeprecatedNodes={classificationDeprecatedNodes}
        classificationDimensions={classificationDimensions}
        classificationEnabled={classificationEnabled}
        classificationFilters={classificationFilters}
        classificationTaxonomyError={classificationTaxonomyError}
        classificationTaxonomyLoading={classificationTaxonomyLoading}
        filters={filters}
        locale={locale}
        onClassificationFiltersChange={onClassificationFiltersChange}
        onRetryClassificationTaxonomy={onRetryClassificationTaxonomy}
        onClearAll={clearAllSpecialistFilters}
        onClose={() => setFiltersOpen(false)}
        open={filtersOpen}
        updateFilter={updateFilter}
        unifiedEnabled={unifiedEnabled}
      />
    </div>
  )
}
