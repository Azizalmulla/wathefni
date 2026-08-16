/** Shared Assessments EN/AR status and action vocabulary (presentation only). */

import type { RecruitingLocale } from '@/lib/recruitingLifecycle'

export type AssessmentVocabKey =
  | 'ready_to_send'
  | 'sent_pending'
  | 'in_progress'
  | 'resend_needed'
  | 'delivery_failed'
  | 'completed'
  | 'needs_review'
  | 'expired'
  | 'cancelled'
  | 'reviewed'
  | 'review_pending'
  | 'send'
  | 'attempts'
  | 'reports'
  | 'send_assessment'
  | 'resend_assessment'
  | 'cancel_assessment'
  | 'mark_reviewed'
  | 'view_report'
  | 'open_attempt'
  | 'wait_for_candidate'
  | 'retry_delivery'
  | 'review_report'

const EN: Record<AssessmentVocabKey, string> = {
  ready_to_send: 'Ready to send',
  sent_pending: 'Sent pending',
  in_progress: 'In progress',
  resend_needed: 'Resend needed',
  delivery_failed: 'Delivery failed',
  completed: 'Completed',
  needs_review: 'Needs review',
  expired: 'Expired',
  cancelled: 'Cancelled',
  reviewed: 'Reviewed',
  review_pending: 'Review pending',
  send: 'Send',
  attempts: 'Attempts',
  reports: 'Reports',
  send_assessment: 'Send assessment',
  resend_assessment: 'Resend assessment',
  cancel_assessment: 'Cancel assessment',
  mark_reviewed: 'Mark reviewed',
  view_report: 'View report',
  open_attempt: 'Open',
  wait_for_candidate: 'Wait for candidate',
  retry_delivery: 'Retry delivery',
  review_report: 'Review report',
}

const AR: Record<AssessmentVocabKey, string> = {
  ready_to_send: 'جاهز للإرسال',
  sent_pending: 'مُرسل بانتظار البدء',
  in_progress: 'قيد التنفيذ',
  resend_needed: 'يحتاج إعادة إرسال',
  delivery_failed: 'فشل التسليم',
  completed: 'مكتمل',
  needs_review: 'يحتاج مراجعة',
  expired: 'منتهي',
  cancelled: 'ملغى',
  reviewed: 'تمت المراجعة',
  review_pending: 'بانتظار المراجعة',
  send: 'إرسال',
  attempts: 'المحاولات',
  reports: 'التقارير',
  send_assessment: 'إرسال التقييم',
  resend_assessment: 'إعادة إرسال التقييم',
  cancel_assessment: 'إلغاء التقييم',
  mark_reviewed: 'تسجيل المراجعة',
  view_report: 'عرض التقرير',
  open_attempt: 'فتح',
  wait_for_candidate: 'انتظار المرشح',
  retry_delivery: 'إعادة محاولة التسليم',
  review_report: 'مراجعة التقرير',
}

const STATUS_ALIASES: Record<string, AssessmentVocabKey> = {
  ready_to_send: 'ready_to_send',
  'ready to send': 'ready_to_send',
  assessment_ready_to_send: 'ready_to_send',
  pending: 'sent_pending',
  sent: 'sent_pending',
  'sent pending': 'sent_pending',
  sent_pending: 'sent_pending',
  assessment_sent_pending: 'sent_pending',
  in_progress: 'in_progress',
  'in progress': 'in_progress',
  assessment_in_progress: 'in_progress',
  expired: 'expired',
  assessment_expired: 'expired',
  resend: 'resend_needed',
  resend_needed: 'resend_needed',
  'resend needed': 'resend_needed',
  assessment_resend_needed: 'resend_needed',
  delivery_failed: 'delivery_failed',
  'delivery failed': 'delivery_failed',
  failed: 'delivery_failed',
  send_failed: 'delivery_failed',
  invitation_failed: 'delivery_failed',
  assessment_delivery_failed: 'delivery_failed',
  completed: 'completed',
  assessment_completed: 'completed',
  needs_review: 'needs_review',
  'needs review': 'needs_review',
  cancelled: 'cancelled',
  canceled: 'cancelled',
  reviewed: 'reviewed',
  unreviewed: 'review_pending',
  review_pending: 'review_pending',
  'review pending': 'review_pending',
  'not sent': 'ready_to_send',
}

const ACTION_ALIASES: Record<string, AssessmentVocabKey> = {
  send_assessment: 'send_assessment',
  resend_assessment: 'resend_assessment',
  cancel_assessment: 'cancel_assessment',
  mark_reviewed: 'mark_reviewed',
  view_report: 'view_report',
  open_attempt: 'open_attempt',
  wait_for_candidate: 'wait_for_candidate',
  retry_delivery: 'retry_delivery',
  review_report: 'review_report',
}

export function assessmentCopy(locale: RecruitingLocale | undefined, key: AssessmentVocabKey): string {
  return (locale === 'ar' ? AR : EN)[key]
}

export function assessmentStatusLabel(
  locale: RecruitingLocale | undefined,
  raw?: string | null,
): string {
  const key = STATUS_ALIASES[String(raw || '').trim().toLowerCase()]
  if (key) return assessmentCopy(locale, key)
  const text = String(raw || '').trim()
  if (!text) return '—'
  // Never leak snake_case; title-case words as last resort.
  return text
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase())
}

export function assessmentActionLabel(
  locale: RecruitingLocale | undefined,
  raw?: string | null,
): string {
  const key = ACTION_ALIASES[String(raw || '').trim().toLowerCase()]
  if (key) return assessmentCopy(locale, key)
  const text = String(raw || '').trim()
  if (!text) return '—'
  return text
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase())
}

export function assessmentCohortChipLabel(
  locale: RecruitingLocale | undefined,
  cohortKey: string,
): string {
  const normalized = String(cohortKey || '').trim().toLowerCase()
  if (normalized === 'assessment_ready_to_send') return assessmentCopy(locale, 'ready_to_send')
  if (normalized === 'assessment_sent_pending') return assessmentCopy(locale, 'sent_pending')
  if (normalized === 'assessment_in_progress') return assessmentCopy(locale, 'in_progress')
  if (normalized === 'assessment_resend_needed' || normalized === 'assessment_expired') {
    return assessmentCopy(locale, 'resend_needed')
  }
  if (normalized === 'assessment_delivery_failed') return assessmentCopy(locale, 'delivery_failed')
  if (normalized === 'assessment_completed') return assessmentCopy(locale, 'completed')
  return assessmentStatusLabel(locale, cohortKey)
}
