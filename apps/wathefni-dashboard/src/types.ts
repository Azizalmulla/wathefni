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
  company_code: string
  email: string
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
}

export type DashboardChatResponse = {
  reply_text: string
  intent?: string | null
  turn_id?: string | null
  candidate_cards: DashboardChatCandidateCard[]
  navigation: DashboardChatNavigation[]
  confirmation?: {
    pending_action_id?: string
    label?: string
    summary?: string | null
    status?: string | null
    is_active?: boolean
  } | null
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
    confirmation?: DashboardChatResponse['confirmation']
    intent?: string | null
    turn_id?: string | null
  }
  created_at?: string
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
  }
  next_action?: PrehireNextAction
  role_priority?: PrehireRolePriority | null
  definitions?: Record<string, unknown>
  overview_as_of?: string
  status_counts: Array<{ status: string; count: number }>
  positions: PositionSummary[]
  recent_applications: ApplicationSummary[]
}

export type PrehireNextAction = {
  action: string
  priority: number
  reason: string
  total_matching: number
  destination?: {
    page?: string
    filters?: Record<string, string>
  }
  authority_source?: string
  label?: string
  as_of?: string
  role?: { position_code?: string; position_title?: string }
  alternatives?: Array<{ action: string; priority: number; total_matching: number }>
  sla_hours?: Record<string, number>
}

export type PrehireRolePriority = {
  position_code: string
  position_title: string
  ready_count?: number
  follow_up_count?: number
  assessment_pending_count?: number
  active_count?: number
  oldest_ready_hours?: number
  priority: number
  reason: string
  destination?: { page?: string; filters?: Record<string, string> }
  ranking_destination?: { page?: string; filters?: Record<string, string> }
}

export type PrehireWorkQueueItem = {
  action_type: string
  app_key?: string
  candidate_name?: string
  position_code?: string
  position_title?: string
  reason: string
  priority: number
  age_hours?: number
  destination?: { page?: string; filters?: Record<string, string> }
  authority_source?: string
  as_of?: string
}

export type PrehireWorkQueueResponse = {
  company_code: string
  ok: boolean
  as_of: string
  authority_source?: string
  total: number
  limit: number
  cursor?: string | null
  next_cursor?: string | null
  has_more?: boolean
  items: PrehireWorkQueueItem[]
  sla_hours?: Record<string, number>
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
  job_key?: string
  application_key?: string
  apply_code?: string
  application_link?: string
  qr_value?: string
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
  canonical_stage?: string
  status_label?: string
  current_step?: string
  screening_status?: string
  data_source?: string
  intake_source?: string
  cv_processing?: {
    status?: string
    received?: boolean
    automatic?: boolean
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
  applications: ApplicationSummary[]
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
  created_at?: string
  updated_at?: string
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
  score: number
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
  }
  role_profile?: {
    key?: string
    label?: string
    criteria?: Array<{ key?: string; label?: string; keywords?: string[] }>
  }
  gpt_evaluation?: {
    source?: string
    fit_summary?: string
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
  application?: ApplicationSummary
}

export type RankingResponse = {
  company_code: string
  ok: boolean
  total_matching: number
  role_profile?: {
    key?: string
    label?: string
    criteria?: Array<{ key?: string; label?: string; keywords?: string[] }>
  }
  candidates: RankingCandidate[]
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
  exports: {
    candidate_rows: number
    role_rows: number
    assessment_rows: number
    interview_rows: number
    followup_rows: number
  }
  summary: {
    cv_received: number
    cv_missing: number
    screening_complete: number
    ready_for_review: number
    assessment_pending: number
    assessment_completed: number
    interview_scheduled: number
    interview_completed: number
    interview_no_show: number
    followups: number
    followup_delivery_events?: number
  }
  breakdowns: {
    applications_by_stage: ReportBreakdownRow[]
    candidates_by_role: ReportBreakdownRow[]
    assessment_status: ReportBreakdownRow[]
    interview_status: ReportBreakdownRow[]
    followups_by_type: ReportBreakdownRow[]
  }
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
}

export type AssessmentsResponse = {
  company_code: string
  ok: boolean
  enabled?: boolean
  module_disabled?: boolean
  required_module?: string
  total: number
  limit?: number
  offset?: number
  status_counts: Array<{ status: string; count: number }>
  average_percent?: number | null
  attempts: AssessmentAttempt[]
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
  providers: { key: string; label: string }[]
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
    outstanding: { item_id?: string | null; label: string; status: string }[]
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
}

export type OnboardingDetailResponse = {
  company_code: string
  hr_mutate_enabled?: boolean
  doc_upload_enabled?: boolean
  document_index?: Record<string, string>
  employee_key: string
  name?: string | null
  phone?: string | null
  status?: string | null
  required_total: number
  received_count: number
  pending_count: number
  received: OnboardingItem[]
  pending: OnboardingItem[]
  received_labels: string[]
  pending_labels: string[]
}

export type PosthireAttendanceRow = {
  attendance_id?: string
  employee_key?: string
  employee_name?: string
  attendance_date?: string
  status?: string
  late_minutes?: number | null
  check_in_at?: string | null
  check_out_at?: string | null
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
}

export type PosthireShiftRow = {
  shift_id?: string
  employee_name?: string
  shift_date?: string
  start_time?: string
  end_time?: string
  location?: string
  status?: string
}

export type PosthireSwapRow = {
  swap_id?: string
  employee_name?: string
  shift_date?: string
  status?: string
}

export type PosthireShiftsResponse = {
  company_code: string
  shifts: PosthireShiftRow[]
  swaps: PosthireSwapRow[]
  start_date?: string
  end_date?: string
  week?: number
  total_count?: number
  limit?: number
  offset?: number
  has_more?: boolean
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

export type PosthireAnalyticsInsight = {
  metric: string
  subject: string
  value: number | string
  detail?: string
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

export type PosthireAnalyticsResponse = {
  company_code: string
  ok?: boolean
  start_date?: string
  end_date?: string
  metric?: string
  counts?: PosthireAnalyticsCounts
  insights?: PosthireAnalyticsInsight[]
  branch_absences?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export type ComplianceBucket = 'expired' | 'expiring_soon' | 'missing' | 'needs_review' | 'valid'

export type ComplianceDocument = {
  employee_key: string
  employee_name: string
  department: string
  document_type: string
  document_label: string
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

export type PosthireComplianceResponse = {
  company_code: string
  summary: ComplianceSummary
  documents: ComplianceDocument[]
  doc_upload_enabled?: boolean
  filtered_total?: number
  offset?: number
  limit?: number | null
  has_more?: boolean
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
