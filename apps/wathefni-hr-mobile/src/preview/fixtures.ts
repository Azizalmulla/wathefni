import type {
  CandidateReview,
  LeaveRequest,
  MobileMe,
  PrioritiesResponse,
} from '@/api/types'
import type { OperationalItem } from '@/features/operations/OperationalViews'

type OperatorFixture = 'hr-only' | 'recruiter-only' | 'restricted-manager' | 'multi-workspace'

const hrFeatures = {
  hr_tasks: { enabled: true, actions: ['read'] },
  leave_approvals: { enabled: true, actions: ['read', 'approve', 'reject'] },
  onboarding_review: { enabled: true, actions: ['read', 'review'] },
  document_review: { enabled: true, actions: ['read', 'review'] },
  attendance_exceptions: { enabled: true, actions: ['read', 'resolve'] },
  today_shifts: { enabled: true, actions: ['read'] },
  shift_swap_decisions: { enabled: true, actions: ['read', 'approve', 'reject'] },
  employee_search: { enabled: false, actions: [], reason: 'action_forbidden' },
  employee_quick_profile: { enabled: false, actions: [], reason: 'action_forbidden' },
  delivery_alerts: { enabled: true, actions: ['read'] },
}

const recruitingFeatures = {
  candidate_rankings: { enabled: true, actions: ['read'], advisory: true },
  candidate_summary: { enabled: true, actions: ['read'] },
  candidate_evidence: { enabled: true, actions: ['read'] },
  candidate_cv: { enabled: true, actions: ['view', 'preview', 'download'] },
  candidate_shortlist: { enabled: true, actions: ['shortlist'], confirmation_required: true },
  candidate_reject: { enabled: true, actions: ['reject'], confirmation_required: true },
  candidate_hire: { enabled: true, actions: ['hire'], confirmation_required: true },
  interview_status: { enabled: true, actions: ['read'] },
  interview_notes: { enabled: true, actions: ['read', 'write'] },
  candidate_communication_status: { enabled: true, actions: ['read'] },
}

export function meFixture(operator: OperatorFixture): MobileMe {
  const hr = operator !== 'recruiter-only'
  const recruiting = operator === 'recruiter-only' || operator === 'multi-workspace'
  const restricted = operator === 'restricted-manager'
  const operatorHRFeatures =
    operator === 'multi-workspace'
      ? {
          ...hrFeatures,
          employee_search: { enabled: true, actions: ['read'] },
          employee_quick_profile: { enabled: true, actions: ['read'] },
        }
      : hrFeatures
  return {
    ok: true,
    principal: {
      user_id: `preview-${operator}`,
      company_code: 'NORTHSTAR',
      display_name: operator === 'recruiter-only' ? 'Maya Al-Sabah' : 'Noura Al-Hamad',
      email: `${operator}@preview.invalid`,
      role: restricted ? 'manager' : operator === 'recruiter-only' ? 'recruiter' : 'hr_manager',
      role_label: restricted ? 'Manager' : operator === 'recruiter-only' ? 'Recruiter' : 'HR Manager',
    },
    permission_authority: 'backend_current',
    account_state: 'active',
    company_state: 'active',
    workspaces: {
      hr: { enabled: hr, features: hr ? structuredClone(operatorHRFeatures) : {} },
      recruiting: { enabled: recruiting, features: recruiting ? structuredClone(recruitingFeatures) : {} },
      owner: { enabled: false, features: {}, reason: 'feature_disabled' },
    },
    scope: {
      restricted,
      binding: restricted ? 'dashboard_user_id' : 'unrestricted',
      configured: true,
      configuration_error: null,
    },
  }
}

