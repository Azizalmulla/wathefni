export type DashboardAccess = {
  token: string
  hrPhone: string
  companyCode: string
  email?: string
  password?: string
}

export type DashboardUserAccess = {
  role?: string
  role_label?: string
  permissions?: string[]
  auth_source?: string
  is_recovery_access?: boolean
  is_platform_admin?: boolean
  user?: {
    user_id?: string
    email?: string
    phone?: string
    name?: string
    role?: string
    role_label?: string
    status?: string
    company_code?: string
    last_active_at?: string | null
    auth_source?: string
    is_recovery_access?: boolean
  }
}

export type DashboardTeamUser = {
  user_id: string
  company_code?: string
  email?: string
  name?: string
  phone?: string
  role: string
  role_label?: string
  status: 'active' | 'invited' | 'disabled' | string
  last_active_at?: string | null
  permissions?: string[]
  auth_source?: string
  is_recovery_access?: boolean
  whatsapp_linked?: boolean
  directory_view?: string
  is_self?: boolean
}

export type DashboardTeamInvite = {
  invite_id: string
  company_code: string
  email: string
  role: string
  status: string
  expires_at?: string
  created_at?: string
}

export type DashboardTeamResponse = {
  company_code: string
  users: DashboardTeamUser[]
  invites: DashboardTeamInvite[]
  role_capabilities?: Record<string, string[]>
  directory_view?: string
  can_manage_team?: boolean
}

// --- Attendance Import -----------------------------------------------------
export type AttendanceImportRecord = {
  employee_key: string
  employee_name?: string | null
  attendance_date: string
  shift_id?: string | null
  check_in_at?: string | null
  check_out_at?: string | null
  status?: string
  late_minutes?: number
  outcome?: string
  issue_codes?: string[]
}

export type AttendanceImportProblem = {
  row_number?: number
  external_id?: string
  name_hint?: string | null
  outcome: string
  issue_codes: string[]
}

export type AttendanceImportUnmatched = {
  external_id: string
  name_hint?: string | null
  count: number
}

export type AttendanceImportCounts = {
  punches?: number
  records?: number
  skipped_locked?: number
  incomplete?: number
  unmatched?: number
  duplicates?: number
  errors?: number
}

export type AttendanceImportPreview = {
  ok: boolean
  headers?: string[]
  suggested_mapping?: Record<string, string>
  applied_mapping?: Record<string, string>
  dropped_biometric?: string[]
  records: AttendanceImportRecord[]
  problems: AttendanceImportProblem[]
  unmatched: AttendanceImportUnmatched[]
  counts: AttendanceImportCounts
  period?: { start: string | null; end: string | null }
}

export type AttendanceImportCommitResponse = {
  ok: boolean
  batch_id: string
  applied: number
  skipped_locked: number
  counts: AttendanceImportCounts
  preview: AttendanceImportPreview
}

export type AttendanceImportBatch = {
  batch_id: string
  filename?: string | null
  source_label?: string | null
  period_start?: string | null
  period_end?: string | null
  counts?: AttendanceImportCounts
  status: string
  created_by_phone?: string | null
  created_at?: string
  reversed_at?: string | null
}

export type AttendanceImportBatchesResponse = {
  company_code: string
  batches: AttendanceImportBatch[]
}

export type AttendanceImportReverseResponse = {
  ok: boolean
  batch_id: string
  reversed: number
  deleted: number
  restored: number
  conflicts: number
  locked_skipped: number
}

export type AttendanceImportMapping = {
  mapping_id: string
  name: string
  mapping: Record<string, string>
  updated_at?: string
}

export type AttendanceImportMappingsResponse = {
  company_code: string
  mappings: AttendanceImportMapping[]
}

export type DashboardAuthResponse = {
  access_token: string
  token_type: string
  expires_at?: string
  company_code: string
  enabled_modules?: string[]
  access: DashboardUserAccess
  user: DashboardTeamUser
  auth_source?: string
  is_recovery_access?: boolean
}

export type DashboardModuleDefinition = {
  key: string
  label: string
  suite: 'pre_hire' | 'post_hire'
  audience: 'candidate' | 'employee' | 'hr'
  order: number
  people_surface: boolean
  toolcall_gated: boolean
  master_flag?: string | null
  configured: boolean
  platform_available: boolean
  effective: boolean
}

export type DashboardBootstrapResponse = {
  company_code: string
  configured_modules: string[]
  effective_modules: string[]
  enabled_modules: string[]
  module_catalog: DashboardModuleDefinition[]
  access: DashboardUserAccess
  user: DashboardTeamUser
  /** Company IANA timezone for greetings and local-time presentation. */
  timezone?: string | null
  /** Tenant pre-hiring visibility policy (shared_company | assigned_only | hybrid). */
  prehire_visibility_policy?: 'shared_company' | 'assigned_only' | 'hybrid' | string | null
  prehire_visibility_scope?: 'company' | 'assigned' | string | null
  prehire_visibility_summary_company_wide?: boolean
  prehire_visibility_oversight?: boolean
  /** Action Inbox Phase 0 — fail-closed viewer allowlist drives nav offerability. */
  action_inbox?: {
    offerable?: boolean
    wave_enabled?: boolean
    viewer_allowlisted?: boolean
    real_canary_enabled?: boolean
    exclude_payroll?: boolean
  } | null
}

export type DashboardChatCandidateCard = {
  app_key?: string
  name?: string
  phone?: string
  position?: string
  status?: string
  score?: number | string | null
  reasons?: string[]
}

export type DashboardChatNavigation = {
  type?: string
  page?: string
  label?: string
  position_code?: string | null
  prompt?: string
  offset?: number
}

export type DashboardChatWorkflowCard = {
  kind?: 'workflow_preview' | 'workflow_result' | string
  title?: string
  status?: string
  steps?: Array<{ step?: string; status?: string; success?: boolean; message?: string | null }>
  channels?: Record<string, unknown> | string | null
  people?: Array<{ name?: string; app_key?: string }>
  missing_fields?: string[]
  blocked_steps?: unknown[]
  idempotency_key?: string
  compensation_state?: {
    strategy?: string
    note?: string
    retry_step?: string | null
    completed_steps?: string[]
  }
  retry_prompt?: string | null
}

export type DashboardChatConfirmation = {
  pending_action_id?: string
  label?: string
  summary?: string | null
  status?: string | null
  is_active?: boolean
  preview?: Record<string, unknown> | null
  steps?: string[] | Array<Record<string, unknown>>
  channels?: unknown
  people?: Array<{ name?: string; app_key?: string }>
  missing_fields?: string[]
  blocked_steps?: unknown[]
  workflow_card?: DashboardChatWorkflowCard | null
}

export type DashboardChatResponse = {
  reply_text: string
  intent?: string | null
  turn_id?: string | null
  candidate_cards: DashboardChatCandidateCard[]
  navigation: DashboardChatNavigation[]
  confirmation?: DashboardChatConfirmation | null
  workflow_card?: DashboardChatWorkflowCard | null
  progress_phase?: string | null
  session?: DashboardChatSession | null
  audit?: Record<string, unknown>
}

export type DashboardChatSession = {
  conversation_id: string
  title?: string
  status?: string
  created_at?: string
  updated_at?: string
  last_message_at?: string
  metadata?: Record<string, unknown>
}

export type DashboardChatStoredMessage = {
  message_id: string
  role: 'user' | 'assistant'
  text: string
  payload?: {
    candidate_cards?: DashboardChatCandidateCard[]
    navigation?: DashboardChatNavigation[]
    confirmation?: DashboardChatConfirmation | null
    workflow_card?: DashboardChatWorkflowCard | null
    intent?: string | null
    turn_id?: string | null
  }
  created_at?: string
}

export type AssistantEmptyState = {
  locale: 'en' | 'ar' | string
  headline: string
  modules: string[]
  chips: string[]
  has_capabilities: boolean
  offerable?: string[]
}

export type AssistantCapabilitiesResponse = {
  ok: boolean
  company_code: string
  catalog: {
    offerable: string[]
    enabled_modules: string[]
    providers: Record<string, boolean>
    capabilities: Record<
      string,
      {
        status?: string
        offerable?: boolean
        module?: string | null
        provider?: string | null
      }
    >
  }
  empty_state: AssistantEmptyState
}

export type SummaryResponse = {
  company_code: string
  module: string
  enabled_modules?: string[]
  access?: DashboardUserAccess
  features?: {
    assessments_enabled?: boolean
  }
  totals: {
    candidates?: number
    applications?: number
    active_applications?: number
    hired_applications?: number
  }
  action_counts?: {
    ready_for_review?: number
    assessment_pending?: number
    follow_up_needed?: number
    ready_for_review_people?: number
    ready_for_review_applications?: number
    assessment_pending_people?: number
    assessment_pending_applications?: number
    follow_up_needed_people?: number
    follow_up_needed_applications?: number
    assessment_ready_to_send?: number
    assessment_ready_to_send_applications?: number
    assessment_resend_needed?: number
    assessment_resend_needed_applications?: number
    assessment_delivery_failed?: number
    assessment_delivery_failed_applications?: number
    assessment_in_progress?: number
    assessment_in_progress_applications?: number
    assessment_sent_pending?: number
    assessment_sent_pending_applications?: number
    assessment_completed?: number
    assessment_completed_applications?: number
    assessment_primary?: {
      action?: string
      cohort_key?: string
      label?: string
      people_count?: number
      application_count?: number
      destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
    } | null
    assessment_cohorts?: AssessmentCohortsPayload
    units?: Record<string, 'people' | 'applications' | 'actions' | 'jobs' | string>
    metrics?: Array<{
      key: string
      unit: string
      people: number
      applications: number
      display: number
    }>
  }
  assessment_cohorts?: AssessmentCohortsPayload
  next_action?: PrehireNextAction
  role_priority?: PrehireRolePriority | null
  role_next_steps?: PrehireRoleNextStep[]
  definitions?: Record<string, unknown>
  overview_as_of?: string
  status_counts: Array<{ status: string; count: number }>
  positions: PositionSummary[]
  recent_applications: ApplicationSummary[]
}

export type AssessmentCohortBlock = {
  key?: string
  people_count?: number
  application_count?: number
  people?: number
  applications?: number
  display_count?: number
  primary_action?: string
  destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
  candidates_destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
}

export type AssessmentCohortsPayload = {
  enabled?: boolean
  cohorts?: Record<string, AssessmentCohortBlock>
  primary?: AssessmentCohortBlock & {
    action?: string
    cohort_key?: string
    label?: string
    people_count?: number
    application_count?: number
  } | null
  definitions?: Record<string, unknown>
  authority_source?: string
  as_of?: string
}

export type PrehireNextAction = {
  action: string
  priority: number
  reason: string
  total_matching: number
  unit?: 'people' | 'applications' | 'actions' | 'jobs' | string
  people_count?: number
  application_count?: number
  destination?: {
    page?: string
    filters?: Record<string, string>
    cohort_key?: string
  }
  ranking_destination?: {
    page?: string
    filters?: Record<string, string>
    cohort_key?: string
  }
  authority_source?: string
  label?: string
  as_of?: string
  role?: { position_code?: string; position_title?: string }
  alternatives?: Array<{
    action: string
    priority: number
    total_matching: number
    unit?: string
    people_count?: number
    application_count?: number
  }>
  sla_hours?: Record<string, number>
}

export type PrehireRoleSignal = {
  unit?: string
  applications?: number
  people?: number
}

