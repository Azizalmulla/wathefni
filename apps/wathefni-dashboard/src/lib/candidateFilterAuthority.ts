import type { CandidateFilters, CandidateSavedViewId } from '@/types'

/** Default Candidates filter blob (React + saved-view replace baseline). */
export const EMPTY_CANDIDATE_FILTERS: CandidateFilters = {
  position: '',
  cvStatus: '',
  assessmentStatus: '',
  interviewStatus: '',
  followUp: '',
  reviewStatus: '',
  activityFrom: '',
  activityTo: '',
  sort: 'newest',
  overviewCohort: '',
  action: '',
  cohortKey: '',
  sourceChannel: '',
  recruiterOwner: '',
  cvProcessingState: '',
  receivedFrom: '',
  receivedTo: '',
  hasGroundedEmail: '',
  hasGroundedPhone: '',
  factCompleteness: '',
  departmentIntakeTag: '',
  view: 'all',
}

const FOLLOW_UP_CONTEXT_KEYS = new Set(['overviewCohort', 'action', 'cohortKey'] as const)

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

/** Drop Follow-up needed deep-link context (and the follow_up predicate itself). */
export function clearFollowUpNeededContext(filters: CandidateFilters): CandidateFilters {
  return {
    ...filters,
    followUp: '',
    overviewCohort: '',
    action: '',
    cohortKey: '',
  }
}

/**
 * Apply a single Candidates filter change.
 * - Changing any non-context key clears overview cohort / action / cohort_key.
 * - Clearing Follow-up needed also clears follow_up + overview_cohort + cohort_key + action.
 */
export function applyCandidateFilterUpdate(
  current: CandidateFilters,
  key: keyof CandidateFilters,
  value: string,
): CandidateFilters {
  const next: CandidateFilters = { ...current, [key]: value }
  if (!FOLLOW_UP_CONTEXT_KEYS.has(key as 'overviewCohort' | 'action' | 'cohortKey')) {
    next.overviewCohort = ''
    next.action = ''
    next.cohortKey = ''
  }
  if (key === 'followUp' && !value) {
    return clearFollowUpNeededContext(next)
  }
  return next
}

/** Advanced-panel reset — preserves position/view; clears follow-up context. */
export function clearCandidateAdvancedFilters(current: CandidateFilters): CandidateFilters {
  return {
    ...current,
    cvStatus: '',
    assessmentStatus: '',
    interviewStatus: '',
    followUp: '',
    reviewStatus: '',
    activityFrom: '',
    activityTo: '',
    sort: 'newest',
    overviewCohort: '',
    action: '',
    cohortKey: '',
    sourceChannel: '',
    recruiterOwner: '',
    cvProcessingState: '',
    receivedFrom: '',
    receivedTo: '',
    hasGroundedEmail: '',
    hasGroundedPhone: '',
    factCompleteness: '',
    departmentIntakeTag: '',
  }
}

/** Replace (not merge) from a saved-view blob so leftover filters cannot stick. */
export function candidateFiltersFromSavedViewBlob(blob: Record<string, unknown> | null | undefined): {
  query: string
  status: string
  filters: CandidateFilters
} {
  const raw = blob || {}
  const viewRaw = asString(raw.view, 'all')
  const view = (viewRaw || 'all') as CandidateSavedViewId
  return {
    query: asString(raw.query),
    status: asString(raw.status),
    filters: {
      ...EMPTY_CANDIDATE_FILTERS,
      position: asString(raw.position),
      cvStatus: asString(raw.cvStatus),
      assessmentStatus: asString(raw.assessmentStatus),
      interviewStatus: asString(raw.interviewStatus),
      followUp: asString(raw.followUp),
      reviewStatus: asString(raw.reviewStatus),
      activityFrom: asString(raw.activityFrom),
      activityTo: asString(raw.activityTo),
      sort: asString(raw.sort, 'newest') || 'newest',
      overviewCohort: asString(raw.overviewCohort),
      action: asString(raw.action),
      cohortKey: asString(raw.cohortKey),
      sourceChannel: asString(raw.sourceChannel),
      recruiterOwner: asString(raw.recruiterOwner),
      cvProcessingState: asString(raw.cvProcessingState),
      receivedFrom: asString(raw.receivedFrom),
      receivedTo: asString(raw.receivedTo),
      hasGroundedEmail: asString(raw.hasGroundedEmail),
      hasGroundedPhone: asString(raw.hasGroundedPhone),
      factCompleteness: asString(raw.factCompleteness),
      departmentIntakeTag: asString(raw.departmentIntakeTag),
      view,
    },
  }
}
