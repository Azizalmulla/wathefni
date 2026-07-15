import { describe, expect, it } from 'vitest'

import { mobileApi, type MobileRequester } from './mobile'

function requester(payload: unknown = { ok: true, items: [] }) {
  const calls: Array<{ path: string; options: unknown }> = []
  const request: MobileRequester = async <T>(path: string, options?: unknown) => {
    calls.push({ path, options })
    return payload as T
  }
  return { calls, request }
}

describe('HR-3 mobile endpoint contract', () => {
  it('uses the registered task and document routes', async () => {
    const tasks = requester()
    await mobileApi.tasks(tasks.request)
    expect(tasks.calls[0].path).toBe('/dashboard/mobile/tasks')

    const document = requester({ ok: true, document: { document_id: 'e:civil_id' } })
    await mobileApi.documentDetail(document.request, 'employee/a', 'civil id')
    expect(document.calls[0].path).toBe(
      '/dashboard/mobile/documents/employee%2Fa/civil%20id',
    )
  })

  it('binds document review to employee and document type', async () => {
    const value = requester({ ok: true })
    await mobileApi.documentReview(
      value.request,
      'employee-1',
      'civil_id',
      { expected_status: 'needs_review' },
    )
    expect(value.calls[0]).toEqual({
      path: '/dashboard/mobile/documents/employee-1/civil_id/review',
      options: {
        method: 'POST',
        json: { expected_status: 'needs_review' },
      },
    })
  })

  it('uses confirmation-capable attendance and swap endpoints', async () => {
    const value = requester({ ok: false, status: 'needs_confirmation' })
    await mobileApi.resolveAttendance(value.request, 'attendance-1', {
      status: 'present',
      idempotency_key: 'test-key-1234',
      confirm: false,
    })
    await mobileApi.swapDecision(value.request, 'swap-1', {
      action: 'approve',
      idempotency_key: 'test-key-5678',
      confirm: false,
    })
    expect(value.calls.map((call) => call.path)).toEqual([
      '/dashboard/mobile/attendance/attendance-1/resolve',
      '/dashboard/mobile/shift-swaps/swap-1/decision',
    ])
  })
})
