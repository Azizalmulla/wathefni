import { describe, expect, test } from 'vitest'

import {
  addressHoldPresentation,
  groupAllowsSafeBulkAdmit,
  heldGroupKindLabel,
  intakeStatePresentation,
} from '@/lib/inboundIntakePresentation'

describe('inboundIntakePresentation', () => {
  test('labels needs_role / role_bound / identity / quarantined / ready in EN and AR', () => {
    expect(intakeStatePresentation('needs_role', 'en').label).toMatch(/Needs a job/i)
    expect(intakeStatePresentation('needs_role', 'ar').label).toMatch(/تحتاج وظيفة/)
    expect(addressHoldPresentation(true, 'en').id).toBe('role_bound')
    expect(addressHoldPresentation(false, 'ar').id).toBe('needs_role')
    expect(intakeStatePresentation('identity_review', 'en').tone).toBe('warning')
    expect(intakeStatePresentation('quarantined', 'en').tone).toBe('danger')
    expect(intakeStatePresentation('ready', 'en').tone).toBe('success')
    expect(intakeStatePresentation('quarantined', 'en').recovery.length).toBeGreaterThan(10)
  })

  test('safe bulk admit only when group has role_code', () => {
    expect(groupAllowsSafeBulkAdmit({ role_code: 'ENG', kind: 'suggested' })).toBe(true)
    expect(groupAllowsSafeBulkAdmit({ role_code: '', kind: 'unclear' })).toBe(false)
    expect(heldGroupKindLabel('unclear', 'en')).toMatch(/No clear job/i)
    expect(heldGroupKindLabel('explicit_review', 'ar')).toMatch(/دور معلن/)
  })
})
