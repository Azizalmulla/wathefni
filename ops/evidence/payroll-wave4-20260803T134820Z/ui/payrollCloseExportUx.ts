/**
 * Payroll Wave 4 — EN/AR copy for close + finance export workspace.
 * Journal drafts + bank-export contract validation only.
 * Payment processing remains disabled. No real bank/WPS/PIFSS/EOS/AI.
 */

export type PayrollCloseExportLocale = 'en' | 'ar'

type Copy = {
  title: string
  subtitle: string
  honesty: string
  paymentDisabled: string
  nativeNonAuth: string
  externalAuthority: string
  tabClose: string
  tabMappings: string
  tabExports: string
  loading: string
  retry: string
  empty: string
  emptyHint: string
  createFromPreview: string
  createFromImport: string
  submitReview: string
  approve: string
  close: string
  reopen: string
  confirmReopen: string
  generateJournal: string
  generateBankContract: string
  recordExport: string
  reasonRequired: string
  reasonPlaceholder: string
  refresh: string
  status: string
  period: string
  totals: string
  immutable: string
  balanced: string
  validationOnly: string
  permissionDenied: string
  disabled: string
  disabledHint: string
  cancel: string
  confirm: string
  mobileHint: string
  sodHint: string
}

const EN: Copy = {
  title: 'Close & finance export',
  subtitle: 'Review, approve, and close payroll runs — journal drafts and bank-export contracts only.',
  honesty:
    'Native results remain non-authoritative previews. External payroll remains money authority. Journal drafts do not post to ERP. Bank-export contracts are validation only — no real bank format, connection, WPS/AS’HAL, payments, PIFSS, EOS, or AI.',
  paymentDisabled: 'Payment processing: disabled',
  nativeNonAuth: 'Native: preview / non-authoritative',
  externalAuthority: 'External: money authority retained',
  tabClose: 'Close runs',
  tabMappings: 'Account mappings',
  tabExports: 'Export history',
  loading: 'Loading close & export…',
  retry: 'Retry',
  empty: 'No close runs yet',
  emptyHint: 'Create a close run from a native preview or external import.',
  createFromPreview: 'From preview',
  createFromImport: 'From import',
  submitReview: 'Submit for review',
  approve: 'Approve',
  close: 'Close run',
  reopen: 'Initiate reopen',
  confirmReopen: 'Confirm reopen',
  generateJournal: 'Generate journal draft',
  generateBankContract: 'Validate bank-export contract',
  recordExport: 'Record export',
  reasonRequired: 'Audit reason required',
  reasonPlaceholder: 'Why are you changing this close or export?',
  refresh: 'Refresh',
  status: 'Status',
  period: 'Period',
  totals: 'Totals',
  immutable: 'Closed snapshots are immutable',
  balanced: 'Journal must balance',
  validationOnly: 'Bank export: validation only',
  permissionDenied: 'You do not have permission for this action.',
  disabled: 'Close & finance export is not enabled',
  disabledHint: 'Wave 4 is gated per company and synthetic-only on staging.',
  cancel: 'Cancel',
  confirm: 'Confirm',
  mobileHint: 'Scroll horizontally on small screens to review totals and export status.',
  sodHint: 'SOD: approve/close and export must be separate actors and permissions.',
}

const AR: Copy = {
  title: 'الإغلاق وتصدير المالية',
  subtitle: 'مراجعة واعتماد وإغلاق تشغيلات الرواتب — مسودات قيود وعقود تصدير بنكي للتحقق فقط.',
  honesty:
    'النتائج المحلية تبقى معاينات غير ملزمة. الرواتب الخارجية تبقى سلطة المال. مسودات القيود لا تُرحَّل إلى نظام المحاسبة. عقود التصدير البنكي للتحقق فقط — بلا صيغة بنك حقيقية أو اتصال أو WPS/أسهل أو مدفوعات أو تأمينات أو مكافأة نهاية خدمة أو ذكاء اصطناعي.',
  paymentDisabled: 'معالجة الدفع: معطّلة',
  nativeNonAuth: 'محلي: معاينة / غير ملزم',
  externalAuthority: 'خارجي: سلطة المال محفوظة',
  tabClose: 'تشغيلات الإغلاق',
  tabMappings: 'ربط الحسابات',
  tabExports: 'سجل التصدير',
  loading: 'جاري تحميل الإغلاق والتصدير…',
  retry: 'إعادة المحاولة',
  empty: 'لا توجد تشغيلات إغلاق بعد',
  emptyHint: 'أنشئ تشغيل إغلاق من معاينة محلية أو استيراد خارجي.',
  createFromPreview: 'من معاينة',
  createFromImport: 'من استيراد',
  submitReview: 'إرسال للمراجعة',
  approve: 'اعتماد',
  close: 'إغلاق التشغيل',
  reopen: 'بدء إعادة الفتح',
  confirmReopen: 'تأكيد إعادة الفتح',
  generateJournal: 'إنشاء مسودة قيد',
  generateBankContract: 'التحقق من عقد التصدير البنكي',
  recordExport: 'تسجيل التصدير',
  reasonRequired: 'سبب التدقيق مطلوب',
  reasonPlaceholder: 'لماذا تغيّر هذا الإغلاق أو التصدير؟',
  refresh: 'تحديث',
  status: 'الحالة',
  period: 'الفترة',
  totals: 'الإجماليات',
  immutable: 'لقطات الإغلاق غير قابلة للتعديل',
  balanced: 'يجب أن يتوازن القيد',
  validationOnly: 'التصدير البنكي: تحقق فقط',
  permissionDenied: 'ليس لديك صلاحية لهذا الإجراء.',
  disabled: 'الإغلاق وتصدير المالية غير مفعّل',
  disabledHint: 'الموجة 4 مقيّدة حسب الشركة وللبيانات الاصطناعية فقط في التجهيز.',
  cancel: 'إلغاء',
  confirm: 'تأكيد',
  mobileHint: 'مرّر أفقياً على الشاشات الصغيرة لمراجعة الإجماليات وحالة التصدير.',
  sodHint: 'فصل الصلاحيات: الاعتماد/الإغلاق والتصدير لممثلين وصلاحيات منفصلة.',
}

export function payrollCloseExportCopy(locale: PayrollCloseExportLocale): Copy {
  return locale === 'ar' ? AR : EN
}

export function closeRunStatusTone(status: string): string {
  switch (status) {
    case 'closed':
      return 'text-emerald-800'
    case 'approved':
      return 'text-sky-800'
    case 'in_review':
      return 'text-amber-800'
    case 'reopened':
      return 'text-orange-800'
    default:
      return 'text-subtle'
  }
}
