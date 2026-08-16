import type { EmployeeSummary, PersonIdentity } from '@hr/api/types'
import type { StatusTone } from '@/components/ui'

/**
 * People directory composition — “Who am I looking for?”
 * Exceptional chips only. Normal active → no chip. No attendance states.
 */

export type PeopleStatusFilter = 'active' | 'left' | 'all'
export type PeopleFilterPanel = null | 'department' | 'status' | 'more'

const ONBOARDING_DONE = new Set(['complete', 'completed', 'done'])
const ONBOARDING_DEAD = new Set(['cancelled_onboarding', 'abandoned_employment_ended'])
const PENDING_START = new Set(['pending_start', 'joining', 'future_start'])

export function isEmploymentLeft(status: string | null | undefined): boolean {
  return String(status || '').trim().toLowerCase() === 'left'
}

export function isEmploymentPendingStart(status: string | null | undefined): boolean {
  return PENDING_START.has(String(status || '').trim().toLowerCase())
}

/** Truly active employment — pending_start is joining, never active. */
export function isEmploymentActive(status: string | null | undefined): boolean {
  if (isEmploymentLeft(status) || isEmploymentPendingStart(status)) return false
  const s = String(status || '').trim().toLowerCase()
  return !s || s === 'active'
}

export function isOnboardingIncomplete(status: string | null | undefined): boolean {
  const s = String(status || '').trim().toLowerCase()
  if (!s || ONBOARDING_DONE.has(s) || ONBOARDING_DEAD.has(s)) return false
  return true
}

export type PeopleExceptionChip = {
  key: 'left' | 'joining' | 'onboarding'
  labelKey: 'hrPeople.chipLeft' | 'hrPeople.chipJoining' | 'hrPeople.chipOnboarding'
  tone: Extract<StatusTone, 'yellow' | 'neutral'>
}

/** At most one chip. Left beats Joining beats Onboarding. Active complete → null. */
export function peopleExceptionChip(
  employee: PersonIdentity | null | undefined,
): PeopleExceptionChip | null {
  if (!employee) return null
  if (isEmploymentLeft(employee.employment_status)) {
    return { key: 'left', labelKey: 'hrPeople.chipLeft', tone: 'neutral' }
  }
  if (isEmploymentPendingStart(employee.employment_status)) {
    return { key: 'joining', labelKey: 'hrPeople.chipJoining', tone: 'yellow' }
  }
  if (isOnboardingIncomplete(employee.onboarding_status)) {
    return { key: 'onboarding', labelKey: 'hrPeople.chipOnboarding', tone: 'yellow' }
  }
  return null
}

export function peopleSecondaryLine(employee: PersonIdentity): string {
  return [employee.position_title, employee.department]
    .map((part) => String(part || '').trim())
    .filter(Boolean)
    .join(' · ')
}

export function filterPeopleRows(
  items: EmployeeSummary[],
  opts: {
    status: PeopleStatusFilter
    department: string | null
    onboardingOpenOnly: boolean
  },
): EmployeeSummary[] {
  return items.filter((row) => {
    const left = isEmploymentLeft(row.employee.employment_status)
    const active = isEmploymentActive(row.employee.employment_status)
    if (opts.status === 'active' && !active) return false
    if (opts.status === 'left' && !left) return false
    if (opts.department) {
      const dept = String(row.employee.department || '').trim()
      if (dept !== opts.department) return false
    }
    if (opts.onboardingOpenOnly && !isOnboardingIncomplete(row.employee.onboarding_status)) {
      return false
    }
    return true
  })
}

export function uniqueDepartments(items: EmployeeSummary[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const row of items) {
    const dept = String(row.employee.department || '').trim()
    if (!dept || seen.has(dept)) continue
    seen.add(dept)
    out.push(dept)
  }
  return out.sort((a, b) => a.localeCompare(b))
}

export const PEOPLE_PAGE_SIZE = 40
