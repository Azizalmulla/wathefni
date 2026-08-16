// Mirrors the backend /app/* payload shapes. Keep in sync with the orchestrator's
// employee-app endpoints in wathefni-orchestrator/app.py.

import type { CompanyBrandIdentity } from '@/branding/CompanyBrand'

export type EmployeeProfile = {
  employee_key: string
  company_code: string
  name: string
  phone: string
  email: string
  position_title: string
  department: string
  onboarding_status: string
  locale: 'en' | 'ar'
}

/** Structured Profile sections from `/app/profile` — canonical fields only. */
export type ProfilePersonal = {
  name: string
  phone: string
  email: string
}

export type ProfileManager = {
  name: string
  phone: string
  employee_key?: string | null
}

export type ProfileEmployment = {
  position_title: string
  department: string
  employee_key: string
  company_code: string
  start_date: string | null
  employment_status: string
  manager: ProfileManager | null
}

export type ProfileResponse = {
  ok: boolean
  employee: EmployeeProfile
  personal: ProfilePersonal
  employment: ProfileEmployment
  onboarding?: {
    completion?: Record<string, unknown>
    completion_state?: string | null
    next_action?: string | null
    satisfied_count?: number
    status?: string | null
    required_total?: number
    received_count?: number
    pending_count?: number
    bank_collection?: Record<string, unknown> | null
  }
}

export type ActivateResponse = {
  ok: boolean
  token: string
  refresh_token: string
  expires_at: string
  employee: EmployeeProfile
  /** Phase 5 — true when activate revoked a prior active device session. */
  replaced_previous_device?: boolean
}

export type DeviceSecurityResponse = {
  ok: boolean
  device: {
    platform: 'ios' | 'android' | 'unknown' | string
    activated_at: string
    last_active_at: string
    status: 'active' | string
  }
}

export type EmployeeFeatureKey =
  | 'home'
  | 'profile'
  | 'inbox'
  | 'settings'
  | 'onboarding'
  | 'preboarding'
  | 'probation'
  | 'documents'
  | 'attendance'
  | 'shifts'
  | 'leave'
  | 'bank'
  | 'payslips'
  | 'performance'
  | 'talent'
  | 'learning'
  | 'benefits'
  | 'engagement'
  | 'compliance_actions'

export type EmployeeFeatureCapability = {
  enabled: boolean
  reason: string | null
  dependency_mode: 'core' | 'all' | 'any'
  module_keys: string[]
  actions: string[]
}

export type MeResponse = EmployeeProfile & {
  ok: boolean
  employee: EmployeeProfile
  company_identity: CompanyBrandIdentity
  account_state: 'active'
  app_state: 'available'
  version: string
  effective_modules: string[]
  enabled_modules: string[]
  enabled_features: EmployeeFeatureKey[]
  features: Record<EmployeeFeatureKey, EmployeeFeatureCapability>
  leave: {
    balances_enabled: boolean
    types: string[]
  }
  leave_balances_enabled: boolean
}

export type CivilIdPartSlot = {
  present?: boolean
  file_id?: string | null
  filename?: string | null
  mime_type?: string | null
  detected_side?: string | null
  hr_warning?: boolean
  uploaded_at?: string | null
}

export type CivilIdParts = {
  schema?: string
  legacy_single?: boolean
  parts_complete?: boolean
  missing?: string[]
  version_id?: string | null
  review_status?: string | null
  attempt_open?: boolean
  front?: CivilIdPartSlot
  back?: CivilIdPartSlot
}

