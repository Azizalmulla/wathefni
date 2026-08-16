/**
 * Payroll Wave 5 — EN/AR copy for PIFSS + EOS review worksheets.
 * Non-authoritative review only. No remittance, filing, or automatic compliance claim.
 */

export type PayrollStatutoryLocale = 'en' | 'ar'

type Copy = {
  title: string
  subtitle: string
  honesty: string
  paymentDisabled: string
  noRemittance: string
  noAutoPayable: string
  counselHint: string
  tabPifss: string
  tabEos: string
  tabRules: string
  loading: string
  retry: string
  empty: string
  emptyHint: string
  generatePifss: string
  generateEos: string
  submitReview: string
  approve: string
  override: string
  confirmOverride: string
  recalculate: string
  reasonRequired: string
  reasonPlaceholder: string
  refresh: string
  status: string
  category: string
  immutable: string
  permissionDenied: string
  disabled: string
  disabledHint: string
  mobileHint: string
  reviewOnly: string
}

const EN: Copy = {
  title: 'PIFSS & EOS review worksheets',
  subtitle: 'Counsel-gated statutory review artefacts — not remittance or payable instructions.',
  honesty:
    'Worksheets are non-authoritative review documents only. No automatic legal-compliance claim. No remittance, statutory filing, bank/WPS/AS’HAL, or automatic EOS payable. Missing or unapproved rule tables fail closed. External payroll remains money authority; native results remain non-authoritative. Payment processing is disabled.',
  paymentDisabled: 'Payment processing: disabled',
  noRemittance: 'No remittance / statutory filing',
  noAutoPayable: 'EOS: review worksheet only — never automatic payable',
  counselHint: 'Unsupported and counsel_required states are explicit. Manual override needs dual approval.',
  tabPifss: 'PIFSS',
  tabEos: 'EOS',
  tabRules: 'Rule tables',
  loading: 'Loading statutory worksheets…',
  retry: 'Retry',
  empty: 'No worksheets yet',
  emptyHint: 'Generate a PIFSS or EOS review worksheet after counsel-approved rules are in place.',
  generatePifss: 'Generate PIFSS worksheet',
  generateEos: 'Generate EOS worksheet',
  submitReview: 'Submit for review',
  approve: 'Approve worksheet',
  override: 'Initiate override',
  confirmOverride: 'Confirm override',
  recalculate: 'Recalculate',
  reasonRequired: 'Audit reason required',
  reasonPlaceholder: 'Why are you generating or changing this worksheet?',
  refresh: 'Refresh',
  status: 'Status',
  category: 'Category',
  immutable: 'Approved history is immutable',
  permissionDenied: 'You do not have permission for this action.',
  disabled: 'Statutory worksheets are not enabled',
  disabledHint: 'Wave 5 is gated per company and synthetic-only on staging.',
  mobileHint: 'Scroll horizontally on small screens to review category and counsel status.',
  reviewOnly: 'Review only — not payment authority',
}

const AR: Copy = {
  title: 'أوراق مراجعة التأمينات ومكافأة نهاية الخدمة',
  subtitle: 'وثائق مراجعة قانونية مقيّدة بالمستشار — ليست تحويلات أو تعليمات دفع.',
  honesty:
    'الأوراق وثائق مراجعة غير ملزمة فقط. بلا ادعاء امتثال قانوني تلقائي. بلا تحويل أو تقديم نظامي أو بنك/WPS/أسهل أو دفع تلقائي لنهاية الخدمة. جداول القواعد الناقصة أو غير المعتمدة تُرفض. الرواتب الخارجية تبقى سلطة المال؛ النتائج المحلية غير ملزمة. معالجة الدفع معطّلة.',
  paymentDisabled: 'معالجة الدفع: معطّلة',
  noRemittance: 'بلا تحويل / تقديم نظامي',
  noAutoPayable: 'نهاية الخدمة: ورقة مراجعة فقط — بلا دفع تلقائي',
  counselHint: 'حالات غير المدعوم ويتطلب مستشار صريحة. التجاوز اليدوي يحتاج موافقة مزدوجة.',
  tabPifss: 'التأمينات',
  tabEos: 'نهاية الخدمة',
  tabRules: 'جداول القواعد',
  loading: 'جاري تحميل أوراق المراجعة…',
  retry: 'إعادة المحاولة',
  empty: 'لا توجد أوراق بعد',
  emptyHint: 'أنشئ ورقة مراجعة بعد اعتماد جداول القواعد من المستشار.',
  generatePifss: 'إنشاء ورقة التأمينات',
  generateEos: 'إنشاء ورقة نهاية الخدمة',
  submitReview: 'إرسال للمراجعة',
  approve: 'اعتماد الورقة',
  override: 'بدء التجاوز',
  confirmOverride: 'تأكيد التجاوز',
  recalculate: 'إعادة الاحتساب',
  reasonRequired: 'سبب التدقيق مطلوب',
  reasonPlaceholder: 'لماذا تنشئ أو تغيّر هذه الورقة؟',
  refresh: 'تحديث',
  status: 'الحالة',
  category: 'الفئة',
  immutable: 'سجل المعتمد غير قابل للتعديل',
  permissionDenied: 'ليس لديك صلاحية لهذا الإجراء.',
  disabled: 'أوراق المراجعة النظامية غير مفعّلة',
  disabledHint: 'الموجة 5 مقيّدة حسب الشركة وللبيانات الاصطناعية فقط في التجهيز.',
  mobileHint: 'مرّر أفقياً على الشاشات الصغيرة لمراجعة الفئة وحالة المستشار.',
  reviewOnly: 'مراجعة فقط — ليست سلطة دفع',
}

export function payrollStatutoryCopy(locale: PayrollStatutoryLocale): Copy {
  return locale === 'ar' ? AR : EN
}

export function statutoryStatusTone(status: string): string {
  switch (status) {
    case 'approved':
      return 'text-emerald-800'
    case 'counsel_required':
    case 'unsupported':
      return 'text-amber-800'
    case 'exception':
      return 'text-orange-800'
    case 'in_review':
      return 'text-sky-800'
    case 'superseded':
      return 'text-subtle'
    default:
      return 'text-subtle'
  }
}
