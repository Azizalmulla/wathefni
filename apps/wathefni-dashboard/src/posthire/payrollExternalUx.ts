/**
 * Payroll Wave 2A-C/D — EN/AR copy for external payroll operations workspace.
 * Money authority remains external; payment_processing stays disabled.
 * Wave 2A-D: operator-facing language (no engineer jargon in primary labels).
 */

export type PayrollExternalLocale = 'en' | 'ar'

type Copy = {
  title: string
  subtitle: string
  honesty: string
  moneyAuthority: string
  paymentDisabled: string
  vendorUnclaimed: string
  notAuthoritative: string
  tabOverview: string
  tabExports: string
  tabQuarantine: string
  tabHistory: string
  tabHelp: string
  tabTimesheets: string
  tabTimesheetsHint: string
  tabExternal: string
  tabExternalHint: string
  tabPayslips: string
  surfaceRun: string
  surfaceHours: string
  surfaceRecords: string
  recordsPayslips: string
  recordsClose: string
  recordsStatutory: string
  payrollHint: string
  loading: string
  retry: string
  emptyExports: string
  emptyExportsHint: string
  emptyQuarantine: string
  emptyQuarantineHint: string
  emptyEvents: string
  emptyEventsHint: string
  readiness: string
  ready: string
  blocked: string
  generateExport: string
  downloadExport: string
  uploadResult: string
  replaceImport: string
  reconcile: string
  rollback: string
  reasonRequired: string
  reasonPlaceholder: string
  period: string
  inputSnapshot: string
  inputSnapshotHint: string
  fingerprintDrift: string
  quarantine: string
  acknowledge: string
  acknowledged: string
  reconciled: string
  differences: string
  matched: string
  unmatched: string
  status: string
  refresh: string
  permissionDenied: string
  disabled: string
  disabledHint: string
  selectFile: string
  uploadBusy: string
  importIdempotent: string
  importOk: string
  importQuarantined: string
  staleFingerprint: string
  managerScoped: string
  auditTimeline: string
  employeeDiffs: string
  runHistory: string
  cancel: string
  confirm: string
  setupTitle: string
  setupMode: string
  setupContracts: string
  setupPeriods: string
  setupPayment: string
  setupOk: string
  setupBlocked: string
  setupModeHint: string
  checklistTitle: string
  checklistSetup: string
  checklistReady: string
  checklistExport: string
  checklistUpload: string
  checklistReconcile: string
  checklistPayslips: string
  checklistClose: string
  packageTitle: string
  packageIncluded: string
  packageExcluded: string
  packageAttendanceNote: string
  csvHelpTitle: string
  csvHelpExport: string
  csvHelpImport: string
  csvHelpBody: string
  pickImportRun: string
  pickExportRun: string
  openQuarantine: string
}

