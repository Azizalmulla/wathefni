import { describe, expect, test } from 'vitest'

import { normalizedJobStatus } from '@/pages/shared/format'
import type { PositionSummary } from '@/types'

function job(partial: Partial<PositionSummary> & Pick<PositionSummary, 'position_code' | 'status'>): PositionSummary {
  return {
    position_code: partial.position_code,
    title: partial.title || partial.position_code,
    status: partial.status,
    application_count: partial.application_count ?? 0,
    active_count: partial.active_count ?? 0,
  } as PositionSummary
}

describe('normalizedJobStatus aliases', () => {
  test('maps legacy aliases through the shared Jobs contract', () => {
    expect(normalizedJobStatus(job({ position_code: 'A', status: 'active' }))).toBe('open')
    expect(normalizedJobStatus(job({ position_code: 'A', status: 'published' }))).toBe('open')
    expect(normalizedJobStatus(job({ position_code: 'A', status: 'inactive' }))).toBe('closed')
    expect(normalizedJobStatus(job({ position_code: 'A', status: 'open' }))).toBe('open')
    expect(normalizedJobStatus(job({ position_code: 'A', status: 'paused' }))).toBe('paused')
    expect(normalizedJobStatus(job({ position_code: 'A', status: 'draft' }))).toBe('draft')
    expect(normalizedJobStatus(job({ position_code: 'A', status: 'closed' }))).toBe('closed')
  })

  test('clickable Applications badge uses active_pipeline, not historical total', () => {
    // Mirrors audit: badge must not equal application_count when terminals remain.
    const social = job({
      position_code: 'SOCIAL_MEDIA_MANAGER',
      status: 'open',
      application_count: 2,
      active_count: 1,
    })
    expect(Number(social.active_count)).toBe(1)
    expect(Number(social.application_count)).toBe(2)
    expect(Number(social.active_count)).not.toBe(Number(social.application_count))
  })
})
