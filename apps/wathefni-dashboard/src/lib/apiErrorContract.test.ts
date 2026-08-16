import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardApiError, getDashboardBootstrap } from './api'
import { listApplicationOffers } from './offers-api'
import { listCompanies } from '../setup-console/api'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.removeItem('wathefni_recruiting_locale')
})

describe('dashboard API error presentation contract', () => {
  it('keeps machine codes available without showing them as user copy', () => {
    const error = new DashboardApiError(
      409,
      { error: 'row_not_approved_pending_apply' },
      'We couldn’t complete this action.',
    )

    expect(error.code).toBe('row_not_approved_pending_apply')
    expect(error.message).toBe('We couldn’t complete this action.')
    expect(error.message).not.toContain('row_not_approved_pending_apply')
  })

  it('uses calm backend copy when the endpoint supplies it', () => {
    const error = new DashboardApiError(
      404,
      { error: 'row_not_found', message: 'This item changed. Refresh and try again.' },
      'We couldn’t complete this action.',
    )

    expect(error.code).toBe('row_not_found')
    expect(error.message).toBe('This item changed. Refresh and try again.')
  })

  it('does not surface a string machine code', () => {
    const error = new DashboardApiError(
      400,
      'stale_row_version',
      'Refresh and try again.',
    )

    expect(error.message).toBe('Refresh and try again.')
  })

  it('does not surface machine codes from the offer API client', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { error: 'offer_state_transition_denied' } }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(listApplicationOffers({
      token: 'test-token',
      companyCode: 'WATHEFNI',
      hrPhone: '',
    }, 'APP-1')).rejects.toThrow('Offer request failed.')
  })

  it('uses a calm Arabic fallback for legacy endpoints without message copy', async () => {
    localStorage.setItem('wathefni_recruiting_locale', 'ar')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { error: 'legacy_machine_code' } }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(getDashboardBootstrap({
      token: 'test-token',
      companyCode: 'WATHEFNI',
      hrPhone: '',
    })).rejects.toThrow('تعذر إكمال طلب لوحة التحكم.')
  })

  it('does not surface machine codes from the setup console client', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'setup_internal_code' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(listCompanies({
      token: 'operator-token',
      phone: '96500000000',
    }, {
      q: '',
      limit: 20,
      offset: 0,
    })).rejects.toThrow('The setup request could not be completed.')
  })
})