export type OnboardingItem = {
  item_id?: string
  label?: string
  document_type?: string
  item_type?: string
  status?: string
  required?: boolean
  file_id?: string | null
  /** ISO date from shared onboarding_items.due_date when present. */
  due_date?: string | null
  authority?: string | null
  collection_mode?: string | null
  owner?: string | null
  responsible_party?: string | null
  waiting_on?: string | null
  actions?: string[]
  rejection_reason?: string | null
  replacement_required?: boolean
  completed_at?: string | null
  current_version_id?: string | null
  current_version_no?: number | null
  review_status?: string | null
  version_filename?: string | null
  group?: string | null
  legacy_status?: string | null
  /** Present on bank ESS checklist rows; mirrors /app/me.features.bank.eligibility.eligible. */
  bank_ess_eligible?: boolean | null
  civil_id_parts?: CivilIdParts | null
  parts_complete?: boolean
}

/** Canonical onboarding completion states. Backend: onboarding_completion_contract. */
export type OnboardingCompletionState =
  | 'not_started'
  | 'in_progress'
  | 'waiting_on_employee'
  | 'waiting_on_hr'
  | 'blocked'
  | 'completed'
  | 'reopened'

export type ContractNextAction = {
  owner?: 'employee' | 'hr' | 'system' | 'none' | string
  message?: string
  message_en?: string
  message_ar?: string
}

export type OnboardingCompletion = {
  contract_version?: string
  state?: OnboardingCompletionState | string
  reason?: string | null
  is_complete?: boolean
  required_total?: number
  satisfied_count?: number
  open_count?: number
  waiting_employee_count?: number
  waiting_hr_count?: number
  blocked_count?: number
  waiting_on_employee_items?: string[]
  waiting_on_hr_items?: string[]
  blocked_items?: string[]
  next_action?: ContractNextAction
  legacy_onboarding_status?: string | null
}

export type OnboardingResponse = {
  ok: boolean
  status: string | null
  /** Canonical completion snapshot. Never recompute completion in the app. */
  completion?: OnboardingCompletion
  next_action?: ContractNextAction
  lifecycle_version?: string | null
  required_total: number
  received_count: number
  pending_count: number
  accepted_count?: number
  items?: OnboardingItem[]
  groups?: {
    your_actions?: OnboardingItem[]
    being_reviewed?: OnboardingItem[]
    handled_by_others?: OnboardingItem[]
    completed?: OnboardingItem[]
  }
  your_actions?: OnboardingItem[]
  being_reviewed?: OnboardingItem[]
  handled_by_others?: OnboardingItem[]
  completed?: OnboardingItem[]
  pending: OnboardingItem[]
  received: OnboardingItem[]
  next_item: OnboardingItem | null
  can_upload: boolean
  bank_collection?: { mode?: string; plaintext_forbidden?: boolean; message?: string }
  /** Same eligibility object as /app/me.features.bank / /app/bank gate. */
  bank_ess?: { eligible?: boolean; reason?: string | null; contract_version?: string | null }
}

/**
 * Bank ESS. Backend: employee_bank_ess.employee_bank_status.
 *
 * `verified`, `payroll_effective` and `submission` are three separate authority
 * layers and must never be merged in the UI: what HR verified, what payroll
 * actually pays to, and what the employee last submitted can all differ.
 */
export type BankSubmissionState =
  | 'none'
  | 'draft'
  | 'pending_hr'
  | 'pending_payroll'
  | 'pending_review' // legacy alias for pending_hr
  | 'approved'
  | 'applied'
  | 'rejected'
  | 'needs_correction'
  | 'withdrawn'

/** Values are masked server-side. `<field>_last4` may accompany a masked field. */
export type BankDisplayValues = Record<string, string | boolean | null>

export type BankEvidenceRow = {
  evidence_id: string
  filename?: string | null
  mime_type?: string | null
  size_bytes?: number | null
  uploaded_at?: string | null
  request_id?: string | null
  extraction_status?: string | null
  extraction_confidence?: number | null
  extraction?: BankExtractionSummary | null
}

