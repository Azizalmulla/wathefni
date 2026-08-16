import type { CompanyBrandIdentity } from '@/branding/CompanyBrand'

export type Locale = 'en' | 'ar'
export type WorkspaceKey = 'hr' | 'recruiting' | 'owner'

export type FeatureCapability = {
  enabled: boolean
  actions: string[]
  reason?: string
  advisory?: boolean
  confirmation_required?: boolean
}

export type WorkspaceCapability = {
  enabled: boolean
  features: Record<string, FeatureCapability>
  reason?: string
}

export type MobileMe = {
  ok: true
  company_identity: CompanyBrandIdentity
  principal: {
    user_id: string
    company_code: string
    display_name: string
    email: string
    role: string
    role_label: string
  }
  permission_authority: 'backend_current'
  account_state: string
  company_state: string
  workspaces: Record<WorkspaceKey, WorkspaceCapability>
  scope: {
    restricted: boolean
    binding: string
    configured: boolean
    configuration_error: string | null
  }
}

export type AuthResponse = {
  ok: true
  access_token: string
  refresh_token: string
  expires_at: string
  refresh_expires_at: string
  channel: 'operator_mobile'
  me: MobileMe
}

export type PriorityItem = {
  type: string
  target_id: string
  summary: string
  status: string
  timestamp: string | null
  due_context: Record<string, unknown> | null
  permitted_actions: string[]
  destination: string
  severity: string | null
}

export type PrioritySection = {
  type: string
  title: string
  total: number
  items: PriorityItem[]
}

export type PrioritiesResponse = {
  ok: true
  generated_at: string
  ranking_policy: 'separated_authoritative_sections_no_invented_urgency'
  sections: PrioritySection[]
}

export type PersonIdentity = {
  employee_key?: string
  name: string
  position_title?: string | null
  department?: string | null
  employment_status?: string | null
  /** Person-level onboarding — exceptional People chip only when incomplete. */
  onboarding_status?: string | null
}

export type LeaveRequest = {
  leave_id: string
  employee: PersonIdentity
  leave_type: string | null
  start_date: string
  end_date: string
  duration_days: number | null
  reason: string | null
  status: string
  decision_note: string | null
  requested_at: string | null
  updated_at: string | null
  shift_conflict_count: number
  balance: unknown
  allowed_actions: string[]
  destination: string
}

export type CandidateReview = {
  app_key: string
  overview: {
    candidate?: { name?: string; email?: string }
    position?: { code?: string; title?: string }
    status?: string
    status_label?: string
    canonical_stage?: string
    current_step?: string
    cv?: Record<string, unknown>
    assessment?: {
      attempt_id?: string
      assessment_version_id?: string
      battery_key?: string
      status?: 'pending' | 'in_progress' | 'completed' | 'cancelled' | 'expired' | string
      delivery_status?: 'pending' | 'sent' | 'failed' | 'intentionally_skipped' | string
      review_status?: 'unreviewed' | 'reviewed' | string
      percent?: number
      band?: string
      summary?: string
      expires_at?: string
      completed_at?: string
    }
    intake_source?: string
    cv_processing?: { status?: string; received?: boolean; automatic?: boolean }
    screening?: { status?: string; automatic?: boolean }
    communication?: {
      status?: string
      message_kind?: string | null
      sent_at?: string | null
      failed_at?: string | null
      last_error?: string | null
      stage_changed_without_contact?: boolean
    }
    automatic_activity?: string[]
    waiting_for_hr?: string[]
  }
  ranking: {
    score: number | null
    confidence: string | number | null
    reasons: string[]
    evidence: string[]
    concerns: string[]
    missing_evidence: string[]
    ai_advisory: true
  }
  cv: {
    available: boolean
    filename: string | null
    mime_type: string | null
    size_bytes: number | null
    preview_path: string | null
    download_path: string | null
  }
  interview: Record<string, unknown> | null
  communication_status: Array<Record<string, unknown>>
  /** Present when employment offers module returns payload for this application. */
  offer?: {
    current?: Record<string, unknown> | null
    items?: unknown[]
    allowed_actions?: string[]
  } | null
  allowed_actions: string[]
}

export type ConfirmationMaterial = {
  confirmation_id: string
  confirmation_hash: string
  action: string
  target: { type: string; id: string }
  summary: string
  consequence: string
  current_state: string
  expires_at: string
  status: string
  idempotent_replay?: boolean
}

export type DecisionResponse = {
  ok: boolean
  status: string
  confirmation: ConfirmationMaterial
  result: unknown
}

export type AllowedAction = string

export type MobileListMeta = {
  generated_at?: string | null
  stale?: boolean
  total?: number
  limit?: number
  offset?: number
  has_more?: boolean
}

export type HRTask = {
  task_id: string
  task_type?: string | null
  source?: string | null
  title: string
  /** Adapter `detail` — not an invented summary. */
  detail?: string | null
  employee?: PersonIdentity | null
  status: string
  priority?: string | null
  created_at?: string | null
  updated_at?: string | null
  destination?: string | null
  allowed_actions: AllowedAction[]
}

export type DocumentReview = {
  document_id: string
  source?: 'compliance' | 'onboarding' | null
  employee?: PersonIdentity | null
  name: string
  document_type?: string | null
  status: string
  status_label?: string | null
  expiry_date?: string | null
  days_until_expiry?: number | null
  last_checked_at?: string | null
  last_reminded_at?: string | null
  reminder_count?: number
  extraction_confidence?: number | null
  has_file?: boolean
  preview_path?: string | null
  download_path?: string | null
  destination?: string | null
  allowed_actions: AllowedAction[]
}

