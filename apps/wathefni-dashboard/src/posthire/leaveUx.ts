/** Leave Wave 4 — EN/AR copy, status maps, honesty messaging (customer-facing). */

export type LeaveLocale = 'en' | 'ar'

export type LeaveDurationUnit = 'full_day' | 'half_day' | 'hourly'

export function leaveCopy(locale: LeaveLocale) {
  const isAr = locale === 'ar'
  return {
    title: isAr ? 'الإجازات' : 'Leave',
    active: isAr ? 'النشطة' : 'Active',
    history: isAr ? 'السجل' : 'History',
    fileLeave: isAr ? 'تقديم إجازة' : 'File leave',
    pendingTitle: isAr ? 'طلبات بانتظار القرار' : 'Pending requests',
    pendingHint: isAr ? 'راجع التفاصيل ثم اعتمد أو ارفض أو اطلب معلومات.' : 'Review details, then approve, decline, or request information.',
    upcomingTitle: isAr ? 'إجازات قادمة' : 'Upcoming leave',
    upcomingHint: isAr ? 'إجازات معتمدة يمكن إلغاؤها قبل البدء.' : 'Approved leave that can be cancelled before it starts.',
    historyTitle: isAr ? 'سجل الإجازات' : 'Leave history',
    historyHint: isAr ? 'المعتمد والمرفوض والملغى والمنسحب.' : 'Approved, declined, cancelled, and withdrawn.',
    emptyPending: isAr ? 'لا طلبات بانتظار القرار' : 'Nothing to approve',
    emptyUpcoming: isAr ? 'لا إجازات قادمة' : 'No upcoming leave',
    emptyHistory: isAr ? 'لا سجل بعد' : 'No leave history yet',
    balancesBanner: isAr
      ? 'أرصدة الإجازات غير ملزمة حالياً (enforced=false) — لا تمنع الاعتماد. الأثر المالي للإجازة بدون راتب يحسبه الرواتب فقط.'
      : 'Leave balances are non-binding while enforced=false — they never block approval. Unpaid monetary impact is calculated by Payroll only.',
    holidayPending: isAr
      ? 'سنة العطل قيد المراجعة — بوابة الأيام المفروضة تُغلق. وضع المراقبة يستخدم العطل المعتمدة فقط.'
      : 'Holiday year is pending review — enforced chargeable-day gates fail closed. Observe mode uses approved/seeded holidays only.',
    approve: isAr ? 'اعتماد' : 'Approve',
    decline: isAr ? 'رفض' : 'Decline',
    needsInfo: isAr ? 'طلب معلومات' : 'Request info',
    cancel: isAr ? 'إلغاء' : 'Cancel',
    withdraw: isAr ? 'سحب' : 'Withdraw',
    resubmit: isAr ? 'إعادة تقديم' : 'Resubmit',
    dualInitiate: isAr ? 'بدء اعتماد مزدوج (متأخر)' : 'Start dual-control (stale)',
    dualConfirm: isAr ? 'تأكيد الاعتماد المزدوج' : 'Confirm dual-control',
    dualConfirmBody: isAr
      ? 'اعتماد منفصل عن بدء الطلب — يؤكد ممثلاً ثانياً ثم يطبّق الإجراء المتأخر.'
      : 'Separate from starting dual-control — a second allowlisted actor confirms, then the stale action applies.',
    more: isAr ? 'المزيد' : 'More',
    viewDetails: isAr ? 'عرض التفاصيل' : 'View details',
    attentionEmpty: isAr ? 'لا طلبات إجازة بانتظار القرار' : 'No leave requests waiting',
    attentionWaiting: (n: number) =>
      isAr
        ? `${n} طلب إجازة بانتظار قرارك`
        : `${n} leave request${n === 1 ? '' : 's'} awaiting your decision`,
    nextDecide: isAr ? 'بانتظار قرار الموارد البشرية' : 'Awaiting HR decision',
    nextResubmit: isAr ? 'بانتظار إعادة التقديم' : 'Awaiting resubmission',
    nextCancel: isAr ? 'يمكن الإلغاء قبل البدء' : 'May cancel before start',
    balanceImpact: isAr ? 'أثر الرصيد (غير ملزم)' : 'Balance impact (non-binding)',
    unpaidNote: isAr
      ? 'إجازة بدون راتب: Leave يرسل التصنيف والمدة فقط — الرواتب تحسب الخصم.'
      : 'Unpaid leave: Leave sends classification and duration only — Payroll calculates any deduction.',
    approveSeparate: isAr
      ? 'الاعتماد قرار منفصل عن تطبيق الرصيد. الرصيد غير ملزم حتى يتم تفعيل التنفيذ.'
      : 'Approval is a separate authority step from balance application. Balances stay non-binding until enforcement is authorized.',
    shiftConflicts: isAr ? 'تعارض مع ورديات مجدولة' : 'Conflicts with scheduled shifts',
    overlapBlocked: isAr ? 'يوجد تداخل مع طلب آخر' : 'Overlaps another leave request',
    permissionDenied: isAr ? 'ليس لديك صلاحية لهذا الإجراء' : 'You do not have permission for this action',
    staleConflict: isAr ? 'تعارض إصدار — حدّث الصفحة وحاول مجدداً' : 'Stale version — refresh and try again',
    sensitiveMasked: isAr ? 'مرفق حسّاس — محجوب' : 'Sensitive attachment — masked',
    durationFull: isAr ? 'يوم كامل' : 'Full day',
    durationHalf: isAr ? 'نصف يوم' : 'Half day',
    durationHourly: isAr ? 'ساعي' : 'Hourly',
    typeAnnual: isAr ? 'سنوية' : 'Annual',
    typeSick: isAr ? 'مرضية' : 'Sick',
    typeUnpaid: isAr ? 'بدون راتب' : 'Unpaid',
    typeOther: isAr ? 'أخرى' : 'Other',
    loading: isAr ? 'جاري التحميل…' : 'Loading…',
    retry: isAr ? 'إعادة المحاولة' : 'Retry',
    ownerHr: isAr ? 'الموارد البشرية / المدير' : 'HR / manager',
    requester: isAr ? 'مقدم الطلب' : 'Requester',
    dates: isAr ? 'التواريخ' : 'Dates',
    duration: isAr ? 'المدة' : 'Duration',
    type: isAr ? 'النوع' : 'Type',
    status: isAr ? 'الحالة' : 'Status',
    nextAction: isAr ? 'الإجراء التالي' : 'Next action',
    allStatuses: isAr ? 'كل الحالات' : 'All statuses',
  }
}

