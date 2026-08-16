import { useRef, useState } from 'react'

import type { ConfirmationView } from '@hr/components/primitives'
import { createIdempotencyKey } from '@hr/lib/idempotency'

import { ApiError } from './client'
import type { ConfirmationMaterial, DecisionResponse } from './types'

type ConfirmationFields = {
  idempotency_key: string
  confirm: boolean
  confirmation_id?: string
  confirmation_hash?: string
}

export function useServerConfirmation<T>({
  keyPrefix,
  execute,
  onSuccess,
}: {
  keyPrefix: string
  execute: (input: T, fields: ConfirmationFields) => Promise<DecisionResponse>
  onSuccess?: () => void | Promise<void>
}) {
  const pending = useRef<{
    input: T
    key: string
    material: ConfirmationMaterial
  } | null>(null)
  const [view, setView] = useState<ConfirmationView | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [succeeded, setSucceeded] = useState(false)

  const prepare = async (input: T) => {
    setLoading(true)
    setError(null)
    setSucceeded(false)
    try {
      const key = createIdempotencyKey(keyPrefix)
      const response = await execute(input, { idempotency_key: key, confirm: false })
      pending.current = { input, key, material: response.confirmation }
      setView({
        target: response.confirmation.summary,
        action: response.confirmation.action,
        consequence: response.confirmation.consequence,
        currentState: response.confirmation.current_state,
      })
    } catch (cause) {
      setError(cause)
      throw cause
    } finally {
      setLoading(false)
    }
  }

  const confirm = async () => {
    const current = pending.current
    if (!current) {
      setError(new ApiError(409, 'confirmation_unavailable', 'Confirmation expired. Close and try again.'))
      return
    }
    setLoading(true)
    setError(null)
    try {
      const response = await execute(current.input, {
        idempotency_key: current.key,
        confirm: true,
        confirmation_id: current.material.confirmation_id,
        confirmation_hash: current.material.confirmation_hash,
      })
      if (!response.ok) {
        throw new ApiError(409, response.status, 'The decision was not completed.')
      }
      pending.current = null
      setView(null)
      setSucceeded(true)
      await onSuccess?.()
    } catch (cause) {
      setError(cause)
      throw cause
    } finally {
      setLoading(false)
    }
  }

  const cancel = () => {
    pending.current = null
    setView(null)
  }

  return { view, visible: Boolean(view), loading, error, succeeded, prepare, confirm, cancel }
}
