/** Frontend mirrors of backend assessment_cohorts.py (Wave 3). */

export const ASSESSMENT_COHORT_READY_TO_SEND = 'assessment_ready_to_send'
export const ASSESSMENT_COHORT_SENT_PENDING = 'assessment_sent_pending'
export const ASSESSMENT_COHORT_IN_PROGRESS = 'assessment_in_progress'
export const ASSESSMENT_COHORT_EXPIRED = 'assessment_expired'
export const ASSESSMENT_COHORT_RESEND_NEEDED = 'assessment_resend_needed'
export const ASSESSMENT_COHORT_DELIVERY_FAILED = 'assessment_delivery_failed'
export const ASSESSMENT_COHORT_COMPLETED = 'assessment_completed'
export const ASSESSMENT_COHORT_ATTENTION = 'assessment_attention'

export type AssessmentActionSurface = 'send' | 'resend' | 'delivery_failed' | 'in_progress' | 'sent_pending' | 'completed' | 'attention'

const TAB_BY_COHORT: Record<string, AssessmentActionSurface> = {
  [ASSESSMENT_COHORT_READY_TO_SEND]: 'send',
  [ASSESSMENT_COHORT_SENT_PENDING]: 'sent_pending',
  [ASSESSMENT_COHORT_IN_PROGRESS]: 'in_progress',
  [ASSESSMENT_COHORT_EXPIRED]: 'resend',
  [ASSESSMENT_COHORT_RESEND_NEEDED]: 'resend',
  [ASSESSMENT_COHORT_DELIVERY_FAILED]: 'delivery_failed',
  [ASSESSMENT_COHORT_COMPLETED]: 'completed',
  [ASSESSMENT_COHORT_ATTENTION]: 'attention',
  assessment_pending: 'attention',
}

const COHORT_BY_TAB: Record<string, string> = {
  send: ASSESSMENT_COHORT_READY_TO_SEND,
  resend: ASSESSMENT_COHORT_RESEND_NEEDED,
  delivery_failed: ASSESSMENT_COHORT_DELIVERY_FAILED,
  in_progress: ASSESSMENT_COHORT_IN_PROGRESS,
  sent_pending: ASSESSMENT_COHORT_SENT_PENDING,
  completed: ASSESSMENT_COHORT_COMPLETED,
  attention: ASSESSMENT_COHORT_ATTENTION,
}

export function normalizeAssessmentCohortKey(raw?: string | null): string {
  const key = String(raw || '').trim().toLowerCase()
  const aliases: Record<string, string> = {
    ready_to_send: ASSESSMENT_COHORT_READY_TO_SEND,
    first_send: ASSESSMENT_COHORT_READY_TO_SEND,
    sent_pending: ASSESSMENT_COHORT_SENT_PENDING,
    pending: ASSESSMENT_COHORT_SENT_PENDING,
    in_progress: ASSESSMENT_COHORT_IN_PROGRESS,
    expired: ASSESSMENT_COHORT_EXPIRED,
    resend: ASSESSMENT_COHORT_RESEND_NEEDED,
    resend_needed: ASSESSMENT_COHORT_RESEND_NEEDED,
    delivery_failed: ASSESSMENT_COHORT_DELIVERY_FAILED,
    completed: ASSESSMENT_COHORT_COMPLETED,
    attention: ASSESSMENT_COHORT_ATTENTION,
    assessment_pending: ASSESSMENT_COHORT_ATTENTION,
    awaiting: ASSESSMENT_COHORT_ATTENTION,
  }
  return aliases[key] || key
}

export function assessmentTabForCohort(cohortKey?: string | null): AssessmentActionSurface {
  const key = normalizeAssessmentCohortKey(cohortKey)
  return TAB_BY_COHORT[key] || 'send'
}

export function assessmentCohortForTab(tab?: string | null): string {
  const key = String(tab || '').trim().toLowerCase()
  return COHORT_BY_TAB[key] || ASSESSMENT_COHORT_READY_TO_SEND
}

export function assessmentQueueActionLabel(
  cohortKey?: string | null,
  locale: 'en' | 'ar' = 'en',
): {
  button: string
  title: string
  description: string
  empty: string
} {
  const isAr = locale === 'ar'
  const tab = assessmentTabForCohort(cohortKey)
  if (tab === 'resend') {
    return {
      button: isAr ? 'إعادة إرسال التقييم' : 'Resend assessment',
      title: isAr ? 'يحتاج إعادة إرسال' : 'Resend needed',
      description: isAr ? 'تقييمات منتهية تحتاج دعوة جديدة.' : 'Expired assessments that need a new invitation.',
      empty: isAr ? 'لا توجد تقييمات منتهية تحتاج إعادة إرسال.' : 'No expired assessments need resend.',
    }
  }
  if (tab === 'delivery_failed') {
    return {
      button: isAr ? 'مراجعة فشل التسليم' : 'Review delivery failure',
      title: isAr ? 'فشل التسليم' : 'Delivery failed',
      description: isAr ? 'دعوات تقييم فشل تسليمها.' : 'Assessment invitations that failed to deliver.',
      empty: isAr ? 'لا توجد حالات فشل تسليم.' : 'No assessment delivery failures.',
    }
  }
  if (tab === 'in_progress') {
    return {
      button: isAr ? 'عرض قيد التنفيذ' : 'View in progress',
      title: isAr ? 'قيد التنفيذ' : 'In progress',
      description: isAr ? 'مرشحون يؤدون التقييم حالياً.' : 'Candidates currently taking an assessment.',
      empty: isAr ? 'لا توجد تقييمات قيد التنفيذ.' : 'No assessments are in progress.',
    }
  }
  if (tab === 'sent_pending') {
    return {
      button: isAr ? 'إعادة إرسال التقييم' : 'Resend assessment',
      title: isAr ? 'مُرسل بانتظار البدء' : 'Sent pending',
      description: isAr ? 'تقييمات أُرسلت وبانتظار بدء المرشح.' : 'Assessments sent and waiting for the candidate to start.',
      empty: isAr ? 'لا توجد تقييمات مرسلة بانتظار البدء.' : 'No sent assessments are waiting.',
    }
  }
  if (tab === 'completed') {
    return {
      button: isAr ? 'عرض التقرير' : 'View report',
      title: isAr ? 'مكتمل' : 'Completed',
      description: isAr ? 'تقييمات مكتملة جاهزة للمراجعة.' : 'Completed assessments ready for review.',
      empty: isAr ? 'لا توجد تقييمات مكتملة في هذه المجموعة.' : 'No completed assessments in this cohort.',
    }
  }
  return {
    button: isAr ? 'إرسال التقييم' : 'Send assessment',
    title: isAr ? 'جاهز للإرسال' : 'Ready to send',
    description: isAr ? 'مرشحون جاهزون لأول إرسال تقييم.' : 'Candidates ready for a first assessment send.',
    empty: isAr ? 'لا يوجد مرشحون جاهزون لأول إرسال.' : 'No candidates are ready for a first assessment send.',
  }
}

export function queuePrimaryAction(cohortKey?: string | null, allowed?: string[] | null): 'send' | 'resend' | 'view' {
  const allowedSet = new Set(allowed || [])
  void cohortKey
  if (allowedSet.has('send_assessment')) return 'send'
  if (allowedSet.has('resend_assessment')) return 'resend'
  return 'view'
}
