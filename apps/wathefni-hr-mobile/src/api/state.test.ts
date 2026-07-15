import { describe, expect, it } from 'vitest'

import { ApiError } from './client'
import { resourceState, stateForError } from './state'

describe('resource state normalization', () => {
  it.each([
    [new ApiError(0, 'network_error', 'offline'), 'offline'],
    [new ApiError(403, 'out_of_scope', 'denied'), 'permission'],
    [new ApiError(401, 'session_expired', 'expired'), 'session_expired'],
    [new ApiError(409, 'stale_decision', 'stale'), 'stale'],
    [new ApiError(403, 'company_archived', 'archived'), 'company_archived'],
  ])('maps %s explicitly', (error, expected) => {
    expect(stateForError(error)).toBe(expected)
  })

  it('keeps loading and empty states deterministic', () => {
    expect(resourceState({ loading: true, empty: true })).toBe('loading')
    expect(resourceState({ empty: true })).toBe('empty')
  })
})
