import { describe, expect, test } from 'vitest'

import { resolveAllowedActions } from './allowedActions'

describe('resolveAllowedActions', () => {
  test('missing lists fail closed', () => {
    expect(resolveAllowedActions(undefined, undefined)).toEqual([])
    expect(resolveAllowedActions(null, null)).toEqual([])
  })

  test('presentation overlay replaces canonical and never unions extras', () => {
    expect(resolveAllowedActions(['cancel_interview', 'open_candidate'], ['cancel_interview'])).toEqual([
      'cancel_interview',
    ])
    expect(resolveAllowedActions(['cancel_interview'], ['cancel_interview', 'invented'])).toEqual([
      'cancel_interview',
      'invented',
    ])
  })

  test('empty presentation list is fail-closed, not a fallback to canonical', () => {
    expect(resolveAllowedActions(['cancel_interview'], [])).toEqual([])
  })

  test('canonical list is used when presentation is absent', () => {
    expect(resolveAllowedActions(['resend_video_link', 'cancel_interview'])).toEqual([
      'resend_video_link',
      'cancel_interview',
    ])
  })
})
