import { describe, expect, test } from 'vitest'

import type { PosthireAnalyticsAttentionItem, PosthireAnalyticsResponse } from '@/types'

function rankOk(items: PosthireAnalyticsAttentionItem[]) {
  const rank = { high: 0, medium: 1, low: 2 } as Record<string, number>
  for (let i = 1; i < items.length; i += 1) {
    const prev = rank[items[i - 1].severity] ?? 9
    const next = rank[items[i].severity] ?? 9
    if (next < prev) return false
  }
  return true
}

describe('Analytics Wave 1 attention contract (client)', () => {
  test('attention items carry deep links into systems of action', () => {
    const sample: PosthireAnalyticsResponse = {
      company_code: 'WATHEFNI',
      as_of: '2026-08-03T15:00:00+03:00',
      timezone: 'Asia/Kuwait',
      contract: 'analytics_attention_wave1',
      attention: [
        {
          id: 'pending_leave',
          severity: 'high',
          reason_en: '3 leave requests await a decision',
          reason_ar: '3 طلبات إجازة بانتظار القرار',
          subject: 'Leave queue',
          source_module: 'leave',
          count: 3,
          deep_link: { page: 'leave' },
        },
        {
          id: 'top_lateness:E1',
          severity: 'medium',
          reason_en: 'Alice has 40 late minutes in the period',
          subject: 'Alice',
          subject_key: 'E1',
          source_module: 'attendance',
          count: 40,
          deep_link: { page: 'employees', employee: 'E1' },
        },
      ],
      headlines: [
        { key: 'absences', label_en: 'Absences', label_ar: 'الغياب', value: 2 },
        { key: 'pending_review', label_en: 'Pending review', label_ar: 'بانتظار المراجعة', value: 3 },
      ],
      sources: {
        partial: true,
        unavailable_source_keys: ['shifts'],
        sources: {
          shifts: {
            module: 'shifts',
            available: false,
            status: 'unavailable',
            note_en: 'shifts is not enabled for this company.',
            note_ar: 'وحدة shifts غير مفعّلة لهذه الشركة.',
          },
        },
      },
      freshness: { stale_after_seconds: 300 },
    }

    expect(sample.contract).toBe('analytics_attention_wave1')
    expect(rankOk(sample.attention || [])).toBe(true)
    expect(sample.headlines?.some((h) => h.key === 'scheduled_shifts')).toBe(false)
    expect(sample.attention?.[0]?.deep_link.page).toBe('leave')
    expect(sample.attention?.[1]?.deep_link).toEqual({ page: 'employees', employee: 'E1' })
    expect(sample.sources?.partial).toBe(true)
    expect(sample.as_of).toContain('+03:00')
  })
})