export function prioritiesFixture(operator: OperatorFixture): PrioritiesResponse {
  const hr = operator !== 'recruiter-only'
  const recruiting = operator === 'recruiter-only' || operator === 'multi-workspace'
  return {
    ok: true,
    generated_at: '2026-07-14T07:00:00+03:00',
    ranking_policy: 'separated_authoritative_sections_no_invented_urgency',
    sections: [
      ...(hr
        ? [
            {
              type: 'leave_approvals',
              title: 'Leave approvals',
              total: 3,
              items: [
                {
                  type: 'leave_approval',
                  target_id: 'leave-preview-001',
                  summary: 'Aisha Al-Rashid · Annual leave',
                  status: 'requested',
                  timestamp: '2026-07-14T06:40:00+03:00',
                  due_context: { start_date: '2026-07-20', end_date: '2026-07-24' },
                  permitted_actions: ['read', 'approve', 'reject'],
                  destination: '/leave/leave-preview-001',
                  severity: 'high',
                },
                {
                  type: 'leave_approval',
                  target_id: 'leave-preview-002',
                  summary: 'Omar Haddad · Sick leave',
                  status: 'requested',
                  timestamp: '2026-07-14T05:10:00+03:00',
                  due_context: { start_date: '2026-07-15', end_date: '2026-07-15' },
                  permitted_actions: ['read', 'approve', 'reject'],
                  destination: '/leave/leave-preview-002',
                  severity: null,
                },
              ],
            },
            {
              type: 'attendance_exceptions',
              title: 'Attendance exceptions',
              total: 2,
              items: [
                {
                  type: 'attendance_exception',
                  target_id: 'attendance-preview-1',
                  summary: 'Late arrival · Fatima Al-Duaij',
                  status: 'late',
                  timestamp: '2026-07-14T08:19:00+03:00',
                  due_context: { date: '2026-07-14' },
                  permitted_actions: ['read', 'resolve'],
                  destination: '/attendance',
                  severity: null,
                },
              ],
            },
          ]
        : []),
      ...(recruiting
        ? [
            {
              type: 'candidate_decisions',
              title: 'Candidate decisions',
              total: 4,
              items: [
                {
                  type: 'candidate_decision',
                  target_id: 'candidate-preview-001',
                  summary: 'Lina Al-Khaled · Senior Product Designer',
                  status: 'review_pending',
                  timestamp: '2026-07-14T04:00:00+03:00',
                  due_context: null,
                  permitted_actions: ['shortlist', 'reject', 'hire'],
                  destination: '/candidates/candidate-preview-001',
                  severity: null,
                },
              ],
            },
          ]
        : []),
    ],
  }
}

export const leaveFixture: LeaveRequest = {
  leave_id: 'leave-preview-001',
  employee: {
    employee_key: 'employee-preview-001',
    name: 'Aisha Al-Rashid',
    position_title: 'Senior Operations Specialist',
    department: 'Operations · Kuwait City',
    employment_status: 'active',
  },
  leave_type: 'Annual leave',
  start_date: '2026-07-20',
  end_date: '2026-07-24',
  duration_days: 5,
  reason: 'Family travel planned during the school break.',
  status: 'requested',
  decision_note: null,
  requested_at: '2026-07-14T06:40:00+03:00',
  updated_at: '2026-07-14T06:40:00+03:00',
  shift_conflict_count: 2,
  balance: { current_balance: 12, requested: 5, remaining_if_approved: 7 },
  allowed_actions: ['read', 'approve', 'reject'],
  destination: '/leave/leave-preview-001',
}

export const candidateFixture: CandidateReview = {
  app_key: 'candidate-preview-001',
  overview: {
    candidate: { name: 'Lina Al-Khaled', email: 'lina@preview.invalid' },
    position: { code: 'SPD-01', title: 'Senior Product Designer' },
    status: 'ready_for_review',
    canonical_stage: 'ready_for_review',
    status_label: 'Ready for review',
    current_step: 'Hiring team review',
    intake_source: 'whatsapp',
    cv_processing: { status: 'completed', received: true, automatic: true },
    screening: { status: 'completed', automatic: true },
    communication: { status: 'pending', stage_changed_without_contact: true },
    automatic_activity: ['cv_received', 'cv_processed', 'screening_updated', 'review_task_created'],
    waiting_for_hr: ['review_candidate', 'inform_candidate'],
  },
  ranking: {
    score: 86,
    confidence: 'medium',
    reasons: [
      'Led end-to-end product design for a regulated fintech platform.',
      'Portfolio shows measurable improvements to onboarding completion.',
    ],
    evidence: [
      'Eight years of product design experience are stated in the CV.',
      'Portfolio case study reports a 23% onboarding completion improvement.',
      'Recent role includes Arabic and English design-system ownership.',
    ],
    concerns: [
      'No direct evidence of managing designers is present in the submitted CV.',
      'Enterprise procurement experience is mentioned but not demonstrated.',
    ],
    missing_evidence: [
      'Current notice period has not been confirmed.',
      'No verified accessibility audit sample was attached.',
    ],
    ai_advisory: true,
  },
  cv: {
    available: true,
    filename: 'Lina-Al-Khaled-CV.pdf',
    mime_type: 'application/pdf',
    size_bytes: 482000,
    preview_path: '/dashboard/mobile/candidates/candidate-preview-001/cv/preview',
    download_path: '/dashboard/mobile/candidates/candidate-preview-001/cv',
  },
  interview: {
    status: 'feedback_pending',
    notes: 'Strong systems thinking. Validate leadership examples in the next round.',
  },
  communication_status: [{ status: 'pending', message_kind: 'application_stage_update' }],
  allowed_actions: ['shortlist', 'reject', 'preview_cv', 'download_cv'],
}

