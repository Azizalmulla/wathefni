/** Wave D Phase 4 — product labels for inbound CV hold / admit states (EN/AR). */

import type { RecruitingLocale } from '@/lib/recruitingLifecycle'

export type IntakeHoldState =
  | 'needs_role'
  | 'role_bound'
  | 'identity_review'
  | 'quarantined'
  | 'ready'
  | 'import_review'
  | 'blocked'

export type IntakeStatePresentation = {
  id: IntakeHoldState
  label: string
  hint: string
  recovery: string
  tone: 'muted' | 'warning' | 'danger' | 'success'
}

const EN: Record<IntakeHoldState, Omit<IntakeStatePresentation, 'id'>> = {
  needs_role: {
    label: 'Needs a job',
    hint: 'CV arrived without a job alias. Assign an open job to admit.',
    recovery: 'Pick a job below, then admit the candidate.',
    tone: 'warning',
  },
  role_bound: {
    label: 'Bound to a job',
    hint: 'This intake address routes CVs to a specific open role.',
    recovery: 'Update forwarding if the wrong role is selected.',
    tone: 'success',
  },
  identity_review: {
    label: 'Identity review',
    hint: 'Name or contact details need a quick HR check before admission.',
    recovery: 'Open the profile, confirm identity, then assign a job.',
    tone: 'warning',
  },
  quarantined: {
    label: 'Quarantined',
    hint: 'Attachment was blocked by safety scanning (malware or policy).',
    recovery: 'Ask the candidate to re-send a clean PDF/DOCX, or rotate the intake address if abused.',
    tone: 'danger',
  },
  blocked: {
    label: 'Blocked',
    hint: 'This CV cannot enter the pipeline until the issue is fixed.',
    recovery: 'Read the reason below, then retry with a clean file or different address.',
    tone: 'danger',
  },
  ready: {
    label: 'Ready for review',
    hint: 'Admitted to a job and waiting in the hiring pipeline.',
    recovery: 'Open the candidate profile to continue screening.',
    tone: 'success',
  },
  import_review: {
    label: 'Needs a job',
    hint: 'Held until HR assigns an open job.',
    recovery: 'Assign a job, then admit.',
    tone: 'warning',
  },
}

const AR: Record<IntakeHoldState, Omit<IntakeStatePresentation, 'id'>> = {
  needs_role: {
    label: 'تحتاج وظيفة',
    hint: 'وصلت السيرة دون اسم مستعار لوظيفة. عيّن وظيفة مفتوحة للإضافة.',
    recovery: 'اختر وظيفة أدناه ثم أضف المرشح.',
    tone: 'warning',
  },
  role_bound: {
    label: 'مربوطة بوظيفة',
    hint: 'عنوان الاستقبال يوجّه السير إلى دور مفتوح محدد.',
    recovery: 'حدّث التحويل إذا كانت الوظيفة غير صحيحة.',
    tone: 'success',
  },
  identity_review: {
    label: 'مراجعة الهوية',
    hint: 'الاسم أو بيانات التواصل تحتاج تأكيداً سريعاً قبل الإضافة.',
    recovery: 'افتح الملف الشخصي، أكّد الهوية، ثم عيّن وظيفة.',
    tone: 'warning',
  },
  quarantined: {
    label: 'محجورة',
    hint: 'حُظر المرفق بسبب فحص الأمان (برمجيات خبيثة أو سياسة).',
    recovery: 'اطلب من المرشح إعادة إرسال PDF/DOCX نظيف، أو دوّر العنوان عند الإساءة.',
    tone: 'danger',
  },
  blocked: {
    label: 'موقوفة',
    hint: 'لا يمكن إدخال هذه السيرة إلى المسار حتى يُحلّ السبب.',
    recovery: 'اقرأ السبب أدناه ثم أعد المحاولة بملف نظيف أو عنوان مختلف.',
    tone: 'danger',
  },
  ready: {
    label: 'جاهزة للمراجعة',
    hint: 'أُضيفت إلى وظيفة وتنتظر في مسار التوظيف.',
    recovery: 'افتح ملف المرشح لمتابعة الفرز.',
    tone: 'success',
  },
  import_review: {
    label: 'تحتاج وظيفة',
    hint: 'معلّقة حتى تعيّن الموارد البشرية وظيفة مفتوحة.',
    recovery: 'عيّن وظيفة ثم أضف المرشح.',
    tone: 'warning',
  },
}

export function intakeStatePresentation(state: IntakeHoldState | string | null | undefined, locale: RecruitingLocale): IntakeStatePresentation {
  const key = String(state || 'needs_role').toLowerCase() as IntakeHoldState
  const table = locale === 'ar' ? AR : EN
  const base = table[key] || table.needs_role
  return { id: table[key] ? key : 'needs_role', ...base }
}

export function addressHoldPresentation(roleBound: boolean, locale: RecruitingLocale): IntakeStatePresentation {
  return intakeStatePresentation(roleBound ? 'role_bound' : 'needs_role', locale)
}

export function heldGroupKindLabel(kind: string, locale: RecruitingLocale): string {
  if (locale === 'ar') {
    if (kind === 'explicit_review') return 'دور معلن — أكّد ثم أضف'
    if (kind === 'suggested') return 'اقتراح وظيفة — راجع ثم أضف'
    return 'بدون وظيفة واضحة'
  }
  if (kind === 'explicit_review') return 'Declared role — confirm to admit'
  if (kind === 'suggested') return 'Suggested job — review then admit'
  return 'No clear job yet'
}

/** Bulk admit is only “safe” when the group already has a role code (confirm path). */
export function groupAllowsSafeBulkAdmit(group: { role_code?: string | null; kind?: string }): boolean {
  return Boolean(String(group.role_code || '').trim())
}
