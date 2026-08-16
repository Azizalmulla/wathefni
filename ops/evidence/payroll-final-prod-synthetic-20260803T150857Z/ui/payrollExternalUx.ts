/**
 * Payroll Wave 2A-C — EN/AR copy for external payroll operations workspace.
 * Money authority remains external; payment_processing stays disabled.
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
  tabTimesheets: string
  tabExternal: string
  tabPayslips: string
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
  fingerprint: string
  fingerprintDrift: string
  quarantine: string
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
}

const EN: Copy = {
  title: 'External payroll',
  subtitle: 'Export inputs, upload vendor results, reconcile — Wathefni does not pay.',
  honesty:
    'External system is money authority. Payment processing is disabled. Imports are mirror-only and never become Wathefni payment authority.',
  moneyAuthority: 'Money authority: external',
  paymentDisabled: 'Payment processing: disabled',
  vendorUnclaimed: 'Vendor: unclaimed (synthetic CSV)',
  notAuthoritative: 'Imported amounts are not authoritative in Wathefni',
  tabOverview: 'Overview',
  tabExports: 'Exports',
  tabQuarantine: 'Quarantine',
  tabHistory: 'Audit',
  tabTimesheets: 'Timesheets',
  tabExternal: 'External run',
  tabPayslips: 'Payslips',
  loading: 'Loading external payroll…',
  retry: 'Retry',
  emptyExports: 'No external exports yet',
  emptyExportsHint: 'Generate an input export when the period is ready.',
  emptyQuarantine: 'Quarantine is clear',
  emptyQuarantineHint: 'Malformed or unmatched rows will appear here.',
  emptyEvents: 'No audit events yet',
  emptyEventsHint: 'Exports, imports, and rollbacks are recorded here.',
  readiness: 'Period readiness',
  ready: 'Ready to export',
  blocked: 'Blocked',
  generateExport: 'Generate input export',
  downloadExport: 'Download CSV',
  uploadResult: 'Upload result',
  replaceImport: 'Replace import',
  reconcile: 'Reconcile',
  rollback: 'Roll back export',
  reasonRequired: 'Audit reason required',
  reasonPlaceholder: 'Why are you doing this?',
  period: 'Pay period',
  fingerprint: 'Input fingerprint',
  fingerprintDrift: 'Fingerprint drift — re-export before importing, or confirm replace.',
  quarantine: 'Quarantine',
  reconciled: 'Reconciled',
  differences: 'Differences',
  matched: 'Matched',
  unmatched: 'Unmatched',
  status: 'Status',
  refresh: 'Refresh',
  permissionDenied: 'You do not have permission for this payroll action.',
  disabled: 'External payroll workflow is off',
  disabledHint: 'Enable Wave 2A for this company to use the external adapter workspace.',
  selectFile: 'Choose result CSV',
  uploadBusy: 'Uploading…',
  importIdempotent: 'Duplicate upload replayed (idempotent).',
  importOk: 'Result imported (mirror only).',
  importQuarantined: 'Import quarantined — review unmatched or malformed rows.',
  staleFingerprint: 'Stale fingerprint — export inputs changed. Re-export or replace carefully.',
  managerScoped: 'Manager scope active — only in-scope employees are included.',
  auditTimeline: 'Audit timeline',
  employeeDiffs: 'Employee-level differences',
  runHistory: 'External run history',
  cancel: 'Cancel',
  confirm: 'Confirm',
}

const AR: Copy = {
  title: 'الرواتب الخارجية',
  subtitle: 'تصدير المدخلات، رفع نتائج المورّد، والمطابقة — وظفني لا يدفع.',
  honesty:
    'النظام الخارجي هو سلطة المال. معالجة الدفع معطّلة. الاستيراد للمرآة فقط ولا يصبح سلطة دفع داخل وظفني.',
  moneyAuthority: 'سلطة المال: خارجي',
  paymentDisabled: 'معالجة الدفع: معطّلة',
  vendorUnclaimed: 'المورّد: غير مُعلَن (CSV تجريبي)',
  notAuthoritative: 'المبالغ المستوردة ليست مرجعًا داخل وظفني',
  tabOverview: 'نظرة عامة',
  tabExports: 'التصديرات',
  tabQuarantine: 'الحجر',
  tabHistory: 'التدقيق',
  tabTimesheets: 'الجداول الزمنية',
  tabExternal: 'تشغيل خارجي',
  tabPayslips: 'قسائم الراتب',
  loading: 'جاري تحميل الرواتب الخارجية…',
  retry: 'إعادة المحاولة',
  emptyExports: 'لا توجد تصديرات خارجية بعد',
  emptyExportsHint: 'أنشئ تصدير مدخلات عندما تكون الفترة جاهزة.',
  emptyQuarantine: 'قائمة الحجر فارغة',
  emptyQuarantineHint: 'ستظهر هنا الصفوف غير المطابقة أو التالفة.',
  emptyEvents: 'لا أحداث تدقيق بعد',
  emptyEventsHint: 'تُسجَّل هنا التصديرات والاستيرادات والتراجع.',
  readiness: 'جاهزية الفترة',
  ready: 'جاهز للتصدير',
  blocked: 'محظور',
  generateExport: 'إنشاء تصدير المدخلات',
  downloadExport: 'تنزيل CSV',
  uploadResult: 'رفع النتيجة',
  replaceImport: 'استبدال الاستيراد',
  reconcile: 'مطابقة',
  rollback: 'التراجع عن التصدير',
  reasonRequired: 'سبب التدقيق مطلوب',
  reasonPlaceholder: 'لماذا تقوم بهذا الإجراء؟',
  period: 'فترة الدفع',
  fingerprint: 'بصمة المدخلات',
  fingerprintDrift: 'انحراف البصمة — أعد التصدير قبل الاستيراد أو أكّد الاستبدال.',
  quarantine: 'الحجر',
  reconciled: 'تمت المطابقة',
  differences: 'الفروقات',
  matched: 'مطابق',
  unmatched: 'غير مطابق',
  status: 'الحالة',
  refresh: 'تحديث',
  permissionDenied: 'ليس لديك صلاحية لهذا الإجراء.',
  disabled: 'سير عمل الرواتب الخارجية غير مفعّل',
  disabledHint: 'فعّل الموجة 2A لهذه الشركة لاستخدام مساحة المحوّل الخارجي.',
  selectFile: 'اختر ملف نتيجة CSV',
  uploadBusy: 'جاري الرفع…',
  importIdempotent: 'أُعيد تشغيل رفع مكرر (متماثل).',
  importOk: 'تم استيراد النتيجة (مرآة فقط).',
  importQuarantined: 'الاستيراد في الحجر — راجع الصفوف غير المطابقة أو التالفة.',
  staleFingerprint: 'بصمة قديمة — تغيّرت المدخلات. أعد التصدير أو استبدل بحذر.',
  managerScoped: 'نطاق المدير مفعّل — يُضمَّن الموظفون ضمن النطاق فقط.',
  auditTimeline: 'الخط الزمني للتدقيق',
  employeeDiffs: 'فروقات على مستوى الموظف',
  runHistory: 'سجل التشغيل الخارجي',
  cancel: 'إلغاء',
  confirm: 'تأكيد',
}

export function payrollExternalCopy(locale: PayrollExternalLocale): Copy {
  return locale === 'ar' ? AR : EN
}

export function statusTone(status: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  const s = String(status || '').toLowerCase()
  if (['exported', 'imported', 'ok', 'reconciled'].some((x) => s.includes(x))) return 'success'
  if (['partial', 'differences', 'superseded'].some((x) => s.includes(x))) return 'warning'
  if (['quarantined', 'rolled_back', 'malformed'].some((x) => s.includes(x))) return 'danger'
  if (['idempotent'].some((x) => s.includes(x))) return 'info'
  return 'neutral'
}
