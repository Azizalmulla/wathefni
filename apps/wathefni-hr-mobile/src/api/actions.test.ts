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

  it('supports explicitly documented CV action aliases only', () => {
    expect(hasAnyAllowedAction(['preview_cv'], ['preview_cv', 'cv_preview', 'preview'])).toBe(true)
  })
})
