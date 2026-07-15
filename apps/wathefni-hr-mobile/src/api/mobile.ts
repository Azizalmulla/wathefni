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
  tasks: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/tasks', normalize.tasks, { signal }),
  onboarding: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/onboarding', normalize.onboarding, { signal }),
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
  documents: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/documents', normalize.documents, { signal }),
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
  attendance: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/attendance', normalize.attendance, { signal }),
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
  swaps: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/shift-swaps', normalize.swaps, { signal }),
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
  employees: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/employees', normalize.employees, { signal }),
  employeeDetail: (request: MobileRequester, employeeKey: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/employees/${segment(employeeKey)}`,
      normalize.employeeDetail,
      { signal },
    ),
  alerts: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/delivery-alerts', normalize.alerts, { signal }),
  candidates: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/candidates', normalize.candidates, { signal }),
  interviews: (request: MobileRequester, signal?: AbortSignal) =>
    normalized(request, '/dashboard/mobile/interviews', normalize.interviews, { signal }),
  interviewDetail: (request: MobileRequester, interviewId: string, signal?: AbortSignal) =>
    normalized(
      request,
      `/dashboard/mobile/interviews/${segment(interviewId)}`,
      normalize.interviewDetail,
      { signal },
    ),
  interviewNotes: (request: MobileRequester, interviewId: string, json: unknown) =>
    request(`/dashboard/mobile/interviews/${segment(interviewId)}/notes`, { method: 'POST', json }),
}
