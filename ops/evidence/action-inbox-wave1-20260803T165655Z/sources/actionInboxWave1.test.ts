import { describe, expect, test } from 'vitest'

import type { ActionInboxItem, PosthireActionInboxResponse } from '@/types'

function rankOk(items: ActionInboxItem[]) {
  const rank = { critical: 0, high: 1, medium: 2, low: 3 } as Record<string, number>
  const source = { compliance: 0, analytics: 1, employees: 2 } as Record<string, number>
  for (let i = 1; i < items.length; i += 1) {
    const prev = items[i - 1]
    const next = items[i]
    const prevKey = [
      rank[prev.severity] ?? 9,
      source[String(prev.source_stream)] ?? 9,
      String(prev.deadline || '9999-99-99'),
    ]
    const nextKey = [
      rank[next.severity] ?? 9,
      source[String(next.source_stream)] ?? 9,
      String(next.deadline || '9999-99-99'),
    ]
    const worse =
      nextKey[0] < prevKey[0] ||
      (nextKey[0] === prevKey[0] && nextKey[1] < prevKey[1]) ||
      (nextKey[0] === prevKey[0] && nextKey[1] === prevKey[1] && String(nextKey[2]) < String(prevKey[2]))
    if (worse) return false
  }
  return true
}

describe('Action Inbox Wave 1 contract (client)', () => {
  test('items carry owner, deadline, escalation, deep links and honesty', () => {
    const sample: PosthireActionInboxResponse = {
      company_code: 'WATHEFNI',
      as_of: '2026-08-03T18:00:00+03:00',
      timezone: 'Asia/Kuwait',
      kuwait_date: '2026-08-03',
      contract: 'action_inbox_wave1',
      items: [
        {
          id: 'compliance:expired:E1:residence',
          severity: 'high',
          what_en: 'Alice residence expired',
          what_ar: 'إقامة Alice منتهية',
          why_en: 'Document finding',
          owner_label_en: 'Company HR / Compliance',
          deadline: '2026-08-03',
          deadline_label_en: 'Overdue',
          escalation_step: 'overdue_daily',
          escalation_label_en: 'Daily follow-up',
          source_stream: 'compliance',
          source_module: 'compliance',
          system_of_action: 'compliance',
          evidence_status_label_en: 'Expired',
          authority_status_label_en: 'Document findings — never government verified',
          government_verified: false,
          deep_link: { page: 'compliance', employee: 'E1', document_type: 'residence' },
        },
        {
          id: 'analytics:pending_leave',
          severity: 'high',
          what_en: '3 leave requests await a decision',
          source_stream: 'analytics',
          source_module: 'leave',
          system_of_action: 'leave',
          owner_label_en: 'Company HR',
          deep_link: { page: 'leave' },
        },
        {
          id: 'employees:E2:onboarding:incomplete',
          severity: 'medium',
          what_en: 'Onboarding incomplete',
          source_stream: 'employees',
          source_module: 'onboarding',
          system_of_action: 'onboarding',
          deep_link: { page: 'onboarding', employee: 'E2' },
        },
      ],
      summary: {
        total: 3,
        by_stream: { analytics: 1, compliance: 1, employees: 1 },
      },
      honesty: {
        mutates_records: false,
        ai: false,
        hiring_reports_separate: true,
        alerts_delivery_owns_notifications: true,
        compliance_wave2: false,
        analytics_wave2: false,
        payroll_money: false,
      },
      freshness: { stale_after_seconds: 300 },
      sources: {
        partial: true,
        unavailable_source_keys: ['analytics'],
      },
    }

    expect(sample.contract).toBe('action_inbox_wave1')
    expect(rankOk(sample.items)).toBe(true)
    expect(sample.items[0].deep_link.page).toBe('compliance')
    expect(sample.items[0].owner_label_en).toBeTruthy()
    expect(sample.items[0].deadline).toBeTruthy()
    expect(sample.items[0].escalation_label_en).toBeTruthy()
    expect(sample.honesty?.mutates_records).toBe(false)
    expect(sample.honesty?.ai).toBe(false)
    expect(sample.sources?.partial).toBe(true)
  })
})
