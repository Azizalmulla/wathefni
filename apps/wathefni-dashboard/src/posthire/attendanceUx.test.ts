import { describe, expect, it } from 'vitest'

import {
  attendanceLifeState,
  caseStatusLabel,
  lifeStateLabel,
  payrollExclusionReason,
} from '@/posthire/attendanceUx'

describe('attendanceUx Wave 4 helpers', () => {
  it('distinguishes captured vs incomplete vs disputed vs locked', () => {
    expect(attendanceLifeState({ status: 'completed', metadata: { exception_state: 'none', approval_status: 'approved' } })).toBe(
      'approved',
    )
    expect(attendanceLifeState({ status: 'incomplete', metadata: { exception_state: 'missing_check_out' } })).toBe('incomplete')
    expect(attendanceLifeState({ status: 'completed', metadata: { approval_status: 'disputed' } })).toBe('disputed')
    expect(attendanceLifeState({ status: 'completed', metadata: { payroll_locked: true } })).toBe('locked')
  })

  it('explains payroll exclusion in EN and AR', () => {
    const en = payrollExclusionReason({ metadata: { exception_state: 'missing_check_in', payroll_eligible: false } }, 'en')
    const ar = payrollExclusionReason({ metadata: { exception_state: 'missing_check_in', payroll_eligible: false } }, 'ar')
    expect(en).toMatch(/Excluded from Payroll/i)
    expect(ar).toMatch(/مستبعد/)
  })

  it('labels approve-ready separately from applied', () => {
    expect(caseStatusLabel('approved', 'en')).toMatch(/ready to apply/i)
    expect(caseStatusLabel('applied', 'en')).toBe('Applied')
    expect(lifeStateLabel('needs_review', 'ar')).toBe('يحتاج مراجعة')
  })
})