export type BankExtractionSummary = {
  status?: string
  confidence?: number
  field_confidence?: Record<string, number>
  proposed?: Partial<Record<string, string>>
  warnings?: string[]
  unreadable_reason?: string | null
  needs_manual_fallback?: boolean
  uncertain?: boolean
  missing_iban?: boolean
  wrong_document_type?: boolean
  authoritative?: boolean
  provider?: string | null
  model?: string | null
  document_type?: string | null
  evidence_id?: string
  masked?: boolean
}

export type BankEvidenceUploadResponse = {
  ok: boolean
  evidence_id: string
  filename?: string | null
  retention_until?: string | null
  extraction?: BankExtractionSummary
  proposed_fields?: Partial<Record<string, string>>
  needs_manual_fallback?: boolean
}

export type BankSubmission = {
  request_id: string
  state?: string | null
  submission_state?: BankSubmissionState | string
  submitted_at?: string | null
  updated_at?: string | null
  proposed?: {
    display?: BankDisplayValues
    fingerprint?: string | null
    fields_proposed?: string[]
    sealed?: boolean
    masked?: boolean
  } | null
  rejection_reason?: string | null
  can_withdraw?: boolean
  can_resubmit?: boolean
  evidence?: BankEvidenceRow[]
}

export type BankStatusResponse = {
  contract_version?: string
  employee_key?: string
  has_verified_bank?: boolean
  has_payroll_effective_bank?: boolean
  verified?: {
    display?: BankDisplayValues
    fingerprint?: string | null
    verified_at?: string | null
    verified_by_stage?: string | null
  } | null
  payroll_effective?: {
    display?: BankDisplayValues
    fingerprint?: string | null
    effective_from?: string | null
    bank_profile_version?: number | null
  } | null
  submission?: BankSubmission | null
  submission_state?: BankSubmissionState | string
  change_under_review?: boolean
  next_step?: ContractNextAction
  can_submit_new?: boolean
  masking?: {
    masked_by_default?: boolean
    reveal_requires_permission?: string
    reveal_is_audited?: boolean
  }
  validation_scheme?: string | { key?: string; scheme?: string } | null
}

export type BankMutationResponse = {
  ok: boolean
  idempotent?: boolean
  bank: BankStatusResponse
}

/**
 * A leave balance as `/app/leave` actually emits it.
 *
 * These names are the server's. An earlier version of this type invented
 * `balance_days`, `accrued_days` and `period_year`, none of which the API has
 * ever sent, so every optional field read as `undefined` and the screen printed
 * a confident `0` days for every leave type. Optional here means "the server may
 * omit it", and an omitted number must render as nothing, never as zero.
 */
export type LeaveBalance = {
  leave_type: string
  entitlement_days?: number
  accrued_to_date?: number
  consumed?: number
  /** Materialized rollup of the ledger: carried in + accrued + adjusted − consumed. */
  current_balance?: number
  /** Days held by pending requests. Null when the company has no reservation column. */
  reserved?: number | null
  /** `current_balance − reserved`. Null when reservations are not tracked. */
  available?: number | null
  /** Eligibility date; before it, the balance exists but cannot be taken. */
  can_take_from?: string | null
}

export type LeaveRequestRow = {
  leave_id: string
  start_date: string
  end_date: string
  leave_type: string | null
  status: string
  reason: string | null
  requested_at: string | null
  decided_at: string | null
}

export type LeaveResponse = {
  ok: boolean
  balances_enabled: boolean
  /**
   * Server-stated honesty. Balances are tracked but never block an approval, so
   * the app may show them as information and must not present them as an
   * allowance the employee is spending down.
   */
  balances_enforced?: boolean
  balances_binding?: boolean
  observe_only?: boolean
  types: string[]
  balances: LeaveBalance[]
  requests: LeaveRequestRow[]
}

/**
 * `/app/leave/history` — paginated leave requests beyond the `/app/leave` ~50 window.
 * Same request fields as the Leave root; no invented balance/policy facts.
 */
