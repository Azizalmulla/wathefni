import type {
  ActivityFilters,
  ActivityResponse,
  ApplicationSummary,
  ApplicationsResponse,
  AssessmentAuthoringDraftsResponse,
  AssessmentAttempt,
  AssessmentConfigResponse,
  AssessmentNormRecalculationResponse,
  AssessmentsResponse,
  AttendanceImportBatchesResponse,
  AttendanceImportCommitResponse,
  AttendanceImportMapping,
  AttendanceImportMappingsResponse,
  AttendanceImportPreview,
  AttendanceImportReverseResponse,
  DashboardAccess,
  DashboardAuthResponse,
  DashboardBootstrapResponse,
  AssistantCapabilitiesResponse,
  DashboardChatResponse,
  DashboardChatSession,
  DashboardChatStoredMessage,
  DashboardTeamResponse,
  DashboardTeamUser,
  EmailSendingActionResponse,
  EmailSendingSettingsResponse,
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
  PayrollExportDetail,
  PosthireShiftsResponse,
  PositionsResponse,
  PositionSummary,
  PrehireNextAction,
  PrehireReportsResponse,
  PrehireWorkQueueResponse,
  Product2AuthoringStatus,
  Product2Blueprint,
  Product2BlueprintInput,
  Product2BlueprintsResponse,
  Product2Draft,
  Product2DraftContent,
  Product2DraftEvidenceResponse,
  Product2Locale,
  Product2RunResponse,
  RankingResponse,
  SetupReadinessResponse,
  SummaryResponse,
  EssOwnViewResponse,
  EssRequestsResponse,
  LifecyclePendingResponse,
  MigrationBatchesResponse,
  OrgHistoryResponse,
  OrgUnitsResponse,
  RemediationQueueResponse,
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

export type TeamPerson = {
  user_id: string
  name: string
  role: string
  role_label?: string
  status?: string
  label?: string
  purpose?: string
}

export type TeamPeopleResponse = {
  company_code: string
  purpose: string
  q?: string | null
  people: TeamPerson[]
  unassigned_allowed?: boolean
  directory_view?: string
}

export function getTeamPeople(
  access: DashboardAccess,
  params: { purpose: string; q?: string; limit?: number } = { purpose: 'recruiter' },
) {
  const search = new URLSearchParams()
  search.set('purpose', params.purpose || 'recruiter')
  if (params.q) search.set('q', params.q)
  if (typeof params.limit === 'number') search.set('limit', String(params.limit))
  return request<TeamPeopleResponse>(`/dashboard/team/people?${search.toString()}`, access)
}

function activitySearchParams(filters: ActivityFilters = {}): URLSearchParams {
  const search = new URLSearchParams()
  if (filters.start_date) search.set('start_date', filters.start_date)
  if (filters.end_date) search.set('end_date', filters.end_date)
  if (filters.actor) search.set('actor', filters.actor)
  if (filters.category && filters.category !== 'all') search.set('category', filters.category)
  if (filters.action_type) search.set('action_type', filters.action_type)
  if (filters.q) search.set('q', filters.q)
  if (typeof filters.limit === 'number') search.set('limit', String(filters.limit))
  if (typeof filters.offset === 'number') search.set('offset', String(filters.offset))
  return search
}

export function getCompanyActivity(access: DashboardAccess, filters: ActivityFilters = {}) {
  const qs = activitySearchParams(filters).toString()
  return request<ActivityResponse>(`/dashboard/activity${qs ? `?${qs}` : ''}`, access)
}

export async function downloadCompanyActivityCsv(access: DashboardAccess, filters: ActivityFilters = {}) {
  const search = activitySearchParams({ ...filters, limit: undefined, offset: undefined })
  search.set('format', 'csv')
  const response = await fetch(`/dashboard/activity?${search.toString()}`, { headers: dashboardHeaders(access) })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not download the activity log.')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] || 'activity.csv'
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
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

export function getSummary(access: DashboardAccess, init?: RequestInit) {
  return request<SummaryResponse>('/dashboard/prehire/summary', access, init)
}

export function getPrehireWorkQueue(
  access: DashboardAccess,
  params: { limit?: number; cursor?: string; scope?: 'mine' | 'company' | string } = {},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 25))
  if (params.cursor) search.set('cursor', params.cursor)
  if (params.scope) search.set('scope', params.scope)
  return request<PrehireWorkQueueResponse>(`/dashboard/prehire/overview/work-queue?${search.toString()}`, access, init)
}

export function getPrehireNextAction(access: DashboardAccess, params: { scope?: 'mine' | 'company' | string } = {}) {
  const search = new URLSearchParams()
  if (params.scope) search.set('scope', params.scope)
  const qs = search.toString()
  return request<PrehireNextAction>(`/dashboard/prehire/overview/next-action${qs ? `?${qs}` : ''}`, access)
}

export function getDashboardBootstrap(access: DashboardAccess) {
  return request<DashboardBootstrapResponse>('/dashboard/bootstrap', access)
}

export function getPrehireVisibilityPolicy(access: DashboardAccess) {
  return request<{
    company_code: string
    prehire_visibility_policy: string
    allowed_policies: string[]
    prehire_visibility_scope?: string
    prehire_visibility_summary_company_wide?: boolean
    prehire_visibility_oversight?: boolean
    version?: number
    updated_at?: string | null
    last_updated_by?: string | null
  }>('/dashboard/prehire/visibility-policy', access)
}

export function putPrehireVisibilityPolicy(
  access: DashboardAccess,
  policy: string,
  concurrency?: { expected_version?: number | null; expected_updated_at?: string | null },
) {
  return request<{
    ok: boolean
    prehire_visibility_policy: string
    previous?: string
    version?: number
    updated_at?: string | null
    last_updated_by?: string | null
  }>('/dashboard/prehire/visibility-policy', access, {
    method: 'PUT',
    body: JSON.stringify({
      prehire_visibility_policy: policy,
      expected_version: concurrency?.expected_version ?? undefined,
      expected_updated_at: concurrency?.expected_updated_at ?? undefined,
    }),
  })
}

export function getPrehirePositions(
  access: DashboardAccess,
  opts?: {
    offset?: number
    limit?: number
    search?: string
    status?: string
    department?: string
    location?: string
    recruiter_user_id?: string
    hiring_manager_user_id?: string
    deadline?: string
    has_remaining_vacancies?: boolean
    cursor?: string
  },
  init?: RequestInit,
) {
  const params = new URLSearchParams()
  if (opts?.offset) params.set('offset', String(opts.offset))
  if (opts?.limit) params.set('limit', String(opts.limit))
  if (opts?.search) params.set('search', opts.search)
  if (opts?.status) params.set('status', opts.status)
  if (opts?.department) params.set('department', opts.department)
  if (opts?.location) params.set('location', opts.location)
  if (opts?.recruiter_user_id) params.set('recruiter_user_id', opts.recruiter_user_id)
  if (opts?.hiring_manager_user_id) params.set('hiring_manager_user_id', opts.hiring_manager_user_id)
  if (opts?.deadline) params.set('deadline', opts.deadline)
  if (opts?.has_remaining_vacancies) params.set('has_remaining_vacancies', 'true')
  if (opts?.cursor) params.set('cursor', opts.cursor)
  const qs = params.toString()
  return request<PositionsResponse>(`/dashboard/prehire/positions${qs ? `?${qs}` : ''}`, access, init)
}

export type JobUpsertPayload = {
  title?: string
  title_en?: string
  title_ar?: string | null
  visibility?: 'public' | 'share_only' | 'internal'
  short_summary_en?: string | null
  short_summary_ar?: string | null
  benefits_en?: string | null
  benefits_ar?: string | null
  approve_content_en?: boolean
  approve_content_ar?: boolean
  position_code?: string
  description?: string
  description_en?: string
  description_ar?: string | null
  requirements?: string[]
  requirements_en?: string[]
  requirements_ar?: string[]
  department?: string | null
  location?: string | null
  employment_type?: string | null
  work_arrangement?: string | null
  contract_type?: string | null
  salary_min?: number | null
  salary_max?: number | null
  currency?: string | null
  salary_visibility?: string | null
  vacancies?: number | null
  application_deadline?: string | null
  expected_start_date?: string | null
  hiring_manager_user_id?: string | null
  recruiter_user_id?: string | null
  save_as_draft?: boolean
  expected_updated_at?: string | null
  expected_version?: number | null
}

