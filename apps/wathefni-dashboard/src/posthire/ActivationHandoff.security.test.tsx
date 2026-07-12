import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import { ActivationHandoffModal } from './PostHire'

const HANDOFF = {
  invite_id: '00000000-0000-0000-0000-000000000001',
  task_id: '00000000-0000-0000-0000-000000000002',
  expires_at: '2026-07-13T12:00:00Z',
  activation_code: '839204',
}

function Harness() {
  const [handoff, setHandoff] = useState<typeof HANDOFF | null>(HANDOFF)
  return handoff ? <ActivationHandoffModal handoff={handoff} onClose={() => setHandoff(null)} /> : <p>Cleared</p>
}

describe('secure activation handoff', () => {
  test('keeps the code in component memory and clears it on close', () => {
    const storageWrite = vi.spyOn(Storage.prototype, 'setItem')
    const clipboardWrite = vi.fn()
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: clipboardWrite } })

    render(<Harness />)
    expect(screen.getByTestId('activation-handoff-code')).toHaveTextContent(HANDOFF.activation_code)
    expect(storageWrite).not.toHaveBeenCalled()
    expect(clipboardWrite).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Close and clear' }))
    expect(screen.queryByText(HANDOFF.activation_code)).not.toBeInTheDocument()
    expect(screen.getByText('Cleared')).toBeInTheDocument()
    expect(storageWrite).not.toHaveBeenCalled()
    expect(clipboardWrite).not.toHaveBeenCalled()
  })
})
