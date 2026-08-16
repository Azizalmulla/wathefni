import type {
  ChannelAccountInput,
  CompanyCreateInput,
  CompanyDetailResponse,
  CompanyLifecycleInput,
  CompanyLifecycleResponse,
  CompanyListResponse,
  CompanyProfileInput,
  CompanySummary,
  LaunchReadinessResponse,
  OwnerInput,
  OwnerResponse,
  SetupCredentials,
} from './types'
import { credentialsFromSession, readStoredSession, refreshSetupSession } from './session'

const SETUP_ROOT = '/dashboard/superadmin/setup'

export class SetupConsoleApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'SetupConsoleApiError'
    this.status = status
  }
}

type SessionListener = (next: SetupCredentials | null) => void
const sessionListeners = new Set<SessionListener>()

/** Notify the shell when silent refresh rotates credentials (or clears them). */
export function onSetupSessionChange(listener: SessionListener): () => void {
  sessionListeners.add(listener)
  return () => {
    sessionListeners.delete(listener)
  }
}

function emitSessionChange(next: SetupCredentials | null) {
  for (const listener of sessionListeners) listener(next)
}

function errorMessageFromPayload(payload: unknown, fallback: string) {
  const detail =
    payload && typeof payload === 'object' && 'detail' in payload
      ? (payload as { detail: unknown }).detail
      : payload
  if (typeof detail === 'string') {
    return /^[a-z][a-z0-9_]+$/.test(detail) ? fallback : detail
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  return fallback
}

async function requestOnce<T>(path: string, credentials: SetupCredentials, init: RequestInit = {}): Promise<T> {
  const token = credentials.token.trim()
  const phone = credentials.phone.trim()
  if (!token || !phone) {
    throw new SetupConsoleApiError(401, 'Operator session is required.')
  }

  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  headers.set('X-HR-Phone', phone)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const response = await fetch(path, { ...init, headers })
  const payload: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new SetupConsoleApiError(
      response.status,
      errorMessageFromPayload(payload, 'The setup request could not be completed.'),
    )
  }
  return payload as T
}

async function request<T>(path: string, credentials: SetupCredentials, init: RequestInit = {}): Promise<T> {
  try {
    return await requestOnce<T>(path, credentials, init)
  } catch (error) {
    if (!(error instanceof SetupConsoleApiError) || error.status !== 401) throw error
    const stored = readStoredSession()
    const refreshed = await refreshSetupSession(stored?.refreshToken)
    if (!refreshed) {
      emitSessionChange(null)
      throw error
    }
    const next = credentialsFromSession(refreshed)
    emitSessionChange(next)
    return requestOnce<T>(path, next, init)
  }
}

export async function listCompanies(
  credentials: SetupCredentials,
  options: { q: string; limit: number; offset: number; includeInactive?: boolean },
): Promise<CompanyListResponse> {
  const search = new URLSearchParams({
    q: options.q,
    limit: String(options.limit),
    offset: String(options.offset),
  })
  if (options.includeInactive) search.set('include_inactive', 'true')
  const payload = await request<
    CompanyListResponse | CompanySummary[] | { items?: CompanySummary[]; total?: number; total_count?: number }
  >(`${SETUP_ROOT}/companies?${search.toString()}`, credentials)

  if (Array.isArray(payload)) {
    return { companies: payload, total: payload.length, limit: options.limit, offset: options.offset }
  }
  const result = payload as Partial<CompanyListResponse> & { items?: CompanySummary[]; total_count?: number }
  const companies = Array.isArray(result.companies)
    ? result.companies
    : Array.isArray(result.items)
      ? result.items
      : []
  return {
    companies,
    total:
      typeof result.total_count === 'number'
        ? result.total_count
        : typeof result.total === 'number'
          ? result.total
          : companies.length,
    limit: typeof result.limit === 'number' ? result.limit : options.limit,
    offset: typeof result.offset === 'number' ? result.offset : options.offset,
  }
}