export type LeaveHistoryResponse = {
  ok: boolean
  locale: 'en' | 'ar'
  kind: 'leave_history'
  requests: LeaveRequestRow[]
  count: number
  has_more: boolean
  next_cursor: string | null
  limit: number
  ordering: 'start_date_desc'
  filters: {
    status: string | null
    date_from: string | null
    date_to: string | null
    year: number | null
  }
}

/**
 * `/app/leave/duration` — what a date range would actually charge.
 *
 * The company's rest days and public holidays decide this, and the app has
 * neither, so it asks. `available: false` means the server declined to answer
 * and the app shows nothing rather than counting calendar days itself.
 */
export type LeaveDurationResponse = {
  ok: boolean
  available: boolean
  reason?: string
  chargeable_days?: number
  calendar_days?: number
  basis?: string
  excludes_public_holidays?: boolean
}

export type ShiftRow = {
  shift_id: string
  shift_date: string
  start_time: string | null
  end_time: string | null
  status: string
  role: string | null
  location: string | null
}

export type AttendanceRow = {
  attendance_date: string
  status: string
}

export type AttendanceResponse = {
  ok: boolean
  window_days: number
  summary: { present: number; late: number; absent: number }
  records: AttendanceRow[]
}

/** Per-module read truth from the server projection. `loading` is client-side only. */
export type HomeModuleReadState = 'disabled' | 'loading' | 'error' | 'ready'

export type WorkdayScheduled = {
  shift_id: string | null
  date: string
  start_time: string | null
  end_time: string | null
  status: string
  role: string | null
  location: string | null
  timezone: string
  notes: string | null
}

/** The canonical attendance record as HR recorded it. Nothing here is client-derived. */
export type WorkdayRecorded = {
  attendance_id: string | null
  shift_id: string | null
  date: string
  status: string
  scheduled_start: string | null
  scheduled_end: string | null
  check_in_at: string | null
  check_out_at: string | null
  late_minutes: number
  early_leave_minutes: number
  notes: string | null
}

export type WorkdayEntry = {
  kind: 'scheduled' | 'recorded_only'
  scheduled: WorkdayScheduled | null
  recorded: WorkdayRecorded | null
}

/**
 * `/app/workday` — read-only Schedule projection over the existing Shifts and
 * Attendance authorities. An authority that is off or unreadable reports its state and
 * carries `null`, so "not available" is never rendered as "nothing scheduled".
 */
export type WorkdayResponse = {
  ok: boolean
  locale: 'en' | 'ar'
  date: string
  authority: {
    shifts: HomeModuleReadState
    attendance: HomeModuleReadState
    shifts_upcoming: HomeModuleReadState
  }
  today: {
    entries: WorkdayEntry[]
    scheduled_count: number | null
    recorded_count: number | null
  }
  upcoming: WorkdayScheduled[] | null
  recent: WorkdayRecorded[] | null
  window: { days: number; summary: { present: number; late: number; absent: number } } | null
  read_only: {
    employee_clocking: boolean
    attendance_correction: boolean
    payroll_effect: boolean
    authority: string
    authority_ar: string
  }
}

/**
 * `/app/schedule/history` — paginated recorded attendance beyond the workday window.
 * `scheduled` is present only when the API resolved a canonical shift_id; never invent it.
 */
export type ScheduleHistoryRecord = {
  recorded: WorkdayRecorded
  scheduled: WorkdayScheduled | null
}

export type ScheduleHistoryResponse = {
  ok: boolean
  locale: 'en' | 'ar'
  kind: 'attendance_history'
  authority: {
    attendance: HomeModuleReadState
    shifts: HomeModuleReadState
  }
  records: ScheduleHistoryRecord[] | null
  count: number | null
  has_more: boolean
  next_cursor: string | null
  limit: number
  ordering: 'attendance_date_desc'
  bounds: {
    date_from: string | null
    date_to: string
  }
  read_only: {
    employee_clocking: boolean
    attendance_correction: boolean
    payroll_effect: boolean
    authority: string
    authority_ar: string
  }
}