const EN: Copy = {
  title: 'External payroll run',
  subtitle: 'Package people & contracts for your payroll system, upload results, and reconcile — Wathefni does not pay.',
  honesty:
    'Your external payroll system remains money authority. Payment processing is disabled here. Uploaded results are a mirror for review only and never become Wathefni payment authority.',
  moneyAuthority: 'Who pays: external payroll system',
  paymentDisabled: 'Wathefni payments: off',
  vendorUnclaimed: 'File format: standard CSV (no named vendor connector)',
  notAuthoritative: 'Mirror amounts are for review only — not payment authority in Wathefni',
  tabOverview: 'Run checklist',
  tabExports: 'Packages & results',
  tabQuarantine: 'Exceptions',
  tabHistory: 'Audit',
  tabHelp: 'CSV guide',
  tabTimesheets: 'Hours review',
  tabTimesheetsHint: 'Review attendance hours — not the vendor package',
  tabExternal: 'External payroll run',
  tabExternalHint: 'Vendor package, upload, reconcile',
  tabPayslips: 'Payslips',
  surfaceRun: 'Run',
  surfaceHours: 'Hours',
  surfaceRecords: 'Records',
  recordsPayslips: 'Payslips',
  recordsClose: 'Close & export',
  recordsStatutory: 'PIFSS & EOS',
  payrollHint: 'Package for the vendor, review hours, then records — Wathefni does not pay money here.',
  loading: 'Loading external payroll run…',
  retry: 'Retry',
  emptyExports: 'No input packages yet',
  emptyExportsHint: 'When setup is ready, create an input package for the pay period.',
  emptyQuarantine: 'No open exceptions',
  emptyQuarantineHint: 'Rows that do not match people or components appear here.',
  emptyEvents: 'No audit events yet',
  emptyEventsHint: 'Packages, uploads, acknowledgements, and rollbacks are recorded here.',
  readiness: 'Period readiness',
  ready: 'Ready to package',
  blocked: 'Blocked — fix setup first',
  generateExport: 'Create input package',
  downloadExport: 'Download CSV',
  uploadResult: 'Upload vendor result',
  replaceImport: 'Replace previous upload',
  reconcile: 'Reconcile',
  rollback: 'Roll back package',
  reasonRequired: 'Please enter a short reason (required for audit)',
  reasonPlaceholder: 'Why are you doing this? (shown in audit)',
  period: 'Pay period',
  inputSnapshot: 'Input snapshot',
  inputSnapshotHint: 'Changes if people or contracts change after download — re-package before uploading.',
  fingerprintDrift: 'Inputs changed since the last package. Create a new package before uploading, or replace carefully.',
  quarantine: 'Exceptions',
  acknowledge: 'Acknowledge exception',
  acknowledged: 'Acknowledged',
  reconciled: 'Matched — no differences',
  differences: 'Differences found — review below',
  matched: 'Matched',
  unmatched: 'Unmatched',
  status: 'Status',
  refresh: 'Refresh',
  permissionDenied: 'You do not have permission for this payroll action.',
  disabled: 'External payroll run is off for this company',
  disabledHint: 'Ask an admin to enable the external payroll adapter for this workspace.',
  selectFile: 'Choose vendor result CSV',
  uploadBusy: 'Uploading…',
  importIdempotent: 'Same file already uploaded (safe replay).',
  importOk: 'Vendor result saved as a mirror for review.',
  importQuarantined: 'Some rows need review in Exceptions.',
  staleFingerprint: 'Inputs changed after download. Create a new package or replace carefully.',
  managerScoped: 'Manager scope: only your team is included.',
  auditTimeline: 'Audit timeline',
  employeeDiffs: 'People & amount differences',
  runHistory: 'Recent packages',
  cancel: 'Cancel',
  confirm: 'Confirm',
  setupTitle: 'Setup status',
  setupMode: 'Payroll mode',
  setupContracts: 'Approved contracts',
  setupPeriods: 'Pay periods',
  setupPayment: 'Payment processing',
  setupOk: 'OK',
  setupBlocked: 'Needs attention',
  setupModeHint: 'Must be External (or Parallel shadow). Mode is set by an admin — it cannot be flipped here.',
  checklistTitle: 'Guided run',
  checklistSetup: '1. Check setup',
  checklistReady: '2. Confirm period ready',
  checklistExport: '3. Create & download package',
  checklistUpload: '4. Upload vendor result',
  checklistReconcile: '5. Reconcile',
  checklistPayslips: '6. Payslip documents (optional)',
  checklistClose: '7. Close & finance drafts (optional)',
  packageTitle: 'What this package includes',
  packageIncluded: 'Included now',
  packageExcluded: 'Not included yet',
  packageAttendanceNote: 'Attendance, leave, and shifts are not packaged in this wave. Hours review stays on the Hours review tab.',
  csvHelpTitle: 'CSV mapping guide',
  csvHelpExport: 'Input package columns (send to payroll / accountant)',
  csvHelpImport: 'Vendor result columns (upload back here)',
  csvHelpBody:
    'Use the same employee_key and component_code values your payroll system expects. opaque_amount is the vendor’s amount for mirror review only — Wathefni does not pay from it. external_run_id should stay stable for the same vendor run.',
  pickImportRun: 'Choose vendor upload',
  pickExportRun: 'Choose input package',
  openQuarantine: 'Open exceptions',
}