export function localizedPrioritiesFixture(
  operator: OperatorFixture,
  locale: 'en' | 'ar',
): PrioritiesResponse {
  const fixture = prioritiesFixture(operator)
  if (locale === 'en') return fixture
  const titles: Record<string, string> = {
    leave_approvals: 'طلبات الإجازة',
    attendance_exceptions: 'استثناءات الحضور',
    candidate_decisions: 'قرارات المرشحين',
  }
  return {
    ...fixture,
    sections: fixture.sections.map((section) => ({
      ...section,
      title: titles[section.type] || section.title,
      items: section.items.map((item) => ({
        ...item,
        summary:
          item.target_id === 'leave-preview-001'
            ? 'عائشة الراشد · إجازة سنوية'
            : item.target_id === 'leave-preview-002'
              ? 'عمر الحداد · إجازة مرضية'
              : item.type === 'attendance_exception'
                ? 'تأخر في الحضور · فاطمة الدعيج'
                : item.type === 'candidate_decision'
                  ? 'لينا الخالد · مصممة منتجات أولى'
                  : item.summary,
        status:
          item.status === 'requested'
            ? 'بانتظار القرار'
            : item.status === 'late'
              ? 'متأخر'
              : item.status === 'review_pending'
                ? 'بانتظار المراجعة'
                : item.status,
      })),
    })),
  }
}

export function localizedLeaveFixture(locale: 'en' | 'ar'): LeaveRequest {
  if (locale === 'en') return leaveFixture
  return {
    ...leaveFixture,
    employee: {
      ...leaveFixture.employee,
      name: 'عائشة الراشد',
      position_title: 'أخصائية عمليات أولى',
      department: 'العمليات · مدينة الكويت',
    },
    leave_type: 'إجازة سنوية',
    reason: 'رحلة عائلية مخططة خلال العطلة المدرسية.',
    status: 'بانتظار القرار',
  }
}

export function localizedCandidateFixture(locale: 'en' | 'ar'): CandidateReview {
  if (locale === 'en') return candidateFixture
  return {
    ...candidateFixture,
    overview: {
      ...candidateFixture.overview,
      candidate: { name: 'لينا الخالد', email: 'lina@preview.invalid' },
      position: { code: 'SPD-01', title: 'مصممة منتجات أولى' },
      status: 'ready_for_review',
      canonical_stage: 'ready_for_review',
      status_label: 'جاهز للمراجعة',
      current_step: 'مراجعة فريق التوظيف',
    },
    ranking: {
      ...candidateFixture.ranking,
      reasons: [
        'قادت تصميم منتج متكامل لمنصة تقنية مالية منظّمة.',
        'تعرض محفظة الأعمال تحسناً قابلاً للقياس في إكمال التسجيل.',
      ],
      evidence: [
        'تذكر السيرة الذاتية ثماني سنوات من الخبرة في تصميم المنتجات.',
        'توثّق دراسة حالة تحسناً بنسبة 23٪ في إكمال رحلة التسجيل.',
        'يشمل دورها الأخير إدارة نظام تصميم عربي وإنجليزي.',
      ],
      concerns: [
        'لا يوجد دليل مباشر في السيرة الذاتية على إدارة فريق من المصممين.',
        'ذُكرت خبرة المشتريات المؤسسية من دون مثال موثّق.',
      ],
      missing_evidence: [
        'لم يتم تأكيد فترة الإشعار الحالية.',
        'لا يوجد نموذج مرفق لتدقيق إمكانية الوصول.',
      ],
    },
    interview: {
      status: 'بانتظار الملاحظات',
      notes: 'تفكير قوي في الأنظمة. يجب التحقق من أمثلة القيادة في الجولة التالية.',
    },
  }
}