export type HomeTaskRow = {
  kind: string
  module: string
  count: number
  severity: 'action_required' | 'informational'
}

/**
 * `/app/home` — server-owned Home projection. Owning modules supply every fact; a
 * module that could not be read reports `error` and carries no value, so the client
 * never turns a failed read into an empty business statement.
 */
export type HomeResponse = {
  ok: boolean
  locale: 'en' | 'ar'
  date: string
  modules: Record<
    'shifts' | 'attendance' | 'leave' | 'onboarding' | 'documents' | 'payslips' | 'notifications',
    HomeModuleReadState
  >
  today: {
    shifts: ShiftRow[] | null
    shift_count: number | null
    attendance: { date: string; status: string } | null
  }
  attendance_window: { window_days: number; summary: { present: number; late: number; absent: number } } | null
  onboarding: {
    state?: string | null
    is_complete?: boolean
    suppress_checklist?: boolean
    required_total: number
    satisfied_count: number
    pending_count: number
    employee_action_required?: boolean
  } | null
  tasks: HomeTaskRow[]
  inbox: { unread: number }
  caught_up: boolean
}

export type EmployeeDocument = {
  file_id: string
  document_type: string | null
  label: string | null
  item_id: string | null
  filename: string | null
  mime_type: string | null
  size_bytes: number | null
  stored_at: string | null
  has_file: boolean
}

export type ComplianceJourneyItem = {
  document_type: string
  label: string
  label_ar?: string
  review_status: string
  review_status_label: string
  expiry_date?: string | null
  issue_date?: string | null
  rejection_reason?: string | null
  renewal_required?: boolean
  can_renew?: boolean
  current_file_id?: string | null
  pending_version_id?: string | null
  ocr_proposal?: Record<string, unknown> | null
  ocr_authoritative?: boolean
  legitimacy_note?: string
  versions?: Array<{
    version_id: string
    version_no: number
    review_status: string
    is_current: boolean
    file_id?: string | null
    expiry_date?: string | null
  }>
}

export type DocumentsResponse = {
  ok: boolean
  count: number
  documents: EmployeeDocument[]
  compliance?: ComplianceJourneyItem[]
  legitimacy_note?: string
}

export type NotificationItem = {
  id: string
  flow: string
  title: string
  body: string | null
  status: string
  created_at: string
  read: boolean
  deep_link?: { path?: string; payslip_id?: string | null } | null
}

export type NotificationsResponse = {
  ok: boolean
  unread: number
  notifications: NotificationItem[]
}

export type PayslipListItem = {
  payslip_id: string
  period_start: string
  period_end: string
  net: number | string
  currency: string
  status: string
  released_at?: string | null
  official_document?: boolean
  download_available?: boolean
}

export type PayslipsResponse = {
  ok: boolean
  count: number
  payslips: PayslipListItem[]
  /** True when another keyset page exists beyond this response. */
  has_more?: boolean
  /** Opaque cursor for the next page; omit or null on the last page. */
  next_cursor?: string | null
  limit?: number
  honesty?: { en?: string; ar?: string }
  locale?: string
}

export type PayslipDetailResponse = {
  ok: boolean
  payslip: {
    payslip_id: string
    period_start: string
    period_end: string
    version_number?: number
    status: string
    released_at?: string | null
    currency: string
    totals: { earnings: number | string; deductions: number | string; net: number | string }
    payment_date: string | null
    official_document: boolean
    download_available: boolean
    download_kind?: string
    honesty?: { en?: string; ar?: string }
  }
  lines: Array<{ line_kind: string; code?: string; label?: string; amount: number | string; currency: string }>
  earnings?: Array<{ line_kind: string; label?: string; amount: number | string; currency: string }>
  deductions?: Array<{ line_kind: string; label?: string; amount: number | string; currency: string }>
  locale?: string
}
