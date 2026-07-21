import { describe, expect, test } from 'vitest'
import {
  jobEligibilityReasonLabel,
  jobIsExternallyShareable,
} from '@/lib/recruitingLifecycle'

describe('job shareability UI helpers', () => {
  test('gates share controls on backend shareable flag even when apply code exists', () => {
    expect(
      jobIsExternallyShareable({
        shareable: false,
        accepts_applications: false,
        application_link: null,
        qr_value: null,
      }),
    ).toBe(false)
    expect(
      jobIsExternallyShareable({
        shareable: true,
        accepts_applications: true,
        application_link: 'https://wa.me/96599338566?text=APPLY-X',
        qr_value: 'https://wa.me/96599338566?text=APPLY-X',
      }),
    ).toBe(true)
  })

  test('eligibility reasons render in English and Arabic', () => {
    expect(jobEligibilityReasonLabel('en', 'job_visibility_denied')).toMatch(/Internal only/i)
    expect(jobEligibilityReasonLabel('ar', 'job_visibility_denied')).toMatch(/داخلية/)
    expect(jobEligibilityReasonLabel('en', 'job_paused')).toMatch(/Paused/i)
    expect(jobEligibilityReasonLabel('ar', 'job_paused')).toMatch(/متوقفة/)
    expect(jobEligibilityReasonLabel('en', 'job_vacancies_exhausted')).toMatch(/vacancies/i)
    expect(jobEligibilityReasonLabel('ar', 'job_deadline_passed')).toMatch(/موعد/)
  })
})
