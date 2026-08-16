import { describe, expect, test } from 'vitest'

import { mapWithConcurrency } from './utils'

describe('mapWithConcurrency', () => {
  test('preserves input order in results regardless of completion order', async () => {
    const items = [40, 10, 30, 20, 0]
    const results = await mapWithConcurrency(items, 3, async (ms, index) => {
      await new Promise((resolve) => setTimeout(resolve, ms))
      return { index, ms }
    })
    expect(results.map((r) => r.index)).toEqual([0, 1, 2, 3, 4])
    expect(results.map((r) => r.ms)).toEqual(items)
  })

  test('never exceeds the concurrency limit and runs every item once', async () => {
    const items = Array.from({ length: 12 }, (_, i) => i)
    let active = 0
    let peak = 0
    const seen: number[] = []
    await mapWithConcurrency(items, 5, async (item) => {
      active += 1
      peak = Math.max(peak, active)
      await new Promise((resolve) => setTimeout(resolve, 5))
      seen.push(item)
      active -= 1
    })
    expect(peak).toBeLessThanOrEqual(5)
    expect([...seen].sort((a, b) => a - b)).toEqual(items)
  })

  test('handles an empty list without scheduling any work', async () => {
    let calls = 0
    const results = await mapWithConcurrency([], 5, async () => {
      calls += 1
      return calls
    })
    expect(results).toEqual([])
    expect(calls).toBe(0)
  })

  test('caps workers at the item count when the limit is larger', async () => {
    const items = [1, 2]
    let active = 0
    let peak = 0
    await mapWithConcurrency(items, 10, async () => {
      active += 1
      peak = Math.max(peak, active)
      await new Promise((resolve) => setTimeout(resolve, 5))
      active -= 1
    })
    expect(peak).toBeLessThanOrEqual(2)
  })
})