export function createPrehirePosition(access: DashboardAccess, payload: JobUpsertPayload) {
  return request<{ ok: boolean; position: PositionSummary }>('/dashboard/prehire/positions', access, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updatePrehirePosition(access: DashboardAccess, positionCode: string, payload: JobUpsertPayload) {
  return request<{ ok: boolean; position: PositionSummary }>(
    `/dashboard/prehire/positions/${encodeURIComponent(positionCode)}`,
    access,
    { method: 'PATCH', body: JSON.stringify(payload) },
  )
}

// Lifecycle transition only. Content edits must use updatePrehirePosition and
// never change status. Existing candidates in the pipeline are never affected.
export function setPositionStatus(
  access: DashboardAccess,
  positionCode: string,
  status: 'draft' | 'open' | 'paused' | 'closed',
  opts?: { expected_updated_at?: string | null; expected_version?: number | null },
) {
  return request<{ ok: boolean; position: PositionSummary }>(
    `/dashboard/prehire/positions/${encodeURIComponent(positionCode)}/status`,
    access,
    {
      method: 'POST',
      body: JSON.stringify({
        status,
        expected_updated_at: opts?.expected_updated_at ?? undefined,
        expected_version: opts?.expected_version ?? undefined,
      }),
    },
  )
}

export function getSetupReadiness(access: DashboardAccess) {
  return request<SetupReadinessResponse>('/dashboard/setup/readiness', access)
}

export function getPrehireReports(
  access: DashboardAccess,
  init?: RequestInit & { locale?: string },
) {
  const locale = String(init?.locale || 'en')
  const headers = init?.headers
  const signal = init?.signal
  return request<PrehireReportsResponse>(
    `/dashboard/prehire/reports?locale=${encodeURIComponent(locale)}`,
    access,
    { headers, signal },
  )
}

export async function downloadPrehireReport(access: DashboardAccess, type: 'candidates' | 'roles' | 'assessments' | 'interviews' | 'followups' | 'followup_delivery_history') {
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

export function getAssistantCapabilities(access: DashboardAccess, locale: 'en' | 'ar' = 'en') {
  return request<AssistantCapabilitiesResponse>(
    `/dashboard/prehire/assistant/capabilities?locale=${encodeURIComponent(locale)}`,
    access,
  )
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
  onEvent: (event: {
    type: 'typing' | 'delta' | 'done' | 'error' | 'progress'
    text?: string
    phase?: string
    tool?: string
    status?: string
    message?: DashboardChatResponse | string
  }) => void,
  options?: { signal?: AbortSignal },
) {
  const response = await fetch('/dashboard/prehire/chat/stream', {
    method: 'POST',
    headers: dashboardHeaders(access, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    signal: options?.signal,
  })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new DashboardApiError(response.status, detail, 'Dashboard chat failed.')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      if (options?.signal?.aborted) {
        await reader.cancel().catch(() => undefined)
        throw new DOMException('Aborted', 'AbortError')
      }
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
  } catch (error) {
    if (options?.signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) {
      throw new DOMException('Aborted', 'AbortError')
    }
    throw error
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
    review_status?: string
    overview_cohort?: string
    assessment_cohort?: string
    activity_from?: string
    activity_to?: string
    sort?: string
    view?: string
    source_channel?: string
    recruiter_owner?: string
    cv_processing_state?: string
    received_from?: string
    received_to?: string
    has_grounded_email?: string
    has_grounded_phone?: string
    fact_completeness?: string
    department_intake_tag?: string
    classification_career_area?: string
    classification_likely_role?: string
    classification_skill?: string
    classification_industry?: string
    classification_seniority?: string
    classification_experience_band?: string
    classification_node_ids?: string
    classification_authority?: string
    classification_confidence?: string
    classification_include_medium_ai?: string
    limit?: number
    offset?: number
  } = {},
  init?: RequestInit,
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
  if (params.review_status) search.set('review_status', params.review_status)
  const cohort = params.overview_cohort || params.assessment_cohort
  if (cohort) search.set('overview_cohort', cohort)
  if (params.activity_from) search.set('activity_from', params.activity_from)
  if (params.activity_to) search.set('activity_to', params.activity_to)
  if (params.sort) search.set('sort', params.sort)
  if (params.view) search.set('view', params.view)
  if (params.source_channel) search.set('source_channel', params.source_channel)
  if (params.recruiter_owner) search.set('recruiter_owner', params.recruiter_owner)
  if (params.cv_processing_state) search.set('cv_processing_state', params.cv_processing_state)
  if (params.received_from) search.set('received_from', params.received_from)
  if (params.received_to) search.set('received_to', params.received_to)
  if (params.has_grounded_email) search.set('has_grounded_email', params.has_grounded_email)
  if (params.has_grounded_phone) search.set('has_grounded_phone', params.has_grounded_phone)
  if (params.fact_completeness) search.set('fact_completeness', params.fact_completeness)
  if (params.department_intake_tag) search.set('department_intake_tag', params.department_intake_tag)
  if (params.classification_career_area) search.set('classification_career_area', params.classification_career_area)
  if (params.classification_likely_role) search.set('classification_likely_role', params.classification_likely_role)
  if (params.classification_skill) search.set('classification_skill', params.classification_skill)
  if (params.classification_industry) search.set('classification_industry', params.classification_industry)
  if (params.classification_seniority) search.set('classification_seniority', params.classification_seniority)
  if (params.classification_experience_band) {
    search.set('classification_experience_band', params.classification_experience_band)
  }
  if (params.classification_node_ids) search.set('classification_node_ids', params.classification_node_ids)
  if (params.classification_authority) search.set('classification_authority', params.classification_authority)
  if (params.classification_confidence) search.set('classification_confidence', params.classification_confidence)
  if (params.classification_include_medium_ai) {
    search.set('classification_include_medium_ai', params.classification_include_medium_ai)
  }
  return request<ApplicationsResponse>(`/dashboard/prehire/applications?${search.toString()}`, access, init)
}

export function getCandidateProfile(access: DashboardAccess, appKey: string, init?: RequestInit) {
  return request<import('@/types').CandidateProfileResponse>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/profile`,
    access,
    init,
  )
}

export function getCandidatePersonProfile(access: DashboardAccess, appKey: string, init?: RequestInit) {
  return request<import('@/types').CandidatePersonProfileResponse>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/person-profile`,
    access,
    init,
  )
}

export function addCandidateToJobViaPersonProfile(
  access: DashboardAccess,
  appKey: string,
  body: { position_code: string; position_title?: string; confirm: boolean },
) {
  return request<{ ok: boolean; app_key: string; status: string; position_code?: string | null }>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/person-profile/add-to-job`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function reviewCandidateFact(
  access: DashboardAccess,
  appKey: string,
  body: {
    action: 'confirm' | 'correct' | 'reject' | 'add' | 'supersede'
    fact_path: string
    new_value?: unknown
    previous_value?: unknown
    note?: string
    evidence_refs?: unknown[]
    supersedes_event_id?: string
    preview?: boolean
    confirm?: boolean
  },
) {
  return request<{ ok: boolean; preview?: boolean; event?: Record<string, unknown>; message?: string }>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/facts/review`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getUnifiedCandidatesFeature(access: DashboardAccess) {
  return request<{
    ok: boolean
    flag: string
    master_enabled: boolean
    allowed_tenants: string[]
    company_code: string | null
    enabled_for_company: boolean
  }>('/dashboard/prehire/candidates/feature', access)
}

export function getTalentPoolClassificationFeature(access: DashboardAccess) {
  return request<{
    ok: boolean
    master_enabled: boolean
    allowed_tenants: string[]
    company_code: string | null
    enabled_for_company: boolean
    schema_enabled: boolean
    manual_enabled: boolean
    workers_enabled: boolean
    ui_enabled: boolean
    coupled_to_unified_candidates: boolean
  }>('/dashboard/prehire/classification/feature', access)
}

export function getTalentPoolClassificationTaxonomy(access: DashboardAccess) {
  return request<{
    ok: boolean
    taxonomy_version?: string
    nodes?: Array<Record<string, unknown>>
    tenant_nodes?: Array<Record<string, unknown>>
    dimensions?: Array<{
      dimension: string
      node_type: string
      nodes: Array<{
        node_id: string
        node_type?: string
        dimension?: string
        label_en?: string
        label_ar?: string
        parent_ids?: string[]
        status?: string
        scope?: string
        broad?: boolean
      }>
    }>
    authorities?: string[]
    confidence_states?: string[]
  }>('/dashboard/prehire/classification/taxonomy', access)
}

export function getApplicationClassification(
  access: DashboardAccess,
  appKey: string,
  params: { runs_offset?: number; runs_limit?: number } = {},
) {
  const search = new URLSearchParams()
  if (params.runs_offset != null) search.set('runs_offset', String(params.runs_offset))
  if (params.runs_limit != null) search.set('runs_limit', String(params.runs_limit))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request<{ ok: boolean; classification: Record<string, unknown> }>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/classification${suffix}`,
    access,
  )
}

export function reviewApplicationClassification(
  access: DashboardAccess,
  appKey: string,
  body: Record<string, unknown>,
) {
  return request<{ ok: boolean; preview?: boolean; event?: Record<string, unknown>; message?: string }>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/classification/review`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getCandidateSavedViews(access: DashboardAccess) {
  return request<{ company_code: string; views: import('@/types').CandidateSavedView[] }>(
    '/dashboard/prehire/candidates/saved-views',
    access,
  )
}

export function saveCandidateSavedView(
  access: DashboardAccess,
  body: { name: string; filters: Record<string, unknown>; view_id?: string },
) {
  return request<{ ok: boolean; view: import('@/types').CandidateSavedView }>(
    '/dashboard/prehire/candidates/saved-views',
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function deleteCandidateSavedView(access: DashboardAccess, viewId: string) {
  return request<{ ok: boolean; view_id: string }>(
    `/dashboard/prehire/candidates/saved-views/${encodeURIComponent(viewId)}`,
    access,
    { method: 'DELETE' },
  )
}

export function getRanking(
  access: DashboardAccess,
  params: { q?: string; position?: string; mode?: 'current' | 'latest' | 'run'; force?: boolean; locale?: string } = {},
) {
  const search = new URLSearchParams({ top_n: '10' })
  if (params.q) search.set('q', params.q)
  if (params.position) search.set('position', params.position)
  if (params.mode) search.set('mode', params.mode)
  if (params.force) search.set('force', 'true')
  if (params.locale) search.set('locale', params.locale)
  return request<RankingResponse>(`/dashboard/prehire/rank?${search.toString()}`, access)
}

export function getNotifications(
  access: DashboardAccess,
  params: { limit?: number; scope?: 'mine' | 'company' | string } = {},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 25))
  if (params.scope) search.set('scope', params.scope)
  return request<NotificationsResponse>(`/dashboard/prehire/notifications?${search.toString()}`, access, init)
}

export function getAssessments(
  access: DashboardAccess,
  params: {
    status?: string
    position?: string
    limit?: number
    offset?: number
    needs_review?: boolean
  } = {},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 100))
  search.set('offset', String(params.offset || 0))
  if (params.status) search.set('status', params.status)
  if (params.position) search.set('position', params.position)
  if (params.needs_review) search.set('needs_review', 'true')
  return request<AssessmentsResponse>(`/dashboard/prehire/assessments?${search.toString()}`, access, init)
}

export function getInterviews(
  access: DashboardAccess,
  params: { status?: string; q?: string; role?: string; date?: string; interviewer?: string; limit?: number; offset?: number } = {},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 25))
  search.set('offset', String(params.offset || 0))
  if (params.status) search.set('status', params.status)
  if (params.q) search.set('q', params.q)
  if (params.role) search.set('role', params.role)
  if (params.date) search.set('date', params.date)
  if (params.interviewer) search.set('interviewer', params.interviewer)
  return request<InterviewsResponse>(`/dashboard/prehire/interviews?${search.toString()}`, access, init)
}