export type PrehireRolePriority = {
  position_code: string
  position_title: string
  unit?: 'people' | 'applications' | 'actions' | 'jobs' | string
  people_count?: number
  application_count?: number
  display_count?: number
  ready_count?: number
  follow_up_count?: number
  assessment_pending_count?: number
  active_count?: number
  active_people?: number
  signals?: {
    follow_up?: PrehireRoleSignal
    ready_for_review?: PrehireRoleSignal
    assessment_pending?: PrehireRoleSignal
  }
  oldest_ready_hours?: number
  pressure_score?: number
  priority: number
  reason: string
  destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
  ranking_destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
}

export type PrehireRoleNextStep = PrehireRolePriority & {
  entity?: string
  next_step?: string
  next_step_label?: string
  authority_source?: string
}

export type PrehireWorkQueueAction = {
  action_type: string
  app_key?: string
  position_code?: string
  position_title?: string
  status?: string
  reason?: string
  priority?: number
  age_hours?: number
  destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
  authority_source?: string
}

export type PrehireWorkQueueApplication = {
  app_key: string
  position_code?: string
  position_title?: string
  status?: string
}

export type PrehireWorkQueueItem = {
  unit?: 'people' | 'applications' | 'actions' | 'jobs' | string
  person_key?: string
  action_type: string
  app_key?: string
  candidate_name?: string
  position_code?: string
  position_title?: string
  status?: string
  stage?: string
  job_label?: string
  reason: string
  priority: number
  age_hours?: number
  action_count?: number
  application_count?: number
  actions?: PrehireWorkQueueAction[]
  applications?: PrehireWorkQueueApplication[]
  destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
  authority_source?: string
  as_of?: string
  /** Wave 4 personal work contract */
  audience?: 'personal' | 'company' | string
  owner?: string
  owner_user_id?: string | null
  due_state?: 'open' | 'due_soon' | 'overdue' | string
  next_action?: string
  source?: string
  entity_type?: string
  entity_id?: string | null
  work_scope?: 'mine' | 'company' | string
}

export type WorkspaceWorkScope = 'mine' | 'attention'

export type WorkspaceWorkItem = {
  work_id: string
  scope?: WorkspaceWorkScope | string
  membership?: 'assigned' | 'unassigned' | 'supervisory' | string
  module?: string
  source_key?: string
  authority_source?: string
  action_type: string
  title_en?: string
  title_ar?: string
  reason_en?: string
  reason_ar?: string
  next_action_en?: string
  next_action_ar?: string
  owner_user_id?: string | null
  owner?: string
  due_state?: string
  due_at?: string | null
  blocked?: boolean
  priority?: number | null
  entity_type?: string
  entity_id?: string | null
  subject_name?: string | null
  destination?: { page?: string; filters?: Record<string, string>; employee?: string; cohort_key?: string }
  dedupe_key?: string
}

export type WorkspaceWorkResponse = {
  company_code: string
  ok: boolean
  contract?: string
  contract_version?: string
  scope?: WorkspaceWorkScope | string
  work_scope?: WorkspaceWorkScope | string
  audience?: string
  can_view_attention?: boolean
  can_view_company_work?: boolean
  as_of?: string
  authority_source?: string
  composes_only?: boolean
  total: number
  limit: number
  has_more?: boolean
  items: WorkspaceWorkItem[]
  counts?: {
    total?: number
    by_module?: Record<string, number>
    by_membership?: Record<string, number>
  }
  sources?: Array<{ source_key?: string; used?: boolean; omitted?: string | null; count?: number }>
}

export type PrehireWorkQueueResponse = {
  company_code: string
  ok: boolean
  as_of: string
  authority_source?: string
  unit?: 'people' | 'applications' | 'actions' | 'jobs' | string
  total: number
  total_count?: number
  action_total?: number
  limit: number
  cursor?: string | null
  next_cursor?: string | null
  has_more?: boolean
  items: PrehireWorkQueueItem[]
  sla_hours?: Record<string, number>
  /** Wave 4 */
  scope?: 'mine' | 'company' | string
  work_scope?: 'mine' | 'company' | string
  can_view_company_work?: boolean
  audience?: 'personal' | 'company' | string
  counts?: {
    ready_for_review?: number
    follow_up?: number
    assessment?: number
    interview_feedback?: number
    interview_scheduling?: number
    overdue_tasks?: number
    approvals?: number
    jobs_owned?: number
    total?: number
  }
  next_action?: PrehireNextAction | null
}

export type PositionsResponse = {
  company_code: string
  positions: PositionSummary[]
  total_count?: number
  limit?: number
  offset?: number
  has_more?: boolean
  next_cursor?: string | null
  status_filter?: string
  summary?: {
    total_positions: number
    open_positions: number
    draft_positions?: number
    paused_positions?: number
    closed_positions: number
    open_roles_with_apply_code?: number
    active_qr_codes: number
    total_applications: number
  }
}

export type PositionSummary = {
  company_code?: string
  company_display_name?: string | null
  job_id?: string | null
  position_code: string
  position_title: string
  title?: string
  title_en?: string
  title_ar?: string | null
  visibility?: 'public' | 'share_only' | 'internal'
  short_summary_en?: string | null
  short_summary_ar?: string | null
  benefits_en?: string | null
  benefits_ar?: string | null
  content_approved_en?: boolean
  content_approved_ar?: boolean
  content_approved_en_at?: string | null
  content_approved_ar_at?: string | null
  publish_ready?: boolean
  publish_blockers?: string[]
  eligibility_reason?: string | null
  shareable?: boolean
  job_key?: string
  application_key?: string
  apply_code?: string
  application_link?: string | null
  qr_value?: string | null
  status?: string
  accepts_applications?: boolean
  description?: string
  description_en?: string
  description_ar?: string | null
  requirements?: unknown
  requirements_en?: unknown
  requirements_ar?: unknown
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
  filled_vacancies?: number | null
  remaining_vacancies?: number | null
  application_deadline?: string | null
  expected_start_date?: string | null
  hiring_manager_user_id?: string | null
  recruiter_user_id?: string | null
  hiring_manager_name?: string | null
  recruiter_name?: string | null
  published_at?: string | null
  closed_at?: string | null
  version?: number
  application_count: number
  active_count: number
  latest_applicant?: string
  latest_applicant_app_key?: string
  created_at?: string
  updated_at?: string
  latest_application_at?: string
  authority_source?: string
  stage_counts?: Array<{ status: string; count: number }>
  recent_applicants?: Array<{
    app_key: string
    phone?: string
    candidate_name?: string
    candidate_email?: string
    status?: string
    ingested_at?: string
    updated_at?: string
  }>
  notifications?: Array<{
    delivery_id: string
    target_phone?: string
    status?: string
    last_error?: string
    created_at?: string
  }>
}

export type CandidateRecordState =
  | 'talent_pool'
  | 'active_application'
  | 'hired'
  | 'archived'
  | 'restricted'
  | string

export type CandidateSavedViewId = 'all' | 'active' | 'talent_pool' | 'hired' | 'archived' | 'restricted'

export type Page =
  | 'overview'
  | 'ai'
  | 'jobs'
  | 'requisitions'
  | 'candidates'
  | 'interviews'
  | 'calendar'
  | 'assessments'
  | 'ranking'
  | 'notifications'
  | 'reports'
  | 'employees'
  | 'workforce'
  | 'inbox'
  | 'preboarding'
  | 'onboarding'
  | 'probation'
  | 'attendance'
  | 'leave'
  | 'performance'
  | 'talent'
  | 'learning'
  | 'benefits'
  | 'employee-relations'
  | 'engagement'
  | 'compensation-planning'
  | 'workforce-planning'
  | 'job-architecture'
  | 'shifts'
  | 'payroll'
  | 'analytics'
  | 'compliance'
  | 'activity'
  | 'settings'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  candidateCards?: DashboardChatCandidateCard[]
  navigation?: DashboardChatNavigation[]
  confirmation?: DashboardChatConfirmation | null
  workflowCard?: DashboardChatWorkflowCard | null
  progressPhase?: string | null
  isStreaming?: boolean
}

export type CandidateFilters = {
  position: string
  cvStatus: string
  assessmentStatus: string
  interviewStatus: string
  followUp: string
  reviewStatus: string
  activityFrom: string
  activityTo: string
  sort: string
  overviewCohort: string
  action: string
  cohortKey: string
  sourceChannel: string
  recruiterOwner: string
  cvProcessingState: string
  receivedFrom: string
  receivedTo: string
  hasGroundedEmail: string
  hasGroundedPhone: string
  factCompleteness: string
  departmentIntakeTag: string
  view: CandidateSavedViewId
}

export type ApplicationSummary = {
  app_key: string
  company_code: string
  phone: string
  candidate?: {
    name?: string
    email?: string
    profile?: Record<string, unknown>
  }
  position?: {
    code?: string
    title?: string
  }
  status?: string
  canonical_stage?: string | null
  lifecycle_version?: number
  status_label?: string
  status_display?: string
  job_display?: string
  assessment_display?: string | null
  communication_display?: string | null
  record_state?: CandidateRecordState
  record_state_label?: string
  is_held?: boolean
  match_reasons?: string[]
  classification_chip?: string | null
  classification_chip_confirmed?: boolean
  classification_state?: string | null
  classification_authority_summary?: {
    confirmed_count?: number
    ai_suggested_count?: number
    rejected_count?: number
  }
  classification_node_ids?: string[]
  grounded_contacts?: {
    email?: string | null
    phone?: string | null
  }
  recruiter_owner?: {
    user_id?: string | null
    label?: string | null
  }
  completeness?: Array<{ section: string; state: string; label: string }>
  privacy?: {
    configured?: boolean
    message?: string | null
    tenant_controller_code?: string | null
    processing_basis_code?: string | null
    privacy_notice_id?: string | null
    privacy_notice_version?: string | null
    retention_policy_id?: string | null
    retention_policy_version?: string | null
    retention_deadline_at?: string | null
    archive_state?: string | null
    restriction_state?: string | null
    legal_hold_state?: string | null
    deletion_request_state?: string | null
    audit_tombstone_ref?: string | null
  }
  department_intake_tag?: string | null
  identity?: {
    compatibility_key_hidden?: boolean
    note?: string
  }
  link_to_job?: {
    available?: boolean
    enabled?: boolean
    label?: string
    reason?: string
  }
  current_step?: string
  screening_status?: string
  data_source?: string
  intake_source?: string
  cv_processing?: {
    status?: string
    received?: boolean
    automatic?: boolean
    label?: string
    bucket?: string
  }
  screening?: {
    status?: string
    automatic?: boolean
  }
  communication?: {
    status?: 'pending' | 'sent' | 'failed' | 'intentionally_skipped' | string
    message_kind?: string
    channel?: string
    sent_at?: string
    failed_at?: string
    last_error?: string
    stage_changed_without_contact?: boolean
  }
  automatic_activity?: string[]
  waiting_for_hr?: string[]
  allowed_actions?: string[]
  assessment_cohort?: string | null
  assessment_allowed_actions?: string[]
  lead_quality?: 'candidate_record' | 'incomplete_lead' | string
  cv?: {
    received?: boolean
    storage_status?: string
    filename?: string
    mime_type?: string
    size_bytes?: number
    preview_available?: boolean
  }
  assessment?: {
    attempt_id?: string
    assessment_version_id?: string
    status?: string
    delivery_status?: string
    review_status?: string
    battery_key?: string
    raw_score?: number
    max_score?: number
    percent?: number
    band?: string
    summary?: string
    expires_at?: string
    cancelled_at?: string
    expired_at?: string
    reviewed_at?: string
    completed_at?: string
  }
  interview?: {
    interview_id?: string
    status?: string
    feedback_status?: string
    interview_type?: 'live' | 'async_video' | string
    async_status?: string
    scheduled_start?: string
    scheduled_end?: string
    meet_link?: string
    calendar_event_id?: string
    calendar_invite_sent?: boolean
    candidate_invited?: boolean
    candidate_notified?: boolean
    notification_channel?: string
    sent_subject?: string
    sent_body?: string
    invite_sent_at?: string
    consent_accepted_at?: string
    completed_at?: string
    summary?: string
    ai_summary?: {
      summary?: string
      overall_summary?: string
      strengths?: string[]
      concerns?: string[]
      communication_notes?: string[]
      role_fit_evidence?: string[]
      gaps_or_risks?: string[]
      missing_evidence?: string[]
      suggested_follow_up_questions?: string[]
      follow_up_points?: string[]
      recommended_next_step?: string
      recommendation?: string
      hr_decision_maker_note?: string
      decision_policy?: string
      source?: string
    }
    response_mode?: CandidateInterview['response_mode']
    video_questions?: CandidateInterview['video_questions']
    video_processing?: CandidateInterview['video_processing']
    video_answers?: CandidateInterview['video_answers']
    video_review_status?: CandidateInterview['video_review_status']
    feedback?: CandidateInterview['feedback']
    presentation?: CandidateInterview['presentation']
    updated_at?: string
  } | null
  ingested_at?: string
  updated_at?: string
  raw_json?: Record<string, unknown>
  ranking?: {
    score?: number
    score_breakdown?: RankingCandidate['score_breakdown']
    confidence?: RankingCandidate['confidence']
    evidence?: string[]
    reasons?: string[]
    role_profile?: RankingCandidate['role_profile']
    gpt_evaluation?: RankingCandidate['gpt_evaluation']
    evidence_digest?: string
    evaluation_audit?: Record<string, unknown>
  }
}

