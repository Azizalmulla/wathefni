/** Shifts Wave 3 — EN/AR copy, status maps, honesty messaging. */

export type ShiftsLocale = 'en' | 'ar'

export function shiftsCopy(locale: ShiftsLocale) {
  const isAr = locale === 'ar'
  return {
    title: isAr ? 'الورديات' : 'Shifts',
    subtitle: isAr
      ? 'افهم جدول هذا الأسبوع وما يحتاج قرارك.'
      : 'Understand this week’s schedule and what needs your decision.',
    surfaceSchedule: isAr ? 'الجدول' : 'Schedule',
    surfaceRequests: isAr ? 'الطلبات' : 'Requests',
    surfacePlanning: isAr ? 'التخطيط' : 'Planning',
    board: isAr ? 'الجدول' : 'Schedule',
    day: isAr ? 'يوم' : 'Day',
    week: isAr ? 'أسبوع' : 'Week',
    thisWeek: isAr ? 'هذا الأسبوع' : 'This week',
    schedule: isAr ? 'جدولة وردية' : 'Schedule a shift',
    scheduleHint: isAr
      ? 'عيّن وردية لهذا اليوم أو الأسبوع.'
      : 'Assign a shift for this day or week.',
    emptyBoardTitle: isAr ? 'لا ورديات في هذه الفترة' : 'No shifts in this period',
    emptyBoardHint: isAr
      ? 'ابدأ بجدولة وردية لموظف ضمن نطاقك.'
      : 'Start by scheduling a shift for someone in your scope.',
    attentionWaiting: (n: number) =>
      isAr
        ? `${n} عنصر يحتاج قرارك في الطلبات`
        : `${n} item${n === 1 ? '' : 's'} need your decision in Requests`,
    attentionClear: isAr ? 'لا طلبات مفتوحة' : 'No open requests',
    planningTools: isAr ? 'أدوات التخطيط' : 'Planning tools',
    showOperations: isAr ? 'إظهار العمليات المتقدمة' : 'Show advanced operations',
    hideOperations: isAr ? 'إخفاء العمليات المتقدمة' : 'Hide advanced operations',
    advancedOps: isAr ? 'عمليات متقدمة' : 'Advanced operations',
    advancedOpsHint: isAr
      ? 'أدوات المشرف فقط — التصدير والتشخيص وتذكيرات النظام.'
      : 'Admin tools only — exports, diagnostics, and system reminders.',
    allBranches: isAr ? 'كل الفروع' : 'All branches',
    allSites: isAr ? 'كل المواقع' : 'All sites',
    allTeams: isAr ? 'كل الفرق' : 'All teams',
    allStatuses: isAr ? 'كل الحالات' : 'All statuses',
    noneOrg: isAr ? 'غير محدد' : 'Not set',
    unmappedOrg: isAr ? 'غير مرتبط' : 'Unmapped',
    unmappedOrgHint: isAr
      ? 'قيمة قديمة غير موجودة في الهيكل — محفوظة كما هي.'
      : 'Legacy value not in Organization — preserved as stored.',
    location: isAr ? 'الموقع التفصيلي' : 'Location',
    allLocations: isAr ? 'كل المواقع التفصيلية' : 'All locations',
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
    reason: isAr ? 'سبب التغيير' : 'Reason for change',
    reasonRequired: isAr ? 'أدخل سبباً قصيراً (٣ أحرف على الأقل) قبل التأكيد' : 'Enter a short reason (at least 3 characters) before confirming',
    reasonPlaceholder: isAr ? 'مثال: تعديل بعد طلب المدير' : 'Example: adjusted after manager request',
    cancelImpact: isAr
      ? 'ستُلغى هذه الوردية من الجدول. يبقى السجل للتدقيق، ولا يُحذف التاريخ.'
      : 'This shift will be removed from the live schedule. History stays for audit — nothing is hard-deleted.',
    reconCancelImpact: isAr
      ? 'سيُغلق عنصر المصالحة كإلغاء مع تسجيل السبب.'
      : 'This reconciliation item will close as an audited cancel.',
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
    reminders: isAr ? 'تذكيرات النظام' : 'System reminders',
    approve: isAr ? 'اعتماد' : 'Approve',
    decline: isAr ? 'رفض' : 'Decline',
    acknowledge: isAr ? 'إقرار' : 'Acknowledge',
    resolveCancel: isAr ? 'إلغاء مع سبب' : 'Cancel with reason',
    loading: isAr ? 'جاري التحميل…' : 'Loading…',
    updating: isAr ? 'جارٍ التحديث…' : 'Updating…',
    cancelled: isAr ? 'تم الإلغاء' : 'Cancelled',
    continueLabel: isAr ? 'متابعة' : 'Continue',
    confirmRequired: isAr ? 'يلزم التأكيد للمتابعة' : 'Confirmation required to continue',
    retry: isAr ? 'إعادة المحاولة' : 'Retry',
    emptyBoard: isAr ? 'لا ورديات في هذه الفترة' : 'No shifts in this period',
    emptySwaps: isAr ? 'لا طلبات تبديل' : 'No swap requests',
    emptyAvailability: isAr ? 'لا طلبات توفر معلّقة' : 'No pending availability',
    emptyRecon: isAr ? 'لا عناصر مصالحة مفتوحة' : 'No open reconciliation items',
    emptyReminders: isAr ? 'لا تذكيرات نظام معلّقة' : 'No system reminder issues',
    emptyRequestsHint: isAr ? 'عندما يصل طلب، يظهر هنا لاتخاذ القرار.' : 'When a request arrives, it will appear here for a decision.',
    permissionDenied: isAr ? 'ليس لديك صلاحية لهذا الإجراء' : 'You do not have permission for this action',
    outOfScope: isAr ? 'خارج نطاق إدارتك' : 'Outside your managed scope',
    staleConflict: isAr
      ? 'تغيّر الجدول منذ آخر تحديث — حدّث الصفحة وحاول مجدداً'
      : 'The schedule changed since you loaded it — refresh and try again',
    selfDecisionDenied: isAr ? 'لا يمكن اتخاذ قرار ذاتي' : 'Self-decision is not allowed',
    allowlistDenied: isAr
      ? 'ليس لديك صلاحية لتغيير الجدول الآن. اطلب من مسؤول الموارد البشرية.'
      : 'You do not have permission to change the schedule right now. Ask an HR admin.',
    honesty: isAr
      ? 'الورديات للجدول المخطط فقط. الحضور للوقت الفعلي. الإجازة لقرارات الغياب. الرواتب للحساب المالي.'
      : 'Shifts owns the planned schedule. Attendance owns worked time. Leave owns absence decisions. Payroll owns money.',
    honestyNoTemplates: isAr
      ? 'الورديات للجدول المخطط فقط. القوالب والجداول المتكررة غير مفعّلة لهذه الشركة.'
      : 'Shifts owns the planned schedule. Templates and recurring schedules are not enabled for this company.',
    honestyPublish: isAr
      ? 'مسودة الجدول → مراجعة → اعتماد → نشر. التراجع ينشئ نسخة جديدة مسجّلة. الورديات المفتوحة وقواعد التغطية اختيارية.'
      : 'Draft schedule → review → approve → publish. Rollback creates a new recorded version. Open shifts and coverage rules are optional.',
    honestyEnterprise: isAr
      ? 'الدورات تساعد على بناء جداول متكررة للفرق. المسودات لا تغيّر الجدول المنشور حتى النشر.'
      : 'Rotations help build repeating team schedules. Drafts do not change the live schedule until you publish.',
    templates: isAr ? 'القوالب' : 'Templates',
    recurring: isAr ? 'الجداول المتكررة' : 'Recurring schedules',
    publish: isAr ? 'النشر' : 'Publishing',
    enterprise: isAr ? 'الدورات' : 'Rotations',
    rotations: isAr ? 'الدورات' : 'Rotations',
    draft: isAr ? 'مسودة' : 'Draft',
    inReview: isAr ? 'قيد المراجعة' : 'In review',
    approved: isAr ? 'معتمد' : 'Approved',
    published: isAr ? 'منشور' : 'Published',
    openShifts: isAr ? 'ورديات مفتوحة' : 'Open shifts',
    coverage: isAr ? 'التغطية' : 'Coverage',
    reviewChanges: isAr ? 'مراجعة التغييرات' : 'Review changes',
    returnToDraft: isAr ? 'إعادة للمسودة' : 'Return to draft',
    submitReview: isAr ? 'إرسال للمراجعة' : 'Submit for review',
    publishAction: isAr ? 'نشر' : 'Publish',
    rollbackDraft: isAr ? 'مسودة تراجع' : 'Rollback draft',
    createPeriod: isAr ? 'إنشاء فترة' : 'Create period',
    createOpenShift: isAr ? 'وردية مفتوحة' : 'Create open shift',
    createCoverage: isAr ? 'قاعدة تغطية' : 'Coverage rule',
    rotationPreview: isAr ? 'معاينة الدورة' : 'Preview rotation',
    generateFromRotation: isAr ? 'مسودة من الدورة' : 'Draft from rotation',
    pamExport: isAr ? 'تصدير الامتثال' : 'Compliance export',
    pamExportHint: isAr
      ? 'ملف للقراءة فقط للمراجعة. لا يُرسل تلقائياً لأي جهة حكومية.'
      : 'Read-only file for review. Nothing is sent automatically to any authority.',
    preview: isAr ? 'معاينة' : 'Preview',
    materialize: isAr ? 'توليد' : 'Generate',
    previewHint: isAr
      ? 'المعاينة تعرض ما سيُجدول. التوليد يضيف الورديات إلى الجدول.'
      : 'Preview shows what would be scheduled. Generate adds those shifts to the schedule.',
    generateDraft: isAr ? 'توليد مسودة' : 'Generate draft',
    generateDraftHint: isAr
      ? 'المسودة لا تغيّر الجدول المنشور. النشر فقط يجعلها حيّة.'
      : 'A draft does not change the live schedule. Only publish makes it live.',
    previewSummary: (counts: {
      newly_generated?: number
      updated_future?: number
      conflict?: number
      unchanged?: number
      cancelled_held?: number
    }) =>
      isAr
        ? `معاينة: جديد ${counts.newly_generated || 0} · محدّث ${counts.updated_future || 0} · تعارض ${counts.conflict || 0} · دون تغيير ${counts.unchanged || 0}`
        : `Preview: ${counts.newly_generated || 0} new · ${counts.updated_future || 0} updated · ${counts.conflict || 0} conflicts · ${counts.unchanged || 0} unchanged`,
    generateSummary: (res: { newly_generated?: number; updated_future?: number; conflict?: number }) =>
      isAr
        ? `تم التوليد: أُنشئ ${res.newly_generated || 0} · حُدّث ${res.updated_future || 0} · تعارض ${res.conflict || 0}`
        : `Generated: ${res.newly_generated || 0} created · ${res.updated_future || 0} updated · ${res.conflict || 0} conflicts`,
    rotationCounts: (work: number, rest: number, travel: number) =>
      isAr ? `عمل ${work} · راحة ${rest} · تنقّل ${travel}` : `${work} work · ${rest} rest · ${travel} travel`,
    realGateOn: isAr
      ? 'تغييرات الجدول تتطلب سبباً وتحديثاً لأحدث نسخة.'
      : 'Schedule changes require a reason and the latest schedule version.',
    timersDisabled: isAr ? 'مؤقتات المشغّل غير مستخدمة' : 'Operator timers are not in use',
    remindersSynthetic: isAr
      ? 'تذكيرات الموظفين الحقيقيين متوقفة ما لم تُعتمد'
      : 'Live employee reminders stay off until explicitly approved',
    talalReadOnly: isAr ? 'تطبيق الموظف للقراءة فقط' : 'Employee app remains read-only',
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
    alreadyPublished: isAr ? 'منشور مسبقاً' : 'Already published',
    coverageMin: (n: string | number) => (isAr ? `الحد الأدنى ${n}` : `Minimum ${n}`),
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
