import type {
  CandidateReview,
  LeaveRequest,
  MobileMe,
  PrioritiesResponse,
} from '@/api/types'

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
      hr: { enabled: hr, features: hr ? hrFeatures : {} },
      recruiting: { enabled: recruiting, features: recruiting ? recruitingFeatures : {} },
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
    status: 'review_pending',
    current_step: 'Hiring team review',
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
  communication_status: [{ status: 'sent', message_kind: 'interview_invite' }],
  allowed_actions: ['shortlist', 'reject', 'hire'],
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
      status: 'بانتظار المراجعة',
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