export type ApplicationsResponse = {
  company_code: string
  total: number
  limit: number
  offset: number
  view?: CandidateSavedViewId | string | null
  applications: ApplicationSummary[]
}

export type CandidateProfileResponse = {
  company_code: string
  application: ApplicationSummary
  record_state?: CandidateRecordState
  held_reason?: string
  source_channel?: string
  sender_provenance?: {
    sender_email?: string
    role?: string
    note?: string
  } | null
  grounded_contacts?: ApplicationSummary['grounded_contacts']
  documents?: Array<Record<string, unknown>>
  files?: Array<Record<string, unknown>>
  facts?: {
    extraction_snapshot?: Record<string, unknown>
    effective?: Record<string, unknown>
    reviews_by_path?: Record<string, unknown>
    events?: Array<Record<string, unknown>>
    completeness?: ApplicationSummary['completeness']
    missing_policy?: string
  }
  privacy?: ApplicationSummary['privacy']
  held_applications?: Array<Record<string, unknown>>
  live_applications?: Array<Record<string, unknown>>
  processing_timeline?: Array<{ label?: string; at?: string | null; actor?: string | null }>
  link_to_job?: ApplicationSummary['link_to_job']
  cv_truth?: Record<string, unknown>
}

/** Backend-authoritative person-aware Candidate profile (independent of list pagination). */
export type CandidateEmploymentFact = {
  title?: string | null
  company?: string | null
  location?: string | null
  start_date?: string | null
  end_date?: string | null
  description?: string | null
  achievements?: string[]
}

export type CandidateEducationFact = {
  degree?: string | null
  institution?: string | null
  location?: string | null
  start_date?: string | null
  end_date?: string | null
  gpa?: string | null
  honors?: string | null
}

export type CandidateProfileFacts = {
  schema?: string
  skills: string[]
  education: string[]
  employment: string[]
  languages: string[]
  certifications?: string[]
  projects?: string[]
  publications?: string[]
  training_courses?: string[]
  memberships_activities?: string[]
  awards_honors?: string[]
  volunteer_work?: string[]
  references?: string[]
  location?: string | null
  professional_summary?: string | null
  primary_expertise?: string | null
  experience_years?: number | null
  availability?: string | null
  unmodeled_sections?: Array<Record<string, unknown>>
  structured?: {
    employment?: CandidateEmploymentFact[]
    volunteer_work?: Array<Record<string, unknown>>
    education?: CandidateEducationFact[]
    skills?: Array<Record<string, unknown>>
    languages?: Array<Record<string, unknown>>
    projects?: Array<Record<string, unknown>>
    publications?: Array<Record<string, unknown>>
    certifications?: Array<Record<string, unknown>>
    training_courses?: Array<Record<string, unknown>>
    memberships_activities?: Array<Record<string, unknown>>
    awards_honors?: Array<Record<string, unknown>>
    references?: Array<Record<string, unknown>>
    contact_details?: Record<string, unknown>
  }
  field_sources?: Record<string, { origin?: string }>
}

export type CandidatePersonProfileResponse = {
  ok?: boolean
  company_code: string
  schema?: string
  resolution?: {
    anchor_app_key?: string
    person_id?: string | null
    membership_id?: string | null
    identity_key?: string
    resolution_method?: string
    email?: string | null
    phone?: string | null
    application_count?: number
    person_application_count?: number
  }
  person?: {
    display_name?: string | null
    email?: string | null
    phone?: string | null
    expertise?: string | null
    summary?: string | null
    location?: string | null
    top_skills?: string[]
    experience_years?: number | null
    source?: string | null
    received_at?: string | null
  }
  profile_facts?: CandidateProfileFacts
  application: ApplicationSummary
  applications: ApplicationSummary[]
  held_applications?: ApplicationSummary[]
  live_applications?: ApplicationSummary[]
  documents?: Array<Record<string, unknown>>
  files?: Array<Record<string, unknown>>
  cv_versions?: {
    current?: {
      id?: string
      filename?: string
      created_at?: string | null
      latest?: boolean
    } | null
    previous?: Array<{
      id?: string
      filename?: string
      created_at?: string | null
      latest?: boolean
    }>
  } | Array<Record<string, unknown>>
  cv_truth?: Record<string, unknown>
  interviews?: Array<Record<string, unknown>>
  assessments?: Array<Record<string, unknown>>
  notes_enabled?: boolean
  notes?: Array<{ source?: string; app_key?: string; interview_id?: string; at?: string | null; text?: string }>
  activity?: string[]
  grounded_contacts?: ApplicationSummary['grounded_contacts']
  record_state?: CandidateRecordState
  source_channel?: string
  add_to_job?: {
    available?: boolean
    enabled?: boolean
    held_app_key?: string | null
    blocked_position_codes?: string[]
    reason?: string | null
  }
  allowed_actions?: string[]
  extraction_evidence?: Record<string, unknown>
}

