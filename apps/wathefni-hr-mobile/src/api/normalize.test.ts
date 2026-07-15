import { describe, expect, it } from 'vitest'

import { normalize } from './normalize'

describe('thin mobile response normalization', () => {
  it('accepts documented collection envelopes', () => {
    const result = normalize.attendance({
      ok: true,
      exceptions: [
        {
          exception_id: 'a-1',
          employee: { name: 'Noura' },
          exception_type: 'late',
          status: 'open',
          allowed_actions: ['resolve', 4],
        },
      ],
    })
    expect(result.items).toEqual([
      expect.objectContaining({
        exception_id: 'a-1',
        exception_type: 'late',
        allowed_actions: ['resolve'],
      }),
    ])
  })

  it('does not invent actions or authority from unknown fields', () => {
    const result = normalize.candidates({
      candidates: [{ app_key: 'c-1', role: 'owner', can_hire: true }],
    })
    expect(result.items[0].allowed_actions).toEqual([])
    expect(result.items[0].score).toBeNull()
  })

  it('normalizes empty and malformed payloads safely', () => {
    expect(normalize.tasks(null).items).toEqual([])
    expect(normalize.employees({ items: [null] }).items[0].employee.name).toBe('—')
  })
})
