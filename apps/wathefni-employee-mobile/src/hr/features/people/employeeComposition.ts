/** Employee quick-profile presentation — facts only, no invented E360 meaning. */

import type { StatusTone } from '@/components/ui'

const STATUS_KEYS: Record<string, string> = {
  active: 'hrEmployee.statusActive',
  left: 'hrEmployee.statusLeft',
  inactive: 'hrEmployee.statusInactive',
  terminated: 'hrEmployee.statusTerminated',
  onboarding: 'hrEmployee.statusOnboarding',
  pending: 'hrEmployee.statusPending',
}

export function employmentStatusLabelKey(status: string | null | undefined): string {
  const raw = String(status || '').trim().toLowerCase()
  if (!raw) return 'hrEmployee.statusOther'
  return STATUS_KEYS[raw] || 'hrEmployee.statusOther'
}

/** Filled Wathefni pink/blue/yellow/green — never brown/orange outline chips. */
export function employmentStatusTone(status: string | null | undefined): StatusTone {
  const raw = String(status || '').trim().toLowerCase()
  if (raw === 'active') return 'green'
  if (raw === 'onboarding' || raw === 'pending') return 'yellow'
  if (raw === 'left' || raw === 'terminated' || raw === 'inactive') return 'pink'
  return 'blue'
}

export function localizeEmploymentStatus(
  status: string | null | undefined,
  t: (key: string) => string,
): string {
  const key = employmentStatusLabelKey(status)
  if (key === 'hrEmployee.statusOther') {
    const raw = String(status || '').trim()
    return raw || t('hrEmployee.statusOther')
  }
  return t(key)
}