export type CandidateSavedView = {
  view_id: string
  company_code: string
  actor_user_id: string
  name: string
  filters: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

export type CandidateInterviewFeedback = {
  state: 'not_started' | 'draft' | 'submitted' | 'complete' | string
  label?: string
  complete?: boolean
  needs_feedback?: boolean
  notes_present?: boolean
  submission_id?: string | null
  legacy_conflict?: boolean
}

export type CandidateInterview = {
  interview_id: string
  company_code: string
  app_key: string
  phone?: string
  candidate_name?: string
  candidate_email?: string
  position_code?: string
  position_title?: string
  application_stage?: string
  application_stage_label?: string
  status?: 'scheduled' | 'completed' | 'no_show' | 'rescheduled' | 'cancelled' | string
  feedback_status?: 'notes_pending' | 'feedback_complete' | string
  scheduled_start?: string
  scheduled_end?: string
  timezone?: string
  meeting_type?: string
  meet_link?: string
  calendar_event_id?: string
  calendar_invite_sent?: boolean
  candidate_invited?: boolean
  candidate_notified?: boolean
  communication_status?: 'pending' | 'sent' | 'failed' | 'intentionally_skipped' | string
  invitation_status?: string
  candidate_confirmation?: string
  notification_channel?: string
  sent_subject?: string
  sent_body?: string
  invite_sent_at?: string
  notes?: string
  notes_status?: string
  transcript?: string
  ai_summary?: {
    summary?: string
    overall_summary?: string
    strengths?: string[]
    concerns?: string[]
    communication_notes?: string[]
    role_fit_evidence?: string[]
    gaps_or_risks?: string[]
    missing_evidence?: string[]
    suggested_follow_up_questions?: string[]
    follow_up_points?: string[]
    follow_up_questions?: string[]
    recommended_next_step?: string
    recommendation?: string
    hr_decision_maker_note?: string
    decision_policy?: string
    source?: string
  }
  interview_type?: 'live' | 'async_video' | string
  async_status?: string
  consent_accepted_at?: string
  completed_at?: string
  response_mode?: 'single_video' | 'per_question_video' | string
  video_questions?: Array<{
    question_id: string
    question_order: number
    question_key?: string
    prompt_text?: string
    competency?: string
    max_duration_seconds?: number
    required?: boolean
  }>
  video_processing?: {
    ready?: boolean
    required_count?: number
    question_count?: number
    response_mode?: 'single_video' | 'per_question_video' | string
    pending_response_ids?: string[]
    failed_response_ids?: string[]
    completed_response_ids?: string[]
    missing_question_ids?: string[]
  }
  video_answers?: Array<{
    response_id: string
    question_id: string
    question_order: number
    question_text?: string
    response_mode?: 'single_video' | 'per_question_video' | string
    covered_questions?: Array<{
      question_id: string
      question_order: number
      prompt_text?: string
      competency?: string
      required?: boolean
    }>
    competency?: string
    required?: boolean
    has_video?: boolean
    video_url?: string
    transcript_status?: 'pending' | 'processing' | 'completed' | 'failed' | string
    transcript_text?: string
    transcript_model?: string
    transcript_language?: string
    transcript_error?: string
    transcribed_at?: string
    duration_seconds?: number
    size_bytes?: number
    submitted_at?: string
  }>
  video_review_status?: {
    state?: 'link_sent' | 'started' | 'submitted' | 'processing' | 'summary_pending' | 'ready_for_review' | 'transcription_failed' | 'cancelled' | string
    label?: string
    description?: string
    tone?: 'default' | 'success' | 'warning' | 'danger' | 'muted' | string
    response_count?: number
    required_count?: number
    failed_count?: number
    pending_count?: number
    missing_count?: number
    summary_ready?: boolean
  }
  source?: string
  next_human_action?: string
  allowed_actions?: string[]
  feedback?: CandidateInterviewFeedback
  feedback_state?: string
  needs_feedback?: boolean
  presentation?: InterviewPresentation
  interviewer_assignments?: string[]
  created_at?: string
  updated_at?: string
}

export type InterviewTruth = CandidateInterview | NonNullable<ApplicationSummary['interview']>

export type InterviewPresentation = {
  version?: string
  interview_type: 'async_video' | 'live_video' | 'phone' | 'in_person' | string
  interview_type_label?: string
  progress_state: string
  progress_label?: string
  schedule_state: 'not_applicable' | 'date_missing' | 'scheduled' | 'past_due' | string
  date_time?: string | null
  invitation_state: string
  invitation_note?: string | null
  candidate_confirmation: string
  evidence_readiness: 'none' | 'waiting' | 'partial' | 'ready' | 'reviewed' | string
  feedback_complete?: boolean
  interviewer_assignment?: {
    assigned?: boolean
    count?: number
    names?: string[]
    label?: string | null
  }
  next_human_action?: string
  next_human_action_legacy?: string | null
  allowed_actions?: string[]
  display?: {
    status_label?: string
    type_label?: string
    show_datetime?: boolean
    is_async?: boolean
  }
}

export type InterviewsResponse = {
  company_code: string
  total: number
  limit?: number
  offset?: number
  status_counts: Array<{ status: string; count: number }>
  feedback_counts: Array<{ feedback_status: string; count: number }>
  video_count?: number
  interviews: CandidateInterview[]
}

export type InterviewMutationResponse = {
  company_code: string
  ok: boolean
  reply?: string
  interview: CandidateInterview
}

export type RankingCandidate = {
  score?: number | null
  score_breakdown?: {
    role_fit?: number
    skill_match?: number
    experience?: number
    accomplishments?: number
    cv_evidence?: number
    screening?: number
    assessment?: number
    interview?: number
    readiness?: number
    confidence?: number
    skills_alignment?: number
    experience_alignment?: number
    education_cert_alignment?: number
    assessment_evidence?: number
    semantic_alignment?: number
  }
  component_scores?: RankingCandidate['score_breakdown']
  role_profile?: {
    key?: string
    label?: string
    criteria?: Array<{ key?: string; label?: string; keywords?: string[] }>
  }
  gpt_evaluation?: {
    source?: string
    fit_summary?: string | null
    strengths?: string[]
    gaps?: string[]
    risks?: string[]
    recommended_next_step?: string
    confidence?: string
    criterion_notes?: string[]
  }
  evaluation_audit?: Record<string, unknown>
  evidence_digest?: string
  confidence?: 'low' | 'medium' | 'high' | string
  evidence?: string[]
  app_key: string
  phone: string
  name: string
  position_code?: string
  position_title?: string
  status?: string
  screening_status?: string
  semantic_similarity?: number
  matched_terms?: string[]
  reasons?: string[]
  eligibility_bucket?: string
  presentation?: RankingPresentation
  ranking_decision?: RankingDecision
  application?: ApplicationSummary
}

export type RankingPresentation = {
  version?: string
  locale?: string
  candidate_name?: string
  job_title?: string
  state?: { code?: string; label?: string }
  score?: {
    show_numeric?: boolean
    value?: number | null
    label?: string
    reason?: string
    components?: Record<string, { value?: number; max?: number; weight?: number; label?: string }>
  }
  explanation?: string
  verdict?: string
  fit?: { code?: string; label?: string; tone?: string }
  strengths?: Array<{ label?: string; value?: string; status?: string } | string>
  gaps?: string[]
  missing?: string[]
  evidence_highlights?: Array<{ label?: string; value?: string } | string>
  evidence_sections?: Array<{ label?: string; value?: string; status?: string }>
  recommended_next_step?: string
  card_mode?: string
  thin?: boolean
  tied?: boolean
}

export type RankingDecision = {
  version?: string
  ranking_status?: string
  eligibility?: { bucket?: string; label?: string; fit_code?: string; fit_label?: string }
  advisory_score?: number | null
  score_state?: { show_numeric?: boolean; label?: string; reason?: string }
  fit_summary?: string | null
  strengths?: string[]
  gaps?: string[]
  missing_evidence?: string[]
  component_scores?: Record<string, number | null>
  component_score_meta?: Record<string, { value?: number | null; max?: number; weight?: number; label?: string }>
  recommended_next_action?: string
  evidence_references?: string[]
  run_freshness?: string
  run_id?: string
  app_key?: string
  application_stage?: string
  job?: { position_code?: string; position_title?: string }
  candidate_name?: string
}

export type RankingResponse = {
  company_code: string
  ok?: boolean
  total_matching: number
  matching_count?: number
  rankable_count?: number
  total_rankable?: number
  eligible_count?: number
  not_applicable_count?: number
  not_met_count?: number
  unknown_count?: number
  restricted_held_count?: number
  shown_top_n?: number
  needs_run?: boolean
  loaded_mode?: string
  stale?: boolean
  run_id?: string
  message?: string
  role_profile?: {
    key?: string
    label?: string
    criteria?: Array<{ key?: string; label?: string; keywords?: string[] }>
  }
  candidates: RankingCandidate[]
  presentation_summary?: string
  comparison?: { status?: string; title?: string; detail?: string }
  provenance?: {
    evidence_policy?: { sources?: { assessment?: string; cv?: string; [key: string]: string | undefined } }
    [key: string]: unknown
  }
  evidence_policy?: { sources?: { assessment?: string; cv?: string; [key: string]: string | undefined } }
}

export type NotificationRow = {
  delivery_id: string
  target_phone?: string
  target_conversation_id?: string
  status?: string
  dashboard_status?: string
  last_error?: string
  app_key?: string
  position_code?: string
  position_title?: string
  candidate_name?: string
  candidate_email?: string
  created_at?: string
}

export type NotificationActionItem = {
  kind: string
  title: string
  count: number
  severity?: 'high' | 'medium' | 'low' | string
  action?: string
  page?: string
  metadata?: Record<string, unknown>
}

export type NotificationsResponse = {
  company_code: string
  enabled_modules?: string[]
  notification_policy?: Record<string, unknown>
  action_items?: NotificationActionItem[]
  notifications: NotificationRow[]
}

export type ReportBreakdownRow = {
  label: string
  count: number
}

export type PrehireReportsResponse = {
  company_code: string
  ok: boolean
  metric_version?: string
  locale?: string
  partial?: boolean
  error?: string | null
  assessments_enabled?: boolean
  interviews_enabled?: boolean
  overview?: {
    open_roles?: number
    active_applications?: number
    ready_for_review?: number
    interview_scheduling_debt?: number
    assessment_pending?: number
    followups_current?: number
    units?: Record<string, string>
  }
  metrics?: {
    version?: string
    metrics?: Array<{ key: string; label: string; value: number | { scheduled?: number; completed?: number } }>
    breakdowns?: {
      applications_by_stage?: ReportBreakdownRow[]
      applications_by_role?: ReportBreakdownRow[]
      assessment_status?: ReportBreakdownRow[]
      interview_status?: ReportBreakdownRow[]
    }
    role_export_total?: number
  }
  exports: {
    candidate_rows: number
    role_rows: number
    assessment_rows: number
    interview_rows: number
    followup_rows: number
    followup_delivery_history_rows?: number
    types?: string[]
  }
  summary: {
    cv_received?: number
    cv_missing?: number
    screening_complete?: number
    ready_for_review?: number
    assessment_pending?: number
    assessment_completed?: number
    interview_scheduled?: number
    interview_completed?: number
    interview_no_show?: number
    interview_scheduling_debt?: number
    active_applications?: number
    open_roles?: number
    followups?: number
    followups_needed?: number
    followup_delivery_events?: number
  }
  breakdowns: {
    applications_by_stage: ReportBreakdownRow[]
    candidates_by_role: ReportBreakdownRow[]
    applications_by_role?: ReportBreakdownRow[]
    assessment_status: ReportBreakdownRow[]
    interview_status: ReportBreakdownRow[]
    followups_by_type: ReportBreakdownRow[]
  }
}

export type AssessmentAttemptPresentation = {
  version?: string
  unit?: string
  person?: { name?: string | null; email?: string | null; phone?: string | null }
  application?: { app_key?: string | null; status?: string | null; position_code?: string | null; position_title?: string | null }
  invitation?: { attempt_id?: string | null; has_active?: boolean; delivery_state?: string; expires_at?: string | null; cancelled_at?: string | null }
  attempt?: {
    state?: string
    delivery_state?: string
    review_state?: string
    report_state?: string
    percent?: number | null
    band?: string | null
    job_match_percent?: number | null
    completed_at?: string | null
  }
  report?: { state?: string; ready?: boolean; immutable?: boolean }
  cohort_key?: string
  display_status?: string
  needs_review?: boolean
  next_human_action?: string
  allowed_actions?: string[]
}

export type AssessmentAttempt = {
  attempt_id: string
  company_code: string
  app_key: string
  phone?: string
  candidate_name?: string
  candidate_email?: string
  position_code?: string
  position_title?: string
  application_status?: string
  battery_key?: string
  assessment_version_id?: string
  status?: string
  delivery_status?: string
  review_status?: string
  current_item_index?: number
  progress_version?: number
  total_items?: number
  answered_count?: number
  percent_complete?: number
  raw_score?: number
  max_score?: number
  percent?: number
  band?: string
  section_scores?: Record<string, { raw?: number; max?: number; percent?: number }>
  ability_scores?: Record<string, { raw?: number; max?: number; percent?: number; percentile?: number; t_score?: number; sten?: number; band?: string }>
  competency_profile?: {
    framework_version?: string
    scores?: Record<string, { score?: number; band?: string; color?: string; label?: string }>
  }
  presentation?: AssessmentAttemptPresentation
  job_match?: {
    role_profile_key?: string
    role_profile_label?: string
    match_confidence?: string
    ability_fit_percent?: number
    competency_fit_percent?: number
    job_match_percent?: number
    fit_band?: string
    strengths?: string[]
    development_areas?: string[]
  }
  report_json?: Record<string, unknown>
  summary?: string
  created_at?: string
  expires_at?: string
  started_at?: string
  completed_at?: string
  cancelled_at?: string
  cancel_reason?: string
  expired_at?: string
  reviewed_at?: string
  reviewed_by_user_id?: string
  review_notes?: string
  updated_at?: string
  /** OCC token when present — used for mark-reviewed. */
  version?: number | null
}

export type AssessmentsResponse = {
  company_code: string
  ok: boolean
  enabled?: boolean
  module_disabled?: boolean
  required_module?: string
  total: number
  attempts_total?: number
  limit?: number
  offset?: number
  status_counts: Array<{ status: string; count: number }>
  average_percent?: number | null
  attempts: AssessmentAttempt[]
  needs_review_count?: number
  report_ready_count?: number
  cohorts?: {
    cohorts?: Record<string, { people_count?: number; application_count?: number; display_count?: number; people?: number; applications?: number; unit?: string }>
    scope?: string
  }
  filter?: { status?: string | null; needs_review?: boolean; position?: string | null }
}

export type AssessmentConfigResponse = {
  company_code: string
  ok: boolean
  battery?: Record<string, unknown> | null
  item_bank?: {
    total_items?: number
    section_totals?: Record<string, number>
    difficulty_totals?: Record<string, number>
    validation?: { ok?: boolean; error_count?: number; errors?: string[] }
    content_policy?: string
  }
  framework?: {
    version?: string
    groups?: Array<{ key?: string; label?: string; competencies?: string[] }>
    competencies?: Record<string, string>
  }
  role_profiles?: Record<string, Record<string, unknown>>
  norms?: {
    active_norm_version?: string
    status?: string
    minimum_recommended_sample?: number
    groups?: Array<Record<string, unknown>>
  }
  guardrails?: Record<string, unknown>
}

export type AssessmentNormRecalculationResponse = {
  ok: boolean
  company_code: string
  battery_key: string
  persisted: boolean
  minimum_sample: number
  status: string
  groups: Array<{
    norm_key?: string
    section?: string
    sample_size?: number
    is_active?: boolean
    source?: string
    percentiles?: Record<string, number>
    raw_json?: Record<string, unknown>
  }>
}

export type Product2Locale = 'en' | 'ar'

export type Product2ModelRole = {
  registry_version_id: string
  role_key: string
  version: number
  provider: string
  requested_model: string
  qualified_provider_model_id?: string | null
  api_kind: string
  enabled: boolean
  output_schema_name: string
  output_schema_version: string
  activated_at?: string | null
}

export type Product2AuthoringStatus = {
  product_version: string
  global_flag: boolean
  production_hard_off: boolean
  publish_available: false
  live_scoring_ai_calls: false
  environment?: string
  model_roles: Product2ModelRole[]
  draft_counts: Record<string, number>
}

export type Product2BlueprintInput = {
  battery_key?: string
  source_locale: Product2Locale
  required_locales: Product2Locale[]
  section: string
  constructs: string[]
  item_type: 'single_choice' | 'competency_keyed'
  difficulty_target: 'easy' | 'medium' | 'hard'
  reading_level: string
  role_context: string[]
  allowed_context: string[]
  prohibited_content: string[]
  scoring_family: 'answer_key' | 'competency_keyed'
  choice_count: number
  originality_policy_version: string
}

export type Product2Blueprint = {
  blueprint_version_id: string
  company_code: string
  blueprint_key: string
  version: number
  status: string
  blueprint_json: Product2BlueprintInput
  blueprint_sha256: string
  created_by_user_id?: string | null
  approved_by_user_id?: string | null
  approved_at?: string | null
  created_at?: string
}

export type Product2DraftChoice = {
  key: string
  text: string
}

export type Product2DraftContent = {
  draft_local_id: string
  locale: Product2Locale
  prompt_text: string
  choices: Product2DraftChoice[]
  proposed_answer_key: string
  proposed_scoring: {
    family: 'answer_key' | 'competency_keyed'
    correct_points: number
    incorrect_points: number
    max_points: number
    choice_points: Array<{ choice_key: string; points: number }>
  }
  compiled_scoring?: Record<string, unknown>
  compiled_scoring_sha256?: string
  rationale: string
  explanation: string
  distractor_rationales: Array<Record<string, unknown>>
  competency_tags: string[]
  skill_tags: string[]
  role_tags: string[]
  difficulty_rationale: string
  assumptions: string[]
  original_content_attested: boolean
  safety_flags: string[]
  translation?: Record<string, unknown>
}

export type Product2Draft = {
  draft_id: string
  company_code: string
  battery_key: string
  lifecycle_status: string
  section?: string
  difficulty?: string
  locale: Product2Locale
  prompt_text: string
  choices: Product2DraftChoice[]
  proposed_answer_key?: string
  proposed_scoring?: Record<string, unknown>
  rationale?: string | null
  explanation?: string | null
  ai_model?: string | null
  source_blueprint_id?: string | null
  current_revision_id?: string | null
  blueprint_version_id?: string | null
  source_run_id?: string | null
  human_reviewer_id?: string | null
  reviewed_at?: string | null
  created_at?: string
  updated_at?: string
  content_json?: Product2DraftContent
  content_sha256?: string
  compiled_scoring_sha256?: string
  revision?: number
}

export type Product2DraftRevision = {
  draft_revision_id: string
  draft_id: string
  company_code: string
  revision: number
  parent_revision_id?: string | null
  source_run_id?: string | null
  revision_kind: string
  content_json: Product2DraftContent
  content_sha256: string
  locale: Product2Locale
  answer_key_id: string
  compiled_scoring_json: Record<string, unknown>
  compiled_scoring_sha256: string
  created_by_actor_type: string
  created_by_user_id?: string | null
  created_at?: string
}

export type Product2DraftReview = {
  review_id: string
  review_type: string
  reviewer_type: string
  reviewer_id?: string | null
  from_status?: string | null
  to_status?: string | null
  findings_json?: Record<string, unknown>
  notes?: string | null
  created_at?: string
}

export type Product2AuthoringEvent = {
  event_id: string
  event_type: string
  actor_type: string
  actor_user_id?: string | null
  from_status?: string | null
  to_status?: string | null
  payload_json?: Record<string, unknown>
  created_at?: string
}

export type Product2Run = {
  run_id: string
  company_code: string
  role_key: string
  run_kind: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'refused' | 'budget_blocked' | string
  registry_version_id: string
  prompt_version_id: string
  blueprint_version_id?: string | null
  draft_id?: string | null
  draft_revision_id?: string | null
  parent_run_id?: string | null
  requested_model: string
  provider_response_model?: string | null
  schema_name: string
  schema_version: string
  schema_sha256: string
  input_json?: Record<string, unknown>
  output_json?: Record<string, unknown> | null
  input_sha256?: string
  output_sha256?: string | null
  input_tokens?: number | null
  output_tokens?: number | null
  estimated_cost_usd?: number | null
  latency_ms?: number | null
  refusal_reason?: string | null
  error_code?: string | null
  error_message?: string | null
  queued_at?: string
  started_at?: string | null
  completed_at?: string | null
  idempotent?: boolean
}

export type Product2BlueprintsResponse = {
  ok: boolean
  blueprints: Product2Blueprint[]
  publish_available: false
}

export type Product2RunResponse = {
  ok: boolean
  run: Product2Run
  queued?: boolean
  publish_available: false
}

export type Product2DraftEvidenceResponse = {
  ok: boolean
  draft: Product2Draft
  revisions: Product2DraftRevision[]
  reviews: Product2DraftReview[]
  events: Product2AuthoringEvent[]
  publish_available: false
}

export type AssessmentAuthoringDraftsResponse = {
  ok: boolean
  drafts: Product2Draft[]
  publish_available: false
}

export type AssessmentReportResponse = {
  company_code: string
  ok: boolean
  attempt: AssessmentAttempt
  report: Record<string, unknown>
  responses: Array<Record<string, unknown>>
}

export type MutationResponse = {
  ok: boolean
  company_code: string
  action_type: string
  status: string
  reply: string
  application?: ApplicationSummary
  result?: Record<string, unknown>
}

export type ImportItemResult = {
  item_id?: string
  original_filename: string
  status: 'imported' | 'duplicate' | 'failed' | 'pending' | string
  app_key?: string | null
  candidate_name?: string | null
  candidate_email?: string | null
  position_code?: string | null
  position_title?: string | null
  duplicate_of_app_key?: string | null
  error?: string | null
  size_bytes?: number | null
}

export type ImportUploadResponse = {
  ok: boolean
  batch_id: string
  company_code: string
  total_files: number
  counts: { imported: number; duplicate: number; failed: number; needs_role: number; review?: number; auto_admitted?: number }
  items: ImportItemResult[]
}

export type ImportBatchSummary = {
  batch_id: string
  status: string
  total_files: number
  imported_count: number
  duplicate_count: number
  failed_count: number
  needs_role_count: number
  created_by_email?: string | null
  created_at?: string
  updated_at?: string
}

export type ImportReviewItem = {
  app_key: string
  status: 'needs_role' | 'import_review' | string
  position_code?: string | null
  position_title?: string | null
  import_batch_id?: string | null
  original_filename?: string | null
  import_source?: string | null
  suggested_code?: string | null
  suggested_title?: string | null
  suggestion_confidence?: number | null
  suggestion_source?: string | null
  candidate_name?: string | null
  candidate_email?: string | null
  ingested_at?: string | null
}

export type ImportReviewResponse = {
  company_code: string
  total: number
  items: ImportReviewItem[]
}

export type ImportIntakeItem = {
  app_key: string
  candidate_name?: string | null
  candidate_email?: string | null
  original_filename?: string | null
  import_source?: string | null
  status: string
  suggested_code?: string | null
  suggested_title?: string | null
  suggestion_confidence?: number | null
  suggestion_source?: string | null
}

export type ImportIntakeGroup = {
  key: string
  kind: 'explicit_review' | 'suggested' | 'unclear'
  role_code?: string | null
  role_title?: string | null
  confidence: 'high' | 'medium' | 'low' | 'none'
  count: number
  app_keys: string[]
  items: ImportIntakeItem[]
}

export type ImportIntakeResponse = {
  company_code: string
  total: number
  auto_admit_explicit_imports: boolean
  auto_admitted_total: number
  groups: ImportIntakeGroup[]
}

export type ImportBulkActionResponse = {
  ok: boolean
  company_code: string
  action: 'confirm' | 'assign' | 'archive'
  updated: number
  skipped: number
  archived: number
  promoted: number
}

export type ImportSettingsResponse = {
  company_code: string
  auto_admit_explicit_imports: boolean
}

export type EmailSendingChoice = {
  id: 'wathefni' | 'microsoft_mailbox' | 'postmark_company_domain' | string
  title: string
  description: string
  recommended?: boolean
  status: 'ready' | 'setup_required' | 'verifying' | 'error' | string
  selectable: boolean
}

export type EmailSendingSettingsResponse = {
  company_code: string
  current_sender: string
  status: 'ready' | 'setup_required' | 'verifying' | 'error' | string
  status_label: string
  choices: EmailSendingChoice[]
  display_name?: string | null
  reply_to?: string | null
  visible_from?: string | null
  interview_email_when_calendar_sent: boolean
  allow_wathefni_emergency_fallback?: boolean
  hr_notice?: string | null
  primary_action?: { id: 'connect' | 'verify' | 'test' | string; label: string } | null
  intake: {
    feature?: {
      enabled: boolean
      global_enabled?: boolean
      allowlisted?: boolean
      tenant_flag?: boolean | null
      domain: string
      architecture?: string
      mailbox_sync_enabled?: boolean
      quotas?: {
        daily_message_quota: number
        monthly_message_quota: number
        daily_source_bytes_quota: number
        monthly_source_bytes_quota: number
        daily_processing_job_quota: number
        commercial_enforced?: boolean
        tenant_overrides?: Record<string, number>
      }
      health?: {
        last_received_at?: string | null
        received_count?: number
        received_7d?: number
        last_status?: string | null
      }
    }
    addresses: Array<{
      intake_id?: string
      address: string
      label?: string | null
      status?: string
      position_code?: string | null
      position_title?: string | null
      role_bound?: boolean
      hold_policy?: string
      health?: {
        last_received_at?: string | null
        received_count?: number
        received_7d?: number
        last_status?: string | null
      } | null
      created_at?: string | null
      updated_at?: string | null
    }>
    public_forward_address?: string | null
    forward_instructions_en: string
    forward_instructions_ar: string
    setup_steps_en?: string[]
    setup_steps_ar?: string[]
    inbound_forwarding_enabled?: boolean | null
  }
}

export type EmailSendingActionResponse = {
  ok: boolean
  action: string
  status?: string
  message?: string
  dns_records?: Array<{ type: string; host: string; value: string; purpose: string }>
  view?: EmailSendingSettingsResponse
}

export type ImportBatchesResponse = {
  company_code: string
  batches: ImportBatchSummary[]
}

export type MailboxConnection = {
  mailbox_id: string
  company_code: string
  provider: string
  provider_label?: string
  email_address?: string | null
  display_name?: string | null
  label_filter?: string | null
  status: string
  status_label: string
  auto_import: boolean
  has_credentials: boolean
  last_synced_at?: string | null
  created_at?: string
  updated_at?: string
}

export type MailboxFeatureStatus = {
  enabled: boolean
  encryption_ready: boolean
  gmail_oauth_ready: boolean
  m365_oauth_ready?: boolean
  premium?: boolean
  default_product?: string
  mailbox_sync_enabled?: boolean
  providers: { key: string; label: string; label_ar?: string; scopes?: string[]; ready?: boolean }[]
  setup_steps_en?: string[]
  setup_steps_ar?: string[]
}

export type MailboxListResponse = {
  company_code: string
  feature: MailboxFeatureStatus
  connections: MailboxConnection[]
}

export type MailboxCheckNowResponse = {
  ok: boolean
  imported: number
  duplicates: number
  skipped: number
  needs_role: number
  message: string
}

// --- Post-hire modules (Employees / Onboarding / Attendance / Leave / Shifts / Payroll / Analytics) ---

export type PosthireActionResult = {
  ok: boolean
  status: string
  message: string
  confirmation: {
    text: string
    action_type: string
    args: Record<string, unknown>
    action_hash?: string | null
  } | null
  result: Record<string, unknown> | null
}

export type PosthireEmployee = {
  employee_key: string
  name: string
  phone: string
  email: string
  position_title: string
  department: string
  onboarding_status: string
  employment_status?: string
  start_date?: string | null
  updated_at?: string | null
  pending_count?: number
  received_count?: number
  required_total?: number
  planned_start_date?: string | null
  overdue_count?: number
  next_owner?: string | null
  next_owner_group?: string | null
  next_item_label?: string | null
  /** Existing next-item status/storage — used to derive primary row action. */
  next_item_status?: string | null
  next_item_storage_status?: string | null
  assignment_status?: string | null
  template_version?: string | null
  /**
   * Canonical onboarding completion for this row, straight from
   * onboarding_completion_contract. The queue must render these instead of
   * re-deriving progress or ownership, or rows disagree with the drawer.
   */
  completion_state?: OnboardingCompletionState | null
  satisfied_count?: number
  open_count?: number
  completion_next_action?: {
    owner?: string | null
    message?: string | null
    message_en?: string | null
    message_ar?: string | null
  } | null
}

export type PosthireEmployeesResponse = {
  company_code: string
  count: number
  employees: PosthireEmployee[]
  total_count?: number
  limit?: number
  offset?: number
  has_more?: boolean
  active_count?: number
  left_count?: number
  onboarding_count?: number
  department_count?: number
}

export type NextActionSeverity = 'critical' | 'high' | 'medium' | 'low'

export type EmployeeProfileNextAction = {
  // Legacy flat shape (flag OFF) — kept optional for backward compatibility.
  label?: string
  page?: string
  // Ranked-engine shape (flag ON).
  id?: string
  severity?: NextActionSeverity
  module: string
  title?: string
  reason?: string
  executable?: boolean
  action_type?: string
  args?: Record<string, unknown>
  action_label?: string
  requires_confirmation?: boolean
  destructive?: boolean
  target?: { page: string; section: string }
  source_at?: string | null
  meta?: Record<string, unknown>
}

export type EmployeeProfileNextActionsSummary = {
  total: number
  by_severity: Record<NextActionSeverity, number>
  visible_cap: number
}

export type EmployeeProfileSections = {
  onboarding?: {
    status: string
    outstanding_count: number
    complete_count: number
    outstanding: {
      item_id?: string | null
      label: string
      status: string
      row_version?: number | null
      owner_group?: string | null
      required?: boolean
    }[]
  }
  compliance?: {
    expired: number
    expiring_soon: number
    missing: number
    needs_review: number
    valid: number
    needs_attention: number
    total_documents: number
    documents: {
      document_type: string
      document_label: string
      status: ComplianceBucket
      status_label: string
      tone: 'danger' | 'warning' | 'success'
      expiry_date?: string | null
      days_until_expiry?: number | null
      last_reminded_at?: string | null
      reminder_count?: number
    }[]
  }
  attendance?: {
    window_days: number
    present: number
    late: number
    absent: number
    recent: { date?: string | null; status?: string; late_minutes: number }[]
  }
  leave?: {
    pending_count: number
    items: { leave_type?: string; start_date?: string | null; end_date?: string | null; status?: string }[]
    balances_enabled?: boolean
    balances?: LeaveBalance[]
  }
  shifts?: {
    upcoming_count: number
    items: { date?: string | null; start_time: string; end_time: string; role: string; location: string; status?: string }[]
  }
  payroll?: {
    items: { timesheet_id?: string | null; period_start?: string | null; period_end?: string | null; status?: string; worked_hours: number; overtime_hours: number }[]
  }
  documents?: {
    count: number
    items: EmployeeDocument[]
  }
}

export type EmployeeDocument = {
  file_id: string
  document_type?: string | null
  label?: string | null
  item_id?: string | null
  filename?: string | null
  mime_type?: string | null
  size_bytes?: number | null
  stored_at?: string | null
  has_file: boolean
}

export type EmployeeDocumentsResponse = {
  company_code: string
  employee_key: string
  count: number
  documents: EmployeeDocument[]
}

export type EmployeeProfileResponse = {
  company_code: string
  employee: PosthireEmployee & {
    hired_at?: string | null
    documents_pending?: number | null
    documents_complete?: number | null
  }
  available_modules: string[]
  sections: EmployeeProfileSections
  next_actions: EmployeeProfileNextAction[]
  next_actions_summary?: EmployeeProfileNextActionsSummary | null
  next_actions_enabled?: boolean
  doc_upload_enabled?: boolean
  hr_mutate_enabled?: boolean
}

export type PosthireOnboardingResponse = {
  company_code: string
  in_progress: PosthireEmployee[]
  completed_count: number
  total: number
  hr_mutate_enabled?: boolean
  total_count?: number
  limit?: number
  offset?: number
  has_more?: boolean
}

export type OnboardingItem = {
  item_id?: string
  label?: string
  item_type?: string
  required?: boolean
  document_type?: string
  status?: string
  value?: string | null
  storage_provider?: string | null
  storage_status?: string | null
  storage_url?: string | null
  drive_url?: string | null
  reminder_count?: number | null
  last_reminded_at?: string | null
  escalated_at?: string | null
  updated_at?: string | null
  category?: string | null
  owner?: string | null
  row_version?: number | null
  due_date?: string | null
  depends_on?: string[] | null
  collection_mode?: string | null
  authority?: string | null
  template_version?: string | null
  blocked_by?: string[] | null
  blocked_reason?: string | null
  owner_group?: string | null
  waiting_on?: string | null
  responsible_party?: string | null
  actions?: string[] | null
  group?: string | null
  rejection_reason?: string | null
  file_id?: string | null
  replacement_required?: boolean | null
  review_status?: string | null
  parts_complete?: boolean | null
  civil_id_parts?: {
    schema?: string
    legacy_single?: boolean
    parts_complete?: boolean
    missing?: string[]
    version_id?: string | null
    review_status?: string | null
    front?: { present?: boolean; file_id?: string | null; hr_warning?: boolean; detected_side?: string | null }
    back?: { present?: boolean; file_id?: string | null; hr_warning?: boolean; detected_side?: string | null }
  } | null
}

export type OnboardingDetailResponse = {
  company_code: string
  hr_mutate_enabled?: boolean
  doc_upload_enabled?: boolean
  document_index?: Record<string, string>
  lifecycle_version?: string | null
  projection?: string | null
  /**
   * Canonical completion snapshot. HR must render this rather than deriving
   * completeness from counts, or the dashboard can disagree with the app.
   */
  completion?: {
    state?: OnboardingCompletionState
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
    next_action?: { owner?: string; message?: string; message_en?: string; message_ar?: string }
    legacy_onboarding_status?: string | null
  }
  onboarding_status?: string | null
  available_tasks?: OnboardingItem[]
  available_tasks_count?: number
  groups?: Record<string, OnboardingItem[]>
  your_actions?: OnboardingItem[]
  being_reviewed?: OnboardingItem[]
  handled_by_others?: OnboardingItem[]
  completed?: OnboardingItem[]
  permission_authority?: string | null
  permission_subject_user_id?: string | null
  permission_subject_company?: string | null
  employee_key: string
  name?: string | null
  phone?: string | null
  status?: string | null
  planned_start_date?: string | null
  template_version?: string | null
  overdue_count?: number
  next_owner?: string | null
  next_owner_group?: string | null
  next_item_label?: string | null
  next_item_status?: string | null
  next_item_storage_status?: string | null
  required_total: number
  received_count: number
  pending_count: number
  items?: OnboardingItem[]
  received: OnboardingItem[]
  pending: OnboardingItem[]
  received_labels: string[]
  pending_labels: string[]
  bank_collection?: {
    mode?: string
    plaintext_forbidden?: boolean
    message?: string
  }
}

export type PosthireAttendanceRow = {
  attendance_id?: string
  employee_key?: string
  employee_name?: string
  attendance_date?: string
  status?: string
  late_minutes?: number | null
  early_leave_minutes?: number | null
  check_in_at?: string | null
  check_out_at?: string | null
  scheduled_start?: string | null
  scheduled_end?: string | null
  notes?: string | null
  /** Backend attendance life-state when the row already carries it. */
  life_state?: string | null
  payroll_exclusion_reason?: string | null
  payroll_exclusion_reason_en?: string | null
  payroll_exclusion_reason_ar?: string | null
  metadata?: {
    exception_state?: string | null
    approval_status?: string | null
    payroll_eligible?: boolean | null
    payroll_locked?: boolean | null
    worked_minutes?: number | null
    early_leave_minutes?: number | null
    sessions?: Array<Record<string, unknown>>
    breaks?: Array<Record<string, unknown>>
    projection_version?: number | null
    [key: string]: unknown
  } | null
}

export type PosthireAttendanceResponse = {
  company_code: string
  date: string
  start_date?: string
  end_date?: string
  is_today?: boolean
  ok?: boolean
  import_enabled?: boolean
  attendance?: PosthireAttendanceRow[]
  status_filter?: string | null
  total_count?: number
  has_more?: boolean
  limit?: number
  offset?: number
}

export type PosthireLeaveRow = {
  leave_id?: string
  employee_key?: string
  employee_name?: string
  employee_phone?: string
  leave_type?: string
  status?: string
  start_date?: string
  end_date?: string
  reason?: string | null
  duration_unit?: string
  half_portion?: string | null
  start_time?: string | null
  end_time?: string | null
  chargeable_days?: number | null
  chargeable_hours?: number | null
  shift_conflict_count?: number | null
  row_version?: number | null
  next_action?: string | null
  temporal_state?: string | null
  is_partial_day?: boolean
  is_unpaid?: boolean
  sensitive_category?: string | null
  balances_enforced?: boolean
  legal_reviewed?: boolean
  /** Additive dual-control presentation fields when API surfaces them. */
  dual_control_pending?: boolean | null
  dual_pending?: boolean | null
  dual_control_status?: string | null
  dual_action_id?: string | null
}

export type LeaveBalance = {
  leave_type: string
  entitlement_days: number
  accrued_to_date: number
  consumed: number
  current_balance: number
  can_take_from?: string | null
  enforced?: boolean
  legal_reviewed?: boolean
}

export type PosthireLeaveResponse = {
  company_code: string
  view?: 'active' | 'history'
  section?: 'pending' | 'upcoming'
  pending?: PosthireLeaveRow[]
  upcoming?: PosthireLeaveRow[]
  history?: PosthireLeaveRow[]
  status_filter?: string | null
  balances_enabled?: boolean
  balances?: Record<string, LeaveBalance[]>
  pending_total?: number
  pending_has_more?: boolean
  upcoming_total?: number
  upcoming_has_more?: boolean
  history_total?: number
  history_has_more?: boolean
  offset?: number
  limit?: number
  balances_enforced?: boolean
  legal_reviewed?: boolean
  observe_only?: boolean
  wave4_enabled?: boolean
  real_decision_gate?: boolean
  holiday_year?: {
    year?: number
    status?: string
    fail_closed_if_enforced?: boolean
    reason?: string | null
    message_en?: string
    message_ar?: string
    enforced?: boolean
  }
}

export type PosthireShiftRow = {
  shift_id?: string
  employee_key?: string
  employee_name?: string
  employee_phone?: string
  shift_date?: string
  start_time?: string
  end_time?: string
  location?: string
  status?: string
  updated_at?: string
  ends_next_day?: boolean
  break_minutes?: number | null
  site_key?: string | null
  branch_key?: string | null
  team_key?: string | null
  position_key?: string | null
  role?: string | null
  /** Governed schedule category. Never inferred from free-text role. Missing → general. */
  assignment_type?: 'guest' | 'operations' | 'night' | 'event' | 'general' | string | null
  ui_state?: string
  is_overnight?: boolean
  open_reconciliation_count?: number
  schedule_reason_code?: string | null
  current_version_no?: number | null
  warnings?: unknown[]
}

export type PosthireSwapRow = {
  swap_id?: string
  employee_name?: string
  requester_employee_key?: string
  target_employee_key?: string
  shift_date?: string
  status?: string
}

export type PosthireAvailabilityRow = {
  availability_id?: string
  employee_key?: string
  employee_name?: string
  employee_phone?: string
  start_date?: string
  end_date?: string
  status?: string
}

export type PosthireReconFlagRow = {
  flag_id?: string
  shift_id?: string
  employee_key?: string
  flag_type?: string
  status?: string
  details?: Record<string, unknown>
}

export type PosthireReminderRow = {
  reminder_id?: string
  shift_id?: string
  employee_key?: string
  status?: string
  last_error?: string | null
}

export type PosthireShiftsWave3 = {
  enabled?: boolean
  version?: string
  actor_hr_allowlisted?: boolean
  actor_manager_allowlisted?: boolean
  real_mutation_gate?: boolean
  can_mutate_real?: boolean
  payroll_money?: boolean
  leave_balances_mutated?: boolean
  attendance_authority_mutated?: boolean
  talal_read_only?: boolean
  real_reminders?: boolean
  permission_matrix?: Record<string, unknown>
}

export type PosthireShiftsResponse = {
  company_code: string
  shifts: PosthireShiftRow[]
  swaps: PosthireSwapRow[]
  availability?: PosthireAvailabilityRow[]
  reconciliation_flags?: PosthireReconFlagRow[]
  terminal_reminders?: PosthireReminderRow[]
  start_date?: string
  end_date?: string
  week?: number
  view?: string
  total_count?: number
  limit?: number
  offset?: number
  has_more?: boolean
  wave3?: PosthireShiftsWave3
  wave4?: {
    enabled?: boolean
    version?: string
    templates?: boolean
    recurring_schedules?: boolean
    rotations?: boolean
    publishing?: boolean
    [key: string]: unknown
  }
  wave5?: {
    enabled?: boolean
    version?: string
    publishing?: boolean
    open_shifts?: boolean
    draft_publish?: boolean
    coverage_rules?: boolean
    [key: string]: unknown
  }
  wave6?: {
    enabled?: boolean
    version?: string
    rotations?: boolean
    remote_rosters?: boolean
    pam_export?: boolean
    pam_submission?: boolean
    compliance_profiles?: boolean
    [key: string]: unknown
  }
}

export type PosthireShiftHistoryResponse = {
  ok?: boolean
  shift?: PosthireShiftRow
  versions?: Array<Record<string, unknown>>
  events?: Array<Record<string, unknown>>
  wave3?: Record<string, unknown>
}

export type PosthireTimesheetRow = {
  timesheet_id?: string
  employee_name?: string
  status?: string
  total_hours?: number | string | null
  overtime_hours?: number | string | null
  worked_minutes?: number | null
  overtime_minutes?: number | null
  period_start?: string
  period_end?: string
}

export type PosthireExportRow = {
  export_id?: string
  period_start?: string
  period_end?: string
  created_at?: string
  status?: string
}

export type PosthirePayrollPolicy = {
  employee_pay_type?: string
  leave_policy?: string
  overtime_policy?: string
  overtime_cap_minutes?: number | null
  absence_deduction_enabled?: boolean
  late_deduction_enabled?: boolean
  early_leave_deduction_enabled?: boolean
  default_hourly_rate_kwd?: number | null
  currency?: string
  payment_processing?: string
  [key: string]: unknown
}

export type PayrollPeriodOption = {
  start_date: string
  end_date: string
  has_timesheets?: boolean
}

export type PosthirePayrollResponse = {
  company_code: string
  timesheets: PosthireTimesheetRow[]
  period: { start_date?: string | null; end_date?: string | null }
  periods?: PayrollPeriodOption[]
  policy?: PosthirePayrollPolicy
  exports: PosthireExportRow[]
  can_export: boolean
  total_count?: number
  draft_count?: number
  limit?: number
  offset?: number
  has_more?: boolean
}

export type PayrollExportPreviewRow = {
  employee_name?: string
  employee_pay_type?: string
  payable_minutes?: number | null
  deduction_minutes?: number | null
  overtime_review_minutes?: number | null
  estimated_amount_kwd?: number | null
  amount_status?: string
}

export type PayrollExportDetail = {
  company_code: string
  export_id: string
  period: { start_date?: string | null; end_date?: string | null }
  status?: string
  row_count?: number | null
  created_at?: string | null
  totals?: Record<string, unknown>
  policy?: PosthirePayrollPolicy
  preview_rows?: PayrollExportPreviewRow[]
}

/** Payroll Wave 2A-C — external adapter operations workspace bootstrap. */
export type ExternalPayrollWorkspaceResponse = {
  ok?: boolean
  enabled?: boolean
  synthetic_only?: boolean
  settings?: {
    payroll_mode?: string
    payment_processing?: string
    money_authority?: string
    attendance_input_source?: string
  }
  setup?: {
    payroll_mode?: string
    mode_label?: string
    mode_ok?: boolean
    payment_processing?: string
    payment_processing_ok?: boolean
    approved_contract_count?: number
    contracts_ok?: boolean
    period_count?: number
    periods_ok?: boolean
    money_authority?: string
    vendor_claimed?: boolean
  }
  package_contents?: {
    included?: string[]
    not_included_yet?: string[]
    export_csv_headers?: string[]
    import_csv_headers?: string[]
    attendance_leave_shifts_packaged?: boolean
  }
  counts?: { exports?: number; imports?: number; quarantine_open?: number; quarantine_total?: number }
  periods?: Array<{
    period_id?: string
    period_start?: string
    period_end?: string
    status?: string
    payroll_mode?: string
    attendance_input_source?: string
    row_version?: number
  }>
  exports?: Array<Record<string, unknown>>
  imports?: Array<Record<string, unknown>>
  quarantine?: Array<Record<string, unknown>>
  events?: Array<Record<string, unknown>>
  can_export?: boolean
  can_manage?: boolean
  can_approve?: boolean
  manager_scoped?: boolean
  authoritative_in_wathefni?: boolean
  money_authority?: string
  payment_processing?: string
  vendor_claimed?: boolean
}

export type PosthireAnalyticsInsight = {
  metric: string
  subject: string
  value: number | string
  detail?: string
  demoted?: boolean
  subject_key?: string | null
}

export type PosthireAnalyticsCounts = {
  scheduled_shifts?: number
  cancelled_shifts?: number
  absent_records?: number
  late_records?: number
  late_minutes?: number
  pending_leave?: number
  pending_availability?: number
  pending_swaps?: number
  [key: string]: number | undefined
}

export type PosthireAnalyticsDeepLink = {
  page: string
  employee?: string
  [key: string]: string | undefined
}

export type PosthireAnalyticsAttentionItem = {
  id: string
  severity: 'high' | 'medium' | 'low' | string
  reason?: string
  reason_en?: string
  reason_ar?: string
  subject: string
  subject_key?: string | null
  location?: string | null
  team?: string | null
  source_module: string
  count?: number
  value?: number | string
  deep_link: PosthireAnalyticsDeepLink
  definition_key?: string
}

export type PosthireAnalyticsHeadline = {
  key: string
  label_en: string
  label_ar: string
  value: number
  hint_en?: string | null
  hint_ar?: string | null
}

export type PosthireAnalyticsDefinition = {
  key: string
  label_en: string
  label_ar: string
  definition_en: string
  definition_ar: string
}

export type PosthireAnalyticsSource = {
  module: string
  available: boolean
  status: string
  authority?: string
  note_en?: string
  note_ar?: string
  error?: string
}

export type PosthireAnalyticsResponse = {
  company_code: string
  ok?: boolean
  start_date?: string
  end_date?: string
  as_of?: string
  timezone?: string
  window?: {
    kind?: string
    label_en?: string
    label_ar?: string
    start_date?: string
    end_date?: string
  }
  metric?: string
  counts?: PosthireAnalyticsCounts
  headlines?: PosthireAnalyticsHeadline[]
  attention?: PosthireAnalyticsAttentionItem[]
  insights?: PosthireAnalyticsInsight[]
  definitions?: PosthireAnalyticsDefinition[]
  sources?: {
    sources?: Record<string, PosthireAnalyticsSource>
    unavailable_source_keys?: string[]
    partial?: boolean
  }
  freshness?: {
    as_of?: string
    max_age_seconds?: number
    stale_after_seconds?: number
  }
  authority?: Record<string, unknown>
  branch_absences?: Array<Record<string, unknown>>
  contract?: string
  [key: string]: unknown
}

export type ComplianceBucket = 'expired' | 'expiring_soon' | 'missing' | 'needs_review' | 'valid'

export type ComplianceEvidenceStatus = 'missing' | 'uploaded' | 'hr_reviewed' | 'expired' | 'expiring'

export type ComplianceDocument = {
  employee_key: string
  employee_name: string
  department: string
  document_type: string
  document_type_canonical?: string
  document_label: string
  document_label_en?: string
  document_label_ar?: string
  status: ComplianceBucket
  status_label: string
  tone: 'danger' | 'warning' | 'success'
  expiry_date?: string | null
  days_until_expiry?: number | null
  last_checked_at?: string | null
  last_reminded_at?: string | null
  reminder_count: number
  confidence?: number | null
  next_action: string
  file_id?: string | null
  evidence_status?: ComplianceEvidenceStatus
  evidence_status_label_en?: string
  evidence_status_label_ar?: string
  government_verified?: boolean
  guidance_only?: boolean
  rule_label_en?: string
  rule_label_ar?: string
  owner_role?: string
  owner_label_en?: string
  owner_label_ar?: string
}

export type ComplianceSummary = {
  expired: number
  expiring_soon: number
  missing: number
  needs_review: number
  valid: number
  needs_attention: number
  total_documents: number
  employees_checked: number
  employees_total: number
}

export type ComplianceFinding = {
  id: string
  severity: 'high' | 'medium' | 'low' | string
  reason?: string
  reason_en: string
  reason_ar?: string
  why_it_matters_en?: string
  why_it_matters_ar?: string
  subject?: string
  subject_key?: string | null
  employee_key?: string | null
  employee_name?: string
  location?: string | null
  team?: string | null
  document_type?: string
  document_type_canonical?: string
  document_label?: string
  document_label_en?: string
  document_label_ar?: string
  bucket?: ComplianceBucket | string
  evidence_status?: ComplianceEvidenceStatus | string
  evidence_status_label_en?: string
  evidence_status_label_ar?: string
  government_verified?: boolean
  rule_label_en?: string
  rule_label_ar?: string
  guidance_only?: boolean
  owner_role?: string
  owner_label_en?: string
  owner_label_ar?: string
  deadline?: string | null
  deadline_label_en?: string
  deadline_label_ar?: string
  days_until_expiry?: number | null
  escalation_step?: string
  escalation_label_en?: string
  escalation_label_ar?: string
  system_of_action?: string
  system_of_action_why_en?: string
  system_of_action_why_ar?: string
  source_module?: string
  deep_link: { page: string; employee?: string; document_type?: string; module?: string }
  secondary_links?: Array<{ page: string; employee?: string; document_type?: string; label_en?: string; label_ar?: string }>
  alerts_delivery_owns_reminders?: boolean
}

export type PosthireComplianceResponse = {
  company_code: string
  summary: ComplianceSummary
  documents: ComplianceDocument[]
  doc_upload_enabled?: boolean
  filtered_total?: number
  offset?: number
  limit?: number | null
  has_more?: boolean
  findings?: ComplianceFinding[]
  findings_summary?: { total?: number; high?: number; medium?: number; low?: number }
  as_of?: string
  timezone?: string
  kuwait_date?: string
  window?: {
    kind?: string
    label_en?: string
    label_ar?: string
    start_date?: string
    end_date?: string
    as_of_date?: string
  }
  freshness?: { as_of?: string; max_age_seconds?: number; stale_after_seconds?: number }
  definitions?: Array<{
    key: string
    label_en: string
    label_ar: string
    definition_en: string
    definition_ar: string
  }>
  sources?: {
    partial?: boolean
    unavailable_source_keys?: string[]
    sources?: Record<
      string,
      {
        module?: string
        available?: boolean
        status?: string
        note_en?: string
        note_ar?: string
      }
    >
  }
  honesty?: Record<string, unknown>
  authority?: Record<string, unknown>
  contract?: string
  contract_version?: string
}

export type ActionInboxItem = {
  id: string
  severity: 'critical' | 'high' | 'medium' | 'low' | string
  what_en: string
  what_ar?: string
  why_en?: string
  why_ar?: string
  employee_key?: string | null
  employee_name?: string | null
  team?: string | null
  location?: string | null
  owner_role?: string
  owner_label_en?: string
  owner_label_ar?: string
  deadline?: string | null
  deadline_label_en?: string | null
  deadline_label_ar?: string | null
  escalation_step?: string | null
  escalation_label_en?: string | null
  escalation_label_ar?: string | null
  source_stream?: 'analytics' | 'compliance' | 'employees' | string
  source_module?: string
  system_of_action?: string
  evidence_status?: string | null
  evidence_status_label_en?: string | null
  evidence_status_label_ar?: string | null
  authority_status?: string | null
  authority_status_label_en?: string | null
  authority_status_label_ar?: string | null
  government_verified?: boolean
  deep_link: { page: string; employee?: string; document_type?: string }
  secondary_links?: Array<{ page: string; employee?: string; label_en?: string; label_ar?: string }>
  alerts_delivery_owns_notifications?: boolean
  grouped?: boolean
  grouped_count?: number
  grouped_document_types?: string[]
  grouped_member_ids?: string[]
}

export type PosthireActionInboxResponse = {
  ok?: boolean
  company_code: string
  contract?: string
  contract_version?: string
  as_of?: string
  timezone?: string
  kuwait_date?: string
  window?: { kind?: string; label_en?: string; label_ar?: string; as_of_date?: string }
  freshness?: { as_of?: string; max_age_seconds?: number; stale_after_seconds?: number }
  items: ActionInboxItem[]
  summary?: {
    total?: number
    by_stream?: Record<string, number>
    by_severity?: Record<string, number>
    deduped_e360_compliance?: number
    grouped_compliance_cases?: number
    grouped_collapsed_members?: number
    pre_group_total?: number
    phase0_drops?: Record<string, number>
  }
  sources?: {
    partial?: boolean
    unavailable_source_keys?: string[]
    analytics?: Record<string, unknown>
    compliance?: Record<string, unknown>
    employees?: Record<string, unknown>
  }
  definitions?: Array<{
    key: string
    label_en: string
    label_ar: string
    definition_en: string
    definition_ar: string
  }>
  honesty?: Record<string, unknown>
  authority?: Record<string, unknown>
}

export type HrTask = {
  task_id: string
  company_code: string
  employee_key: string | null
  employee_name: string | null
  task_type: string
  source: string | null
  title: string
  detail: string | null
  status: string
  priority: string
  related_message_id: string | null
  created_at: string
  updated_at: string
}

export type HrTasksResponse = {
  ok: boolean
  company_code: string
  open_count: number
  total?: number
  limit?: number
  offset?: number
  tasks: HrTask[]
}

// HR-readable delivery status for an employee message (the technical reason
// lives in last_error, never shown as the headline status).
export type OutboundDeliveryStatus =
  | 'pending'
  | 'delivered_whatsapp'
  | 'delivered_template'
  | 'sent_email_fallback'
  | 'needs_hr_action'
  | 'failed'
  | 'suppressed'
  | 'throttled'
  | 'dashboard_only'

export type OutboundFollowUpMessage = {
  message_id: string
  employee_key: string | null
  employee_name: string | null
  flow: string
  flow_label: string
  criticality: string
  status: OutboundDeliveryStatus
  kind?: 'issue' | 'info'
  reason: string
  suggested_action: string
  has_email: boolean
  has_task: boolean
  attempts: number | null
  last_attempt_at: string
}

export type MessagingReadiness = {
  whatsapp_connected: boolean
  whatsapp_links: number
  templates_configured: boolean
  email_fallback: boolean
  employees_total: number
  employees_with_email: number
  employees_missing_email: number
  summary: string
}

export type OutboundNeedsFollowUpResponse = {
  ok: boolean
  company_code: string
  count: number
  total?: number
  limit?: number
  offset?: number
  messages: OutboundFollowUpMessage[]
  messaging: MessagingReadiness
}

export type SetupReadinessStep = {
  key: string
  title: string
  done: boolean
  optional: boolean
  why: string
  action_label: string
  action_page: string
}

export type SetupReadinessResponse = {
  company_code: string
  ready: boolean
  completed: number
  total: number
  steps: SetupReadinessStep[]
}

export type ActivityActor = {
  name?: string | null
  email?: string | null
  phone?: string | null
  role?: string | null
  role_label?: string | null
  display: string
}

export type ActivityItem = {
  id: string
  at: string | null
  actor: ActivityActor
  action_type: string
  category: string
  summary: string
  target?: string | null
  status?: string | null
  sensitive: boolean
}

export type ActivityActorOption = {
  user_id?: string | null
  name?: string | null
  email?: string | null
  role_label?: string | null
}

export type ActivityResponse = {
  company_code: string
  total: number
  limit: number
  offset: number
  count: number
  has_more: boolean
  categories: string[]
  actors: ActivityActorOption[]
  items: ActivityItem[]
}

export type ActivityFilters = {
  start_date?: string
  end_date?: string
  actor?: string
  category?: string
  action_type?: string
  q?: string
  limit?: number
  offset?: number
}

/* ——— Employees 360 Wave 6 (Wave 3–5 API shapes) ——— */

export type EssRequestState =
  | 'draft'
  | 'submitted'
  | 'needs_information'
  | 'needs_review'
  | 'pending_manager'
  | 'pending_hr'
  | 'pending_payroll'
  | 'approved'
  | 'applied'
  | 'rejected'
  | 'withdrawn'
  | 'failed'
  | string

export type EssRequestRow = {
  request_id: string
  company_code?: string
  employee_key: string
  request_type: string
  state: EssRequestState
  requester_kind?: string
  approval_route?: Array<{ step?: string; role?: string; status?: string }>
  approval_cursor?: number
  proposed_values?: Record<string, unknown>
  fail_reason?: string | null
  created_at?: string
  updated_at?: string
}

export type EssRequestsResponse = {
  ok?: boolean
  requests: EssRequestRow[]
}

export type EssOwnViewResponse = {
  ok?: boolean
  employee_key: string
  bank?: { iban?: string; bank_name?: string; has_bank_on_file?: boolean; masked?: boolean }
  personal?: Record<string, unknown>
  documents?: Array<Record<string, unknown>>
  access_policy?: Record<string, unknown>
}

/* ——— Bank ESS (backend: employee_bank_ess.hr_bank_review) ——— */

export type BankSubmissionState =
  | 'none'
  | 'draft'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'needs_correction'
  | 'withdrawn'
  | string

/** Masked server-side. `<field>_masked` / `<field>_last4` are markers, not rows. */
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
  extraction?: {
    status?: string
    confidence?: number
    proposed?: Record<string, string>
    warnings?: string[]
    unreadable_reason?: string | null
    needs_manual_fallback?: boolean
    uncertain?: boolean
    missing_iban?: boolean
    wrong_document_type?: boolean
    authoritative?: boolean
    document_type?: string | null
    masked?: boolean
  } | null
}

