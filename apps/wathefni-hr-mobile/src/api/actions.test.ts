import { describe, expect, it } from 'vitest'

import { hasAnyAllowedAction, visibleActions } from './actions'

describe('backend-controlled action visibility', () => {
  it('shows only exact backend allowed_actions', () => {
    expect(visibleActions(['shortlist', 'hire'], ['shortlist', 'reject', 'hire'])).toEqual([
      'shortlist',
      'hire',
    ])
  })

  it('does not infer actions from status or aliases', () => {
    expect(visibleActions([], ['approve', 'reject'])).toEqual([])
    expect(hasAnyAllowedAction(['read'], ['preview_cv', 'preview'])).toBe(false)
  })

  it('does not invent schedule_interview when backend omits it', () => {
    expect(visibleActions(['shortlist', 'reject'], ['schedule_interview'])).toEqual([])
    expect(hasAnyAllowedAction(['shortlist', 'reject', 'hire'], ['schedule_interview'])).toBe(false)
  })
})
