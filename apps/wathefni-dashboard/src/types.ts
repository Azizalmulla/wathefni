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
  }
  status_counts: Array<{ status: string; count: number }>
  positions: PositionSummary[]
  recent_applications: ApplicationSummary[]
}

export type PositionSummary = {
  company_code?: string
  position_code: string
  position_title: string
  job_key?: string
  application_key?: string
  apply_code?: string
  application_link?: string
  qr_value?: string
  status?: string
  description?: string
  requirements?: unknown
  application_count: number
  active_count: number
  latest_applicant?: string
  latest_applicant_app_key?: string
  created_at?: string
  updated_at?: string
  latest_application_at?: string
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
  current_step?: string
  screening_status?: string
  data_source?: string
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
    status?: string
    raw_score?: number
    max_score?: number
    percent?: number
    band?: string
    summary?: string
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
  notification_channel?: string
  sent_subject?: string
  sent_body?: string
  invite_sent_at?: string
  notes?: string
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
  status?: string
  current_item_index?: number
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
  started_at?: string
  completed_at?: string
  updated_at?: string
}

export type AssessmentsResponse = {
  company_code: string
  ok: boolean
  enabled?: boolean
  module_disabled?: boolean
  required_module?: string
  total: number
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
  updated_at?: string | null
  pending_count?: number
  received_count?: number
}

export type PosthireEmployeesResponse = {
  company_code: string
  count: number
  employees: PosthireEmployee[]
}

export type EmployeeProfileNextAction = {
  module: string
  label: string
  page: string
}

export type EmployeeProfileSections = {
  onboarding?: {
    status: string
    outstanding_count: number
    complete_count: number
    outstanding: { label: string; status: string }[]
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
    items: { period_start?: string | null; period_end?: string | null; status?: string; worked_hours: number; overtime_hours: number }[]
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
}

export type PosthireOnboardingResponse = {
  company_code: string
  in_progress: PosthireEmployee[]
  completed_count: number
  total: number
  hr_mutate_enabled?: boolean
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
  ok?: boolean
  attendance?: PosthireAttendanceRow[]
  status_filter?: string | null
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
  pending: PosthireLeaveRow[]
  upcoming: PosthireLeaveRow[]
  balances_enabled?: boolean
  balances?: Record<string, LeaveBalance[]>
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

export type PosthirePayrollResponse = {
  company_code: string
  timesheets: PosthireTimesheetRow[]
  period: { start_date?: string | null; end_date?: string | null }
  policy?: PosthirePayrollPolicy
  exports: PosthireExportRow[]
  can_export: boolean
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

export type OutboundFollowUpMessage = {
  message_id: string
  employee_key: string | null
  employee_name: string | null
  flow: string
  template_key: string | null
  criticality: string
  status: OutboundDeliveryStatus
  channel_used: string | null
  last_error: string | null
  attempts: number
  hr_task_id: string | null
  body_preview: string | null
  created_at: string
  updated_at: string
}

export type OutboundNeedsFollowUpResponse = {
  ok: boolean
  company_code: string
  count: number
  messages: OutboundFollowUpMessage[]
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