export type BankDecisionEvent = {
  request_id?: string
  action?: string
  from_state?: string | null
  to_state?: string | null
  actor_user_id?: string | null
  actor_employee_key?: string | null
  detail?: Record<string, unknown> | null
  created_at?: string | null
}

export type BankReviewResponse = {
  contract_version?: string
  employee_key?: string
  has_verified_bank?: boolean
  /** What HR verified. Distinct from what payroll pays to. */
  verified?: {
    display?: BankDisplayValues
    fingerprint?: string | null
    verified_at?: string | null
    verified_by_stage?: string | null
  } | null
  /** What payroll actually uses right now. */
  payroll_effective?: {
    display?: BankDisplayValues
    effective_from?: string | null
    bank_profile_version?: number | null
  } | null
  submission?: {
    request_id: string
    state?: string | null
    submission_state?: BankSubmissionState
    concurrency_version?: number | null
    submitted_at?: string | null
    updated_at?: string | null
    proposed?: { display?: BankDisplayValues; fingerprint?: string | null; sealed?: boolean } | null
    rejection_reason?: string | null
    can_withdraw?: boolean
    can_resubmit?: boolean
    evidence?: BankEvidenceRow[]
  } | null
  submission_state?: BankSubmissionState
  change_under_review?: boolean
  next_step?: { owner?: string; message?: string; message_en?: string; message_ar?: string }
  comparison?: {
    current_verified?: BankDisplayValues
    proposed?: BankDisplayValues
    changed_fields?: string[]
    is_first_submission?: boolean
  }
  verified_history?: Array<{
    request_id?: string
    fingerprint?: string | null
    display?: BankDisplayValues
    verified_by_user_id?: string | null
    verified_by_stage?: string | null
    verified_at?: string | null
  }>
  effective_history?: Array<{
    effective_from?: string | null
    effective_to?: string | null
    display?: BankDisplayValues
    bank_profile_version?: number | null
  }>
  decision_history?: BankDecisionEvent[]
  payroll_lock?: { locked?: boolean; period_status?: string | null; period_end?: string | null }
  masking?: { masked_by_default?: boolean; reveal_requires_permission?: string; reveal_is_audited?: boolean }
}

