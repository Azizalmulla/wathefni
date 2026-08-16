import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ResourceState, resolveListDataState } from './dataState'

describe('resolveListDataState', () => {
  test('never treats a failed read as empty', () => {
    expect(resolveListDataState({ error: true, itemCount: 0 })).toBe('error')
    expect(resolveListDataState({ error: true, itemCount: 3 })).toBe('error')
    expect(resolveListDataState({ loading: true, itemCount: 0 })).toBe('loading')
    expect(resolveListDataState({ itemCount: 0 })).toBe('empty')
    expect(resolveListDataState({ itemCount: 2 })).toBe('ready')
  })

  test('forbidden and unavailable win over empty', () => {
    expect(resolveListDataState({ forbidden: true, itemCount: 0 })).toBe('forbidden')
    expect(resolveListDataState({ unavailable: true, itemCount: 0 })).toBe('unavailable')
  })
})

describe('ResourceState', () => {
  test('error copy is not an empty-success message (EN/AR)', () => {
    const { rerender } = render(<ResourceState kind="error" locale="en" />)
    expect(screen.getByRole('alert')).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/nothing to show/i)).not.toBeInTheDocument()
    rerender(<ResourceState kind="error" locale="ar" />)
    expect(screen.getByRole('alert')).toHaveTextContent('ليست نتيجة فارغة')
  })

  test('retry is offered on error', () => {
    const onRetry = vi.fn()
    render(<ResourceState kind="error" locale="en" onRetry={onRetry} />)
    screen.getByRole('button', { name: 'Retry' }).click()
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
