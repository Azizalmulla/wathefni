import type {
  ApplicationsResponse,
  AssessmentConfigResponse,
  AssessmentNormRecalculationResponse,
  AssessmentsResponse,
  DashboardAccess,
  DashboardAuthResponse,
  DashboardChatResponse,
  DashboardChatSession,
  DashboardChatStoredMessage,
  DashboardTeamResponse,
  DashboardTeamUser,
  EmployeeDocumentsResponse,
  ImportBatchesResponse,
  ImportBulkActionResponse,
  ImportIntakeResponse,
  ImportReviewResponse,
  ImportSettingsResponse,
  ImportUploadResponse,
  InterviewMutationResponse,
  InterviewsResponse,
  MailboxCheckNowResponse,
  MailboxConnection,
  MailboxListResponse,
  MutationResponse,
  NotificationsResponse,
  PosthireActionResult,
  PosthireAnalyticsResponse,
  PosthireComplianceResponse,
  PosthireAttendanceResponse,
  PosthireEmployee,
  PosthireEmployeesResponse,
  EmployeeProfileResponse,
  HrTasksResponse,
  OnboardingDetailResponse,
  OutboundNeedsFollowUpResponse,
  PosthireLeaveResponse,
  PosthireOnboardingResponse,
  PosthirePayrollResponse,
  PosthireShiftsResponse,
  PrehireReportsResponse,
  RankingResponse,
  SetupReadinessResponse,
  SummaryResponse,
} from '@/types'

type DashboardErrorDetail = {
  error?: string
  message?: string
  required_permission?: string
  role?: string
  company_code?: string
}

export class DashboardApiError extends Error {
  status: number
  code: string
  detail: DashboardErrorDetail | string | Record<string, unknown>

  constructor(status: number, detail: DashboardApiError['detail'], fallback: string) {
    const parsed = typeof detail === 'object' && detail && 'error' in detail ? detail as DashboardErrorDetail : null
    super(parsed?.message || parsed?.error || (typeof detail === 'string' ? detail : fallback))
    this.name = 'DashboardApiError'
    this.status = status
    this.code = parsed?.error || 'dashboard_request_failed'
    this.detail = detail
  }
}