/* ——— Onboarding completion (backend: onboarding_completion_contract) ——— */

export type OnboardingCompletionState =
  | 'not_started'
  | 'in_progress'
  | 'waiting_on_employee'
  | 'waiting_on_hr'
  | 'blocked'
  | 'completed'
  | 'reopened'
  | string

export type OnboardingCompletionResponse = {
  ok?: boolean
  contract_version?: string
  employee_key?: string
  state?: OnboardingCompletionState
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
  next_action?: { owner?: string; message?: string; message_en?: string; message_ar?: string }
  first_completed_at?: string | null
  last_completed_at?: string | null
  reopened_at?: string | null
  reopen_count?: number
  history?: Array<{
    from_state?: string | null
    to_state?: string
    reason?: string | null
    actor?: string | null
    created_at?: string | null
  }>
}

export type OrgUnitRow = {
  org_unit_id: string
  unit_type: string
  name: string
  unit_key?: string
  parent_org_unit_id?: string | null
  status?: string
  effective_from?: string | null
}

export type OrgUnitsResponse = { ok?: boolean; units: OrgUnitRow[] }

export type OrgHistoryRow = {
  history_id?: string
  employee_key?: string
  change_type?: string
  effective_from?: string
  effective_to?: string | null
  department_unit_id?: string | null
  location_unit_id?: string | null
  manager_employee_key?: string | null
  reason?: string | null
  status?: string
}

export type OrgHistoryResponse = { ok?: boolean; history: OrgHistoryRow[] }

export type LifecyclePendingResponse = {
  ok?: boolean
  company_code?: string
  count: number
  requests: Array<Record<string, unknown>>
}

export type RemediationRow = {
  employment_id: string
  employee_key?: string | null
  policy_pack_status?: string
  jurisdiction_code?: string | null
  worker_category?: string | null
  missing_fields?: string[]
  employment_status?: string
}

export type RemediationQueueResponse = {
  ok?: boolean
  company_code?: string
  count: number
  rows: RemediationRow[]
  note?: string
}

export type MigrationBatchRow = {
  batch_id: string
  filename?: string
  status: string
  row_count?: number
  success_count?: number
  fail_count?: number
  created_at?: string
  committed_at?: string | null
  rolled_back_at?: string | null
}

export type MigrationBatchesResponse = { ok?: boolean; batches: MigrationBatchRow[]; count?: number }