export function getCompany(credentials: SetupCredentials, companyCode: string) {
  return request<CompanyDetailResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}`,
    credentials,
  )
}

export function createCompany(credentials: SetupCredentials, input: CompanyCreateInput) {
  return request<{ created?: boolean; readiness?: unknown }>(`${SETUP_ROOT}/companies`, credentials, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateCompanyProfile(
  credentials: SetupCredentials,
  companyCode: string,
  input: CompanyProfileInput,
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/profile`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function updateCompanyModules(
  credentials: SetupCredentials,
  companyCode: string,
  modules: string[],
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/modules`,
    credentials,
    { method: 'PATCH', body: JSON.stringify({ modules }) },
  )
}

export function updateCompanySettings(
  credentials: SetupCredentials,
  companyCode: string,
  settings: Record<string, unknown>,
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/settings`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(settings) },
  )
}

export function createOwner(credentials: SetupCredentials, companyCode: string, input: OwnerInput) {
  return request<OwnerResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/owner`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function updateCompanyLifecycle(
  credentials: SetupCredentials,
  companyCode: string,
  input: CompanyLifecycleInput,
) {
  return request<CompanyLifecycleResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/lifecycle`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function linkHrWhatsApp(credentials: SetupCredentials, companyCode: string, phone: string) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/whatsapp-link`,
    credentials,
    { method: 'POST', body: JSON.stringify({ phone }) },
  )
}

export function saveChannelAccount(
  credentials: SetupCredentials,
  companyCode: string,
  input: ChannelAccountInput,
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/channel-account`,
    credentials,
    { method: 'PUT', body: JSON.stringify(input) },
  )
}

export function deleteChannelAccount(credentials: SetupCredentials, companyCode: string) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/channel-account`,
    credentials,
    { method: 'DELETE' },
  )
}

export function getCompanyEmailAdmin(credentials: SetupCredentials, companyCode: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/email`,
    credentials,
  )
}

export function seedCompanyEmailMailboxes(credentials: SetupCredentials, companyCode: string, domain: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/email/mailboxes/seed`,
    credentials,
    { method: 'POST', body: JSON.stringify({ domain }) },
  )
}

export function patchCompanyEmailMailbox(
  credentials: SetupCredentials,
  companyCode: string,
  mailboxId: string,
  body: { status?: string; allow_send?: boolean; exchange_scope_ref?: string; entra_user_id?: string },
) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/email/mailboxes/${encodeURIComponent(mailboxId)}`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function probeCompanyEmailMailbox(credentials: SetupCredentials, companyCode: string, mailboxId: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/email/mailboxes/${encodeURIComponent(mailboxId)}/probe`,
    credentials,
    { method: 'POST' },
  )
}

export function createCompanyEmailDomain(credentials: SetupCredentials, companyCode: string, domain: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/email/domains`,
    credentials,
    { method: 'POST', body: JSON.stringify({ domain }) },
  )
}

export function refreshCompanyEmailDomain(credentials: SetupCredentials, companyCode: string, domainId: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/email/domains/${encodeURIComponent(domainId)}/refresh`,
    credentials,
    { method: 'POST' },
  )
}

export function forceCompanyEmailWathefni(credentials: SetupCredentials, companyCode: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/email/force-wathefni`,
    credentials,
    { method: 'POST' },
  )
}

export function getWizardSteps(credentials: SetupCredentials, locale = 'en') {
  return request<{ ok: boolean; steps: Array<{ step: number; key: string; label: string }>; purchasable_modules: Array<{ key: string; label: string; suite: string; depends_on: string[] }> }>(
    `${SETUP_ROOT}/wizard/steps?locale=${encodeURIComponent(locale)}`,
    credentials,
  )
}

