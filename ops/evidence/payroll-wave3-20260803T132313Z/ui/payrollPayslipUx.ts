/**
 * Payroll Wave 3 — EN/AR copy for payslip workspace.
 * Native = preview non-authoritative; external = external money authority.
 * Payment processing remains disabled. No bank/WPS/payments.
 */

export type PayrollPayslipLocale = 'en' | 'ar'

type Copy = {
  title: string
  subtitle: string
  honesty: string
  nativeLabel: string
  externalLabel: string
  paymentDisabled: string
  notMoney: string
  tabList: string
  tabHistory: string
  tabPayslips: string
  loading: string
  retry: string
  empty: string
  emptyHint: string
  generateNative: string
  generateExternal: string
  download: string
  replace: string
  revoke: string
  reasonRequired: string
  reasonPlaceholder: string
  refresh: string
  status: string
  version: string
  earnings: string
  deductions: string
  net: string
  period: string
  employee: string
  audit: string
  historyRetained: string
  managerScoped: string
  permissionDenied: string
  disabled: string
  disabledHint: string
  cancel: string
  confirm: string
  mobileHint: string
}

const EN: Copy = {
  title: 'Payslips',
  subtitle: 'Preview and external payslip documents — Wathefni does not pay.',
  honesty:
    'Native payslips are non-authoritative previews. External payslips mirror imported results; the external system remains money authority. Payment processing is disabled.',
  nativeLabel: 'Native preview (not payment authority)',
  externalLabel: 'External mirror (external is money authority)',
  paymentDisabled: 'Payment processing: disabled',
  notMoney: 'Payslips are documents only — not payment authority',
  tabList: 'Active',
  tabHistory: 'History',
  tabPayslips: 'Payslips',
  loading: 'Loading payslips…',
  retry: 'Retry',
  empty: 'No payslips yet',
  emptyHint: 'Generate from a native preview run or an external import.',
  generateNative: 'Generate from preview',
  generateExternal: 'Generate from import',
  download: 'Download',
  replace: 'Replace',
  revoke: 'Revoke',
  reasonRequired: 'Audit reason required',
  reasonPlaceholder: 'Why are you generating or changing this payslip?',
  refresh: 'Refresh',
  status: 'Status',
  version: 'Version',
  earnings: 'Earnings',
  deductions: 'Deductions',
  net: 'Net',
  period: 'Period',
  employee: 'Employee',
  audit: 'Audit',
  historyRetained: 'History is retained — replace/revoke never deletes',
  managerScoped: 'Showing employees in your scope only',
  permissionDenied: 'You do not have permission for this payslip action.',
  disabled: 'Payslips are not enabled',
  disabledHint: 'Wave 3 payslips are disabled for this company.',
  cancel: 'Cancel',
  confirm: 'Confirm',
  mobileHint: 'Scroll sideways on small screens to review lines and history.',
}

const AR: Copy = {
  title: 'قسائم الراتب',
  subtitle: 'وثائق معاينة وخارجية — وظّفني لا يدفع.',
  honesty:
    'قسائم المعاينة المحلية غير ملزمة. القسائم الخارجية مرآة للنتائج المستوردة؛ النظام الخارجي يبقى سلطة المال. معالجة الدفع معطّلة.',
  nativeLabel: 'معاينة محلية (ليست سلطة دفع)',
  externalLabel: 'مرآة خارجية (الخارجي هو سلطة المال)',
  paymentDisabled: 'معالجة الدفع: معطّلة',
  notMoney: 'القسائم وثائق فقط — ليست سلطة دفع',
  tabList: 'النشطة',
  tabHistory: 'السجل',
  tabPayslips: 'القسائم',
  loading: 'جارٍ تحميل القسائم…',
  retry: 'إعادة المحاولة',
  empty: 'لا قسائم بعد',
  emptyHint: 'أنشئ من تشغيل معاينة محلي أو استيراد خارجي.',
  generateNative: 'إنشاء من المعاينة',
  generateExternal: 'إنشاء من الاستيراد',
  download: 'تنزيل',
  replace: 'استبدال',
  revoke: 'إلغاء',
  reasonRequired: 'سبب التدقيق مطلوب',
  reasonPlaceholder: 'لماذا تنشئ أو تغيّر هذه القسيمة؟',
  refresh: 'تحديث',
  status: 'الحالة',
  version: 'الإصدار',
  earnings: 'المستحقات',
  deductions: 'الخصومات',
  net: 'الصافي',
  period: 'الفترة',
  employee: 'الموظف',
  audit: 'التدقيق',
  historyRetained: 'يُحتفظ بالسجل — الاستبدال/الإلغاء لا يحذف',
  managerScoped: 'تُعرض فقط الموظفون ضمن نطاقك',
  permissionDenied: 'ليست لديك صلاحية لهذا الإجراء.',
  disabled: 'القسائم غير مفعّلة',
  disabledHint: 'قسائم الموجة 3 غير مفعّلة لهذه الشركة.',
  cancel: 'إلغاء',
  confirm: 'تأكيد',
  mobileHint: 'مرّر أفقياً على الشاشات الصغيرة لمراجعة البنود والسجل.',
}

export function payrollPayslipCopy(locale: PayrollPayslipLocale): Copy {
  return locale === 'ar' ? AR : EN
}

export function payslipStatusTone(status: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  const s = String(status || '').toLowerCase()
  if (s === 'active') return 'success'
  if (s === 'replaced') return 'warning'
  if (s === 'revoked') return 'danger'
  return 'neutral'
}
