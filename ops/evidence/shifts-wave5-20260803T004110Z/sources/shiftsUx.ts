/** Shifts Wave 3 — EN/AR copy, status maps, honesty messaging. */

export type ShiftsLocale = 'en' | 'ar'

export function shiftsCopy(locale: ShiftsLocale) {
  const isAr = locale === 'ar'
  return {
    title: isAr ? 'الورديات' : 'Shifts',
    subtitle: isAr
      ? 'جدولة مباشرة للموارد البشرية والمدراء ضمن النطاق — مع قوالب وجداول متكررة اختيارية عند التفعيل.'
      : 'Direct scheduling for HR and scoped managers — optional templates and recurring schedules when enabled.',
    board: isAr ? 'لوحة الجدول' : 'Schedule board',
    day: isAr ? 'يوم' : 'Day',
    week: isAr ? 'أسبوع' : 'Week',
    thisWeek: isAr ? 'هذا الأسبوع' : 'This week',
    schedule: isAr ? 'جدولة وردية' : 'Schedule a shift',
    scheduleHint: isAr
      ? 'عيّن وردية مباشرة — لا يلزم إعداد مؤسسي.'
      : 'Assign a shift directly — no enterprise setup required.',
    employee: isAr ? 'الموظف' : 'Employee',
    date: isAr ? 'التاريخ' : 'Date',
    start: isAr ? 'البداية' : 'Start',
    end: isAr ? 'النهاية' : 'End',
    site: isAr ? 'الموقع' : 'Site',
    branch: isAr ? 'الفرع' : 'Branch',
    team: isAr ? 'الفريق' : 'Team',
    role: isAr ? 'الدور' : 'Role',
    filters: isAr ? 'تصفية' : 'Filters',
    clearFilters: isAr ? 'مسح التصفية' : 'Clear filters',
    overnight: isAr ? 'ليلية (تعبر منتصف الليل)' : 'Overnight (crosses midnight)',
    overnightHint: isAr
      ? 'تظهر عبر اليومين دون تكرار السلطة.'
      : 'Shown across both dates without duplicating authority.',
    splitHint: isAr ? 'نوافذ منفصلة لنفس اليوم' : 'Separate windows on the same day',
    reason: isAr ? 'سبب التدقيق' : 'Audit reason',
    reasonRequired: isAr ? 'سبب التدقيق مطلوب للتغييرات الحقيقية' : 'Audit reason required for real mutations',
    ackAvailability: isAr ? 'أقرّ بتعارض التوفر' : 'Acknowledge availability conflict',
    ackLeave: isAr ? 'أقرّ بتعارض الإجازة' : 'Acknowledge leave conflict',
    create: isAr ? 'جدولة' : 'Schedule',
    reschedule: isAr ? 'إعادة جدولة' : 'Reschedule',
    softCancel: isAr ? 'إلغاء ناعم' : 'Soft-cancel',
    edit: isAr ? 'تعديل' : 'Edit',
    history: isAr ? 'السجل' : 'History',
    lineage: isAr ? 'النسب / الإصدارات' : 'Lineage / versions',
    swaps: isAr ? 'طلبات التبديل' : 'Swap requests',
    availability: isAr ? 'التوفر' : 'Availability',
    reconciliation: isAr ? 'المصالحة' : 'Reconciliation',
    reminders: isAr ? 'فشل التذكير النهائي' : 'Terminal reminder failures',
    approve: isAr ? 'اعتماد' : 'Approve',
    decline: isAr ? 'رفض' : 'Decline',
    acknowledge: isAr ? 'إقرار' : 'Acknowledge',
    resolveCancel: isAr ? 'إلغاء مع تدقيق' : 'Audited cancel',
    loading: isAr ? 'جاري التحميل…' : 'Loading…',
    retry: isAr ? 'إعادة المحاولة' : 'Retry',
    emptyBoard: isAr ? 'لا ورديات في هذه الفترة' : 'No shifts in this period',
    emptySwaps: isAr ? 'لا طلبات تبديل' : 'No swap requests',
    emptyAvailability: isAr ? 'لا طلبات توفر معلّقة' : 'No pending availability',
    emptyRecon: isAr ? 'لا عناصر مصالحة مفتوحة' : 'No open reconciliation items',
    emptyReminders: isAr ? 'لا فشل تذكير نهائي' : 'No terminal reminder failures',
    permissionDenied: isAr ? 'ليس لديك صلاحية لهذا الإجراء' : 'You do not have permission for this action',
    outOfScope: isAr ? 'خارج نطاق إدارتك' : 'Outside your managed scope',
    staleConflict: isAr ? 'تعارض التزامن — حدّث وحاول مجدداً' : 'Stale concurrency — refresh and try again',
    selfDecisionDenied: isAr ? 'لا يمكن اتخاذ قرار ذاتي' : 'Self-decision is not allowed',
    allowlistDenied: isAr
      ? 'التعديلات الحقيقية مقيدة بقائمة السماح'
      : 'Real mutations are limited to the named allowlist',
    honesty: isAr
      ? 'الورديات تملك الفترات المخططة فقط. الحضور يملك الوقت الفعلي. الإجازات تملك القرارات. الرواتب تملك الحساب المالي. المسودات والمعاينات لا تؤثر على التشغيل حتى النشر. سلطة التشغيل تبقى في التعيينات L0 المنشورة.'
      : 'Shifts owns planned intervals only. Attendance owns worked time. Leave owns leave decisions. Payroll owns money. Drafts and previews never affect operations until publish. Published L0 assignments remain operational authority.',
    honestyNoTemplates: isAr
      ? 'الورديات تملك الفترات المخططة فقط. الحضور يملك الوقت الفعلي. الإجازات تملك القرارات. الرواتب تملك الحساب المالي. القوالب والجداول المتكررة غير مفعّلة.'
      : 'Shifts owns planned intervals only. Attendance owns worked time. Leave owns leave decisions. Payroll owns money. Templates and recurring schedules are not enabled.',
    honestyPublish: isAr
      ? 'طبقة النشر: المسودة → المراجعة → الاعتماد → النشر. التراجع عبر إصدار مدقّق جديد. الورديات المفتوحة وقواعد التغطية اختيارية للشركات المتوسطة.'
      : 'Publish layer: draft → review → approve → publish. Rollback via a new audited version. Open shifts and coverage are optional for medium/enterprise companies.',
    templates: isAr ? 'القوالب والتكرار' : 'Templates & recurrence',
    publish: isAr ? 'النشر والتغطية' : 'Publish & coverage',
    draft: isAr ? 'مسودة' : 'Draft',
    inReview: isAr ? 'قيد المراجعة' : 'In review',
    approved: isAr ? 'معتمد' : 'Approved',
    published: isAr ? 'منشور' : 'Published',
    openShifts: isAr ? 'ورديات مفتوحة' : 'Open shifts',
    coverage: isAr ? 'التغطية' : 'Coverage',
    reviewChanges: isAr ? 'مراجعة التغييرات' : 'Review changes',
    publishAction: isAr ? 'نشر' : 'Publish',
    preview: isAr ? 'معاينة' : 'Preview',
    materialize: isAr ? 'توليد' : 'Generate',
    previewHint: isAr
      ? 'المعاينة تصنّف التعيينات قبل الكتابة. التوليد يكتب تعيينات L0 مجدولة.'
      : 'Preview classifies occurrences before write. Generate writes scheduled L0 assignments.',
    generateDraft: isAr ? 'توليد مسودة' : 'Generate draft',
    generateDraftHint: isAr
      ? 'المسودة لا تكتب سلطة تشغيل. النشر فقط يرقّي إلى L0.'
      : 'Draft does not write operational authority. Only publish promotes to L0.',
    realGateOn: isAr
      ? 'بوابة التعديل الحقيقي مفعّلة — يلزم السماح بالاسم وسبب التدقيق ورمز التزامن.'
      : 'Real mutation gate is on — named allowlist, audit reason, and concurrency token required.',
    timersDisabled: isAr ? 'مؤقتات المشغّل متوقفة افتراضياً' : 'Operator timers remain disabled by default',
    remindersSynthetic: isAr
      ? 'تذكيرات الموظفين الحقيقيين متوقفة ما لم تُعتمد صراحة'
      : 'Real-employee reminders stay off unless explicitly approved',
    talalReadOnly: isAr ? 'تطبيق طلال للقراءة فقط' : 'Talal employee-app remains read-only',
    statusScheduled: isAr ? 'مجدول' : 'Scheduled',
    statusCancelled: isAr ? 'ملغى' : 'Cancelled',
    statusConflicted: isAr ? 'تعارض' : 'Conflicted',
    statusRecon: isAr ? 'يتطلب مصالحة' : 'Reconciliation required',
    partialData: isAr ? 'بيانات جزئية — حدّث لاحقاً' : 'Partial data — refresh later',
    denied: isAr ? 'مرفوض' : 'Denied',
    seasonalWarn: isAr ? 'تحذير موسمي' : 'Seasonal warning',
    refresh: isAr ? 'تحديث' : 'Refresh',
    close: isAr ? 'إغلاق' : 'Close',
    save: isAr ? 'حفظ' : 'Save',
    noActions: isAr ? 'لا إجراءات متاحة' : 'No actions available',
    viewHistory: isAr ? 'عرض السجل' : 'View history',
    currentVersion: isAr ? 'الإصدار الحالي' : 'Current version',
    priorVersion: isAr ? 'إصدار سابق' : 'Prior version',
  }
}

