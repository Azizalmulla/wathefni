import { DashboardApiError } from '@/lib/api'
import { accessIssueFromError } from '@/lib/access'
import { customerVisibleBrandCopy } from '@/lib/publicBrand'
import { type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { rankingDecisionFor } from '@/lib/rankingPresentation'
import type {
  ApplicationSummary,
  CandidateInterview,
  InterviewTruth,
  PositionSummary,
  RankingCandidate,
  SummaryResponse,
} from '@/types'

export function transcriptStatusLabel(value: string | null | undefined) {
  const normalized = String(value || '').toLowerCase()
  if (['completed', 'ready'].includes(normalized)) return 'Ready'
  if (['failed', 'error'].includes(normalized)) return 'Needs retry'
  return 'Preparing summary'
}

export function candidateName(application: ApplicationSummary) {
  return application.candidate?.name || application.phone || 'Unknown candidate'
}

export const STAGE_LABELS: Record<string, string> = {
  awaiting_cv: 'Waiting for CV',
  cv_processing: 'Processing CV',
  cv_received: 'Processing CV',
  screening: 'Processing CV',
  ready_for_review: 'Ready for review',
  screening_complete: 'Ready for review',
  review_pending: 'Ready for review',
  shortlisted: 'Shortlisted',
  interview: 'Interview',
  scheduled: 'Scheduled',
  completed: 'Completed',
  no_show: 'No-show',
  rescheduled: 'Rescheduled',
  cancelled: 'Cancelled',
  notes_pending: 'Notes pending',
  feedback_complete: 'Feedback complete',
  hired: 'Hired',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  in_progress: 'In progress',
  in_review: 'In review',
  needs_review: 'Needs review',
  pending_review: 'Pending review',
  not_started: 'Not started',
  phone_screen: 'Phone screen',
  offered: 'Shortlisted',
  offer_sent: 'Shortlisted',
  link_sent: 'Sent',
  opened: 'Opened',
  consented: 'Opened',
  submitted: 'Submitted',
  processing: 'Processing',
  transcription_failed: 'Needs retry',
  summary_pending: 'Preparing summary',
  synthetic_until_client_benchmark: 'Collecting company results',
  internal_synthetic_until_client_benchmark: 'Collecting company results',
  video_ready_for_review: 'Ready for review',
}

export function stageLabel(value: string | null | undefined) {
  const normalized = String(value || 'unknown').toLowerCase()
  if (STAGE_LABELS[normalized]) return STAGE_LABELS[normalized]
  const spaced = normalized.replaceAll('_', ' ').trim()
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : spaced
}

export function friendlyDashboardError(error: unknown, fallback: string, locale: RecruitingLocale = 'en') {
  return customerVisibleBrandCopy(resolveFriendlyDashboardError(error, fallback, locale))
}

function resolveFriendlyDashboardError(error: unknown, fallback: string, locale: RecruitingLocale = 'en') {
  const concurrencyMessage = locale === 'ar'
    ? 'تم تحديث هذا السجل بواسطة مستخدم آخر. راجع أحدث نسخة قبل الحفظ.'
    : 'This was updated by another user. Review the latest version before saving.'
  const staleMessage = locale === 'ar'
    ? 'تغيّر هذا الطلب. حدّث الصفحة وراجع المرحلة الحالية قبل المحاولة مجدداً.'
    : 'This application changed. Refresh it and review the current stage before trying again.'
  const permissionMessage = locale === 'ar'
    ? 'ليست لديك صلاحية لتنفيذ هذا الإجراء.'
    : 'You do not have permission to do this action.'
  const assessmentErrorMessages: Record<string, string> = {
    attempt_expired: 'This assessment link has expired. Send a new invitation to let the candidate continue.',
    assessment_resend_failed: 'The assessment could not be resent. Review the candidate contact details and try again.',
    already_sent: 'An assessment invitation is already active. Resend only if the candidate needs a new link.',
    delivery_failed: 'The invitation could not be delivered. Check the candidate email/WhatsApp and retry.',
    report_not_ready: 'The report is not ready yet. Wait for scoring to finish before opening it.',
    invalid_transition: 'That assessment action is not valid for the current state.',
    stale_attempt: 'This assessment changed. Refresh and use the latest invitation.',
    duplicate_request: 'This request was already processed. Refresh to see the current state.',
  }
  const concurrencyCodes = new Set([
    'stale_version',
    'stale_update',
    'stale_job_version',
    'stale_job_update',
    'stale_note_version',
    'stale_task_version',
    'stale_ownership_version',
    'stale_lifecycle_version',
    'stale_settings_version',
    'stale_settings_update',
    'stale_interview_notes',
    'stale_assessment_review',
    'missing_expected_version',
  ])
  if (error instanceof DashboardApiError) {
    const detailObj = typeof error.detail === 'object' && error.detail ? error.detail as Record<string, unknown> : null
    if (concurrencyCodes.has(error.code) || detailObj?.conflict === true) {
      if (locale === 'ar' && typeof detailObj?.message_ar === 'string' && detailObj.message_ar) return detailObj.message_ar
      if (typeof detailObj?.message === 'string' && detailObj.message) return detailObj.message
      return concurrencyMessage
    }
    if (assessmentErrorMessages[error.code]) return assessmentErrorMessages[error.code]
    if (/attempt_expired|assessment_resend_failed|already_sent|delivery_failed|report_not_ready|invalid_transition|stale_attempt|duplicate_request/i.test(error.message)) {
      const matched = Object.keys(assessmentErrorMessages).find((key) => new RegExp(key, 'i').test(error.message))
      if (matched) return assessmentErrorMessages[matched]
    }
    if (['stale_state', 'stale_decision', 'stage_mismatch', 'application_state_changed'].includes(error.code)) {
      return staleMessage
    }
    if (['permission_denied', 'action_forbidden', 'forbidden_transition'].includes(error.code)) {
      return permissionMessage
    }
    if (error.code === 'account_inactive') {
      return 'Your account is not active.'
    }
    if (error.code === 'module_disabled') {
      return 'This feature is not enabled for this company.'
    }
    const accessIssue = accessIssueFromError(error)
    if (accessIssue) return accessIssue.description
    if (/invalid_grant|gmail_auth|token has been expired/i.test(error.message)) return 'Email needs reconnecting.'
    if (/no_usable_conversation_id|conversation_closed|conversation_inactive/i.test(error.message)) return 'WhatsApp conversation is not active.'
    if (error.message && !/backend|traceback|exception|error"|detail|module_disabled|auth_failed|not_found|permission_denied/i.test(error.message)) return error.message
  }
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  if (!message) return fallback
  if (/stale_state|stale_decision|stage_mismatch|state changed/i.test(message)) {
    return staleMessage
  }
  if (/action_forbidden|permission_denied|forbidden_transition/i.test(message)) {
    return permissionMessage
  }
  if (/invalid_grant|gmail_auth|token has been expired/i.test(message)) return 'Email needs reconnecting.'
  if (/no_usable_conversation_id|conversation_closed|conversation_inactive/i.test(message)) return 'WhatsApp conversation is not active.'
  if (/conversation_|no_usable_|backend|traceback|exception|error"|detail|module_disabled|auth_failed|not_found/i.test(message)) {
    return fallback
  }
  return message
}

export function assessmentStatusCount(statusCounts: Array<{ status: string; count: number }>, status: string) {
  return statusCounts.find((item) => item.status === status)?.count || 0
}

export function interviewStatusCount(statusCounts: Array<{ status: string; count: number }>, status: string) {
  return statusCounts.find((item) => item.status === status)?.count || 0
}

export function interviewFeedbackCount(feedbackCounts: Array<{ feedback_status: string; count: number }>, status: string) {
  return feedbackCounts.find((item) => item.feedback_status === status)?.count || 0
}

export function assessmentAverageLabel(value: number | null | undefined) {
  if (value == null || Number.isNaN(Number(value))) return 'No completed attempts yet'
  return `${value}%`
}

export function setupCalibrationLabel(value: string | null | undefined) {
  const normalized = String(value || '').toLowerCase()
  if (!normalized || normalized.includes('synthetic') || normalized.includes('benchmark')) return 'Collecting company results'
  if (normalized.includes('empirical') || normalized.includes('ready')) return 'Ready'
  return stageLabel(normalized)
}

/** Presentation-only: setup is ready when calibration is Ready and content validation passes. */
export function assessmentSetupIsReady(config: {
  norms?: { status?: string } | null
  item_bank?: { validation?: { ok?: boolean } | null } | null
} | null | undefined) {
  if (!config) return false
  const calibrationReady = setupCalibrationLabel(config.norms?.status) === 'Ready'
  const contentOk = Boolean(config.item_bank?.validation?.ok)
  return calibrationReady && contentOk
}

/** Latest norms group updated_at from config payload (already returned by backend). */
export function assessmentSetupLastRefreshedAt(config: {
  norms?: { groups?: Array<Record<string, unknown>> } | null
} | null | undefined): string | null {
  const groups = config?.norms?.groups
  if (!Array.isArray(groups) || !groups.length) return null
  let latestMs = Number.NaN
  let latestRaw: string | null = null
  for (const group of groups) {
    const raw = group?.updated_at
    if (typeof raw !== 'string' || !raw.trim()) continue
    const ms = Date.parse(raw)
    if (!Number.isFinite(ms)) continue
    if (!Number.isFinite(latestMs) || ms > latestMs) {
      latestMs = ms
      latestRaw = raw
    }
  }
  return latestRaw
}

export function assessmentSetupLastRefreshedLabel(
  value: string | null | undefined,
  locale: RecruitingLocale = 'en',
) {
  if (!value) return locale === 'ar' ? 'آخر تحديث غير مسجّل' : 'Last refreshed not recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return locale === 'ar' ? 'آخر تحديث غير مسجّل' : 'Last refreshed not recorded'
  const formatted = date.toLocaleString(locale === 'ar' ? 'ar' : 'en', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
  return locale === 'ar' ? `آخر تحديث ${formatted}` : `Last refreshed ${formatted}`
}

export function assessmentQueue(applications: ApplicationSummary[], cohortKey?: string) {
  // Presentation-only: never drop server-authorized cohort rows.
  // Eligibility / CV / delivery membership is backend authority.
  void cohortKey
  return Array.isArray(applications) ? applications : []
}

export function assessmentModuleEnabled(
  state: { enabled_modules?: string[] } | null | undefined,
  summary?: SummaryResponse | null,
) {
  if (Array.isArray(state?.enabled_modules)) return state.enabled_modules.includes('assessments')
  if (typeof summary?.features?.assessments_enabled === 'boolean') return summary.features.assessments_enabled
  return false
}

export function summaryValue(summary: CandidateInterview['ai_summary'] | undefined, keys: string[]) {
  const data = summary as Record<string, unknown> | undefined
  for (const key of keys) {
    const value = data?.[key]
    if (typeof value === 'string' && value.trim()) return value
    if (typeof value === 'number') return String(value)
  }
  return ''
}

export function normalizeOverallImpression(value: string) {
  const normalized = value.trim()
  if (!normalized) return ''
  if (/^evidence ready$/i.test(normalized) || /^review needed$/i.test(normalized)) return 'Needs more evidence'
  return normalized
}

export function normalizeEvidenceConfidence(value: string) {
  const normalized = value.trim()
  if (!normalized) return ''
  if (/^decision support$/i.test(normalized) || /^unknown$/i.test(normalized)) return 'Limited'
  return normalized
}

export function asyncVideoDisplayStatus(
  interview: InterviewTruth,
): { label: string; description: string; tone: 'default' | 'success' | 'warning' | 'danger' | 'muted' } {
  const review = interview.video_review_status
  const state = String(review?.state || '').toLowerCase()
  const asyncStatus = String(interview.async_status || '').toLowerCase()
  const hasResponse = Boolean(review?.response_count || ('video_answers' in interview && interview.video_answers?.length))
  const summaryReady = Boolean(review?.summary_ready || interview.ai_summary?.summary || interview.ai_summary?.overall_summary)
  if (String(interview.status || '').toLowerCase() === 'cancelled') {
    return { label: 'Cancelled', description: 'This video interview is no longer active.', tone: 'muted' }
  }
  if (interview.feedback?.complete || interview.feedback_status === 'feedback_complete') {
    return { label: 'Reviewed', description: 'HR review notes are saved for this video interview.', tone: 'success' }
  }
  if (state === 'ready_for_review' || summaryReady) {
    return { label: 'Ready for review', description: 'The video answer and AI summary are ready for HR review.', tone: 'success' }
  }
  if (state === 'processing' || state === 'summary_pending' || state === 'transcription_failed' || Boolean(review?.pending_count || review?.failed_count)) {
    return {
      label: 'Processing',
      description: 'The candidate submitted the video. The written summary is being prepared.',
      tone: review?.failed_count ? 'danger' : 'warning',
    }
  }
  if (state === 'submitted' || hasResponse || asyncStatus === 'completed' || String(interview.status || '').toLowerCase() === 'completed') {
    return { label: 'Submitted', description: 'The candidate submitted the video response.', tone: 'warning' }
  }
  if (state === 'started' || ['opened', 'consented', 'in_progress'].includes(asyncStatus)) {
    return { label: 'Opened', description: 'The candidate opened the link and started the video interview flow.', tone: 'default' }
  }
  return { label: 'Sent', description: 'The video interview link has been sent. Waiting for the candidate response.', tone: 'default' }
}

export function videoInterviewProcessingLine(interview: CandidateInterview) {
  if (interview.interview_type === 'async_video') return asyncVideoDisplayStatus(interview).description
  const answers = interview.video_answers || []
  if (!answers.length) return 'Waiting for the candidate to submit a video answer.'
  const failed = answers.filter((answer) => answer.transcript_status === 'failed').length
  if (failed) return `${failed} answer${failed === 1 ? '' : 's'} need summary retry. Original video remains available.`
  const pending = answers.filter((answer) => answer.transcript_status !== 'completed').length
  if (pending) return 'Video response is submitted. The written summary is being prepared.'
  if (interview.ai_summary?.summary || interview.ai_summary?.overall_summary) return 'Video answer and OctoHR analysis are ready for HR review.'
  return 'Video answer is ready. AI summary is being prepared.'
}

export function calendarEventLabel(interview: InterviewTruth) {
  if (interview.calendar_event_id) return 'Calendar event created'
  return 'Not recorded'
}

export function notificationChannelLabel(channel: string | null | undefined) {
  const normalized = String(channel || '').toLowerCase()
  if (!normalized) return 'Not recorded'
  if (normalized === 'whatsapp') return 'WhatsApp'
  if (normalized === 'email') return 'Email'
  if (normalized === 'both' || normalized === 'whatsapp_email') return 'WhatsApp + email'
  if (normalized === 'calendar' || normalized === 'calendar_email') return 'Google Calendar email'
  return stageLabel(normalized)
}

export function inviteTruthLabel(interview: InterviewTruth) {
  if (interview.candidate_notified) return `Sent${interview.notification_channel ? ` via ${notificationChannelLabel(interview.notification_channel)}` : ''}`
  if (interview.calendar_invite_sent) return 'Calendar invite sent'
  if (interview.candidate_invited) return 'Candidate invited'
  return 'Not recorded'
}

export function notesStateLabel(interview: InterviewTruth) {
  if ('notes' in interview && interview.notes?.trim()) return 'HR notes saved'
  if ('transcript' in interview && interview.transcript?.trim()) return 'Transcript saved'
  return 'Notes pending'
}

export function normalizedJobStatus(job: PositionSummary) {
  const raw = String(job.status || '').toLowerCase()
  if (['open', 'active', 'published'].includes(raw)) return 'open'
  if (raw === 'inactive') return 'closed'
  if (['closed', 'paused', 'draft'].includes(raw)) return raw
  return Number(job.active_count || 0) > 0 ? 'open' : 'closed'
}

export function rankingCandidateApplication(candidate: RankingCandidate): ApplicationSummary {
  const decision = rankingDecisionFor(candidate)
  const ranking = {
    score: decision.advisory_score == null ? undefined : decision.advisory_score,
    score_breakdown: candidate.score_breakdown || candidate.component_scores,
    confidence: candidate.confidence,
    evidence: decision.evidence_references || candidate.evidence,
    reasons: candidate.reasons,
    role_profile: candidate.role_profile,
    gpt_evaluation: candidate.gpt_evaluation,
    evidence_digest: candidate.evidence_digest,
    evaluation_audit: candidate.evaluation_audit,
  }
  if (candidate.application) {
    return { ...candidate.application, ranking }
  }
  return {
    app_key: candidate.app_key,
    company_code: '',
    phone: candidate.phone,
    candidate: { name: candidate.name },
    position: {
      code: candidate.position_code,
      title: candidate.position_title || candidate.position_code,
    },
    status: candidate.status,
    screening_status: candidate.screening_status,
    ranking,
  }
}