export function createWizardDraft(
  credentials: SetupCredentials,
  input: { company_code?: string; synthetic?: boolean; locale?: string; idempotency_key?: string },
) {
  return request<{ ok: boolean; draft_id: string; current_step: number; draft_json: Record<string, unknown>; steps: unknown[] }>(
    `${SETUP_ROOT}/wizard/drafts`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function getWizardDraft(credentials: SetupCredentials, draftId: string) {
  return request<{ ok: boolean; draft: Record<string, unknown>; steps: Array<{ step: number; key: string; label: string }> }>(
    `${SETUP_ROOT}/wizard/drafts/${encodeURIComponent(draftId)}`,
    credentials,
  )
}

export function saveWizardDraft(
  credentials: SetupCredentials,
  draftId: string,
  input: { patch: Record<string, unknown>; current_step?: number },
) {
  return request<{ ok: boolean; current_step: number; autosaved?: boolean; draft_json: Record<string, unknown> }>(
    `${SETUP_ROOT}/wizard/drafts/${encodeURIComponent(draftId)}`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function validateWizardStep(credentials: SetupCredentials, draftId: string, step: number) {
  return request<{ ok: boolean; blockers: Array<{ code: string; remediation: string }>; warnings: Array<{ code: string; remediation: string }> }>(
    `${SETUP_ROOT}/wizard/drafts/${encodeURIComponent(draftId)}/validate/${step}`,
    credentials,
    { method: 'POST', body: '{}' },
  )
}

export function getCompanyControl(credentials: SetupCredentials, companyCode: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/control`,
    credentials,
  )
}

export function getLaunchReadiness(credentials: SetupCredentials, companyCode: string) {
  return request<LaunchReadinessResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/launch-readiness`,
    credentials,
  )
}

export type EmployeeAppAccessPolicy = {
  ok?: boolean
  company_code?: string
  module_enabled: boolean
  access_mode: 'all' | 'selected'
  ux_mode?: 'everyone' | 'departments' | 'employees'
  selection_scope?: 'departments' | 'employees' | null
  selected_departments: string[]
  selected_department_org_unit_ids?: string[]
  selected_department_org_unit_labels?: Record<string, string>
  selected_employee_keys?: string[]
  departments?: Array<{
    org_unit_id?: string
    id?: string
    name: string
    status?: string
    unit_key?: string
    active_employee_count?: number
  }>
  policy_attention?: {
    needs_attention?: boolean
    reasons?: string[]
    ambiguous_names?: Array<{ name: string; matches?: Array<{ org_unit_id?: string; name?: string; status?: string }> }>
    unresolved_names?: string[]
    archived_org_unit_ids?: string[]
    missing_org_unit_ids?: string[]
    message_en?: string | null
    message_ar?: string | null
  }
  name_migration?: Record<string, unknown>
  company_app_status?: string
  ops_deep_link?: string
  future_hire?: string
  large_removal_threshold?: number
  phase?: string
}

export type EmployeeAppAccessPreview = {
  ok?: boolean
  module_enabled?: boolean
  will_gain_access: number
  will_lose_access: number
  unchanged: number
  active_sessions_affected: number
  pending_invites_affected?: number
  requires_large_removal_confirm: boolean
  message_en?: string
  message_ar?: string
  sample_gain?: string[]
  sample_lose?: string[]
  drilldown_available?: boolean
}

export type EmployeeAppAccessEmployee = {
  employee_key: string
  name?: string | null
  phone?: string | null
  email?: string | null
  department?: string | null
  department_org_unit_id?: string | null
  employment_status?: string | null
  app_access_enabled?: boolean
  reason?: string
}

export function getEmployeeAppAccessPolicy(credentials: SetupCredentials, companyCode: string) {
  return request<EmployeeAppAccessPolicy>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/employee-app-access`,
    credentials,
  )
}

export function previewEmployeeAppAccessPolicy(
  credentials: SetupCredentials,
  companyCode: string,
  input: {
    ux_mode: 'everyone' | 'departments' | 'employees'
    selected_departments?: string[]
    selected_department_org_unit_ids?: string[]
    selected_employee_keys?: string[]
  },
) {
  return request<EmployeeAppAccessPreview>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/employee-app-access/preview`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function previewEmployeeAppAccessDrilldown(
  credentials: SetupCredentials,
  companyCode: string,
  input: {
    ux_mode: 'everyone' | 'departments' | 'employees'
    bucket: 'gain' | 'lose' | 'unchanged'
    selected_department_org_unit_ids?: string[]
    selected_employee_keys?: string[]
    q?: string
    limit?: number
    offset?: number
  },
) {
  return request<{
    ok?: boolean
    bucket: string
    total_count: number
    employees: EmployeeAppAccessEmployee[]
    has_more: boolean
    next_offset?: number | null
  }>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/employee-app-access/preview/details`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function resolveEmployeeAppAccessAttention(
  credentials: SetupCredentials,
  companyCode: string,
  input: {
    remove_org_unit_ids?: string[]
    replace_org_unit_ids?: Array<{ from: string; to: string }>
    reason: string
  },
) {
  return request<{ ok: boolean; policy?: EmployeeAppAccessPolicy }>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/employee-app-access/resolve-attention`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function searchEmployeeAppAccessEmployees(
  credentials: SetupCredentials,
  companyCode: string,
  options: {
    q?: string
    limit?: number
    offset?: number
    department_org_unit_id?: string
    employment_status?: string
    selected_only?: boolean
    selected_keys?: string[]
  } = {},
) {
  const params = new URLSearchParams()
  if (options.q) params.set('q', options.q)
  if (options.limit != null) params.set('limit', String(options.limit))
  if (options.offset != null) params.set('offset', String(options.offset))
  if (options.department_org_unit_id) params.set('department_org_unit_id', options.department_org_unit_id)
  if (options.employment_status) params.set('employment_status', options.employment_status)
  if (options.selected_only) params.set('selected_only', 'true')
  if (options.selected_keys?.length) params.set('selected_keys', options.selected_keys.join(','))
  const qs = params.toString()
  return request<{
    ok?: boolean
    employees: EmployeeAppAccessEmployee[]
    total_count: number
    has_more: boolean
    next_offset?: number | null
    page_size_max?: number
  }>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/employee-app-access/employees${qs ? `?${qs}` : ''}`,
    credentials,
  )
}

export function updateEmployeeAppAccessPolicy(
  credentials: SetupCredentials,
  companyCode: string,
  input: {
    access_mode?: 'all' | 'selected'
    selected_departments?: string[]
    selected_department_org_unit_ids?: string[]
    selected_employee_keys?: string[]
    selection_scope?: 'departments' | 'employees'
    ux_mode?: 'everyone' | 'departments' | 'employees'
    sync_invites?: boolean
    apply_reconcile?: boolean
    confirm_large_impact?: boolean
    reason?: string
  },
) {
  return request<{ ok: boolean; policy?: EmployeeAppAccessPolicy; preview?: EmployeeAppAccessPreview; reconcile?: Record<string, unknown>; noop?: boolean }>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/employee-app-access`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function getSetupOwnershipContract(credentials: SetupCredentials) {
  return request<Record<string, unknown>>(`${SETUP_ROOT}/ownership`, credentials)
}

export type PayrollSetupResponse = {
  ok?: boolean
  phase?: string
  company_code?: string
  module_enabled?: boolean
  payroll_mode?: string
  product_mode?: string
  attendance_payroll_mode?: string | null
  attendance_ux?: string
  attendance_choices?: Array<{ key: string; label_en: string; label_ar: string }>
  setup_extras?: {
    payroll_frequency?: string
    cutoff_day?: number | null
    period_end_rule?: string
    working_calendar_note?: string
    weekend_days?: string[]
    working_days?: string[]
    calendar_configured?: boolean
  }
  working_calendar?: {
    weekend_days?: string[]
    working_days?: string[]
    configured?: boolean
    note?: string
    holiday_year?: number
    holidays?: Array<{ holiday_date?: string; name?: string }>
    holiday_count?: number
    ownership?: Record<string, string>
  }
  statutory_inputs?: {
    incomplete?: number
    complete?: number
    missing_category_count?: number
    missing_pifss_wage_count?: number
    sample_missing_category?: Array<{ employee_key?: string; name?: string }>
    sample_missing_pifss_wage?: Array<{ employee_key?: string; name?: string }>
    message_en?: string
    message_ar?: string
    ops_deep_link?: string
  }
  variance_policy?: {
    gross_delta_abs?: number
    net_delta_abs?: number
    gross_delta_pct?: number
    net_delta_pct?: number
    advisory_only?: boolean
    never_rewrites_money?: boolean
  }
  allowlist?: {
    active_count?: number
    employees?: Array<{ employee_key?: string; reason?: string }>
  }
  finalize_policy?: {
    persisted?: boolean
    require_review_step?: boolean
    require_distinct_approver?: boolean
    allow_approver_as_finalizer?: boolean
    enterprise_sod_strict?: boolean
  }
  entitlement?: { state?: string; mode_a_opt_in?: boolean }
  approved_policy?: Record<string, unknown> | null
  approved_compensation_contracts?: number
  readiness?: {
    state?: string
    label_en?: string
    label_ar?: string
    ok?: boolean
    issues?: Array<{
      code?: string
      field?: string
      message_en?: string
      message_ar?: string
      how_to_fix?: string
      fix_href?: string
      severity?: string
      count?: number
    }>
    blockers?: Array<{
      code?: string
      field?: string
      message_en?: string
      message_ar?: string
      how_to_fix?: string
      fix_href?: string
      severity?: string
    }>
    attention?: Array<{
      code?: string
      field?: string
      message_en?: string
      message_ar?: string
      how_to_fix?: string
      fix_href?: string
      severity?: string
      count?: number
    }>
  }
  wathefni_owned?: {
    kuwait_statutory_baseline_version?: string
    calculation_engine?: string
    authority_sealing_rules?: string
    payment_processing?: string
    company_editable?: boolean
  }
  ops_deep_link?: string
}

export function getPayrollSetup(credentials: SetupCredentials, companyCode: string) {
  return request<PayrollSetupResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/payroll-setup`,
    credentials,
  )
}

export type ModulePolicyPayload = {
  ok?: boolean
  module_key?: string
  module_enabled?: boolean
  inactive?: boolean
  setup_status?: string
  summary_en?: string
  summary_ar?: string
  policies?: Array<{
    leave_type?: string
    days_per_year?: number
    eligibility_months?: number
    accrual_method?: string
    weekend_days?: string[]
    exclude_public_holidays?: boolean
    allow_negative?: boolean
  }>
  required?: Record<string, unknown>
  optional?: Record<string, unknown>
  advanced?: Record<string, unknown>
  calendar_reference?: { weekend_days?: string[]; setup_href?: string }
  ops_deep_link?: string
}

export type ModulePoliciesResponse = {
  ok: boolean
  phase?: string
  company_code?: string
  leave?: ModulePolicyPayload
  attendance?: ModulePolicyPayload
  shifts?: ModulePolicyPayload
  documents?: ModulePolicyPayload
  onboarding?: ModulePolicyPayload
  requisitions?: ModulePolicyPayload
  preboarding?: ModulePolicyPayload
  probation?: ModulePolicyPayload
  onboarding_auto_start?: ModulePolicyPayload
  wave1?: Record<string, unknown>
  cross_module?: Record<string, string>
}

export function getModulePolicies(credentials: SetupCredentials, companyCode: string) {
  return request<ModulePoliciesResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/module-policies`,
    credentials,
  )
}

export type TeamAccessMember = {
  user_id?: string
  name?: string
  email?: string
  phone?: string
  role?: string
  role_label_en?: string
  role_label_ar?: string
  status?: string
  access_summary_en?: string
  access_summary_ar?: string
  access_keys?: string[]
}

export type TeamAccessResponse = {
  ok: boolean
  company_code?: string
  members?: TeamAccessMember[]
  active_owner_count?: number
  pending_invites?: number
  role_presets?: Array<{
    role: string
    label_en?: string
    label_ar?: string
    access_summary_en?: string
    access_summary_ar?: string
    can_manage_team?: boolean
  }>
  ownership?: Record<string, string>
  safety?: Record<string, unknown>
}

export function getTeamAccess(credentials: SetupCredentials, companyCode: string) {
  return request<TeamAccessResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/team-access`,
    credentials,
  )
}

export type IntegrationCatalogCard = {
  key: string
  label_en?: string
  label_ar?: string
  purpose_en?: string
  purpose_ar?: string
  status?: string
  has_credentials?: boolean
  credentials_label_en?: string
  credentials_label_ar?: string
  detail_en?: string
  detail_ar?: string
  configure_href?: string
  activity_href?: string | null
  family?: string
}

export type IntegrationsCatalogResponse = {
  ok: boolean
  company_code?: string
  cards?: IntegrationCatalogCard[]
  ownership?: Record<string, string>
  honesty?: Record<string, unknown>
}

export function getIntegrationsCatalog(credentials: SetupCredentials, companyCode: string) {
  return request<IntegrationsCatalogResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/integrations-catalog`,
    credentials,
  )
}

export function updateModulePolicy(
  credentials: SetupCredentials,
  companyCode: string,
  moduleKey: string,
  input: Record<string, unknown>,
) {
  return request<{ ok: boolean; policy?: ModulePolicyPayload; actions?: unknown[] }>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/module-policies/${encodeURIComponent(moduleKey)}`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function updatePayrollSetup(
  credentials: SetupCredentials,
  companyCode: string,
  input: Record<string, unknown>,
) {
  return request<{ ok: boolean; setup?: PayrollSetupResponse; actions?: unknown[]; mode_switch_audited?: boolean }>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/payroll-setup`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function searchPayrollAllowlistCandidates(
  credentials: SetupCredentials,
  companyCode: string,
  options: { q?: string; limit?: number; offset?: number } = {},
) {
  const params = new URLSearchParams()
  if (options.q) params.set('q', options.q)
  if (options.limit != null) params.set('limit', String(options.limit))
  if (options.offset != null) params.set('offset', String(options.offset))
  const qs = params.toString()
  return request<{
    employees: Array<{ employee_key: string; name?: string; phone?: string; on_allowlist?: boolean }>
    total_count: number
    has_more: boolean
  }>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/payroll-setup/allowlist-candidates${qs ? `?${qs}` : ''}`,
    credentials,
  )
}

export function getProviders(credentials: SetupCredentials) {
  return request<{ ok: boolean; providers: Array<{ provider_key: string; label: string; support_tier: string; selectable: boolean; notes: string }> }>(
    `${SETUP_ROOT}/providers`,
    credentials,
  )
}

export function runCompanyReadiness(credentials: SetupCredentials, companyCode: string, moduleKey?: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/readiness/run`,
    credentials,
    { method: 'POST', body: JSON.stringify({ module_key: moduleKey || null }) },
  )
}

export function previewImpact(
  credentials: SetupCredentials,
  companyCode: string,
  input: { action: string; module_key?: string },
) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/impact-preview`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function moduleLifecycleAction(
  credentials: SetupCredentials,
  companyCode: string,
  moduleKey: string,
  input: { action: string; reason?: string },
) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/modules/${encodeURIComponent(moduleKey)}/lifecycle`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function previewOffboarding(credentials: SetupCredentials, companyCode: string) {
  return request<Record<string, unknown>>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/offboarding/preview`,
    credentials,
    { method: 'POST', body: '{}' },
  )
}
