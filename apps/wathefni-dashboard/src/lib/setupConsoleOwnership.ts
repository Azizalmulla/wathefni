/**
 * Setup Console Phase 1 — canonical configuration ownership + deep links.
 * Product language only (no feature-flag / canary jargon in UI strings).
 */
export type ConfigOwner = 'setup_console' | 'operational_module' | 'platform'

export type OwnershipEntry = {
  key: string
  labelEn: string
  labelAr: string
  owner: ConfigOwner
  ownerLabelEn: string
  /** Deep link into Setup Console (hash/query) or dashboard ops */
  setupHref?: string
  opsHref?: string
  notesEn?: string
}

/** Canonical company-setup owners. Operational day-to-day stays on module screens. */
export const SETUP_CONSOLE_OWNERSHIP: OwnershipEntry[] = [
  {
    key: 'company_identity',
    labelEn: 'Company identity',
    labelAr: 'هوية الشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-profile',
    notesEn: 'Name, country, timezone, currency.',
  },
  {
    key: 'module_entitlements',
    labelEn: 'What this company uses',
    labelAr: 'ما تستخدمه الشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-modules',
  },
  {
    key: 'employee_app_enabled',
    labelEn: 'Employee App on/off',
    labelAr: 'تطبيق الموظف تشغيل/إيقاف',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-modules',
  },
  {
    key: 'employee_app_access_policy',
    labelEn: 'Who can use the Employee App',
    labelAr: 'من يمكنه استخدام تطبيق الموظف',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-app-access',
    notesEn: 'Company policy: all employees or selected / by department. Day-to-day enable/revoke stays in Employees.',
  },
  {
    key: 'employee_app_per_employee',
    labelEn: 'Per-employee app access',
    labelAr: 'وصول التطبيق لكل موظف',
    owner: 'operational_module',
    ownerLabelEn: 'Employees',
    opsHref: '/dashboard?page=employees',
    setupHref: '/setup-console#classic-app-access',
  },
  {
    key: 'channel_policy',
    labelEn: 'Channels & company WhatsApp',
    labelAr: 'القنوات وواتساب الشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-channels',
  },
  {
    key: 'hr_personal_whatsapp',
    labelEn: 'Your WhatsApp login link',
    labelAr: 'ربط واتساب لحسابك',
    owner: 'operational_module',
    ownerLabelEn: 'Settings → Account',
    opsHref: '/dashboard?page=settings',
    notesEn: 'Personal operator identity — not company channel policy.',
  },
  {
    key: 'payroll_company_setup',
    labelEn: 'Company payroll setup',
    labelAr: 'إعداد رواتب الشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-payroll-setup',
    opsHref: '/dashboard?page=payroll',
    notesEn: 'Mode, cycle, attendance payroll mode, components, approvals — Setup Console. Runs stay in Payroll.',
  },
  {
    key: 'payroll_runs',
    labelEn: 'Payroll runs & reviews',
    labelAr: 'تشغيل ومراجعة الرواتب',
    owner: 'operational_module',
    ownerLabelEn: 'Payroll',
    opsHref: '/dashboard?page=payroll',
  },
  {
    key: 'team_day_to_day',
    labelEn: 'Invite & manage team users',
    labelAr: 'دعوة وإدارة فريق العمل',
    owner: 'operational_module',
    ownerLabelEn: 'Settings → Team',
    opsHref: '/dashboard?page=settings',
    setupHref: '/setup-console#classic-team-access',
    notesEn: 'First Owner seed is Setup; ongoing invites/roles are Settings → Team (single writer).',
  },
  {
    key: 'team_access_summary',
    labelEn: 'Team & access overview',
    labelAr: 'نظرة على الفريق والوصول',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console (summary) + Settings → Team (writer)',
    setupHref: '/setup-console#classic-team-access',
    opsHref: '/dashboard?page=settings',
    notesEn: 'Setup shows people, roles, access summaries. Role changes use Settings APIs with last-owner + privilege guards.',
  },
  {
    key: 'integrations_catalog',
    labelEn: 'Integrations catalog',
    labelAr: 'كتالوج التكاملات',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-integrations',
    opsHref: '/dashboard?page=employees&view=migration',
    notesEn: 'Status + deep links only. Sync runs stay in Migration & Sync. Secrets stay sealed.',
  },
  {
    key: 'integrations_connected_systems',
    labelEn: 'Connected systems operations',
    labelAr: 'تشغيل الأنظمة المتصلة',
    owner: 'operational_module',
    ownerLabelEn: 'Migration & Sync',
    setupHref: '/setup-console#classic-integrations',
    opsHref: '/dashboard?page=employees&view=migration',
    notesEn: 'Connector CRUD, sync, exceptions, history — Migration & Sync. Setup catalogs only.',
  },
  {
    key: 'hr_personal_whatsapp',
    labelEn: 'Personal HR WhatsApp identity',
    labelAr: 'هوية واتساب الموارد البشرية الشخصية',
    owner: 'operational_module',
    ownerLabelEn: 'Settings → Account',
    opsHref: '/dashboard?page=settings',
    setupHref: '/setup-console#classic-channels',
    notesEn: 'Company messaging is Setup; personal HR WhatsApp identity is Settings → Account.',
  },
  {
    key: 'leave_company_policy',
    labelEn: 'Leave company policy',
    labelAr: 'سياسة الإجازات للشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-module-leave',
    opsHref: '/dashboard?page=leave',
    notesEn: 'Types, entitlement, eligibility, notice — Setup. Requests/balances stay in Leave.',
  },
  {
    key: 'performance_company_policy',
    labelEn: 'Performance company policy',
    labelAr: 'سياسة الأداء للشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-wave4-performance',
    opsHref: '/dashboard?page=performance',
    notesEn: 'Goals/reviews/check-ins/calibration policies — Setup. Workspace does not duplicate them. Talent stays separate.',
  },
  {
    key: 'talent_company_policy',
    labelEn: 'Talent company policy',
    labelAr: 'سياسة المواهب للشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-wave4-talent',
    opsHref: '/dashboard?page=talent',
    notesEn: 'Profile/potential/HiPo/succession/mobility policies — Setup. Distinct from Performance and recruiting talent_pool.',
  },
  {
    key: 'job_architecture_company_policy',
    labelEn: 'Job Architecture configuration',
    labelAr: 'تهيئة هيكل الوظائف',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-wave6-job-architecture',
    opsHref: '/dashboard?page=job-architecture',
    notesEn: 'Platform foundation — not a separate SKU. JA Job Profile ≠ Recruiting Job ≠ Requisition. Salary bands stay out.',
  },
  {
    key: 'learning_company_policy',
    labelEn: 'Learning & Development company policy',
    labelAr: 'سياسة التعلم والتطوير للشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-wave6-learning',
    opsHref: '/dashboard?page=learning',
    notesEn: 'Catalog, assignments, sessions, evidence-backed completion, certificates. Does not duplicate Wave 4 development plans.',
  },
  {
    key: 'benefits_company_policy',
    labelEn: 'Benefits company policy',
    labelAr: 'سياسة المزايا للشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-wave6-benefits',
    opsHref: '/dashboard?page=benefits',
    notesEn: 'Plan → eligibility → enrollment/waiver → coverage. Claims out. Payroll handoff optional.',
  },
  {
    key: 'attendance_company_policy',
    labelEn: 'Attendance company policy',
    labelAr: 'سياسة الحضور للشركة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console (+ Payroll for pay impact)',
    setupHref: '/setup-console#classic-module-attendance',
    opsHref: '/dashboard?page=attendance',
    notesEn: 'Grace/correction policy in Setup; attendance→pay + calendar in Payroll Setup. Logs stay in Attendance.',
  },
  {
    key: 'shifts_company_policy',
    labelEn: 'Shifts scheduling policy',
    labelAr: 'سياسة جدولة المناوبات',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-module-shifts',
    opsHref: '/dashboard?page=shifts',
    notesEn: 'Conflict/overnight/publish defaults — Setup. Templates/rosters/publish stay in Shifts. Rest days from Payroll calendar.',
  },
  {
    key: 'documents_compliance_company_policy',
    labelEn: 'Documents & compliance requirements',
    labelAr: 'متطلبات المستندات والامتثال',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-module-documents',
    opsHref: '/dashboard?page=compliance',
    notesEn: 'Required types + reminder windows — Setup. Uploads/reviews stay in Documents/Compliance ops. OCR is Wathefni-owned.',
  },
  {
    key: 'onboarding_company_policy',
    labelEn: 'Onboarding template policy',
    labelAr: 'سياسة قالب التهيئة',
    owner: 'setup_console',
    ownerLabelEn: 'Setup Console',
    setupHref: '/setup-console#classic-module-onboarding',
    opsHref: '/dashboard?page=onboarding',
    notesEn: 'Template bind + defaults for new hires — Setup. Active journeys stay in Onboarding. Historical pins preserved.',
  },
  {
    key: 'leave_attendance_shifts_ops',
    labelEn: 'Leave / Attendance / Shifts operations',
    labelAr: 'عمليات الإجازات والحضور والمناوبات',
    owner: 'operational_module',
    ownerLabelEn: 'Module workspaces',
    opsHref: '/dashboard?page=leave',
    setupHref: '/setup-console#classic-module-policies',
  },
]

export const MODULE_DISABLE_SEMANTICS = {
  stop_new_activity: true,
  hide_navigation: true,
  block_apis: true,
  preserve_history: true,
  preserve_audit: true,
  delete_data: false,
  silent_cancel_records: false,
  employee_app_extra: 'Disabling Employee App revokes active app sessions and supersedes open invites.',
} as const

export function dashboardPageHref(page: string, extra?: Record<string, string>): string {
  const params = new URLSearchParams({ page })
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v) params.set(k, v)
    }
  }
  return `/dashboard?${params.toString()}`
}

export function setupConsoleHref(anchor?: string): string {
  return anchor ? `/setup-console${anchor.startsWith('#') ? anchor : `#${anchor}`}` : '/setup-console'
}

export function ownershipByKey(key: string): OwnershipEntry | undefined {
  return SETUP_CONSOLE_OWNERSHIP.find((e) => e.key === key)
}