export function operationalFixture(view: string, locale: 'en' | 'ar'): OperationalItem[] {
  const ar = locale === 'ar'
  const fixtures: Record<string, OperationalItem[]> = {
    tasks: [
      {
        id: 'task-1',
        title: ar ? 'مراجعة مستندات الانضمام' : 'Review joining documents',
        subtitle: ar ? 'نور الصباح · مستندان بانتظار المراجعة' : 'Noor Al-Sabah · 2 documents pending',
        meta: ar ? 'الاستحقاق ١٦ يوليو ٢٠٢٦' : 'Due 16 July 2026',
        status: ar ? 'قيد الانتظار' : 'pending',
      },
    ],
    onboarding: [
      {
        id: 'employee-1',
        title: ar ? 'نور الصباح' : 'Noor Al-Sabah',
        subtitle: ar ? 'مراجعة المستندات' : 'Document review',
        meta: ar ? 'يبدأ في ٢٦ يوليو ٢٠٢٦' : 'Starts 26 July 2026',
        status: ar ? 'قيد التنفيذ' : 'in progress',
      },
    ],
    documents: [
      {
        id: 'employee-1:civil_id',
        title: ar ? 'نور الصباح' : 'Noor Al-Sabah',
        subtitle: ar ? 'البطاقة المدنية' : 'Civil ID',
        meta: ar ? 'تم التقديم في ١٤ يوليو ٢٠٢٦' : 'Submitted 14 July 2026',
        status: ar ? 'يحتاج مراجعة' : 'needs review',
        allowedActions: ['review'],
      },
    ],
    attendance: [
      {
        id: 'attendance-1',
        title: ar ? 'فاطمة الدعيج' : 'Fatima Al-Duaij',
        subtitle: ar ? 'تأخر في الحضور' : 'Late arrival',
        meta: ar ? '١٤ يوليو ٢٠٢٦، ٨:١٩ ص' : '14 July 2026, 8:19 am',
        status: ar ? 'مفتوح' : 'open',
        allowedActions: ['resolve'],
      },
    ],
    shifts: [
      {
        id: 'shift-1',
        title: ar ? 'يوسف الغانم' : 'Yousef Al-Ghanem',
        subtitle: ar ? 'فرع مدينة الكويت' : 'Kuwait City branch',
        meta: ar ? '٩:٠٠ ص إلى ٥:٠٠ م' : '9:00 am–5:00 pm',
        status: ar ? 'مجدولة' : 'scheduled',
      },
      {
        id: 'swap-1',
        title: ar ? 'تبديل مناوبة · دلال العوضي' : 'Shift swap · Dalal Al-Awadi',
        subtitle: ar ? 'تعارض مع موعد طبي' : 'Medical appointment conflict',
        meta: ar ? '١٧ يوليو ٢٠٢٦' : '17 July 2026',
        status: ar ? 'بانتظار القرار' : 'pending decision',
      },
    ],
    employees: [
      {
        id: 'employee-2',
        title: ar ? 'سارة الكندري' : 'Sara Al-Kandari',
        subtitle: ar ? 'مديرة عمليات' : 'Operations Manager',
        meta: ar ? 'العمليات · مدينة الكويت' : 'Operations · Kuwait City',
        status: ar ? 'نشطة' : 'active',
      },
    ],
    'delivery-alerts': [
      {
        id: 'alert-1',
        title: ar ? 'تعذّر إرسال دعوة المقابلة' : 'Interview invite not delivered',
        subtitle: ar ? 'تعذر تسليم البريد الإلكتروني للمرشح' : 'Candidate email delivery failed',
        meta: ar ? 'البريد الإلكتروني · ١٤ يوليو ٢٠٢٦' : 'Email · 14 July 2026',
        status: ar ? 'يحتاج متابعة' : 'needs attention',
      },
    ],
    candidates: [
      {
        id: 'candidate-1',
        title: ar ? 'لينا الخالد' : 'Lina Al-Khaled',
        subtitle: ar ? 'مصممة منتجات أولى' : 'Senior Product Designer',
        meta: ar
          ? 'طلب عبر واتساب · قيد الانتظار · مراجعة الأدلة واختيار الخطوة التالية'
          : 'WhatsApp application · Pending · Review evidence and choose the next step',
        status: ar ? 'جاهز للمراجعة' : 'Ready for review',
      },
    ],
    interviews: [
      {
        id: 'interview-1',
        title: ar ? 'لينا الخالد' : 'Lina Al-Khaled',
        subtitle: ar ? 'مصممة منتجات أولى' : 'Senior Product Designer',
        meta: ar
          ? 'مجدولة · ١٦ يوليو ٢٠٢٦، ١٠:٣٠ ص · تسجيل ملاحظات المقابلة'
          : 'Scheduled · 16 July 2026, 10:30 am · Record interview notes',
        status: ar ? 'المقابلة' : 'Interview',
      },
    ],
  }
  return fixtures[view] || []
}