export function shiftStatusLabel(uiState: string | null | undefined, locale: ShiftsLocale): string {
  const c = shiftsCopy(locale)
  const s = String(uiState || 'scheduled').toLowerCase()
  if (s === 'cancelled') return c.statusCancelled
  if (s === 'conflicted') return c.statusConflicted
  if (s === 'reconciliation_required') return c.statusRecon
  if (s === 'scheduled') return c.statusScheduled
  return s || c.statusScheduled
}

export function shiftStatusTone(uiState: string | null | undefined): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  const s = String(uiState || 'scheduled').toLowerCase()
  if (s === 'cancelled') return 'danger'
  if (s === 'conflicted') return 'warning'
  if (s === 'reconciliation_required') return 'review'
  if (s === 'scheduled') return 'success'
  return 'info'
}

export function formatShiftWindow(
  date?: string | null,
  start?: string | null,
  end?: string | null,
  endsNext?: boolean,
  locale: ShiftsLocale = 'en',
): string {
  const d = (date || '').slice(0, 10) || '—'
  const s = (start || '').toString().slice(0, 5) || '—'
  const e = (end || '').toString().slice(0, 5) || '—'
  if (endsNext) {
    return locale === 'ar' ? `${d} ${s}→+1 ${e}` : `${d} ${s}→+1 ${e}`
  }
  return `${d} ${s}–${e}`
}
