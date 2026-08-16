/** Frontend mirror of assessments_queue_contract / cohort application_count rule. */

export type AssessmentCohortCountBlock = {
  people_count?: number
  application_count?: number
  display_count?: number
  people?: number
  applications?: number
  unit?: string
}

/** Operational cohort badges: application_count only — never attempt status_counts. */
export function applicationCountOnly(block?: AssessmentCohortCountBlock | null): number {
  if (!block) return 0
  return Number(block.application_count ?? block.applications ?? 0)
}

export function cohortCountsFromPayload(
  cohorts?: { cohorts?: Record<string, AssessmentCohortCountBlock> } | null,
): Record<string, AssessmentCohortCountBlock> {
  return (cohorts?.cohorts && typeof cohorts.cohorts === 'object' ? cohorts.cohorts : {}) as Record<
    string,
    AssessmentCohortCountBlock
  >
}