export function updateInterviewStatus(access: DashboardAccess, interviewId: string, status: string) {
  return request<InterviewMutationResponse>(`/dashboard/prehire/interviews/${encodeURIComponent(interviewId)}`, access, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function interviewAssignInterviewer(access: DashboardAccess, interviewId: string, payload: Record<string, unknown>) {
  return request<InterviewMutationResponse>(`/dashboard/prehire/interviews/${encodeURIComponent(interviewId)}/actions/assign-interviewer`, access, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  })
}

export function interviewSendVideoInvitation(access: DashboardAccess, interviewId: string, payload: Record<string, unknown> = {}) {
  return request<InterviewMutationResponse>(`/dashboard/prehire/interviews/${encodeURIComponent(interviewId)}/actions/send-video-invitation`, access, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  })
}

export function interviewReschedule(access: DashboardAccess, interviewId: string, payload: Record<string, unknown>) {
  return request<InterviewMutationResponse>(`/dashboard/prehire/interviews/${encodeURIComponent(interviewId)}/reschedule`, access, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  })
}

export function saveInterviewNotes(
  access: DashboardAccess,
  interviewId: string,
  body: {
    notes: string
    transcript?: string
    status?: string
    generate_summary?: boolean
    expected_updated_at?: string | null
    expected_version?: number | null
  },
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

const PRODUCT2_AUTHORING_PATH = '/dashboard/prehire/assessments/authoring/product2'

export function getProduct2AuthoringStatus(access: DashboardAccess) {
  return request<Product2AuthoringStatus>(`${PRODUCT2_AUTHORING_PATH}/status`, access)
}

export function getProduct2Blueprints(access: DashboardAccess, status?: string) {
  const search = new URLSearchParams()
  if (status) search.set('status', status)
  const qs = search.toString()
  return request<Product2BlueprintsResponse>(`${PRODUCT2_AUTHORING_PATH}/blueprints${qs ? `?${qs}` : ''}`, access)
}

export function createProduct2Blueprint(
  access: DashboardAccess,
  body: { blueprint_key: string; blueprint: Product2BlueprintInput; approve?: boolean },
) {
  return request<{ ok: boolean; blueprint: Product2Blueprint; publish_available: false }>(
    `${PRODUCT2_AUTHORING_PATH}/blueprints`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function generateProduct2Drafts(
  access: DashboardAccess,
  body: { blueprint_version_id: string; requested_item_count: number },
) {
  return request<Product2RunResponse>(`${PRODUCT2_AUTHORING_PATH}/generate`, access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function runProduct2SecondaryReview(access: DashboardAccess, draftId: string) {
  return request<Product2RunResponse>(
    `${PRODUCT2_AUTHORING_PATH}/drafts/${encodeURIComponent(draftId)}/secondary-review`,
    access,
    { method: 'POST' },
  )
}

export function adaptProduct2Draft(access: DashboardAccess, draftId: string, targetLocale: Product2Locale) {
  return request<Product2RunResponse>(
    `${PRODUCT2_AUTHORING_PATH}/drafts/${encodeURIComponent(draftId)}/adapt`,
    access,
    { method: 'POST', body: JSON.stringify({ target_locale: targetLocale }) },
  )
}

export function reviewProduct2TranslationPair(access: DashboardAccess, translationPairId: string) {
  return request<Product2RunResponse>(
    `${PRODUCT2_AUTHORING_PATH}/translation-pairs/${encodeURIComponent(translationPairId)}/review`,
    access,
    { method: 'POST' },
  )
}

export function humanReviewProduct2TranslationPair(
  access: DashboardAccess,
  translationPairId: string,
  body: { decision: 'approve' | 'rewrite' | 'retire'; notes?: string },
) {
  return request<{
    ok: boolean
    translation_pair: Record<string, unknown>
    human_reviewed: true
    publish_available: false
  }>(
    `${PRODUCT2_AUTHORING_PATH}/translation-pairs/${encodeURIComponent(translationPairId)}/human-review`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function rewriteProduct2Draft(access: DashboardAccess, draftId: string, content: Product2DraftContent) {
  return request<{
    ok: boolean
    draft: Product2Draft
    revision: Record<string, unknown>
    prior_reviews_invalidated: true
    publish_available: false
  }>(
    `${PRODUCT2_AUTHORING_PATH}/drafts/${encodeURIComponent(draftId)}/rewrite`,
    access,
    { method: 'POST', body: JSON.stringify({ content }) },
  )
}

export function getProduct2DraftEvidence(access: DashboardAccess, draftId: string) {
  return request<Product2DraftEvidenceResponse>(
    `${PRODUCT2_AUTHORING_PATH}/drafts/${encodeURIComponent(draftId)}/evidence`,
    access,
  )
}

export function getProduct2Run(access: DashboardAccess, runId: string) {
  return request<Product2RunResponse>(`${PRODUCT2_AUTHORING_PATH}/runs/${encodeURIComponent(runId)}`, access)
}

// Product-2 reuses the established human-only lifecycle transitions. These
// endpoints never add an item to the live bank and have no publish operation.
export function getAssessmentAuthoringDrafts(access: DashboardAccess, status?: string) {
  const search = new URLSearchParams({ limit: '100' })
  if (status) search.set('status', status)
  return request<AssessmentAuthoringDraftsResponse>(
    `/dashboard/prehire/assessments/authoring/drafts?${search.toString()}`,
    access,
  )
}

export function transitionAssessmentAuthoringDraft(
  access: DashboardAccess,
  draftId: string,
  body: {
    to_status: 'ai_draft' | 'human_review' | 'pilot' | 'approved' | 'retired'
    notes?: string
    rejection_reason?: string
    original_content_attested?: boolean
  },
) {
  return request<{ ok: boolean; draft: Product2Draft; published: false; live_bank_unchanged: true }>(
    `/dashboard/prehire/assessments/authoring/drafts/${encodeURIComponent(draftId)}/transition`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function recalculateAssessmentNorms(access: DashboardAccess, persist = true) {
  const search = new URLSearchParams({ persist: String(persist), minimum_sample: '200' })
  return request<AssessmentNormRecalculationResponse>(`/dashboard/prehire/assessments/norms/recalculate?${search.toString()}`, access, {
    method: 'POST',
  })
}

export function getAssessmentReportPayload(access: DashboardAccess, attemptId: string, init?: RequestInit) {
  return request<{ attempt?: AssessmentAttempt; report?: Record<string, unknown>; report_presentation?: import('@/components/assessments/AssessmentReportPage').AssessmentReportPresentation }>(
    `/dashboard/prehire/assessments/${encodeURIComponent(attemptId)}`,
    access,
    init,
  )
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

export async function downloadCandidateCv(access: DashboardAccess, appKey: string, filename?: string) {
  const response = await fetch(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/cv/preview`, {
    headers: dashboardHeaders(access),
  })
  const contentType = response.headers.get('Content-Type') || ''
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const detail = payload?.detail || payload
    throw new DashboardApiError(response.status, detail, 'Could not download the CV.')
  }
  if (contentType.includes('application/json')) {
    const payload = (await response.json()) as { url?: string; filename?: string }
    if (!payload.url) throw new Error('CV download URL was not returned.')
    const anchor = document.createElement('a')
    anchor.href = payload.url
    anchor.download = payload.filename || filename || 'cv'
    anchor.target = '_blank'
    anchor.rel = 'noopener noreferrer'
    anchor.click()
    return
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || `${appKey}-cv`
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

function openPreviewUrl(url: string, previewWindow: Window | null) {
  if (previewWindow) {
    previewWindow.location.assign(url)
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

type CandidateDecisionAction = 'shortlist' | 'reject' | 'hire'

type CandidateConfirmation = {
  confirmation_id: string
  confirmation_token: string
  observed_stage: string
  observed_version: number
  target_payload: Record<string, unknown>
}

async function confirmedCandidateDecision(
  access: DashboardAccess,
  application: ApplicationSummary,
  action: CandidateDecisionAction,
  targetPayload: Record<string, unknown>,
) {
  const observedStage = application.canonical_stage || application.status || ''
  const observedVersion = application.lifecycle_version ?? 0
  const idempotencyKey = `candidate:${action}:${application.app_key}:${observedVersion}:${crypto.randomUUID()}`
  const prepared = await request<{ ok: boolean; confirmation: CandidateConfirmation }>(
    `/dashboard/prehire/applications/${encodeURIComponent(application.app_key)}/confirmations`,
    access,
    {
      method: 'POST',
      body: JSON.stringify({
        action,
        observed_stage: observedStage,
        observed_version: observedVersion,
        target_payload: targetPayload,
        idempotency_key: idempotencyKey,
      }),
    },
  )
  const confirmation = prepared.confirmation
  return request<MutationResponse>(
    `/dashboard/prehire/applications/${encodeURIComponent(application.app_key)}/${action === 'shortlist' ? 'shortlist' : action}`,
    access,
    {
      method: 'POST',
      body: JSON.stringify({
        confirmation_id: confirmation.confirmation_id,
        confirmation_token: confirmation.confirmation_token,
        observed_stage: confirmation.observed_stage,
        observed_version: confirmation.observed_version,
        target_payload: confirmation.target_payload,
      }),
    },
  )
}

export function shortlistCandidate(access: DashboardAccess, application: ApplicationSummary, note?: string) {
  return confirmedCandidateDecision(access, application, 'shortlist', { note: note?.trim() || null })
}

export function hireCandidate(access: DashboardAccess, application: ApplicationSummary, note?: string) {
  return confirmedCandidateDecision(access, application, 'hire', { note: note?.trim() || null })
}

export function rejectCandidate(access: DashboardAccess, application: ApplicationSummary, note?: string) {
  return confirmedCandidateDecision(access, application, 'reject', {
    reason_code: 'not_selected',
    note: note?.trim() || null,
  })
}

export function notifyCandidate(access: DashboardAccess, appKey: string, message?: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/notify`, access, {
    method: 'POST',
    body: JSON.stringify({ message: message || null, account_id: 'default' }),
  })
}

export function sendAssessment(access: DashboardAccess, appKey: string, message?: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/assessment`, access, {
    method: 'POST',
    body: JSON.stringify({ account_id: 'default', message: message || null }),
  })
}

export function resendAssessment(access: DashboardAccess, attemptId: string, message?: string) {
  return request<MutationResponse>(`/dashboard/prehire/assessments/${encodeURIComponent(attemptId)}/resend`, access, {
    method: 'POST',
    body: JSON.stringify({ account_id: 'default', message: message || null }),
  })
}

export function cancelAssessment(access: DashboardAccess, attemptId: string, reason: string) {
  return request<MutationResponse>(`/dashboard/prehire/assessments/${encodeURIComponent(attemptId)}/cancel`, access, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function reviewAssessment(
  access: DashboardAccess,
  attemptId: string,
  notes?: string,
  concurrency?: { expected_updated_at?: string | null; expected_version?: number | null },
) {
  return request<MutationResponse>(`/dashboard/prehire/assessments/${encodeURIComponent(attemptId)}/review`, access, {
    method: 'POST',
    body: JSON.stringify({
      notes: notes || null,
      expected_updated_at: concurrency?.expected_updated_at ?? undefined,
      expected_version: concurrency?.expected_version ?? undefined,
    }),
  })
}

export function sendVideoInterview(access: DashboardAccess, appKey: string, message?: string) {
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/video-interview`, access, {
    method: 'POST',
    body: JSON.stringify({ account_id: 'default', send_invite: true, response_mode: 'single_video', message: message || null }),
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

export function getEmailSendingSettings(access: DashboardAccess) {
  return request<EmailSendingSettingsResponse>('/dashboard/prehire/integrations/email', access)
}

export type IntakeAddressRow = EmailSendingSettingsResponse['intake']['addresses'][number]

export type IntakeListResponse = {
  company_code: string
  feature: NonNullable<EmailSendingSettingsResponse['intake']['feature']>
  addresses: IntakeAddressRow[]
  forward_instructions_en?: string
  forward_instructions_ar?: string
  setup_steps_en?: string[]
  setup_steps_ar?: string[]
}

export function listIntakeAddresses(access: DashboardAccess) {
  return request<IntakeListResponse>('/dashboard/prehire/integrations/intake', access)
}

export function createIntakeAddress(
  access: DashboardAccess,
  body: {
    local_part?: string
    label?: string | null
    position_code?: string | null
    position_title?: string | null
  } = {},
) {
  return request<{ ok: boolean; address: IntakeAddressRow }>('/dashboard/prehire/integrations/intake', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function disableIntakeAddress(access: DashboardAccess, intakeId: string) {
  return request<{ ok: boolean; address: IntakeAddressRow }>(
    `/dashboard/prehire/integrations/intake/${encodeURIComponent(intakeId)}/disable`,
    access,
    { method: 'POST' },
  )
}

export function rotateIntakeAddress(access: DashboardAccess, intakeId: string) {
  return request<{ ok: boolean; previous: IntakeAddressRow; address: IntakeAddressRow }>(
    `/dashboard/prehire/integrations/intake/${encodeURIComponent(intakeId)}/rotate`,
    access,
    { method: 'POST' },
  )
}

export function updateEmailSendingSettings(
  access: DashboardAccess,
  body: {
    current_sender?: string
    outbound_mode?: string
    display_name?: string | null
    reply_to?: string | null
    interview_email_when_calendar_sent?: boolean
    allow_wathefni_emergency_fallback?: boolean
    public_forward_address?: string | null
    inbound_forwarding_enabled?: boolean
    inbound_quotas?: Record<string, number>
  },
) {
  return request<EmailSendingSettingsResponse>('/dashboard/prehire/integrations/email', access, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function emailSendingPrimaryAction(access: DashboardAccess, body: { action: 'connect' | 'verify' | 'test'; domain?: string }) {
  return request<EmailSendingActionResponse>('/dashboard/prehire/integrations/email/action', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
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

export function getPosthireEmployees(access: DashboardAccess, opts?: { offset?: number; limit?: number; search?: string }) {
  const params = new URLSearchParams()
  if (opts?.offset) params.set('offset', String(opts.offset))
  if (opts?.limit) params.set('limit', String(opts.limit))
  if (opts?.search) params.set('search', opts.search)
  const qs = params.toString()
  return request<PosthireEmployeesResponse>(`/dashboard/posthire/employees${qs ? `?${qs}` : ''}`, access)
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

// Edit an existing employee's core fields. Only the provided fields are sent
// (PATCH semantics). Returns { status: 'duplicate' } with ok:false when the new
// phone collides with another employee, so the caller shows a friendly message.
export function updateEmployee(
  access: DashboardAccess,
  employeeKey: string,
  body: {
    name?: string
    phone?: string
    email?: string
    position_title?: string
    department?: string
    start_date?: string | null
    expected_updated_at: string
  },
) {
  return request<{ ok: boolean; status: 'updated' | 'duplicate'; employee: PosthireEmployee | null; message?: string }>(
    `/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}`,
    access,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

// Mark an employee as left (inactive) or reactivate them through the durable,
// idempotent status-change workflow. Never deletes history.
export function setEmployeeStatus(
  access: DashboardAccess,
  employeeKey: string,
  body: {
    status: 'left' | 'active'
    reason: string
    idempotency_key: string
    expected_status: 'left' | 'active'
    expected_updated_at: string
    approver_user_id: string
    approval_reference: string
    approval_mode: 'separate_approval' | 'self_approved_internal_canary'
  },
) {
  return request<{
    ok: boolean
    committed: boolean
    verified: boolean
    status: 'updated' | 'committed_verification_pending'
    operator_verification_required: boolean
    result_id: string
    change_id: string
    idempotency_key: string
    employment_status: string
    employee: PosthireEmployee | null
  }>(
    `/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/status`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export type EmployeeStatusApprover = {
  user_id: string
  name: string
  email: string
  role: string
  phone: string
}

export type EmployeeStatusApprovalPolicy = {
  company_code: string
  environment: string
  canary_allowed: boolean
  production_safe_required: boolean
  self_approval_allowed: boolean
  requester_has_approve_permission: boolean
  requester_dual_grant: boolean
  eligible_approver_count: number
  eligible_approvers: EmployeeStatusApprover[]
  status_change_available: boolean
  blocked_reason: string | null
}

export type EmployeeStatusApprovalRequestRow = {
  request_id: string
  employee_key: string
  requested_status: string
  expected_status: string
  reason: string
  approval_reference: string
  requester_user_id: string
  designated_approver_user_id: string
  status: string
  created_at?: string
}

export function getEmployeeStatusApprovalPolicy(access: DashboardAccess) {
  return request<EmployeeStatusApprovalPolicy>('/dashboard/posthire/employee-status/approval-policy', access)
}

export function listEmployeeStatusPending(access: DashboardAccess, employeeKey?: string) {
  const q = employeeKey ? `?employee_key=${encodeURIComponent(employeeKey)}` : ''
  return request<{ ok: boolean; count: number; requests: EmployeeStatusApprovalRequestRow[] }>(
    `/dashboard/posthire/employee-status/pending${q}`,
    access,
  )
}

export function createEmployeeStatusApprovalRequest(
  access: DashboardAccess,
  employeeKey: string,
  body: {
    status: 'left' | 'active'
    reason: string
    idempotency_key: string
    expected_status: 'left' | 'active'
    expected_updated_at: string
    designated_approver_user_id: string
    approval_reference: string
  },
) {
  return request<{ ok: boolean; idempotent?: boolean; request: EmployeeStatusApprovalRequestRow }>(
    `/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/status/requests`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function cancelEmployeeStatusApprovalRequest(access: DashboardAccess, requestId: string) {
  return request<{ ok: boolean; request: EmployeeStatusApprovalRequestRow }>(
    `/dashboard/posthire/employee-status/requests/${encodeURIComponent(requestId)}/cancel`,
    access,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export function decideEmployeeStatusApprovalRequest(
  access: DashboardAccess,
  requestId: string,
  body: { action: 'approve' | 'reject'; decision_reason?: string },
) {
  return request<{
    ok: boolean
    decision: 'approve' | 'reject'
    committed: boolean
    idempotent?: boolean
    request: EmployeeStatusApprovalRequestRow
    status_change?: { verified?: boolean; result_id?: string; employment_status?: string }
  }>(
    `/dashboard/posthire/employee-status/requests/${encodeURIComponent(requestId)}/decide`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function createEmployeeAppHandoff(
  access: DashboardAccess,
  employeeKey: string,
  body: {
    delivery_mode: 'hr_task_only'
    idempotency_key: string
    reason: string
    supersede_invite_id?: string
  },
) {
  return request<{
    ok: boolean
    invite_id: string
    task_id: string
    audit_result_id: string
    employee_key: string
    expires_at: string
    delivery_mode: 'hr_task_only'
    activation_code: string
  }>(
    `/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/app-invite`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getEmployeeProfile(access: DashboardAccess, employeeKey: string) {
  return request<EmployeeProfileResponse>(`/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}`, access)
}

export function getPosthireOnboarding(access: DashboardAccess, opts?: { offset?: number; limit?: number; search?: string }) {
  const params = new URLSearchParams()
  if (opts?.offset) params.set('offset', String(opts.offset))
  if (opts?.limit) params.set('limit', String(opts.limit))
  if (opts?.search) params.set('search', opts.search)
  const qs = params.toString()
  return request<PosthireOnboardingResponse>(`/dashboard/posthire/onboarding${qs ? `?${qs}` : ''}`, access)
}

export function getOnboardingDetail(access: DashboardAccess, employeeKey: string) {
  return request<OnboardingDetailResponse>(`/dashboard/posthire/onboarding/${encodeURIComponent(employeeKey)}`, access)
}

export function getPosthireAttendance(
  access: DashboardAccess,
  range?: { start_date?: string; end_date?: string },
  opts?: { offset?: number; limit?: number },
) {
  const params = new URLSearchParams()
  if (range?.start_date) params.set('start_date', range.start_date)
  if (range?.end_date) params.set('end_date', range.end_date)
  if (opts?.offset) params.set('offset', String(opts.offset))
  if (opts?.limit) params.set('limit', String(opts.limit))
  const qs = params.toString()
  return request<PosthireAttendanceResponse>(`/dashboard/posthire/attendance${qs ? `?${qs}` : ''}`, access)
}

// --- Attendance Import (behind WATHEFNI_ATTENDANCE_IMPORT) ------------------
// All uploads are multipart; the browser sets the boundary so we must not set
// Content-Type. The same file is sent for preview and commit (no raw upload is
// stored on the server).
async function attendanceImportUpload<T>(access: DashboardAccess, path: string, form: FormData): Promise<T> {
  const response = await fetch(path, { method: 'POST', headers: dashboardHeaders(access), body: form })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new DashboardApiError(response.status, payload?.detail || payload, 'Attendance import failed.')
  return payload as T
}

export function previewAttendanceImport(access: DashboardAccess, body: { file: File; mapping?: Record<string, string>; mappingId?: string }) {
  const form = new FormData()
  form.append('file', body.file)
  if (body.mapping) form.append('mapping', JSON.stringify(body.mapping))
  if (body.mappingId) form.append('mapping_id', body.mappingId)
  return attendanceImportUpload<AttendanceImportPreview>(access, '/dashboard/posthire/attendance/import/preview', form)
}

export function commitAttendanceImport(access: DashboardAccess, body: { file: File; mapping?: Record<string, string>; sourceLabel?: string }) {
  const form = new FormData()
  form.append('file', body.file)
  if (body.mapping) form.append('mapping', JSON.stringify(body.mapping))
  if (body.sourceLabel) form.append('source_label', body.sourceLabel)
  return attendanceImportUpload<AttendanceImportCommitResponse>(access, '/dashboard/posthire/attendance/import/commit', form)
}

export function listAttendanceImportBatches(access: DashboardAccess) {
  return request<AttendanceImportBatchesResponse>('/dashboard/posthire/attendance/import/batches', access)
}

export function reverseAttendanceImportBatch(access: DashboardAccess, batchId: string) {
  return request<AttendanceImportReverseResponse>(`/dashboard/posthire/attendance/import/batches/${encodeURIComponent(batchId)}/reverse`, access, { method: 'POST' })
}

export function listAttendanceImportMappings(access: DashboardAccess) {
  return request<AttendanceImportMappingsResponse>('/dashboard/posthire/attendance/import/mappings', access)
}

// --- Attendance Capture Ops (Wave 2E dark; WATHEFNI_ATTENDANCE_CAPTURE_OPS) ---
export function getCaptureOpsOverview(access: DashboardAccess) {
  return request<Record<string, unknown>>('/dashboard/posthire/attendance/capture-ops', access)
}

export function seedCaptureOpsSynthetic(access: DashboardAccess, tag?: string) {
  return request<Record<string, unknown>>('/dashboard/posthire/attendance/capture-ops/seed-synthetic', access, {
    method: 'POST',
    body: JSON.stringify(tag ? { tag } : {}),
  })
}

export function approveCaptureMapping(
  access: DashboardAccess,
  itemId: string,
  body: { employee_key: string; expected_row_version: number; replay?: boolean; employee_phone?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/attendance/capture-ops/remediation/${encodeURIComponent(itemId)}/approve-mapping`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function rejectCaptureRemediation(
  access: DashboardAccess,
  itemId: string,
  body: { expected_row_version: number; reason?: string; employee_phone?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/attendance/capture-ops/remediation/${encodeURIComponent(itemId)}/reject`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function updateCaptureConnectorHealth(
  access: DashboardAccess,
  connectorId: string,
  body: {
    status?: string
    lag_seconds?: number
    error_count?: number
    last_error?: string | null
    last_sync_at?: string | null
    checkpoint?: string | null
    connector_version?: string | null
  },
) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/attendance/capture-ops/connectors/${encodeURIComponent(connectorId)}/health`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function saveAttendanceImportMapping(access: DashboardAccess, body: { name: string; mapping: Record<string, string> }) {
  return request<{ ok: boolean; mapping: AttendanceImportMapping }>('/dashboard/posthire/attendance/import/mappings', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function bindAttendanceDevice(access: DashboardAccess, body: { external_id: string; employee_key: string }) {
  return request<{ ok: boolean }>('/dashboard/posthire/attendance/import/map', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// --- Attendance operations (Wave 3/4 HR exception queue; synthetic-safe) ---
export function listAttendanceOpsExceptions(access: DashboardAccess, params?: { status?: string; kind?: string }) {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.kind) q.set('kind', params.kind)
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return request<Record<string, unknown>>(`/dashboard/attendance/ops/exceptions${suffix}`, access)
}

export function assignAttendanceOpsException(
  access: DashboardAccess,
  exceptionId: string,
  body: { owner_phone: string; expected_row_version: number; priority?: string; due_at?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/attendance/ops/exceptions/${encodeURIComponent(exceptionId)}/assign`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function reopenAttendanceOpsException(
  access: DashboardAccess,
  exceptionId: string,
  body: { expected_row_version: number; evidence_note: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/attendance/ops/exceptions/${encodeURIComponent(exceptionId)}/reopen`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function requestAttendanceOpsCorrection(
  access: DashboardAccess,
  body: {
    employee_key: string
    work_date: string
    changes: Record<string, unknown>
    shift_id?: string
    exception_id?: string
    kind?: string
  },
) {
  return request<Record<string, unknown>>('/dashboard/attendance/ops/corrections', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function reviewAttendanceOpsCase(
  access: DashboardAccess,
  caseId: string,
  body: { decision: 'approved' | 'rejected' | string; expected_row_version: number; decision_note?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/attendance/ops/cases/${encodeURIComponent(caseId)}/review`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function applyAttendanceOpsCase(
  access: DashboardAccess,
  caseId: string,
  body: { expected_row_version: number; idempotency_key: string; shift_id?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/attendance/ops/cases/${encodeURIComponent(caseId)}/apply`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function raiseAttendanceOpsDispute(
  access: DashboardAccess,
  body: { employee_key: string; work_date: string; reason: string; exception_id?: string; case_id?: string; shift_key?: string },
) {
  return request<Record<string, unknown>>('/dashboard/attendance/ops/disputes', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function resolveAttendanceOpsDispute(
  access: DashboardAccess,
  disputeId: string,
  body: { resolution: string; expected_row_version: number; resolution_note?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/attendance/ops/disputes/${encodeURIComponent(disputeId)}/resolve`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function commentAttendanceOps(
  access: DashboardAccess,
  body: { entity_type: string; entity_id: string; body: string },
) {
  return request<Record<string, unknown>>('/dashboard/attendance/ops/comments', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// Download attendance for the selected range as CSV. Auth is header-based, so we
// fetch with credentials and hand the browser a blob (no raw URL in the DOM).
export async function exportAttendanceCsv(access: DashboardAccess, range: { start_date: string; end_date: string }) {
  const params = new URLSearchParams({ start_date: range.start_date, end_date: range.end_date })
  const response = await fetch(`/dashboard/posthire/attendance/export.csv?${params.toString()}`, {
    headers: dashboardHeaders(access),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not export attendance.')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] || `attendance-${range.start_date}-to-${range.end_date}.csv`
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function getPosthireLeave(
  access: DashboardAccess,
  opts?: { view?: 'active' | 'history'; status?: string; section?: 'pending' | 'upcoming'; offset?: number; limit?: number },
) {
  const params = new URLSearchParams()
  if (opts?.view) params.set('view', opts.view)
  if (opts?.status) params.set('status', opts.status)
  if (opts?.section) params.set('section', opts.section)
  if (opts?.offset) params.set('offset', String(opts.offset))
  if (opts?.limit) params.set('limit', String(opts.limit))
  const qs = params.toString()
  return request<PosthireLeaveResponse>(`/dashboard/posthire/leave${qs ? `?${qs}` : ''}`, access)
}

export function getPosthireShifts(access: DashboardAccess, week = 0, opts?: { offset?: number; limit?: number }) {
  const params = new URLSearchParams()
  if (week) params.set('week', String(week))
  if (opts?.offset) params.set('offset', String(opts.offset))
  if (opts?.limit) params.set('limit', String(opts.limit))
  const qs = params.toString()
  return request<PosthireShiftsResponse>(`/dashboard/posthire/shifts${qs ? `?${qs}` : ''}`, access)
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
  body: {
    shift_date: string
    start_time: string
    end_time: string
    expected_updated_at: string
    allow_leave_conflicts?: boolean
  },
) {
  return request<{ ok: boolean; status: string; message?: string; notified?: boolean }>(
    `/dashboard/posthire/shifts/${encodeURIComponent(shiftId)}/reschedule`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getPosthirePayroll(
  access: DashboardAccess,
  period?: { start_date?: string; end_date?: string; offset?: number; limit?: number },
) {
  const params = new URLSearchParams()
  if (period?.start_date) params.set('start_date', period.start_date)
  if (period?.end_date) params.set('end_date', period.end_date)
  if (period?.offset) params.set('offset', String(period.offset))
  if (period?.limit) params.set('limit', String(period.limit))
  const qs = params.toString()
  return request<PosthirePayrollResponse>(`/dashboard/posthire/payroll${qs ? `?${qs}` : ''}`, access)
}

export function getPayrollExportDetail(access: DashboardAccess, exportId: string) {
  return request<PayrollExportDetail>(`/dashboard/posthire/payroll/exports/${encodeURIComponent(exportId)}`, access)
}

// Download a finalized payroll export as CSV. Header-authenticated fetch → blob.
export async function downloadPayrollExportCsv(access: DashboardAccess, exportId: string) {
  const response = await fetch(`/dashboard/posthire/payroll/exports/${encodeURIComponent(exportId)}/download.csv`, {
    headers: dashboardHeaders(access),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not download the payroll export.')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] || `payroll-export-${exportId}.csv`
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function getPosthireAnalytics(access: DashboardAccess) {
  return request<PosthireAnalyticsResponse>('/dashboard/posthire/analytics', access)
}

export function getPosthireCompliance(
  access: DashboardAccess,
  opts?: { offset?: number; limit?: number; search?: string; bucket?: string },
) {
  const params = new URLSearchParams()
  if (opts?.offset) params.set('offset', String(opts.offset))
  if (opts?.limit) params.set('limit', String(opts.limit))
  if (opts?.search) params.set('search', opts.search)
  if (opts?.bucket && opts.bucket !== 'all') params.set('bucket', opts.bucket)
  const qs = params.toString()
  return request<PosthireComplianceResponse>(`/dashboard/posthire/compliance${qs ? `?${qs}` : ''}`, access)
}

export function getEmployeeDocuments(access: DashboardAccess, employeeKey: string) {
  return request<EmployeeDocumentsResponse>(`/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/documents`, access)
}

export function getEmployeeComplianceJourney(access: DashboardAccess, employeeKey: string) {
  return request<{
    ok: boolean
    documents: Array<{
      document_type: string
      label: string
      review_status: string
      review_status_label: string
      expiry_date?: string | null
      rejection_reason?: string | null
      ocr_proposal?: Record<string, unknown> | null
      ocr_authoritative?: boolean
      pending_version_id?: string | null
      versions?: Array<Record<string, unknown>>
    }>
    legitimacy_note?: string
  }>(`/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/documents/compliance`, access)
}

export async function reviewEmployeeDocument(
  access: DashboardAccess,
  employeeKey: string,
  documentType: string,
  body: {
    action: 'approve' | 'reject' | 'request_reupload' | 'correct_metadata'
    version_id?: string | null
    reason?: string | null
    issue_date?: string | null
    expiry_date?: string | null
    document_number?: string | null
    confirm_ocr?: boolean
  },
) {
  return request<{ ok: boolean; action: string; legitimacy_note?: string }>(
    `/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/documents/${encodeURIComponent(documentType)}/review`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
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

export function getHrTasks(access: DashboardAccess, status = 'open', params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams()
  search.set('status', status)
  search.set('limit', String(params.limit || 100))
  search.set('offset', String(params.offset || 0))
  return request<HrTasksResponse>(`/dashboard/hr-tasks?${search.toString()}`, access)
}

export function resolveHrTask(access: DashboardAccess, taskId: string, status: 'done' | 'dismissed' = 'done') {
  return request<{ ok: boolean; task: { task_id: string; status: string } }>(
    `/dashboard/hr-tasks/${encodeURIComponent(taskId)}/resolve`,
    access,
    { method: 'POST', body: JSON.stringify({ status }) },
  )
}

export function getOutboundNeedsFollowUp(access: DashboardAccess, params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams()
  search.set('limit', String(params.limit || 100))
  search.set('offset', String(params.offset || 0))
  return request<OutboundNeedsFollowUpResponse>(`/dashboard/outbound/needs-follow-up?${search.toString()}`, access)
}

export function generateCandidateEvaluation(access: DashboardAccess, appKey: string, force = false) {
  const search = new URLSearchParams()
  if (force) search.set('force', 'true')
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request<MutationResponse>(`/dashboard/prehire/applications/${encodeURIComponent(appKey)}/evaluation${suffix}`, access, {
    method: 'POST',
  })
}

// --- Wathefni Calendar C1–C3 -------------------------------------------------

export type CalendarEvent = {
  event_id: string
  company_code?: string
  event_type?: string
  title?: string
  title_ar?: string
  description?: string
  description_ar?: string
  status?: string
  start_at?: string
  end_at?: string
  timezone?: string
  all_day?: boolean
  location?: string
  meeting_url?: string
  visibility?: string
  sensitivity?: string
  busy?: boolean
  version?: number
  updated_at?: string
  detail_level?: 'full' | 'limited' | 'busy_only' | 'hidden' | string
  attendees?: Array<Record<string, unknown>>
  guests?: Array<Record<string, unknown>>
  links?: Array<Record<string, unknown>>
  org_scope_ids?: string[]
  organizer_user_id?: string
  owner_user_id?: string
  interview_managed?: boolean
  interview_id?: string
  authority?: string
  metadata?: Record<string, unknown>
}

export type CalendarEventsResponse = {
  ok: boolean
  company_code: string
  scope: string
  org_scope_id?: string | null
  start: string
  end: string
  events: CalendarEvent[]
  count: number
  team?: {
    show_team_switch?: boolean
    has_team_scope?: boolean
    has_company_oversight?: boolean
    no_team_guidance?: boolean
    scopes?: Array<{ org_scope_id: string; org_scope_kind?: string; label?: string | null }>
    primary_org_scope_id?: string | null
  }
}

export type CalendarOverviewResponse = {
  ok: boolean
  company_code: string
  scope: string
  today: string
  month: { year: number; month: number; busy_days: string[] }
  today_count: number
  upcoming: CalendarEvent[]
  upcoming_count: number
  max_items: number
  can_add_event: boolean
}

export type CalendarConflict = {
  type: string
  affected_ref?: { kind?: string; id?: string; label?: string }
  start_at?: string
  end_at?: string
  severity?: string
  blocking?: boolean
  message?: string
  message_ar?: string
  attendee_role?: string
}

export function getCalendarEvents(
  access: DashboardAccess,
  params: {
    start: string
    end: string
    scope?: 'mine' | 'team' | 'company' | string
    org_scope_id?: string
    event_type?: string
    status?: string
    mine_only?: boolean
  },
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  search.set('start', params.start)
  search.set('end', params.end)
  search.set('scope', params.scope || 'mine')
  if (params.org_scope_id) search.set('org_scope_id', params.org_scope_id)
  if (params.event_type) search.set('event_type', params.event_type)
  if (params.status) search.set('status', params.status)
  if (params.mine_only) search.set('mine_only', 'true')
  return request<CalendarEventsResponse>(`/dashboard/calendar/events?${search.toString()}`, access, init)
}

export function getCalendarTeamScopes(access: DashboardAccess, init?: RequestInit) {
  return request<{
    ok: boolean
    show_team_switch: boolean
    has_team_scope: boolean
    has_company_oversight: boolean
    no_team_guidance: boolean
    scopes: Array<{ org_scope_id: string; org_scope_kind?: string; label?: string | null }>
    primary_org_scope_id?: string | null
  }>('/dashboard/calendar/team-scopes', access, init)
}

export function getCalendarOverview(access: DashboardAccess, scope: 'mine' | 'company' = 'mine', init?: RequestInit) {
  const search = new URLSearchParams({ scope })
  return request<CalendarOverviewResponse>(`/dashboard/calendar/overview?${search.toString()}`, access, init)
}

export function previewCalendarConflicts(access: DashboardAccess, body: Record<string, unknown>) {
  return request<{
    ok: boolean
    conflicts: CalendarConflict[]
    blocking: CalendarConflict[]
    warnings: CalendarConflict[]
    blocking_count: number
    warning_count: number
  }>('/dashboard/calendar/conflicts/preview', access, { method: 'POST', body: JSON.stringify(body) })
}

export function getCalendarEvent(access: DashboardAccess, eventId: string, init?: RequestInit) {
  return request<{ ok: boolean; company_code: string; event: CalendarEvent }>(
    `/dashboard/calendar/events/${encodeURIComponent(eventId)}`,
    access,
    init,
  )
}

export function createCalendarEvent(access: DashboardAccess, body: Record<string, unknown>) {
  return request<{ ok: boolean; company_code: string; event: CalendarEvent }>('/dashboard/calendar/events', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateCalendarEvent(access: DashboardAccess, eventId: string, body: Record<string, unknown>) {
  return request<{ ok: boolean; company_code: string; event: CalendarEvent }>(
    `/dashboard/calendar/events/${encodeURIComponent(eventId)}`,
    access,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function cancelCalendarEvent(
  access: DashboardAccess,
  eventId: string,
  body: { expected_version: number; expected_updated_at?: string },
) {
  return request<{ ok: boolean; company_code: string; event: CalendarEvent }>(
    `/dashboard/calendar/events/${encodeURIComponent(eventId)}/cancel`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function rsvpCalendarEvent(
  access: DashboardAccess,
  eventId: string,
  body: { rsvp_status: string; expected_rsvp_version?: number; target_user_id?: string },
) {
  return request<{ ok: boolean; company_code: string; event: CalendarEvent; attendee?: Record<string, unknown> }>(
    `/dashboard/calendar/events/${encodeURIComponent(eventId)}/rsvp`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function inviteCalendarGuest(
  access: DashboardAccess,
  eventId: string,
  guestId: string,
  body: { channel?: string } = {},
) {
  return request<{ ok: boolean; invite_path?: string }>(
    `/dashboard/calendar/events/${encodeURIComponent(eventId)}/guests/${encodeURIComponent(guestId)}/invite`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getCalendarRescheduleRequests(
  access: DashboardAccess,
  params: { event_id?: string; status?: string } = {},
  init?: RequestInit,
) {
  const search = new URLSearchParams()
  if (params.event_id) search.set('event_id', params.event_id)
  if (params.status) search.set('status', params.status)
  const q = search.toString()
  return request<{ ok: boolean; requests: Array<Record<string, unknown>>; count: number }>(
    `/dashboard/calendar/reschedule-requests${q ? `?${q}` : ''}`,
    access,
    init,
  )
}

export function resolveCalendarRescheduleRequest(
  access: DashboardAccess,
  requestId: string,
  body: { decision: string; resolution_note?: string },
) {
  return request<{ ok: boolean; request: Record<string, unknown>; message?: string; safe_next_action?: string }>(
    `/dashboard/calendar/reschedule-requests/${encodeURIComponent(requestId)}/resolve`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export type CalendarSyncConnection = {
  connection_id: string
  company_code: string
  provider_key: string
  mode: string
  status: string
  account_email?: string | null
  external_calendar_id?: string
  display_name?: string | null
  sync_event_types?: string[]
  sync_include_candidate_name?: boolean
  with_meet_default?: boolean
  platform_integration_id?: string | null
  last_sync_at?: string | null
  last_error?: string | null
  has_credentials?: boolean
}

export type PlatformCompanyIntegration = {
  integration_id: string
  company_code: string
  provider_key: string
  status: string
  connection_mode?: string | null
  account_email?: string | null
  impersonation_email?: string | null
  external_tenant_id?: string | null
  display_name?: string | null
  granted_scopes?: string[]
  capabilities?: string[]
  implemented_capabilities?: string[]
  reserved_capabilities_noted?: string[]
  health?: Record<string, unknown>
  last_error?: string | null
  has_credentials?: boolean
  reconnect_required?: boolean
  credential_expires_at?: string | null
  credential_days_remaining?: number | null
  expiry_warning?: string | null
}

export type CalendarSyncBinding = {
  binding_id: string
  event_id: string
  connection_id: string
  provider_event_id?: string | null
  external_html_link?: string | null
  sync_status: string
  last_pushed_version?: number | null
  last_synced_at?: string | null
  last_error?: string | null
  provider_key?: string
  connection_mode?: string
  connection_status?: string
  account_email?: string | null
}

export function getCalendarSyncConnections(access: DashboardAccess) {
  return request<{ ok: boolean; company_code: string; connections: CalendarSyncConnection[]; count: number }>(
    '/dashboard/calendar/sync/connections',
    access,
  )
}

export function getPlatformIntegrations(access: DashboardAccess) {
  return request<{
    ok: boolean
    company_code: string
    integrations: PlatformCompanyIntegration[]
    count: number
    registry: Record<string, unknown>
    modes: Record<string, unknown>
  }>('/dashboard/platform/integrations', access)
}

export function getPlatformIntegrationChecklist(
  access: DashboardAccess,
  providerKey: string,
  mode: string,
) {
  return request<{ ok: boolean; checklist: Record<string, unknown> }>(
    `/dashboard/platform/integrations/checklist?provider_key=${encodeURIComponent(providerKey)}&mode=${encodeURIComponent(mode)}`,
    access,
  )
}

export function startPlatformOAuth(
  access: DashboardAccess,
  body: { provider_key: 'google_workspace' | 'microsoft_365'; attach_calendar?: boolean },
) {
  return request<{ ok: boolean; authorize_url: string; checklist?: Record<string, unknown> }>(
    '/dashboard/platform/integrations/oauth/start',
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function connectMicrosoftEnterprise(
  access: DashboardAccess,
  body: {
    tenant_id: string
    client_id: string
    calendar_identity: string
    client_secret?: string
    certificate_pem?: string
    certificate_thumbprint?: string
    display_name?: string
    credential_expires_at?: string
    validate?: boolean
    dry_run_accept?: boolean
  },
) {
  return request<{ ok: boolean; integration: PlatformCompanyIntegration; connection?: CalendarSyncConnection; checklist?: Record<string, unknown> }>(
    '/dashboard/platform/integrations/microsoft/enterprise',
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function connectGoogleEnterprise(
  access: DashboardAccess,
  body: {
    impersonation_email: string
    service_account_json: string
    display_name?: string
    validate?: boolean
    dry_run_accept?: boolean
  },
) {
  return request<{ ok: boolean; integration: PlatformCompanyIntegration; connection?: CalendarSyncConnection; checklist?: Record<string, unknown> }>(
    '/dashboard/platform/integrations/google/enterprise',
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function healthcheckPlatformIntegration(access: DashboardAccess, integrationId: string) {
  return request<{ ok: boolean; integration: PlatformCompanyIntegration; health: Record<string, unknown> }>(
    `/dashboard/platform/integrations/${encodeURIComponent(integrationId)}/health`,
    access,
    { method: 'POST', body: '{}' },
  )
}

export function disconnectPlatformIntegration(access: DashboardAccess, integrationId: string) {
  return request<{ ok: boolean; integration: PlatformCompanyIntegration }>(
    `/dashboard/platform/integrations/${encodeURIComponent(integrationId)}/disconnect`,
    access,
    { method: 'POST', body: '{}' },
  )
}

/** @deprecated Product UX must not paste refresh tokens — ops fallback only. */
export function connectPlatformIntegration(
  access: DashboardAccess,
  body: {
    provider_key: 'google_workspace' | 'microsoft_365'
    account_email: string
    refresh_token: string
    display_name?: string
    external_tenant_id?: string
    attach_calendar?: boolean
    with_meet_default?: boolean
    external_calendar_id?: string
  },
) {
  return request<{
    ok: boolean
    integration: PlatformCompanyIntegration
    connection?: CalendarSyncConnection
  }>('/dashboard/platform/integrations/connect', access, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function connectCalendarGoogleSync(
  access: DashboardAccess,
  body: {
    account_email: string
    refresh_token: string
    external_calendar_id?: string
    display_name?: string
    sync_event_types?: string[]
    sync_include_candidate_name?: boolean
    with_meet_default?: boolean
  },
) {
  return request<{ ok: boolean; connection: CalendarSyncConnection; integration?: PlatformCompanyIntegration }>(
    '/dashboard/calendar/sync/connections/google',
    access,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}

export function connectCalendarMicrosoftSync(
  access: DashboardAccess,
  body: {
    account_email: string
    refresh_token: string
    external_calendar_id?: string
    display_name?: string
    external_tenant_id?: string
    with_meet_default?: boolean
  },
) {
  return request<{ ok: boolean; connection: CalendarSyncConnection; integration?: PlatformCompanyIntegration }>(
    '/dashboard/calendar/sync/connections/microsoft',
    access,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}

export function ensureCalendarLegacyOperatorSync(access: DashboardAccess) {
  return request<{ ok: boolean; connection: CalendarSyncConnection }>(
    '/dashboard/calendar/sync/connections/legacy-operator',
    access,
    { method: 'POST', body: '{}' },
  )
}

export function updateCalendarSyncConnection(
  access: DashboardAccess,
  connectionId: string,
  body: {
    sync_event_types?: string[]
    sync_include_candidate_name?: boolean
    external_calendar_id?: string
    with_meet_default?: boolean
    display_name?: string
  },
) {
  return request<{ ok: boolean; connection: CalendarSyncConnection }>(
    `/dashboard/calendar/sync/connections/${encodeURIComponent(connectionId)}`,
    access,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function disconnectCalendarSync(access: DashboardAccess, connectionId: string) {
  return request<{ ok: boolean; connection: CalendarSyncConnection }>(
    `/dashboard/calendar/sync/connections/${encodeURIComponent(connectionId)}/disconnect`,
    access,
    { method: 'POST', body: '{}' },
  )
}

export function reconnectCalendarSync(access: DashboardAccess, connectionId: string, refreshToken?: string) {
  return request<{ ok: boolean; connection: CalendarSyncConnection; repair?: Record<string, unknown> }>(
    `/dashboard/calendar/sync/connections/${encodeURIComponent(connectionId)}/reconnect`,
    access,
    { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken || null }) },
  )
}

export function getCalendarEventSync(access: DashboardAccess, eventId: string, init?: RequestInit) {
  return request<{
    ok: boolean
    event_id: string
    detail?: 'full' | 'status'
    customer_status?: 'synced' | 'pending' | 'unavailable' | null
    bindings: CalendarSyncBinding[]
  }>(
    `/dashboard/calendar/events/${encodeURIComponent(eventId)}/sync`,
    access,
    init,
  )
}

export function retryCalendarEventSync(access: DashboardAccess, eventId: string) {
  return request<{ ok: boolean; enqueued?: number }>(
    `/dashboard/calendar/events/${encodeURIComponent(eventId)}/sync/retry`,
    access,
    { method: 'POST', body: '{}' },
  )
}

/* ——— Employees 360 Wave 6 clients (Wave 3–5 APIs; no client-side authority) ——— */

export function getEmployeeLifecyclePending(access: DashboardAccess, opts?: { employee_key?: string }) {
  const params = new URLSearchParams()
  if (opts?.employee_key) params.set('employee_key', opts.employee_key)
  const qs = params.toString()
  return request<LifecyclePendingResponse>(`/dashboard/posthire/employee-lifecycle/pending${qs ? `?${qs}` : ''}`, access)
}

export function decideEmployeeLifecycleRequest(
  access: DashboardAccess,
  requestId: string,
  body: { action: 'approve' | 'reject'; decision_reason?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/employee-lifecycle/requests/${encodeURIComponent(requestId)}/decide`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function cancelEmployeeLifecycleRequest(access: DashboardAccess, requestId: string) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/employee-lifecycle/requests/${encodeURIComponent(requestId)}/cancel`,
    access,
    { method: 'POST', body: '{}' },
  )
}

export function getEmployeeLifecycleRemediation(access: DashboardAccess) {
  return request<RemediationQueueResponse>('/dashboard/posthire/employee-lifecycle/remediation', access)
}

export function getEmployeeOrgUnits(access: DashboardAccess, opts?: { unit_type?: string }) {
  const params = new URLSearchParams()
  if (opts?.unit_type) params.set('unit_type', opts.unit_type)
  const qs = params.toString()
  return request<OrgUnitsResponse>(`/dashboard/posthire/employee-org/units${qs ? `?${qs}` : ''}`, access)
}

export function getEmployeeOrgHistory(access: DashboardAccess, employeeKey: string) {
  return request<OrgHistoryResponse>(`/dashboard/posthire/employees/${encodeURIComponent(employeeKey)}/org-history`, access)
}

export function getEmployeeOrgReconcile(access: DashboardAccess, opts?: { as_of?: string }) {
  const params = new URLSearchParams()
  if (opts?.as_of) params.set('as_of', opts.as_of)
  const qs = params.toString()
  return request<Record<string, unknown>>(`/dashboard/posthire/employee-org/reconcile${qs ? `?${qs}` : ''}`, access)
}

export function listEmployeeOrgMigrationBatches(access: DashboardAccess, limit = 50) {
  return request<MigrationBatchesResponse>(`/dashboard/posthire/employee-org/migration-batches?limit=${limit}`, access)
}

export function dryRunEmployeeOrgMigrationBatch(access: DashboardAccess, batchId: string) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/employee-org/migration-batches/${encodeURIComponent(batchId)}/dry-run`,
    access,
    { method: 'POST', body: '{}' },
  )
}

export function commitEmployeeOrgMigrationBatch(access: DashboardAccess, batchId: string) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/employee-org/migration-batches/${encodeURIComponent(batchId)}/commit`,
    access,
    { method: 'POST', body: '{}' },
  )
}

export function rollbackEmployeeOrgMigrationBatch(access: DashboardAccess, batchId: string) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/employee-org/migration-batches/${encodeURIComponent(batchId)}/rollback`,
    access,
    { method: 'POST', body: '{}' },
  )
}

export function getEmployeeEssPolicy(access: DashboardAccess) {
  return request<{ ok?: boolean; enabled?: boolean; matrix?: Record<string, unknown> }>(
    '/dashboard/posthire/employee-ess/policy',
    access,
  )
}

export function listEmployeeEssRequests(
  access: DashboardAccess,
  opts?: { employee_key?: string; state?: string; actor_employee_key?: string },
) {
  const params = new URLSearchParams()
  if (opts?.employee_key) params.set('employee_key', opts.employee_key)
  if (opts?.state) params.set('state', opts.state)
  if (opts?.actor_employee_key) params.set('actor_employee_key', opts.actor_employee_key)
  const qs = params.toString()
  return request<EssRequestsResponse>(`/dashboard/posthire/employee-ess/requests${qs ? `?${qs}` : ''}`, access)
}

export function getEmployeeEssOwnView(access: DashboardAccess, employeeKey: string, actorEmployeeKey?: string) {
  const params = new URLSearchParams()
  if (actorEmployeeKey) params.set('actor_employee_key', actorEmployeeKey)
  const qs = params.toString()
  return request<EssOwnViewResponse>(
    `/dashboard/posthire/employee-ess/me/${encodeURIComponent(employeeKey)}${qs ? `?${qs}` : ''}`,
    access,
  )
}

export function decideEmployeeEssRequest(
  access: DashboardAccess,
  requestId: string,
  body: { action: 'approve' | 'reject'; comment?: string; actor_employee_key?: string },
) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/employee-ess/requests/${encodeURIComponent(requestId)}/decide`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function applyEmployeeEssRequest(access: DashboardAccess, requestId: string, body?: { idempotency_key?: string }) {
  return request<Record<string, unknown>>(
    `/dashboard/posthire/employee-ess/requests/${encodeURIComponent(requestId)}/apply`,
    access,
    { method: 'POST', body: JSON.stringify(body || {}) },
  )
}

export function reconcileEmployeeEss(access: DashboardAccess) {
  return request<Record<string, unknown>>('/dashboard/posthire/employee-ess/reconcile', access)
}

