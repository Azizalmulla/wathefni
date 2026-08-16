import { describe, expect, it } from 'vitest'

import {
  assessmentSetupIsReady,
  assessmentSetupLastRefreshedAt,
  assessmentSetupLastRefreshedLabel,
} from '@/pages/shared/format'

describe('assessment setup configuration presentation', () => {
  it('marks setup ready only when calibration Ready and content ok', () => {
    expect(
      assessmentSetupIsReady({
        norms: { status: 'empirical_ready' },
        item_bank: { validation: { ok: true } },
      }),
    ).toBe(true)
    expect(
      assessmentSetupIsReady({
        norms: { status: 'synthetic_until_client_benchmark' },
        item_bank: { validation: { ok: true } },
      }),
    ).toBe(false)
    expect(
      assessmentSetupIsReady({
        norms: { status: 'empirical_ready' },
        item_bank: { validation: { ok: false } },
      }),
    ).toBe(false)
  })

  it('picks the latest norms group updated_at', () => {
    expect(
      assessmentSetupLastRefreshedAt({
        norms: {
          groups: [
            { updated_at: '2026-07-01T10:00:00Z' },
            { updated_at: '2026-07-20T12:30:00Z' },
            { updated_at: '2026-07-10T08:00:00Z' },
          ],
        },
      }),
    ).toBe('2026-07-20T12:30:00Z')
    expect(assessmentSetupLastRefreshedAt({ norms: { groups: [] } })).toBeNull()
  })

  it('labels missing refresh timestamps for EN/AR', () => {
    expect(assessmentSetupLastRefreshedLabel(null, 'en')).toBe('Last refreshed not recorded')
    expect(assessmentSetupLastRefreshedLabel(null, 'ar')).toBe('آخر تحديث غير مسجّل')
    expect(assessmentSetupLastRefreshedLabel('2026-07-20T12:30:00Z', 'en')).toMatch(/^Last refreshed /)
    expect(assessmentSetupLastRefreshedLabel('2026-07-20T12:30:00Z', 'ar')).toMatch(/^آخر تحديث /)
  })
})
