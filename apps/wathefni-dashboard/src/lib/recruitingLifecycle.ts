export const CANONICAL_APPLICATION_STAGES = [
  'awaiting_cv',
  'cv_processing',
  'ready_for_review',
  'shortlisted',
  'interview',
  'hired',
  'rejected',
  'withdrawn',
] as const

export const COMMUNICATION_STATES = ['pending', 'sent', 'failed', 'intentionally_skipped'] as const

export type RecruitingLocale = 'en' | 'ar'
export type CanonicalApplicationStage = (typeof CANONICAL_APPLICATION_STAGES)[number]
export type CommunicationState = (typeof COMMUNICATION_STATES)[number]

const LEGACY_STAGE_MAP: Record<string, CanonicalApplicationStage> = {
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

export const STAGE_LABELS: Record<RecruitingLocale, Record<CanonicalApplicationStage, string>> = {
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

export const COMMUNICATION_LABELS: Record<RecruitingLocale, Record<CommunicationState, string>> = {
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

export const ACTION_LABELS: Record<RecruitingLocale, Record<string, string>> = {
  en: {
    shortlist: 'Shortlist',
    reject: 'Reject',
    schedule_interview: 'Schedule interview',
    hire: 'Hire',
    notify: 'Contact candidate',
    send_assessment: 'Send assessment',
    send_video_interview: 'Send video interview',
    preview_cv: 'Preview CV',
    download_cv: 'Download CV',
    generate_evaluation: 'Generate analysis',
    mark_completed: 'Mark completed',
    mark_no_show: 'Mark no-show',
    cancel_interview: 'Cancel interview',
    write_notes: 'Write notes',
    open_candidate: 'Open candidate',
  },
  ar: {
    shortlist: 'إضافة للقائمة المختصرة',
    reject: 'رفض',
    schedule_interview: 'جدولة مقابلة',
    hire: 'تعيين',
    notify: 'التواصل مع المرشح',
    send_assessment: 'إرسال التقييم',
    send_video_interview: 'إرسال مقابلة فيديو',
    preview_cv: 'معاينة السيرة الذاتية',
    download_cv: 'تنزيل السيرة الذاتية',
    generate_evaluation: 'إنشاء التحليل',
    mark_completed: 'تحديد كمكتملة',
    mark_no_show: 'تسجيل عدم الحضور',
    cancel_interview: 'إلغاء المقابلة',
    write_notes: 'كتابة الملاحظات',
    open_candidate: 'فتح ملف المرشح',
  },
}

const COPY = {
  en: {
    language: 'العربية',
    candidateList: 'Candidate list',
    candidateListDescription: 'The real application stage, contact state, and next HR action for every candidate.',
    candidate: 'Candidate',
    job: 'Job',
    entryMethod: 'Entry method',
    applicationStage: 'Application stage',
    cvProcessing: 'CV processing',
    screening: 'Screening',
    communication: 'Communication',
    nextHumanAction: 'Next human action',
    automaticActions: 'Automatic actions',
    waitingForHr: 'Waiting for HR',
    operatorActions: 'Operator actions',
    candidateFacts: 'Verified facts',
    sourceEvidence: 'Source evidence',
    analysis: 'Wathefni analysis',
    recommendation: 'Recommendation',
    concerns: 'Concerns',
    missingInformation: 'Missing information',
    confidence: 'Confidence',
    humanDecision: 'Human decision',
    advisory: 'Advisory only. A human operator remains responsible for every decision.',
    notInformed: 'Stage changed — candidate has not been informed',
    noAutomaticActions: 'No automatic action is recorded yet.',
    noPendingHr: 'No HR action is currently waiting.',
    noPermittedActions: 'No actions are permitted for your current role and application stage.',
    interviewQueue: 'Interview queue',
    interviewQueueDescription: 'Interview status is shown separately from the candidate’s application stage.',
    interviewStatus: 'Interview status',
    schedule: 'Date and time',
    channelLocation: 'Channel or location',
    invitationStatus: 'Invitation status',
    candidateConfirmation: 'Candidate confirmation',
    notesStatus: 'Notes status',
    aiSummary: 'Wathefni analysis',
    noAdvisoryAnalysis: 'No advisory analysis is available yet.',
    dateNotSet: 'Date and time not set',
    recordedVideo: 'Recorded video',
    open: 'Open',
    candidateContacted: 'Candidate contacted',
    currentStage: 'Current stage',
    // Overview / Control Center
    overviewNextAction: 'Suggested next action',
    overviewOpenWorkQueue: 'Open work queue',
    overviewOpenFollowUps: 'Open follow-ups',
    overviewOpenReady: 'Review candidates',
    overviewOpenAssessments: 'Open awaiting assessments',
    overviewOpenRoleRanking: 'Open role ranking',
    overviewCheckRanking: 'Check ranking',
    overviewNeedsAttention: 'What needs attention today',
    overviewNeedsAttentionDescription: 'Start with the hiring actions that move candidates forward.',
    overviewReviewReady: 'Review ready candidates',
    overviewReviewReadyDetailOne: '1 candidate ready for an HR decision.',
    overviewReviewReadyDetail: '{count} candidates ready for an HR decision.',
    overviewReviewReadyEmpty: 'No candidates are waiting for HR review.',
    overviewSendAssessments: 'Send pending assessments',
    overviewSendAssessmentsDetailOne: '1 candidate is ready for assessment.',
    overviewSendAssessmentsDetail: '{count} candidates are ready for assessment.',
    overviewSendAssessmentsEmpty: 'No assessment sends are pending.',
    overviewFollowUp: 'Follow up with candidates',
    overviewFollowUpDetailOne: '1 candidate needs HR follow-up.',
    overviewFollowUpDetail: '{count} candidates need HR follow-up.',
    overviewFollowUpEmpty: 'No candidate follow-ups need attention.',
    overviewPrioritizeRole: 'Prioritize by role',
    overviewPrioritizeRoleEmpty: 'No role needs priority attention right now.',
    overviewPriorityQueue: 'Priority queue',
    overviewPriorityQueueDescription: 'Specific people to contact or decide on next.',
    overviewTopPriorities: 'Top priorities',
    overviewViewAll: 'View all',
    overviewShowLess: 'Show less',
    overviewQueueCount: '{count} actions',
    overviewRoleNextSteps: 'Role next steps',
    overviewRoleNextStepsDescription: 'What each opening needs from HR next.',
    overviewEmptyQueue: 'No urgent hiring actions right now.',
    overviewNoRoles: 'No active roles to analyze yet.',
    overviewBadgeFollowUp: 'Follow up',
    overviewBadgeReady: 'Ready',
    overviewBadgeAssessment: 'Assessment',
    overviewBadgeInterview: 'Interview',
    overviewBadgeRole: 'Role',
    overviewHeroFollowUpReason: '{count} candidates could not be reached. The oldest has been waiting {days} days.',
    overviewHeroFollowUpReasonOne: '1 candidate could not be reached and still needs a follow-up.',
    overviewHeroReadyReason: '{count} candidates are waiting for an HR decision.',
    overviewHeroReadyReasonOne: '1 candidate is waiting for an HR decision.',
    overviewHeroAssessmentReason: '{count} candidates are waiting for an assessment to be sent.',
    overviewHeroAssessmentReasonOne: '1 candidate is waiting for an assessment to be sent.',
    overviewHeroInterviewReason: '{count} candidates still need interview scheduling.',
    overviewHeroInterviewReasonOne: '1 candidate still needs interview scheduling.',
    overviewQueueFollowUp: 'Could not reach this candidate — follow up on another channel.',
    overviewQueueReady: 'Ready for an HR decision.',
    overviewQueueAssessment: 'Assessment send is still pending.',
    overviewQueueInterview: 'Interview scheduling is still needed.',
    overviewScheduleInterviews: 'Schedule interviews',
    overviewPageTitle: 'Wathefni Pre-Hiring Control Center',
    overviewPageSubtitle: 'A clean view of who needs review, who needs follow-up, and what HR should do next.',
    overviewEmptyHeroTitle: 'You’re caught up',
    overviewEmptyHeroReason: 'No open roles need attention, and there are no candidates waiting for review, follow-up, or assessment.',
    overviewRoleActiveCount: '{count} active',
    overviewRoleNoApplicants: 'No applicants yet. Share the QR or application link.',
    overviewRoleOpenList: 'Open the candidate list and decide who needs review first.',
    overviewRoleNoUrgent: 'No urgent action for this opening right now.',
    overviewRoleHelpScreeningOne: 'Help 1 candidate finish screening.',
    overviewRoleHelpScreening: 'Help {count} candidates finish screening.',
    overviewRoleReviewOne: 'Review 1 candidate and decide who moves forward.',
    overviewRoleReview: 'Review {count} candidates and decide who moves forward.',
    overviewRolePlanInterviewAssessmentOne: 'Plan interviews or assessments for 1 shortlisted candidate.',
    overviewRolePlanInterviewAssessment: 'Plan interviews or assessments for {count} shortlisted candidates.',
    overviewRolePlanInterviewOne: 'Plan interviews for 1 shortlisted candidate.',
    overviewRolePlanInterview: 'Plan interviews for {count} shortlisted candidates.',
    overviewRoleMoveForwardOne: 'Open this role and move 1 candidate forward.',
    overviewRoleMoveForward: 'Open this role and move {count} candidates forward.',
  },
  ar: {
    language: 'English',
    candidateList: 'قائمة المرشحين',
    candidateListDescription: 'المرحلة الفعلية للطلب وحالة التواصل والخطوة التالية للموارد البشرية.',
    candidate: 'المرشح',
    job: 'الوظيفة',
    entryMethod: 'طريقة الدخول',
    applicationStage: 'مرحلة الطلب',
    cvProcessing: 'معالجة السيرة الذاتية',
    screening: 'الفرز',
    communication: 'حالة التواصل',
    nextHumanAction: 'الإجراء البشري التالي',
    automaticActions: 'الإجراءات التلقائية',
    waitingForHr: 'بانتظار الموارد البشرية',
    operatorActions: 'إجراءات المشغّل',
    candidateFacts: 'حقائق موثّقة',
    sourceEvidence: 'أدلة المصدر',
    analysis: 'تحليل وظفني',
    recommendation: 'التوصية',
    concerns: 'المخاوف',
    missingInformation: 'المعلومات الناقصة',
    confidence: 'مستوى الثقة',
    humanDecision: 'القرار البشري',
    advisory: 'للاستشارة فقط. يبقى المشغّل البشري مسؤولاً عن كل قرار.',
    notInformed: 'تغيّرت المرحلة — لم يتم إبلاغ المرشح',
    noAutomaticActions: 'لم يتم تسجيل إجراء تلقائي حتى الآن.',
    noPendingHr: 'لا يوجد إجراء معلّق للموارد البشرية حالياً.',
    noPermittedActions: 'لا توجد إجراءات مسموحة لدورك ومرحلة الطلب الحالية.',
    interviewQueue: 'قائمة المقابلات',
    interviewQueueDescription: 'تُعرض حالة المقابلة بشكل منفصل عن مرحلة طلب المرشح.',
    interviewStatus: 'حالة المقابلة',
    schedule: 'التاريخ والوقت',
    channelLocation: 'القناة أو الموقع',
    invitationStatus: 'حالة الدعوة',
    candidateConfirmation: 'تأكيد المرشح',
    notesStatus: 'حالة الملاحظات',
    aiSummary: 'تحليل وظفني',
    noAdvisoryAnalysis: 'لا يتوفر تحليل استشاري حتى الآن.',
    dateNotSet: 'لم يتم تحديد التاريخ والوقت',
    recordedVideo: 'فيديو مسجّل',
    open: 'فتح',
    candidateContacted: 'تم التواصل مع المرشح',
    currentStage: 'المرحلة الحالية',
    overviewNextAction: 'الإجراء التالي المقترح',
    overviewOpenWorkQueue: 'فتح قائمة العمل',
    overviewOpenFollowUps: 'فتح المتابعات',
    overviewOpenReady: 'مراجعة المرشحين',
    overviewOpenAssessments: 'فتح بانتظار التقييم',
    overviewOpenRoleRanking: 'فتح ترتيب الوظيفة',
    overviewCheckRanking: 'عرض الترتيب',
    overviewNeedsAttention: 'ما يحتاج انتباهك اليوم',
    overviewNeedsAttentionDescription: 'ابدأ بإجراءات التوظيف التي تحرّك المرشحين إلى الأمام.',
    overviewReviewReady: 'مراجعة المرشحين الجاهزين',
    overviewReviewReadyDetailOne: 'مرشح واحد جاهز لقرار الموارد البشرية.',
    overviewReviewReadyDetail: '{count} مرشحين جاهزين لقرار الموارد البشرية.',
    overviewReviewReadyEmpty: 'لا يوجد مرشحون بانتظار المراجعة.',
    overviewSendAssessments: 'إرسال التقييمات المعلقة',
    overviewSendAssessmentsDetailOne: 'مرشح واحد جاهز للتقييم.',
    overviewSendAssessmentsDetail: '{count} مرشحين جاهزين للتقييم.',
    overviewSendAssessmentsEmpty: 'لا توجد تقييمات معلّقة للإرسال.',
    overviewFollowUp: 'متابعة المرشحين',
    overviewFollowUpDetailOne: 'مرشح واحد يحتاج متابعة من الموارد البشرية.',
    overviewFollowUpDetail: '{count} مرشحين يحتاجون متابعة من الموارد البشرية.',
    overviewFollowUpEmpty: 'لا توجد متابعات تحتاج انتباهًا.',
    overviewPrioritizeRole: 'أولوية حسب الوظيفة',
    overviewPrioritizeRoleEmpty: 'لا توجد وظيفة تحتاج أولوية الآن.',
    overviewPriorityQueue: 'قائمة الأولويات',
    overviewPriorityQueueDescription: 'أشخاص محددون للتواصل معهم أو اتخاذ قرار بشأنهم تاليًا.',
    overviewTopPriorities: 'أعلى الأولويات',
    overviewViewAll: 'عرض الكل',
    overviewShowLess: 'عرض أقل',
    overviewQueueCount: '{count} إجراءات',
    overviewRoleNextSteps: 'الخطوات التالية للوظائف',
    overviewRoleNextStepsDescription: 'ما تحتاجه كل وظيفة من الموارد البشرية تاليًا.',
    overviewEmptyQueue: 'لا توجد إجراءات توظيف عاجلة الآن.',
    overviewNoRoles: 'لا توجد وظائف نشطة للتحليل بعد.',
    overviewBadgeFollowUp: 'متابعة',
    overviewBadgeReady: 'جاهز',
    overviewBadgeAssessment: 'تقييم',
    overviewBadgeInterview: 'مقابلة',
    overviewBadgeRole: 'وظيفة',
    overviewHeroFollowUpReason: 'تعذر الوصول إلى {count} مرشحين. أقدمهم بانتظار المتابعة منذ {days} يومًا.',
    overviewHeroFollowUpReasonOne: 'تعذر الوصول إلى مرشح واحد وما زال يحتاج متابعة.',
    overviewHeroReadyReason: '{count} مرشحين بانتظار قرار من الموارد البشرية.',
    overviewHeroReadyReasonOne: 'مرشح واحد بانتظار قرار من الموارد البشرية.',
    overviewHeroAssessmentReason: '{count} مرشحين بانتظار إرسال التقييم.',
    overviewHeroAssessmentReasonOne: 'مرشح واحد بانتظار إرسال التقييم.',
    overviewHeroInterviewReason: '{count} مرشحين ما زالوا يحتاجون جدولة مقابلة.',
    overviewHeroInterviewReasonOne: 'مرشح واحد ما زال يحتاج جدولة مقابلة.',
    overviewQueueFollowUp: 'تعذر الوصول إلى هذا المرشح — تابع عبر قناة أخرى.',
    overviewQueueReady: 'جاهز لقرار الموارد البشرية.',
    overviewQueueAssessment: 'إرسال التقييم ما زال معلّقًا.',
    overviewQueueInterview: 'ما زالت جدولة المقابلة مطلوبة.',
    overviewScheduleInterviews: 'جدولة المقابلات',
    overviewPageTitle: 'مركز التحكم في التوظيف المسبق — وظفني',
    overviewPageSubtitle: 'عرض واضح لمن يحتاج مراجعة أو متابعة، وما يجب على الموارد البشرية فعله تاليًا.',
    overviewEmptyHeroTitle: 'لا يوجد عمل معلّق الآن',
    overviewEmptyHeroReason: 'لا توجد وظائف مفتوحة تحتاج انتباهًا، ولا مرشحون بانتظار المراجعة أو المتابعة أو التقييم.',
    overviewRoleActiveCount: '{count} نشط',
    overviewRoleNoApplicants: 'لا يوجد متقدمون بعد. شارك رمز QR أو رابط التقديم.',
    overviewRoleOpenList: 'افتح قائمة المرشحين وقرر من يحتاج المراجعة أولًا.',
    overviewRoleNoUrgent: 'لا يوجد إجراء عاجل لهذه الوظيفة الآن.',
    overviewRoleHelpScreeningOne: 'ساعد مرشحًا واحدًا على إكمال الفرز.',
    overviewRoleHelpScreening: 'ساعد {count} مرشحين على إكمال الفرز.',
    overviewRoleReviewOne: 'راجع مرشحًا واحدًا وقرر من يتقدم.',
    overviewRoleReview: 'راجع {count} مرشحين وقرر من يتقدم.',
    overviewRolePlanInterviewAssessmentOne: 'خطّط لمقابلة أو تقييم لمرشح واحد في القائمة المختصرة.',
    overviewRolePlanInterviewAssessment: 'خطّط لمقابلات أو تقييمات لـ {count} مرشحين في القائمة المختصرة.',
    overviewRolePlanInterviewOne: 'خطّط لمقابلة لمرشح واحد في القائمة المختصرة.',
    overviewRolePlanInterview: 'خطّط لمقابلات لـ {count} مرشحين في القائمة المختصرة.',
    overviewRoleMoveForwardOne: 'افتح هذه الوظيفة وحرّك مرشحًا واحدًا إلى الأمام.',
    overviewRoleMoveForward: 'افتح هذه الوظيفة وحرّك {count} مرشحين إلى الأمام.',
  },
} as const

export type RecruitingCopyKey = keyof (typeof COPY)['en']

export function recruitingCopy(locale: RecruitingLocale, key: RecruitingCopyKey, vars?: Record<string, string | number>): string {
  let text: string = COPY[locale][key]
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replace(`{${name}}`, String(value))
    }
  }
  return text
}

export function canonicalStage(value: string | null | undefined): CanonicalApplicationStage | null {
  const normalized = String(value || '').trim().toLowerCase()
  if ((CANONICAL_APPLICATION_STAGES as readonly string[]).includes(normalized)) {
    return normalized as CanonicalApplicationStage
  }
  return LEGACY_STAGE_MAP[normalized] || null
}

export function canonicalStageLabel(value: string | null | undefined, locale: RecruitingLocale = 'en'): string {
  const stage = canonicalStage(value)
  return stage ? STAGE_LABELS[locale][stage] : locale === 'ar' ? 'مرحلة غير معروفة' : 'Unknown stage'
}

export function communicationState(value: string | null | undefined): CommunicationState {
  const normalized = String(value || '').trim().toLowerCase()
  if ((COMMUNICATION_STATES as readonly string[]).includes(normalized)) return normalized as CommunicationState
  if (['queued', 'retrying', 'throttled'].includes(normalized)) return 'pending'
  if (['delivered', 'completed', 'recovered'].includes(normalized)) return 'sent'
  if (['suppressed', 'dashboard_only', 'skipped'].includes(normalized)) return 'intentionally_skipped'
  if (normalized) return normalized.includes('fail') ? 'failed' : 'pending'
  return 'intentionally_skipped'
}

export function communicationLabel(value: string | null | undefined, locale: RecruitingLocale = 'en'): string {
  return COMMUNICATION_LABELS[locale][communicationState(value)]
}

export function facetStatusLabel(value: string | null | undefined, locale: RecruitingLocale = 'en'): string {
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

export function actionLabel(value: string, locale: RecruitingLocale = 'en'): string {
  return ACTION_LABELS[locale][value] || value.replaceAll('_', ' ')
}

export function intakeSourceLabel(value: string | null | undefined, locale: RecruitingLocale = 'en'): string {
  const normalized = String(value || 'unknown').toLowerCase()
  const labels: Record<string, [string, string]> = {
    whatsapp: ['WhatsApp application', 'طلب عبر واتساب'],
    bulk_import: ['Bulk CV import', 'استيراد جماعي للسير الذاتية'],
    email: ['Recruiting email', 'البريد الإلكتروني للتوظيف'],
    manual: ['Manual entry', 'إدخال يدوي'],
    unknown: ['Source not recorded', 'المصدر غير مسجّل'],
  }
  const label = labels[normalized] || [normalized.replaceAll('_', ' '), normalized.replaceAll('_', ' ')]
  return label[locale === 'ar' ? 1 : 0]
}

export function workflowItemLabel(value: string, locale: RecruitingLocale = 'en'): string {
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
  const label = labels[value] || [value.replaceAll('_', ' '), value.replaceAll('_', ' ')]
  return label[locale === 'ar' ? 1 : 0]
}