async function request<T>(path: string, access: DashboardAccess, init: RequestInit = {}): Promise<T> {
  const headers = dashboardHeaders(access, init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const response = await fetch(path, { ...init, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload?.detail || payload
    throw new DashboardApiError(response.status, detail, 'Dashboard request failed.')
  }
  return payload as T
}

function dashboardHeaders(access: DashboardAccess, initHeaders?: HeadersInit) {
  const headers = new Headers(initHeaders)
  const token = access.token.trim()
  const hrPhone = access.hrPhone.trim()
  const companyCode = access.companyCode.trim().toUpperCase()
  if (!token) {
    throw new DashboardApiError(401, { error: 'dashboard_auth_failed', message: 'Dashboard token is required.' }, 'Dashboard token is required.')
  }
  if (!companyCode) {
    throw new DashboardApiError(400, { error: 'dashboard_company_required', message: 'Company code is required for dashboard access.' }, 'Company code is required for dashboard access.')
  }
  headers.set('Authorization', `Bearer ${token}`)
  headers.set('X-Company-Code', companyCode)
  if (hrPhone) headers.set('X-HR-Phone', hrPhone)
  return headers
}

export async function loginDashboard(access: DashboardAccess) {
  const response = await fetch('/dashboard/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: access.email || null,
      password: access.password || null,
      company_code: access.companyCode || null,
      token: access.token || null,
      hr_phone: access.hrPhone || null,
    }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not log in.')
  return payload as DashboardAuthResponse
}

export async function acceptDashboardInvite(body: { invite_token: string; name: string; password: string; phone?: string }) {
  const response = await fetch('/dashboard/team/invites/accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not accept invite.')
  return payload as DashboardAuthResponse
}

export function logoutDashboard(access: DashboardAccess) {
  return request<{ ok: boolean }>('/dashboard/auth/logout', access, { method: 'POST' })
}

export function getDashboardTeam(access: DashboardAccess) {
  return request<DashboardTeamResponse>('/dashboard/team', access)
}

export function inviteDashboardUser(access: DashboardAccess, body: { email: string; role: string; name?: string; phone?: string }) {
  return request<{ ok: boolean; user: DashboardTeamUser; invite_token?: string }>('/dashboard/team/invites', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateDashboardUser(access: DashboardAccess, userId: string, body: { role?: string; status?: string; name?: string; phone?: string }) {
  return request<{ ok: boolean; user: DashboardTeamUser }>(`/dashboard/team/users/${encodeURIComponent(userId)}`, access, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function linkDashboardWhatsApp(access: DashboardAccess, phone: string) {
  return request<{ ok: boolean; phone: string }>('/dashboard/team/whatsapp-link', access, {
    method: 'POST',
    body: JSON.stringify({ phone }),
  })
}

export function getSummary(access: DashboardAccess) {
  return request<SummaryResponse>('/dashboard/prehire/summary', access)
}

export function getSetupReadiness(access: DashboardAccess) {
  return request<SetupReadinessResponse>('/dashboard/setup/readiness', access)
}

export function getPrehireReports(access: DashboardAccess) {
  return request<PrehireReportsResponse>('/dashboard/prehire/reports', access)
}

export async function downloadPrehireReport(access: DashboardAccess, type: 'candidates' | 'roles' | 'assessments' | 'interviews' | 'followups') {
  const response = await fetch(`/dashboard/prehire/reports/export?type=${encodeURIComponent(type)}`, {
    headers: dashboardHeaders(access),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new DashboardApiError(response.status, detail, 'Could not download report.')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] || `wathefni-prehire-${type}.csv`
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function getDashboardChatSessions(access: DashboardAccess) {
  return request<{ sessions: DashboardChatSession[] }>('/dashboard/prehire/chat/sessions', access)
}

export function getDashboardChatSession(access: DashboardAccess, conversationId: string) {
  return request<{ session: DashboardChatSession; messages: DashboardChatStoredMessage[] }>(
    `/dashboard/prehire/chat/sessions/${encodeURIComponent(conversationId)}`,
    access,
  )
}

export function startDashboardChatSession(access: DashboardAccess, currentConversationId?: string) {
  return request<{ session: DashboardChatSession; cancelled_pending_confirmations?: number }>('/dashboard/prehire/chat/sessions/new', access, {
    method: 'POST',
    body: JSON.stringify({ current_conversation_id: currentConversationId || null }),
  })
}

export async function streamDashboardChat(
  access: DashboardAccess,
  body: { message: string; conversation_id?: string; page?: string; selected_app_key?: string },
  onEvent: (event: { type: 'typing' | 'delta' | 'done' | 'error'; text?: string; message?: DashboardChatResponse | string }) => void,
) {
  const response = await fetch('/dashboard/prehire/chat/stream', {
    method: 'POST',
    headers: dashboardHeaders(access, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new DashboardApiError(response.status, detail, 'Dashboard chat failed.')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    for (const event of events) {
      const line = event.split('\n').find((item) => item.startsWith('data: '))
      if (!line) continue
      onEvent(JSON.parse(line.slice(6)))
    }
  }
}

export function getApplications(
  access: DashboardAccess,
  params: {
    q?: string
    status?: string
    position?: string
    cv_status?: string
    assessment_status?: string
    interview_status?: string
    follow_up?: string
    activity_from?: string
    activity_to?: string
    sort?: string
    limit?: number
    offset?: number
  } = {},
) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 50))
  search.set('offset', String(params.offset || 0))
  if (params.q) search.set('q', params.q)
  if (params.status) search.set('status', params.status)
  if (params.position) search.set('position', params.position)
  if (params.cv_status) search.set('cv_status', params.cv_status)
  if (params.assessment_status) search.set('assessment_status', params.assessment_status)
  if (params.interview_status) search.set('interview_status', params.interview_status)
  if (params.follow_up) search.set('follow_up', params.follow_up)
  if (params.activity_from) search.set('activity_from', params.activity_from)
  if (params.activity_to) search.set('activity_to', params.activity_to)
  if (params.sort) search.set('sort', params.sort)
  return request<ApplicationsResponse>(`/dashboard/prehire/applications?${search.toString()}`, access)
}

export function getRanking(access: DashboardAccess, params: { q?: string; position?: string }) {
  const search = new URLSearchParams({ top_n: '10' })
  if (params.q) search.set('q', params.q)
  if (params.position) search.set('position', params.position)
  return request<RankingResponse>(`/dashboard/prehire/rank?${search.toString()}`, access)
}

export function getNotifications(access: DashboardAccess, params: { limit?: number } = {}) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 25))
  return request<NotificationsResponse>(`/dashboard/prehire/notifications?${search.toString()}`, access)
}

export function getAssessments(access: DashboardAccess, params: { status?: string; position?: string; limit?: number } = {}) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 100))
  if (params.status) search.set('status', params.status)
  if (params.position) search.set('position', params.position)
  return request<AssessmentsResponse>(`/dashboard/prehire/assessments?${search.toString()}`, access)
}

export function getInterviews(
  access: DashboardAccess,
  params: { status?: string; q?: string; role?: string; date?: string; interviewer?: string; limit?: number; offset?: number } = {},
) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 25))
  search.set('offset', String(params.offset || 0))
  if (params.status) search.set('status', params.status)
  if (params.q) search.set('q', params.q)
  if (params.role) search.set('role', params.role)
  if (params.date) search.set('date', params.date)
  if (params.interviewer) search.set('interviewer', params.interviewer)
  return request<InterviewsResponse>(`/dashboard/prehire/interviews?${search.toString()}`, access)
}

