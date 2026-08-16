/**
 * Candidates stage-bucket contract — single source of truth for list Stage display
 * and Stage filter expansion.
 *
 * Axis separation (approved):
 * - candidates.view.* — job/governance (All, With a job, No job / Talent Pool, Hired,
 *   Archived, Restricted). Owned by unified view predicates.
 * - candidates.stage.* — application lifecycle only.
 *
 * Talent Pool / needs_role / import_review are NOT Stage New.
 * Legacy offered / offer_sent display and filter as Shortlisted until Offer is a
 * real lifecycle stage end-to-end.
 */

/** Toolbar value for label "New" (awaiting_cv kept for saved-view compat). */
export const STAGE_FILTER_NEW = 'awaiting_cv'
export const STAGE_FILTER_READY = 'ready_for_review'
export const STAGE_FILTER_SHORTLISTED = 'shortlisted'
export const STAGE_FILTER_INTERVIEW = 'interview'
export const STAGE_FILTER_HIRED = 'hired'
export const STAGE_FILTER_REJECTED = 'rejected'
export const STAGE_FILTER_WITHDRAWN = 'withdrawn'

/** Display bucket keys (Stage column). */
export const STAGE_BUCKET_NEW = 'new'
export const STAGE_BUCKET_READY = 'ready_for_review'
export const STAGE_BUCKET_SHORTLISTED = 'shortlisted'
export const STAGE_BUCKET_INTERVIEW = 'interview'
export const STAGE_BUCKET_HIRED = 'hired'
export const STAGE_BUCKET_REJECTED = 'rejected'
export const STAGE_BUCKET_WITHDRAWN = 'withdrawn'
export const STAGE_BUCKET_ARCHIVED = 'archived'
/** Quiet non-lifecycle value for Talent Pool / no-job held rows. */
export const STAGE_BUCKET_NONE = 'none'
/** Unmapped lifecycle status — never silently New. */
export const STAGE_BUCKET_UNKNOWN = 'unknown'

export const CANDIDATE_STAGE_FILTER_STATUSES: Record<string, readonly string[]> = {
  [STAGE_FILTER_NEW]: [
    'awaiting_cv',
    'cv_processing',
    'cv_received',
    'screening',
    'cv_request',
    'cv_upload',
  ],
  [STAGE_FILTER_READY]: ['ready_for_review', 'screening_complete', 'review_pending'],
  [STAGE_FILTER_SHORTLISTED]: ['shortlisted', 'offered', 'offer_sent'],
  [STAGE_FILTER_INTERVIEW]: ['interview', 'scheduled'],
  [STAGE_FILTER_HIRED]: ['hired'],
  [STAGE_FILTER_REJECTED]: ['rejected'],
  [STAGE_FILTER_WITHDRAWN]: ['withdrawn'],
}

/** Map a raw application.status (or alias) to a lifecycle display bucket, or null. */
export function lifecycleBucketForStatus(status: string | null | undefined): string | null {
  const raw = String(status || '').trim().toLowerCase()
  if (!raw) return null
  if (CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_NEW].includes(raw)) return STAGE_BUCKET_NEW
  if (CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_READY].includes(raw)) return STAGE_BUCKET_READY
  if (CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_SHORTLISTED].includes(raw)) return STAGE_BUCKET_SHORTLISTED
  if (CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_INTERVIEW].includes(raw)) return STAGE_BUCKET_INTERVIEW
  if (raw === STAGE_FILTER_HIRED) return STAGE_BUCKET_HIRED
  if (raw === STAGE_FILTER_REJECTED) return STAGE_BUCKET_REJECTED
  if (raw === STAGE_FILTER_WITHDRAWN) return STAGE_BUCKET_WITHDRAWN
  if (raw === 'archived') return STAGE_BUCKET_ARCHIVED
  return null
}

/** Expand a Stage toolbar value (or raw alias) to every matching application.status. */
export function expandStageFilterStatuses(filterValue: string): string[] {
  const key = String(filterValue || '').trim().toLowerCase()
  if (!key) return []
  const direct = CANDIDATE_STAGE_FILTER_STATUSES[key]
  if (direct) return [...direct]
  for (const statuses of Object.values(CANDIDATE_STAGE_FILTER_STATUSES)) {
    if (statuses.includes(key)) return [...statuses]
  }
  return [key]
}

export function isTalentPoolStageExempt(application: {
  is_held?: boolean | null
  record_state?: string | null
  status?: string | null
}): boolean {
  const status = String(application.status || '').trim().toLowerCase()
  return Boolean(
    application.record_state === 'talent_pool'
      || status === 'needs_role'
      || status === 'import_review',
  )
}
