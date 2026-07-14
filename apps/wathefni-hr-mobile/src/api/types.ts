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
    current_step?: string
    cv?: Record<string, unknown>
    assessment?: unknown
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