export type OnboardingChecklistItem = {
  item_id: string
  label: string
  item_type?: string | null
  document_type?: string | null
  required: boolean
  status: string
  /** Lifecycle group: being_reviewed | your_actions | … */
  group?: string | null
  is_bank_ess?: boolean
  has_file?: boolean
  preview_path?: string | null
  download_path?: string | null
  allowed_actions: AllowedAction[]
}

export type OnboardingEmployee = {
  employee_key: string
  employee: PersonIdentity
  status: string
  pending_count?: number
  received_count?: number
  hr_actionable_count?: number
  hr_mutate_enabled?: boolean
  hr_actionable_items?: OnboardingChecklistItem[]
  waiting_on_employee_items?: OnboardingChecklistItem[]
  /** HR-actionable items only (alias of hr_actionable_items). */
  items?: OnboardingChecklistItem[]
  allowed_actions: AllowedAction[]
}

export type AttendanceExceptionKind =
  | 'absence'
  | 'lateness'
  | 'early_leave'
  | 'missing_check_in'
  | 'missing_check_out'
  | 'incomplete_session'

export type AttendanceException = {
  attendance_id: string
  /** @deprecated use attendance_id — kept as alias for route keys */
  exception_id: string
  employee: PersonIdentity
  /** Canonical Ops kind — never invent mobile-only English labels. */
  exception_kind: AttendanceExceptionKind | null
  is_exception: boolean
  status: string
  attendance_date?: string | null
  scheduled_start?: string | null
  scheduled_end?: string | null
  check_in_at?: string | null
  check_out_at?: string | null
  late_minutes: number
  early_leave_minutes: number
  occurred_at?: string | null
  note?: string | null
  updated_at?: string | null
  /** request_correction when resolve is offered (authority may leave pending). */
  action_mode: 'request_correction' | 'read'
  allowed_actions: AllowedAction[]
  destination?: string | null
}

export type Shift = {
  shift_id: string
  employee: PersonIdentity
  /** Canonical L0 / ui status: scheduled | cancelled | conflicted | … — never invent mobile-only values. */
  status: string
  shift_date?: string | null
  starts_at?: string | null
  ends_at?: string | null
  location?: string | null
  role?: string | null
  timezone?: string | null
  updated_at?: string | null
  allowed_actions: AllowedAction[]
  destination?: string | null
}

export type ShiftSwapStatus = 'requested' | 'approved' | 'rejected' | 'cancelled' | string

export type ShiftSwap = {
  swap_id: string
  requester: PersonIdentity
  /** Canonical web field is target; UI may label Replacement. */
  replacement?: PersonIdentity | null
  status: ShiftSwapStatus
  shift_date?: string | null
  starts_at?: string | null
  ends_at?: string | null
  reason?: string | null
  decision_note?: string | null
  requested_at?: string | null
  decided_at?: string | null
  updated_at?: string | null
  requester_shift_id?: string | null
  target_shift_id?: string | null
  requester_shift?: Shift | null
  target_shift?: Shift | null
  allowed_actions: AllowedAction[]
  destination?: string | null
}

export type EmployeeSummary = {
  employee_key: string
  employee: PersonIdentity
  email?: string | null
  phone?: string | null
  started_on?: string | null
  allowed_actions: AllowedAction[]
}

export type DeliveryAlert = {
  alert_id: string
  title: string
  summary?: string | null
  status: string
  kind?: string | null
  channel?: string | null
  flow?: string | null
  flow_label?: string | null
  occurred_at?: string | null
  suggested_action?: string | null
  attempts?: number
  has_task?: boolean
  employee?: {
    employee_key?: string | null
    name?: string | null
  } | null
  destination?: string | null
  allowed_actions: AllowedAction[]
}

export type CandidateSummary = {
  app_key: string
  candidate: { name: string; email?: string | null }
  position?: { code?: string | null; title?: string | null }
  status: string
  canonical_stage?: string | null
  status_label?: string | null
  intake_source?: string | null
  communication_status?: string | null
  next_human_action?: string | null
  score?: number | null
  confidence?: string | number | null
  updated_at?: string | null
  allowed_actions: AllowedAction[]
}

export type InterviewSummary = {
  interview_id: string
  app_key?: string | null
  candidate: { name: string; email?: string | null }
  position?: { code?: string | null; title?: string | null }
  status: string
  application_stage?: string | null
  application_stage_label?: string | null
  interview_type?: string | null
  feedback_status?: string | null
  scheduled_at?: string | null
  scheduled_end?: string | null
  timezone?: string | null
  meeting?: { type?: string | null; join_url?: string | null }
  notes?: string | null
  communication_status?: string | null
  invitation_status?: string | null
  candidate_confirmation?: string | null
  notes_status?: string | null
  next_human_action?: string | null
  ai_summary?: Record<string, unknown>
  ai_advisory?: true
  updated_at?: string | null
  notes_version?: number | null
  allowed_actions: AllowedAction[]
}

export type PrehirePositionSummary = {
  position_code: string
  title?: string | null
  status?: string | null
  department?: string | null
  open_count?: number | null
  ready_for_review?: number | null
}

export type MobileCollection<T> = MobileListMeta & {
  ok: true
  items: T[]
}

export type MobileDetail<T> = MobileListMeta & {
  ok: true
  item: T
}

export type CandidatesCollection = MobileCollection<CandidateSummary> & {
  requires_position?: boolean
  ranking_unavailable?: boolean
  ranking_error?: string | null
  message?: string | null
}

export type PositionsCollection = MobileListMeta & {
  ok: true
  items: PrehirePositionSummary[]
}
