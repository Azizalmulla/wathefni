import { describe, expect, test } from 'vitest'

import type { ComplianceFinding, PosthireComplianceResponse } from '@/types'

function rankOk(items: ComplianceFinding[]) {
  const rank = { high: 0, medium: 1, low: 2 } as Record<string, number>
  for (let i = 1; i < items.length; i += 1) {
    const prev = rank[items[i - 1].severity] ?? 9
    const next = rank[items[i].severity] ?? 9
    if (next < prev) return false
  }
  return true
}

describe('Compliance Wave 1 findings contract (client)', () => {
  test('findings carry owner, deadline, escalation, deep links and honesty', () => {
    const sample: PosthireComplianceResponse = {
      company_code: 'WATHEFNI',
      as_of: '2026-08-03T18:00:00+03:00',
      timezone: 'Asia/Kuwait',
      kuwait_date: '2026-08-03',
      contract: 'compliance_findings_wave1',
      summary: {
        expired: 1,
        expiring_soon: 1,
        missing: 1,
        needs_review: 0,
        valid: 2,
        needs_attention: 3,
        total_documents: 5,
        employees_checked: 3,
        employees_total: 3,
      },
      documents: [],
      findings: [
        {
          id: 'expired:E1:residence',
          severity: 'high',
          reason_en: "Alice's Residence is expired by 5 days",
          reason_ar: 'الإقامة لـ Alice منتهية منذ 5 يوم',
          employee_key: 'E1',
          document_type_canonical: 'residence',
          evidence_status: 'expired',
          government_verified: false,
          guidance_only: true,
          owner_role: 'hr_compliance',
          owner_label_en: 'Company HR / Compliance',
          deadline: '2026-08-03',
          escalation_step: 'overdue_daily',
          system_of_action: 'compliance',
          deep_link: { page: 'compliance', employee: 'E1', document_type: 'residence' },
          secondary_links: [{ page: 'employees', employee: 'E1', label_en: 'Open employee' }],
          alerts_delivery_owns_reminders: true,
        },
        {
          id: 'missing:E2:work_permit',
          severity: 'medium',
          reason_en: "Bob's Work permit is missing",
          employee_key: 'E2',
          evidence_status: 'missing',
          owner_role: 'hr_compliance',
          deep_link: { page: 'onboarding', employee: 'E2', document_type: 'work_permit' },
        },
      ],
      honesty: {
        government_verified: false,
        legal_compliance_claims: false,
        fine_calculations: false,
        analytics_excludes_compliance: true,
      },
      freshness: { stale_after_seconds: 300 },
      sources: {
        partial: true,
        unavailable_source_keys: ['onboarding'],
      },
    }

    expect(sample.contract).toBe('compliance_findings_wave1')
    expect(rankOk(sample.findings || [])).toBe(true)
    expect(sample.findings?.[0]?.deep_link.page).toBe('compliance')
    expect(sample.findings?.[1]?.deep_link.page).toBe('onboarding')
    expect(sample.findings?.[0]?.government_verified).toBe(false)
    expect(sample.findings?.[0]?.owner_role).toBe('hr_compliance')
    expect(sample.findings?.[0]?.escalation_step).toBe('overdue_daily')
    expect(sample.honesty?.legal_compliance_claims).toBe(false)
    expect(sample.as_of).toContain('+03:00')
    expect(sample.sources?.partial).toBe(true)
  })
})
