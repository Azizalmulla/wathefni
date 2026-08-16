import type { RequestOptions } from './client'
import type { DecisionResponse } from './types'
import { normalize } from './normalize'

export type MobileRequester = <T>(
  path: string,
  options?: Omit<RequestOptions, 'token'>,
) => Promise<T>

async function normalized<T>(
  request: MobileRequester,
  path: string,
  parser: (payload: unknown) => T,
  options?: Omit<RequestOptions, 'token'>,
): Promise<T> {
  return parser(await request<unknown>(path, options))
}

const segment = (value: string) => encodeURIComponent(value)

export const mobileApi = {
  tasks: (
    request: MobileRequester,
    opts?: { status?: string; offset?: number; limit?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    params.set('status', opts?.status || 'open')
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 100))))
    return normalized(request, `/dashboard/mobile/tasks?${params.toString()}`, normalize.tasks, {
      signal: opts?.signal,
    })
  },
  taskDetail: (request: MobileRequester, taskId: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/tasks/${segment(taskId)}`,
      normalize.taskDetail,
      { signal },
    ),
  taskResolve: (request: MobileRequester, taskId: string, json: unknown) =>
    request(`/dashboard/mobile/tasks/${segment(taskId)}/resolve`, { method: 'POST', json }),
  onboarding: (
    request: MobileRequester,
    opts?: { search?: string; offset?: number; limit?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    const search = (opts?.search || '').trim()
    if (search) params.set('search', search)
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 100))))
    const qs = params.toString()
    return normalized(
      request,
      `/dashboard/mobile/onboarding${qs ? `?${qs}` : ''}`,
      normalize.onboarding,
      { signal: opts?.signal },
    )
  },
  onboardingDetail: (request: MobileRequester, employeeKey: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/onboarding/${segment(employeeKey)}`,
      normalize.onboardingDetail,
      { signal },
    ),
  onboardingReview: (request: MobileRequester, employeeKey: string, json: unknown) =>
    request<DecisionResponse>(`/dashboard/mobile/onboarding/${segment(employeeKey)}/review`, {
      method: 'POST',
      json,
    }),
  documents: (
    request: MobileRequester,
    opts?: { status?: string; q?: string; offset?: number; limit?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    params.set('status', opts?.status || 'needs_review')
    if (opts?.q) params.set('q', opts.q)
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 100))))
    return normalized(
      request,
      `/dashboard/mobile/documents?${params.toString()}`,
      normalize.documents,
      { signal: opts?.signal },
    )
  },
  documentDetail: (
    request: MobileRequester,
    employeeKey: string,
    documentType: string,
    signal?: AbortSignal,
  ) =>
    normalized(
      request,
      `/dashboard/mobile/documents/${segment(employeeKey)}/${segment(documentType)}`,
      normalize.documentDetail,
      { signal },
    ),
  documentReview: (
    request: MobileRequester,
    employeeKey: string,
    documentType: string,
    json: unknown,
  ) =>
    request(
      `/dashboard/mobile/documents/${segment(employeeKey)}/${segment(documentType)}/review`,
      { method: 'POST', json },
    ),
  attendance: (
    request: MobileRequester,
    opts?: {
      start_date?: string
      end_date?: string
      status?: string
      offset?: number
      limit?: number
      signal?: AbortSignal
    },
  ) => {
    const params = new URLSearchParams()
    if (opts?.start_date) params.set('start_date', opts.start_date)
    if (opts?.end_date) params.set('end_date', opts.end_date)
    if (opts?.status) params.set('status', opts.status)
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 200))))
    const qs = params.toString()
    return normalized(
      request,
      `/dashboard/mobile/attendance${qs ? `?${qs}` : ''}`,
      normalize.attendance,
      { signal: opts?.signal },
    )
  },
  attendanceDetail: (request: MobileRequester, attendanceId: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/attendance/${segment(attendanceId)}`,
      normalize.attendanceDetail,
      { signal },
    ),
  resolveAttendance: (request: MobileRequester, exceptionId: string, json: unknown) =>
    request<DecisionResponse>(`/dashboard/mobile/attendance/${segment(exceptionId)}/resolve`, {
      method: 'POST',
      json,
    }),
  shifts: (request: MobileRequester, date: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/shifts?date=${encodeURIComponent(date)}`,
      normalize.shifts,
      { signal },
    ),
  swaps: (
    request: MobileRequester,
    opts?: { status?: string; offset?: number; limit?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    if (opts?.status) params.set('status', opts.status)
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 200))))
    const qs = params.toString()
    return normalized(
      request,
      `/dashboard/mobile/shift-swaps${qs ? `?${qs}` : ''}`,
      normalize.swaps,
      { signal: opts?.signal },
    )
  },
  swapDetail: (request: MobileRequester, swapId: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/shift-swaps/${segment(swapId)}`,
      normalize.swapDetail,
      { signal },
    ),
  swapDecision: (request: MobileRequester, swapId: string, json: unknown) =>
    request<DecisionResponse>(`/dashboard/mobile/shift-swaps/${segment(swapId)}/decision`, {
      method: 'POST',
      json,
    }),
  employees: (
    request: MobileRequester,
    opts?: { search?: string; offset?: number; limit?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    const search = (opts?.search || '').trim()
    if (search) params.set('search', search)
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 100))))
    const qs = params.toString()
    return normalized(
      request,
      `/dashboard/mobile/employees${qs ? `?${qs}` : ''}`,
      normalize.employees,
      { signal: opts?.signal },
    )
  },
  employeeDetail: (request: MobileRequester, employeeKey: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/employees/${segment(employeeKey)}`,
      normalize.employeeDetail,
      { signal },
    ),
  alerts: (
    request: MobileRequester,
    opts?: { offset?: number; limit?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 100))))
    const qs = params.toString()
    return normalized(
      request,
      `/dashboard/mobile/delivery-alerts${qs ? `?${qs}` : ''}`,
      normalize.alerts,
      { signal: opts?.signal },
    )
  },
  candidates: (
    request: MobileRequester,
    opts?: { position?: string; q?: string; status?: string; limit?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    if (opts?.position) params.set('position', opts.position)
    if (opts?.q) params.set('q', opts.q)
    if (opts?.status) params.set('status', opts.status)
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 50))))
    const qs = params.toString()
    return normalized(
      request,
      `/dashboard/mobile/candidates${qs ? `?${qs}` : ''}`,
      normalize.candidates,
      { signal: opts?.signal },
    )
  },
  positions: (
    request: MobileRequester,
    opts?: { q?: string; status?: string; limit?: number; offset?: number; signal?: AbortSignal },
  ) => {
    const params = new URLSearchParams()
    params.set('status', opts?.status || 'open')
    if (opts?.q) params.set('q', opts.q)
    if (typeof opts?.limit === 'number') params.set('limit', String(Math.max(1, Math.min(opts.limit, 100))))
    if (typeof opts?.offset === 'number') params.set('offset', String(Math.max(0, opts.offset)))
    return normalized(
      request,
      `/dashboard/mobile/positions?${params.toString()}`,
      normalize.positions,
      { signal: opts?.signal },
    )
  },
  interviews: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/interviews', normalize.interviews, { signal }),
  interviewDetail: (request: MobileRequester, interviewId: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/interviews/${segment(interviewId)}`,
      normalize.interviewDetail,
      { signal },
    ),
  interviewNotes: (
    request: MobileRequester,
    interviewId: string,
    json: {
      notes: string
      status?: string | null
      generate_summary?: boolean
      expected_updated_at?: string | null
      expected_version?: number | null
    },
  ) =>
    request(`/dashboard/mobile/interviews/${segment(interviewId)}/notes`, { method: 'POST', json }),
}
