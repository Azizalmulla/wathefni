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
}

export type HRTask = {
  task_id: string
  title: string
  summary?: string | null
  status: string
  due_at?: string | null
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
  submitted_at?: string | null
  preview_path?: string | null
  download_path?: string | null
  allowed_actions: AllowedAction[]
}

export type OnboardingChecklistItem = {
  item_id: string
  label: string
  item_type?: string | null
  document_type?: string | null
  required: boolean
  status: string
  preview_path?: string | null
  download_path?: string | null
  allowed_actions: AllowedAction[]
}

export type OnboardingEmployee = {
  employee_key: string
  employee: PersonIdentity
  status: string
  start_date?: string | null
  current_step?: string | null
  documents?: DocumentReview[]
  items?: OnboardingChecklistItem[]
  allowed_actions: AllowedAction[]
}

export type AttendanceException = {
  exception_id: string
  employee: PersonIdentity
  exception_type: string
  status: string
  occurred_at?: string | null
  note?: string | null
  allowed_actions: AllowedAction[]
}

export type Shift = {
  shift_id: string
  employee: PersonIdentity
  status: string
  starts_at?: string | null
  ends_at?: string | null
  location?: string | null
  allowed_actions: AllowedAction[]
}

export type ShiftSwap = {
  swap_id: string
  requester: PersonIdentity
  replacement?: PersonIdentity | null
  status: string
  starts_at?: string | null
  ends_at?: string | null
  reason?: string | null
  allowed_actions: AllowedAction[]
}

export type EmployeeSummary = {
  employee_key: string
  employee: PersonIdentity
  email?: string | null
  phone?: string | null
  started_on?: string | null
  manager_name?: string | null
  allowed_actions: AllowedAction[]
}

export type DeliveryAlert = {
  alert_id: string
  title: string
  summary?: string | null
  status: string
  channel?: string | null
  occurred_at?: string | null
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
  allowed_actions: AllowedAction[]
}

export type MobileCollection<T> = MobileListMeta & {
  ok: true
  items: T[]
}

export type MobileDetail<T> = MobileListMeta & {
  ok: true
  item: T
}
