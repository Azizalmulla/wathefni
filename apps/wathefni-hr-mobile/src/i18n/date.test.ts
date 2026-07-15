import { describe, expect, it } from 'vitest'

import { formatDate, formatDateRange, formatDateTime, formatTimeRange } from './date'

describe('localized HR date formatting', () => {
  it('never exposes raw ISO strings in English UI', () => {
    const input = '2026-07-15T08:30:00+03:00'
    const output = formatDateTime(input, 'en')
    expect(output).not.toContain('2026-07-15T')
    expect(output).toContain('2026')
  })

  it('uses natural Arabic month and numeral output', () => {
    const output = formatDate('2026-07-15', 'ar')
    expect(output).toMatch(/يوليو/)
    expect(output).toMatch(/[٠-٩]/)
  })

  it('formats date and time ranges without ISO separators', () => {
    expect(formatDateRange('2026-07-15', '2026-07-18', 'en')).not.toContain('2026-07-')
    expect(
      formatTimeRange('2026-07-15T08:30:00+03:00', '2026-07-15T17:00:00+03:00', 'ar'),
    ).toContain('إلى')
  })

  it('uses a safe placeholder for invalid backend dates', () => {
    expect(formatDate('not-a-date', 'en')).toBe('—')
  })
})
