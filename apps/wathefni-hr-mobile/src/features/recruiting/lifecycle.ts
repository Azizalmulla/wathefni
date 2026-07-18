export const canonicalStages = [
  'awaiting_cv',
  'cv_processing',
  'ready_for_review',
  'shortlisted',
  'interview',
  'hired',
  'rejected',
  'withdrawn',
] as const

export const communicationStates = ['pending', 'sent', 'failed', 'intentionally_skipped'] as const

type Locale = 'en' | 'ar'
type Stage = (typeof canonicalStages)[number]
type Communication = (typeof communicationStates)[number]

const legacy: Record<string, Stage> = {
  cv_request: 'awaiting_cv',
  cv_upload: 'awaiting_cv',
  cv_received: 'cv_processing',
  screening: 'cv_processing',
  screening_complete: 'ready_for_review',
  review_pending: 'ready_for_review',
  scheduled: 'interview',
  offered: 'shortlisted',
  offer_sent: 'shortlisted',
}

export const stageLabels: Record<Locale, Record<Stage, string>> = {
  en: {
    awaiting_cv: 'Waiting for CV',
    cv_processing: 'Processing CV',
    ready_for_review: 'Ready for review',
    shortlisted: 'Shortlisted',
    interview: 'Interview',
    hired: 'Hired',
    rejected: 'Rejected',
    withdrawn: 'Withdrawn',
  },
  ar: {
    awaiting_cv: 'بانتظار السيرة الذاتية',
    cv_processing: 'معالجة السيرة الذاتية',
    ready_for_review: 'جاهز للمراجعة',
    shortlisted: 'في القائمة المختصرة',
    interview: 'المقابلة',
    hired: 'تم التعيين',
    rejected: 'مرفوض',
    withdrawn: 'منسحب',
  },
}

export const communicationLabels: Record<Locale, Record<Communication, string>> = {
  en: {
    pending: 'Pending',
    sent: 'Sent',
    failed: 'Failed',
    intentionally_skipped: 'Intentionally skipped',
  },
  ar: {
    pending: 'قيد الانتظار',
    sent: 'تم الإرسال',
    failed: 'فشل الإرسال',
    intentionally_skipped: 'تم التجاوز عمداً',
  },
}

export function canonicalStage(value: string | null | undefined): Stage | null {
  const normalized = String(value || '').trim().toLowerCase()
  if ((canonicalStages as readonly string[]).includes(normalized)) return normalized as Stage
  return legacy[normalized] || null
}

export function lifecycleStageLabel(value: string | null | undefined, locale: Locale): string {
  const stage = canonicalStage(value)
  return stage ? stageLabels[locale][stage] : locale === 'ar' ? 'مرحلة غير معروفة' : 'Unknown stage'
}

export function communicationState(value: string | null | undefined): Communication {
  const normalized = String(value || '').trim().toLowerCase()
  if ((communicationStates as readonly string[]).includes(normalized)) return normalized as Communication
  if (['queued', 'retrying', 'throttled'].includes(normalized)) return 'pending'
  if (['delivered', 'completed', 'recovered'].includes(normalized)) return 'sent'
  if (['suppressed', 'dashboard_only', 'skipped'].includes(normalized)) return 'intentionally_skipped'
  if (normalized) return normalized.includes('fail') ? 'failed' : 'pending'
  return 'intentionally_skipped'
}

export function lifecycleCommunicationLabel(value: string | null | undefined, locale: Locale): string {
  return communicationLabels[locale][communicationState(value)]
}