export function updateInterviewStatus(access: DashboardAccess, interviewId: string, status: string) {
  return request<InterviewMutationResponse>(`/dashboard/prehire/interviews/${encodeURIComponent(interviewId)}`, access, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function saveInterviewNotes(
  access: DashboardAccess,
  interviewId: string,
  body: { notes: string; transcript?: string; status?: string; generate_summary?: boolean },
) {
  return request<InterviewMutationResponse>(`/dashboard/prehire/interviews/${encodeURIComponent(interviewId)}/notes`, access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function retryVideoInterviewTranscripts(access: DashboardAccess, interviewId: string) {
  return request<InterviewMutationResponse>(`/dashboard/prehire/interviews/${encodeURIComponent(interviewId)}/transcripts/retry`, access, {
    method: 'POST',
  })
}

export async function previewVideoInterviewAnswer(access: DashboardAccess, videoUrl: string) {
  const response = await fetch(videoUrl, { headers: dashboardHeaders(access) })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new DashboardApiError(response.status, detail, 'Could not open the video answer.')
  }
  const blob = await response.blob()
  window.open(URL.createObjectURL(blob), '_blank', 'noopener,noreferrer')
}

export function getAssessmentConfig(access: DashboardAccess) {
  return request<AssessmentConfigResponse>('/dashboard/prehire/assessments/config', access)
}

export function recalculateAssessmentNorms(access: DashboardAccess, persist = true) {
  const search = new URLSearchParams({ persist: String(persist), minimum_sample: '200' })
  return request<AssessmentNormRecalculationResponse>(`/dashboard/prehire/assessments/norms/recalculate?${search.toString()}`, access, {
    method: 'POST',
  })
}

export async function previewAssessmentReport(access: DashboardAccess, attemptId: string) {
  const previewWindow = window.open('about:blank', '_blank')
  previewWindow?.document.write(
    '<!doctype html><title>Opening assessment report...</title><body style="font-family: system-ui, sans-serif; padding: 24px;">Opening assessment report...</body>',
  )
  const response = await fetch(`/dashboard/prehire/assessments/${encodeURIComponent(attemptId)}/report`, {
    headers: dashboardHeaders(access),
  })
  if (!response.ok) {
    previewWindow?.close()
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  openPreviewUrl(url, previewWindow)
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export async function previewCandidateCv(access: DashboardAccess, appKey: string) {
  const previewWindow = window.open('about:blank', '_blank')
  previewWindow?.document.write(
    '<!doctype html><title>Opening CV...</title><body style="font-family: system-ui, sans-serif; padding: 24px;">Opening CV...</body>',
  )
  const response = await fetch(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/cv/preview`, {
    headers: dashboardHeaders(access),
  })
  const contentType = response.headers.get('Content-Type') || ''
  if (!response.ok) {
    previewWindow?.close()
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (contentType.includes('application/json')) {
    const payload = (await response.json()) as { url?: string }
    if (!payload.url) {
      previewWindow?.close()
      throw new Error('CV preview URL was not returned.')
    }
    openPreviewUrl(payload.url, previewWindow)
    return
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  openPreviewUrl(url, previewWindow)
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

function openPreviewUrl(url: string, previewWindow: Window | null) {
  if (previewWindow) {
    previewWindow.location.assign(url)
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

export function shortlistCandidate(access: DashboardAccess, appKey: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/shortlist`, access, {
    method: 'POST',
  })
}

export function hireCandidate(access: DashboardAccess, appKey: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/hire`, access, {
    method: 'POST',
  })
}

export function rejectCandidate(access: DashboardAccess, appKey: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/reject`, access, {
    method: 'POST',
  })
}

export function notifyCandidate(access: DashboardAccess, appKey: string, message?: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/notify`, access, {
    method: 'POST',
    body: JSON.stringify({ message: message || null, account_id: 'default' }),
  })
}

export function sendAssessment(access: DashboardAccess, appKey: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/assessment`, access, {
    method: 'POST',
    body: JSON.stringify({ account_id: 'default' }),
  })
}

export function sendVideoInterview(access: DashboardAccess, appKey: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/video-interview`, access, {
    method: 'POST',
    body: JSON.stringify({ account_id: 'default', send_invite: true, response_mode: 'single_video' }),
  })
}

export async function uploadBulkCvImport(
  access: DashboardAccess,
  body: { files: File[]; metadataFile?: File | null; positionCode?: string; positionTitle?: string; source?: string },
) {
  const form = new FormData()
  for (const file of body.files) form.append('files', file)
  if (body.metadataFile) form.append('metadata_file', body.metadataFile)
  if (body.positionCode) form.append('position_code', body.positionCode)
  if (body.positionTitle) form.append('position_title', body.positionTitle)
  if (body.source) form.append('source', body.source)
  // Let the browser set the multipart boundary — do not set Content-Type here.
  const headers = dashboardHeaders(access)
  const response = await fetch('/dashboard/prehire/import/upload', { method: 'POST', headers, body: form })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not import CVs.')
  return payload as ImportUploadResponse
}

export function getImportBatches(access: DashboardAccess, limit = 10) {
  return request<ImportBatchesResponse>(`/dashboard/prehire/import/batches?limit=${limit}`, access)
}

export function getImportReview(access: DashboardAccess, params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 50))
  search.set('offset', String(params.offset || 0))
  return request<ImportReviewResponse>(`/dashboard/prehire/import/review?${search.toString()}`, access)
}

export function assignImportRole(
  access: DashboardAccess,
  body: { app_key: string; position_code?: string; position_title?: string; promote?: boolean },
) {
  return request<{ ok: boolean; app_key: string; status: string; position_code?: string | null }>(
    '/dashboard/prehire/import/items/assign',
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getImportIntake(access: DashboardAccess, limit = 500) {
  return request<ImportIntakeResponse>(`/dashboard/prehire/import/intake?limit=${limit}`, access)
}

export function bulkImportAction(
  access: DashboardAccess,
  body: { action: 'confirm' | 'assign' | 'archive'; app_keys: string[]; position_code?: string; position_title?: string },
) {
  return request<ImportBulkActionResponse>('/dashboard/prehire/import/items/bulk', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getImportSettings(access: DashboardAccess) {
  return request<ImportSettingsResponse>('/dashboard/prehire/import/settings', access)
}

export function updateImportSettings(access: DashboardAccess, autoAdmit: boolean) {
  return request<ImportSettingsResponse>('/dashboard/prehire/import/settings', access, {
    method: 'PUT',
    body: JSON.stringify({ auto_admit_explicit_imports: autoAdmit }),
  })
}

export async function downloadImportReport(access: DashboardAccess, batchId: string) {
  const response = await fetch(`/dashboard/prehire/import/batches/${encodeURIComponent(batchId)}/report.csv`, {
    headers: dashboardHeaders(access),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not download the import report.')
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `import-${batchId}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}

export function getMailboxConnections(access: DashboardAccess) {
  return request<MailboxListResponse>('/dashboard/prehire/integrations/mailbox', access)
}

export function connectMailbox(access: DashboardAccess, body: { label_filter?: string } = {}) {
  return request<{ ok: boolean; mailbox_id: string; authorize_url: string }>('/dashboard/prehire/integrations/mailbox/connect', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getMailboxLabels(access: DashboardAccess, mailboxId: string) {
  return request<{ company_code: string; labels: string[] }>(`/dashboard/prehire/integrations/mailbox/${encodeURIComponent(mailboxId)}/labels`, access)
}

export function updateMailbox(access: DashboardAccess, mailboxId: string, body: { label_filter?: string | null; auto_import?: boolean }) {
  return request<{ ok: boolean; connection: MailboxConnection }>(`/dashboard/prehire/integrations/mailbox/${encodeURIComponent(mailboxId)}`, access, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function checkMailboxNow(access: DashboardAccess, mailboxId: string) {
  return request<MailboxCheckNowResponse>(`/dashboard/prehire/integrations/mailbox/${encodeURIComponent(mailboxId)}/check-now`, access, {
    method: 'POST',
  })
}

export function disconnectMailbox(access: DashboardAccess, mailboxId: string) {
  return request<{ ok: boolean }>(`/dashboard/prehire/integrations/mailbox/${encodeURIComponent(mailboxId)}`, access, {
    method: 'DELETE',
  })
}

// --- Post-hire modules ---------------------------------------------------
// Every native post-hire action routes through one endpoint that runs the SAME
// action registry as the Wathefni Assistant (RBAC, preflight, confirmation, audit).
// Sensitive actions return { confirmation } on the first call; re-send the same
// action_type + args to execute.

export function runPosthireAction(access: DashboardAccess, body: { action_type: string; args?: Record<string, unknown> }) {
  return request<PosthireActionResult>('/dashboard/posthire/action', access, {
    method: 'POST',
    body: JSON.stringify({ action_type: body.action_type, args: body.args || {} }),
  })
}

export function getPosthireEmployees(access: DashboardAccess) {
  return request<PosthireEmployeesResponse>('/dashboard/posthire/employees', access)
}

// Add a single employee directly to the workforce (no pre-hiring pipeline). The
// server returns { status: 'exists' } with ok:false when the phone already maps
// to an employee, so the caller shows a friendly message instead of throwing.
export function createEmployee(
  access: DashboardAccess,
  body: { name: string; phone: string; email?: string; position_title?: string; department?: string; start_date?: string },
) {
  return request<{ ok: boolean; status: 'created' | 'exists'; employee: PosthireEmployee | null; message?: string }>(
    '/dashboard/posthire/employees',
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export type EmployeeImportRow = { row: number; name: string; reason?: string }
export type EmployeeImportResult = {
  ok: boolean
  dry_run: boolean
  total_rows: number
  counts: { created: number; skipped: number; needs_review: number; failed: number }
  results: {
    created: EmployeeImportRow[]
    skipped: EmployeeImportRow[]
    needs_review: EmployeeImportRow[]
    failed: EmployeeImportRow[]
  }
}

// Bulk import employees from CSV/XLSX. The browser sets the multipart boundary,
// so we must not set Content-Type here. dryRun previews the result without writing.
export async function importEmployees(access: DashboardAccess, body: { file: File; dryRun?: boolean }) {
  const form = new FormData()
  form.append('file', body.file)
  form.append('dry_run', body.dryRun ? 'true' : 'false')
  const response = await fetch('/dashboard/posthire/employees/import', {
    method: 'POST',
    headers: dashboardHeaders(access),
    body: form,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not import employees.')
  return payload as EmployeeImportResult
}

export function getEmployeeProfile(access: DashboardAccess, employeeKey: string) {
  return request<EmployeeProfileResponse>(`/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}`, access)
}

export function getPosthireOnboarding(access: DashboardAccess) {
  return request<PosthireOnboardingResponse>('/dashboard/posthire/onboarding', access)
}

export function getOnboardingDetail(access: DashboardAccess, employeeKey: string) {
  return request<OnboardingDetailResponse>(`/dashboard/posthire/onboarding/${encodeURIComponent(employeeKey)}`, access)
}

export function getPosthireAttendance(access: DashboardAccess) {
  return request<PosthireAttendanceResponse>('/dashboard/posthire/attendance', access)
}

export function getPosthireLeave(access: DashboardAccess) {
  return request<PosthireLeaveResponse>('/dashboard/posthire/leave', access)
}

export function getPosthireShifts(access: DashboardAccess, week = 0) {
  const qs = week ? `?week=${encodeURIComponent(String(week))}` : ''
  return request<PosthireShiftsResponse>(`/dashboard/posthire/shifts${qs}`, access)
}

export function cancelShift(access: DashboardAccess, shiftId: string) {
  return request<{ ok: boolean; status: string; message?: string; notified?: boolean }>(
    `/dashboard/posthire/shifts/${encodeURIComponent(shiftId)}/cancel`,
    access,
    { method: 'POST' },
  )
}

export function rescheduleShift(
  access: DashboardAccess,
  shiftId: string,
  body: { shift_date: string; start_time: string; end_time: string },
) {
  return request<{ ok: boolean; status: string; message?: string; notified?: boolean }>(
    `/dashboard/posthire/shifts/${encodeURIComponent(shiftId)}/reschedule`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getPosthirePayroll(access: DashboardAccess) {
  return request<PosthirePayrollResponse>('/dashboard/posthire/payroll', access)
}

export function getPosthireAnalytics(access: DashboardAccess) {
  return request<PosthireAnalyticsResponse>('/dashboard/posthire/analytics', access)
}

export function getPosthireCompliance(access: DashboardAccess) {
  return request<PosthireComplianceResponse>('/dashboard/posthire/compliance', access)
}

export function getEmployeeDocuments(access: DashboardAccess, employeeKey: string) {
  return request<EmployeeDocumentsResponse>(`/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/documents`, access)
}

// Upload (or replace) an employee onboarding document for a checklist item. The
// browser sets the multipart boundary, so we must not set Content-Type here.
export async function uploadEmployeeDocument(
  access: DashboardAccess,
  employeeKey: string,
  body: { file: File; itemId: string },
) {
  const form = new FormData()
  form.append('file', body.file)
  form.append('item_id', body.itemId)
  const response = await fetch(`/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/documents`, {
    method: 'POST',
    headers: dashboardHeaders(access),
    body: form,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not upload the document.')
  return payload as { ok: boolean; file_id: string | null; item_id: string; storage_status?: string }
}

// Open or download an employee document. Auth is header-based, so we fetch the
// proxied file with credentials and hand the browser a blob URL (local files) or
// follow the access-controlled external URL (e.g. Google Drive). No raw storage
// URL is ever exposed in the DOM.
export async function openEmployeeDocument(
  access: DashboardAccess,
  fileId: string,
  options: { disposition?: 'inline' | 'attachment'; filename?: string } = {},
) {
  const disposition = options.disposition || 'inline'
  const previewWindow = disposition === 'inline' ? window.open('about:blank', '_blank') : null
  previewWindow?.document.write(
    '<!doctype html><title>Opening document...</title><body style="font-family: system-ui, sans-serif; padding: 24px;">Opening document...</body>',
  )
  const response = await fetch(`/dashboard/posthire/documents/${encodeURIComponent(fileId)}?disposition=${disposition}`, {
    headers: dashboardHeaders(access),
  })
  const contentType = response.headers.get('Content-Type') || ''
  if (!response.ok) {
    previewWindow?.close()
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new DashboardApiError(response.status, detail, 'Could not open the document.')
  }
  if (contentType.includes('application/json')) {
    const payload = (await response.json()) as { url?: string }
    if (!payload.url) {
      previewWindow?.close()
      throw new Error('Document URL was not returned.')
    }
    openPreviewUrl(payload.url, previewWindow)
    return
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  if (disposition === 'attachment') {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = options.filename || 'document'
    anchor.click()
  } else {
    openPreviewUrl(url, previewWindow)
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

// --- HR tasks & delivery follow-up (outbound layer, Phase B) --------------
// "What should HR do next?" surface for the shared outbound delivery layer.
// Reads always succeed and simply return empty until flows are wired (Phase C+).

export function getHrTasks(access: DashboardAccess, status = 'open') {
  return request<HrTasksResponse>(`/dashboard/hr-tasks?status=${encodeURIComponent(status)}`, access)
}

export function resolveHrTask(access: DashboardAccess, taskId: string, status: 'done' | 'dismissed' = 'done') {
  return request<{ ok: boolean; task: { task_id: string; status: string } }>(
    `/dashboard/hr-tasks/${encodeURIComponent(taskId)}/resolve`,
    access,
    { method: 'POST', body: JSON.stringify({ status }) },
  )
}

export function getOutboundNeedsFollowUp(access: DashboardAccess) {
  return request<OutboundNeedsFollowUpResponse>('/dashboard/outbound/needs-follow-up', access)
}

export function generateCandidateEvaluation(access: DashboardAccess, appKey: string, force = false) {
  const search = new URLSearchParams()
  if (force) search.set('force', 'true')
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/evaluation${suffix}`, access, {
    method: 'POST',
  })
}