export function statusLabel(status: string | null | undefined, locale: LeaveLocale): string {
  const s = String(status || '').toLowerCase()
  const map: Record<string, { en: string; ar: string }> = {
    requested: { en: 'Requested', ar: 'مطلوب' },
    needs_review: { en: 'Needs review', ar: 'يحتاج مراجعة' },
    needs_info: { en: 'Needs information', ar: 'يحتاج معلومات' },
    approved: { en: 'Approved', ar: 'معتمد' },
    rejected: { en: 'Declined', ar: 'مرفوض' },
    cancelled: { en: 'Cancelled', ar: 'ملغى' },
    withdrawn: { en: 'Withdrawn', ar: 'منسحب' },
    expired_stale: { en: 'Expired (stale)', ar: 'منتهٍ (متأخر)' },
    declined_lifecycle: { en: 'Declined (lifecycle)', ar: 'مرفوض (دورة حياة)' },
  }
  return (map[s] || { en: s || '—', ar: s || '—' })[locale]
}

export function durationLabel(unit: string | null | undefined, locale: LeaveLocale, portion?: string | null): string {
  const c = leaveCopy(locale)
  const u = String(unit || 'full_day')
  if (u === 'half_day') {
    const p = String(portion || 'am').toLowerCase()
    const half = p === 'pm' || p === 'second_half' ? (locale === 'ar' ? 'مساءً' : 'PM') : locale === 'ar' ? 'صباحاً' : 'AM'
    return `${c.durationHalf} · ${half}`
  }
  if (u === 'hourly') return c.durationHourly
  return c.durationFull
}

export function typeLabel(leaveType: string | null | undefined, locale: LeaveLocale): string {
  const c = leaveCopy(locale)
  const t = String(leaveType || '').toLowerCase()
  if (t === 'annual' || t === 'vacation' || t === 'time_off') return c.typeAnnual
  if (t === 'sick' || t === 'medical') return c.typeSick
  if (t === 'unpaid') return c.typeUnpaid
  return c.typeOther
}

export function statusTone(status: string | null | undefined): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  const s = String(status || '').toLowerCase()
  if (s === 'approved') return 'success'
  if (s === 'rejected' || s === 'cancelled' || s === 'expired_stale') return 'danger'
  if (s === 'needs_info' || s === 'needs_review') return 'review'
  if (s === 'withdrawn') return 'paused'
  if (s === 'requested') return 'warning'
  return 'info'
}

export function formatLeaveDates(start?: string | null, end?: string | null, locale: LeaveLocale = 'en'): string {
  const fmt = (v?: string | null) => {
    if (!v) return '—'
    try {
      return new Date(`${String(v).slice(0, 10)}T12:00:00`).toLocaleDateString(locale === 'ar' ? 'ar-KW' : 'en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    } catch {
      return String(v).slice(0, 10)
    }
  }
  const a = fmt(start)
  const b = fmt(end)
  return a === b ? a : `${a} → ${b}`
}