export function facetStatusLabel(value: string | null | undefined, locale: Locale): string {
  const normalized = String(value || '').trim().toLowerCase()
  const labels: Record<string, [string, string]> = {
    received: ['Received', 'تم الاستلام'],
    not_received: ['Not received', 'لم يتم الاستلام'],
    completed: ['Completed', 'مكتملة'],
    complete: ['Complete', 'مكتملة'],
    in_progress: ['In progress', 'قيد التنفيذ'],
    not_started: ['Not started', 'لم تبدأ'],
    scheduled: ['Scheduled', 'مجدولة'],
    rescheduled: ['Rescheduled', 'أعيدت جدولتها'],
    no_show: ['No-show', 'لم يحضر'],
    cancelled: ['Cancelled', 'ملغاة'],
    confirmed: ['Confirmed', 'تم التأكيد'],
    not_confirmed: ['Not confirmed', 'لم يتم التأكيد'],
    not_requested: ['Not requested', 'لم يُطلب'],
    pending: ['Pending', 'قيد الانتظار'],
    notes_pending: ['Notes pending', 'الملاحظات معلّقة'],
    feedback_complete: ['Feedback complete', 'اكتملت الملاحظات'],
  }
  const label = labels[normalized]
  if (label) return label[locale === 'ar' ? 1 : 0]
  if (!normalized) return locale === 'ar' ? 'غير مسجّل' : 'Not recorded'
  return normalized.replaceAll('_', ' ')
}

export function lifecycleActionLabel(value: string, locale: Locale): string {
  const labels: Record<string, [string, string]> = {
    shortlist: ['Shortlist', 'إضافة للقائمة المختصرة'],
    reject: ['Reject', 'رفض'],
    schedule_interview: ['Schedule interview', 'جدولة مقابلة'],
    hire: ['Hire', 'تعيين'],
  }
  const normalized = String(value || '')
  const label = labels[normalized] || [normalized.replaceAll('_', ' '), normalized.replaceAll('_', ' ')]
  return label[locale === 'ar' ? 1 : 0]
}

export function workflowLabel(value: string | null | undefined, locale: Locale): string {
  const labels: Record<string, [string, string]> = {
    cv_received: ['CV received and stored', 'تم استلام السيرة الذاتية وحفظها'],
    cv_processed: ['CV processed', 'تمت معالجة السيرة الذاتية'],
    screening_updated: ['Screening facet updated', 'تم تحديث بيانات الفرز'],
    review_task_created: ['Ready-for-review task created', 'تم إنشاء مهمة جاهزة للمراجعة'],
    review_candidate: ['Review evidence and choose the next step', 'مراجعة الأدلة واختيار الخطوة التالية'],
    schedule_interview: ['Schedule the interview', 'جدولة المقابلة'],
    record_interview_notes: ['Record interview notes', 'تسجيل ملاحظات المقابلة'],
    decide_after_interview: ['Make the post-interview human decision', 'اتخاذ القرار البشري بعد المقابلة'],
    resolve_communication: ['Resolve the communication failure', 'معالجة فشل التواصل'],
    inform_candidate: ['Inform the candidate of the stage change', 'إبلاغ المرشح بتغيير المرحلة'],
    resolve_invitation: ['Resolve the invitation failure', 'معالجة فشل الدعوة'],
    send_invitation: ['Send the interview invitation', 'إرسال دعوة المقابلة'],
    record_notes: ['Record interview notes', 'تسجيل ملاحظات المقابلة'],
    decide_application: ['Choose the next application step', 'اختيار الخطوة التالية للطلب'],
    review_next_step: ['Review and choose the next step', 'المراجعة واختيار الخطوة التالية'],
    conduct_interview: ['Conduct the interview', 'إجراء المقابلة'],
  }
  const normalized = String(value || '')
  const label = labels[normalized] || [normalized.replaceAll('_', ' '), normalized.replaceAll('_', ' ')]
  return label[locale === 'ar' ? 1 : 0]
}

export function intakeLabel(value: string | null | undefined, locale: Locale): string {
  const labels: Record<string, [string, string]> = {
    whatsapp: ['WhatsApp application', 'طلب عبر واتساب'],
    bulk_import: ['Bulk CV import', 'استيراد جماعي للسير الذاتية'],
    email: ['Recruiting email', 'البريد الإلكتروني للتوظيف'],
    manual: ['Manual entry', 'إدخال يدوي'],
    unknown: ['Source not recorded', 'المصدر غير مسجّل'],
  }
  const normalized = String(value || 'unknown').toLowerCase()
  const label = labels[normalized] || [normalized.replaceAll('_', ' '), normalized.replaceAll('_', ' ')]
  return label[locale === 'ar' ? 1 : 0]
}