const AR: Copy = {
  title: 'تشغيل الرواتب الخارجية',
  subtitle: 'جهّز الأشخاص والعقود لنظام الرواتب، ارفع النتائج، وطابِق — وظفني لا يدفع.',
  honesty:
    'نظام الرواتب الخارجي يبقى سلطة المال. معالجة الدفع هنا معطّلة. النتائج المرفوعة مرآة للمراجعة فقط ولا تصبح سلطة دفع داخل وظفني.',
  moneyAuthority: 'من يدفع: نظام الرواتب الخارجي',
  paymentDisabled: 'مدفوعات وظفني: متوقفة',
  vendorUnclaimed: 'صيغة الملف: CSV قياسي (بدون موصل مورّد مسمّى)',
  notAuthoritative: 'المبالغ المرآتية للمراجعة فقط — ليست سلطة دفع داخل وظفني',
  tabOverview: 'قائمة التشغيل',
  tabExports: 'الحزم والنتائج',
  tabQuarantine: 'الاستثناءات',
  tabHistory: 'التدقيق',
  tabHelp: 'دليل CSV',
  tabTimesheets: 'مراجعة الساعات',
  tabTimesheetsHint: 'مراجعة ساعات الحضور — ليست حزمة المورّد',
  tabExternal: 'تشغيل الرواتب الخارجية',
  tabExternalHint: 'حزمة المورّد، الرفع، المطابقة',
  tabPayslips: 'قسائم الراتب',
  surfaceRun: 'التشغيل',
  surfaceHours: 'الساعات',
  surfaceRecords: 'السجلات',
  recordsPayslips: 'قسائم الراتب',
  recordsClose: 'الإغلاق والتصدير',
  recordsStatutory: 'التأمينات ونهاية الخدمة',
  payrollHint: 'جهّز حزمة المورّد، راجع الساعات، ثم السجلات — وظفني لا يدفع مالاً هنا.',
  loading: 'جاري تحميل تشغيل الرواتب الخارجية…',
  retry: 'إعادة المحاولة',
  emptyExports: 'لا توجد حزم مدخلات بعد',
  emptyExportsHint: 'عند جاهزية الإعداد، أنشئ حزمة مدخلات لفترة الدفع.',
  emptyQuarantine: 'لا استثناءات مفتوحة',
  emptyQuarantineHint: 'تظهر هنا الصفوف التي لا تطابق أشخاصًا أو مكونات.',
  emptyEvents: 'لا أحداث تدقيق بعد',
  emptyEventsHint: 'تُسجَّل هنا الحزم والرفع والإقرار والتراجع.',
  readiness: 'جاهزية الفترة',
  ready: 'جاهز للتحزيم',
  blocked: 'محظور — أصلِح الإعداد أولًا',
  generateExport: 'إنشاء حزمة المدخلات',
  downloadExport: 'تنزيل CSV',
  uploadResult: 'رفع نتيجة المورّد',
  replaceImport: 'استبدال الرفع السابق',
  reconcile: 'مطابقة',
  rollback: 'التراجع عن الحزمة',
  reasonRequired: 'أدخل سببًا قصيرًا (مطلوب للتدقيق)',
  reasonPlaceholder: 'لماذا تقوم بهذا الإجراء؟ (يظهر في التدقيق)',
  period: 'فترة الدفع',
  inputSnapshot: 'لقطة المدخلات',
  inputSnapshotHint: 'تتغيّر إذا تغيّر الأشخاص أو العقود بعد التنزيل — أعِد التحزيم قبل الرفع.',
  fingerprintDrift: 'تغيّرت المدخلات منذ آخر حزمة. أنشئ حزمة جديدة قبل الرفع، أو استبدل بحذر.',
  quarantine: 'الاستثناءات',
  acknowledge: 'إقرار الاستثناء',
  acknowledged: 'تم الإقرار',
  reconciled: 'متطابق — لا فروقات',
  differences: 'وُجدت فروقات — راجع أدناه',
  matched: 'مطابق',
  unmatched: 'غير مطابق',
  status: 'الحالة',
  refresh: 'تحديث',
  permissionDenied: 'ليس لديك صلاحية لهذا الإجراء.',
  disabled: 'تشغيل الرواتب الخارجية غير مفعّل لهذه الشركة',
  disabledHint: 'اطلب من المسؤول تفعيل محوّل الرواتب الخارجية لهذه المساحة.',
  selectFile: 'اختر ملف نتيجة CSV من المورّد',
  uploadBusy: 'جاري الرفع…',
  importIdempotent: 'نفس الملف مرفوع مسبقًا (إعادة آمنة).',
  importOk: 'حُفظت نتيجة المورّد كمرآة للمراجعة.',
  importQuarantined: 'بعض الصفوف تحتاج مراجعة في الاستثناءات.',
  staleFingerprint: 'تغيّرت المدخلات بعد التنزيل. أنشئ حزمة جديدة أو استبدل بحذر.',
  managerScoped: 'نطاق المدير: يُضمَّن فريقك فقط.',
  auditTimeline: 'الخط الزمني للتدقيق',
  employeeDiffs: 'فروقات الأشخاص والمبالغ',
  runHistory: 'الحزم الأخيرة',
  cancel: 'إلغاء',
  confirm: 'تأكيد',
  setupTitle: 'حالة الإعداد',
  setupMode: 'وضع الرواتب',
  setupContracts: 'العقود المعتمدة',
  setupPeriods: 'فترات الدفع',
  setupPayment: 'معالجة الدفع',
  setupOk: 'جاهز',
  setupBlocked: 'يحتاج انتباهًا',
  setupModeHint: 'يجب أن يكون خارجيًا (أو ظلًا موازيًا). يضبطه المسؤول — لا يمكن تغييره هنا.',
  checklistTitle: 'تشغيل موجّه',
  checklistSetup: '١. تحقق من الإعداد',
  checklistReady: '٢. أكّد جاهزية الفترة',
  checklistExport: '٣. أنشئ الحزمة ونزّلها',
  checklistUpload: '٤. ارفع نتيجة المورّد',
  checklistReconcile: '٥. طابِق',
  checklistPayslips: '٦. مستندات قسائم الراتب (اختياري)',
  checklistClose: '٧. الإغلاق ومسودات المالية (اختياري)',
  packageTitle: 'ماذا تتضمن هذه الحزمة',
  packageIncluded: 'مُضمَّن الآن',
  packageExcluded: 'غير مُضمَّن بعد',
  packageAttendanceNote: 'الحضور والإجازات والمناوبات غير مُضمَّنة في هذه الموجة. مراجعة الساعات تبقى في تبويب مراجعة الساعات.',
  csvHelpTitle: 'دليل أعمدة CSV',
  csvHelpExport: 'أعمدة حزمة المدخلات (تُرسل للرواتب / المحاسب)',
  csvHelpImport: 'أعمدة نتيجة المورّد (تُرفع هنا)',
  csvHelpBody:
    'استخدم نفس employee_key و component_code التي يتوقعها نظام الرواتب. opaque_amount هو مبلغ المورّد للمراجعة فقط — وظفني لا يدفع منه. حافظ على external_run_id ثابتًا لنفس تشغيل المورّد.',
  pickImportRun: 'اختر رفع المورّد',
  pickExportRun: 'اختر حزمة المدخلات',
  openQuarantine: 'فتح الاستثناءات',
}

export function payrollExternalCopy(locale: PayrollExternalLocale): Copy {
  return locale === 'ar' ? AR : EN
}

export function statusTone(status: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  const s = String(status || '').toLowerCase()
  if (['exported', 'imported', 'ok', 'reconciled', 'acknowledged'].some((x) => s.includes(x))) return 'success'
  if (['partial', 'differences', 'superseded'].some((x) => s.includes(x))) return 'warning'
  if (['quarantined', 'rolled_back', 'malformed'].some((x) => s.includes(x))) return 'danger'
  if (['idempotent'].some((x) => s.includes(x))) return 'info'
  return 'neutral'
}

export function importRunLabel(row: Record<string, unknown>, locale: PayrollExternalLocale): string {
  const start = String(row.period_start || row.created_at || '').slice(0, 10)
  const status = String(row.status || '')
  const matched = row.matched_count != null ? String(row.matched_count) : '—'
  if (locale === 'ar') return `${start || 'رفع'} · ${status} · مطابق ${matched}`
  return `${start || 'Upload'} · ${status} · matched ${matched}`
}
