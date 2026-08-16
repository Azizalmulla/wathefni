import type { ApplicationSummary } from '@/types'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import {
  CANDIDATE_STAGE_FILTER_STATUSES,
  STAGE_BUCKET_ARCHIVED,
  STAGE_BUCKET_HIRED,
  STAGE_BUCKET_NONE,
  STAGE_BUCKET_READY,
  STAGE_BUCKET_REJECTED,
  STAGE_BUCKET_UNKNOWN,
  STAGE_BUCKET_WITHDRAWN,
  expandStageFilterStatuses,
  isTalentPoolStageExempt,
  lifecycleBucketForStatus,
} from '@/lib/candidatesStageContract'

export function isHeldCandidate(application: ApplicationSummary) {
  return Boolean(
    application.is_held
      || application.record_state === 'talent_pool'
      || application.status === 'needs_role'
      || application.status === 'import_review'
      || application.status === 'import_archived',
  )
}

/** HR-facing stage labels for the Candidates list only. Profile keeps fuller lifecycle copy. */
const LIST_STAGE_LABELS: Record<RecruitingLocale, Record<string, string>> = {
  en: {
    new: 'New',
    ready_for_review: 'Ready for review',
    shortlisted: 'Shortlisted',
    interview: 'Interview',
    hired: 'Hired',
    rejected: 'Rejected',
    withdrawn: 'Withdrawn',
    reviewed: 'Reviewed',
    archived: 'Archived',
    none: '—',
    unknown: 'Unknown',
  },
  ar: {
    new: 'جديد',
    ready_for_review: 'جاهز للمراجعة',
    shortlisted: 'القائمة المختصرة',
    interview: 'المقابلة',
    hired: 'تم التعيين',
    rejected: 'مرفوض',
    withdrawn: 'منسحب',
    reviewed: 'تمت المراجعة',
    archived: 'مؤرشف',
    none: '—',
    unknown: 'غير معروف',
  },
}

const LIST_SOURCE_LABELS: Record<RecruitingLocale, Record<string, string>> = {
  en: {
    email: 'Email',
    whatsapp: 'WhatsApp',
    manual: 'Manual upload',
    job_application: 'Job application',
    unknown: 'Unknown source',
  },
  ar: {
    email: 'البريد الإلكتروني',
    whatsapp: 'واتساب',
    manual: 'رفع يدوي',
    job_application: 'تقديم على وظيفة',
    unknown: 'مصدر غير معروف',
  },
}

const NOT_IDENTIFIED: Record<RecruitingLocale, string> = {
  en: 'Not identified',
  ar: 'غير محدد',
}

const NO_JOB: Record<RecruitingLocale, string> = {
  en: 'No job assigned',
  ar: 'غير مرتبط بوظيفة',
}

const IDENTITY_REVIEW: Record<RecruitingLocale, string> = {
  en: 'Review identity',
  ar: 'مراجعة الهوية',
}

export type CandidateListPerson = {
  /** Stable client key for the person group on this page. */
  listKey: string
  primary: ApplicationSummary
  applications: ApplicationSummary[]
  additionalActiveJobs: number
  identityReviewWarning: boolean
}

export function isGeneralCandidate(application: ApplicationSummary) {
  return isHeldCandidate(application) && (
    application.record_state === 'talent_pool'
    || application.status === 'needs_role'
    || application.status === 'import_review'
  )
}

export function candidateInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0] || ''}${parts[parts.length - 1][0] || ''}`.toUpperCase()
}

const ARABIC_SCRIPT = /[\u0600-\u06FF]/
const LATIN_LETTER = /[A-Za-z]/

/**
 * Display-only name formatter. Never mutates stored/canonical names.
 * Preserves Arabic and already-mixed Latin casing; title-cases only all-lower / all-upper Latin.
 */
export function formatCandidateDisplayName(raw: string | null | undefined, locale: RecruitingLocale = 'en') {
  const name = String(raw || '').trim().replace(/\s+/g, ' ')
  if (!name) return locale === 'ar' ? 'مرشح بدون اسم' : 'Unnamed candidate'
  if (ARABIC_SCRIPT.test(name)) return name

  const letters = name.replace(/[^A-Za-z]/g, '')
  if (!letters) return name
  const allLower = letters === letters.toLowerCase()
  const allUpper = letters === letters.toUpperCase()
  if (!allLower && !allUpper) return name

  return name.split(' ').map((part) => {
    if (!LATIN_LETTER.test(part)) return part
    if (part.includes('-')) {
      return part.split('-').map((segment) => titleCaseLatinToken(segment)).join('-')
    }
    return titleCaseLatinToken(part)
  }).join(' ')
}

function titleCaseLatinToken(token: string) {
  if (!token) return token
  // Keep short all-caps abbreviations when the whole name was uppercased (IT, HR, QA).
  if (/^[A-Z]{2,4}$/.test(token) && token === token.toUpperCase() && token.length <= 3) {
    // Still normalize typical name tokens; abbreviations of length 2–3 stay upper only if not a name particle.
    if (!/^(AL|EL|BIN|IBN)$/i.test(token)) return token.toUpperCase()
  }
  const lower = token.toLowerCase()
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}

export const CANDIDATE_LIST_PERSON_PAGE_SIZE = 25

export function candidateListFooterLabel(
  personTotal: number,
  pageOffset: number,
  pageSize: number,
  locale: RecruitingLocale,
) {
  if (!personTotal) return locale === 'ar' ? 'لا مرشحين للعرض' : 'No candidates to show'
  const from = pageOffset + 1
  const to = Math.min(pageOffset + pageSize, personTotal)
  if (locale === 'ar') {
    if (personTotal === 1) return 'مرشح واحد'
    return `عرض ${from}–${to} من ${personTotal} مرشحاً`
  }
  if (personTotal === 1) return '1 candidate'
  return `Showing ${from}–${to} of ${personTotal} candidates`
}

export type CandidateListJobPresentation = {
  /** Single visible Job-column value (title, no-job label, or application-count label). */
  title: string
  activeApplications: number
}

/** Arabic application-count label with simple dual/plural forms. */
export function candidateListApplicationCountLabel(count: number, locale: RecruitingLocale) {
  if (locale === 'ar') {
    if (count === 1) return 'طلب واحد'
    if (count === 2) return 'طلبان'
    if (count >= 3 && count <= 10) return `${count} طلبات`
    return `${count} طلباً`
  }
  if (count === 1) return '1 application'
  return `${count} applications`
}

/**
 * Job column for list scanning:
 * - no active job → No job assigned
 * - one active application → exact Job title
 * - multiple active applications → total count only (e.g. "2 applications")
 */
export function candidateListJobPresentation(
  application: ApplicationSummary,
  locale: RecruitingLocale,
  additionalActiveJobs = 0,
): CandidateListJobPresentation {
  if (isGeneralCandidate(application)) {
    return { title: NO_JOB[locale], activeApplications: 0 }
  }
  const title = application.position?.title
    || (application.job_display && application.job_display !== 'Not linked' ? application.job_display : '')
    || application.position?.code
    || '—'
  const extraJobs = Math.max(0, additionalActiveJobs)
  const activeApplications = title === '—' ? 0 : 1 + extraJobs
  if (activeApplications <= 0) {
    return { title: NO_JOB[locale], activeApplications: 0 }
  }
  if (activeApplications === 1) {
    return { title, activeApplications: 1 }
  }
  return {
    title: candidateListApplicationCountLabel(activeApplications, locale),
    activeApplications,
  }
}

/** Strip advisory / compound chip wording to one clean professional field. */
export function candidateExpertiseLabel(application: ApplicationSummary, locale: RecruitingLocale = 'en') {
  const raw = String(application.classification_chip || '').trim()
  if (!raw) return NOT_IDENTIFIED[locale]

  let cleaned = raw
    .replace(/^(Confirmed|Advisory|AI suggested|AI|HR confirmed)\s*:\s*/i, '')
    .replace(/^(Confirmed|Advisory|AI suggested)\s+/i, '')
    .trim()

  // Prefer the most specific segment after separators like "Technology · Software Engineering"
  if (cleaned.includes('·')) {
    const parts = cleaned.split('·').map((part) => part.trim()).filter(Boolean)
    cleaned = parts[parts.length - 1] || cleaned
  } else if (cleaned.includes(' - ')) {
    const parts = cleaned.split(' - ').map((part) => part.trim()).filter(Boolean)
    cleaned = parts[parts.length - 1] || cleaned
  }

  cleaned = cleaned
    .replace(/\b(career area|likely role|authority|taxonomy)\b/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim()

  if (!cleaned || /^(unknown|unclassified|n\/a|none)$/i.test(cleaned)) {
    return NOT_IDENTIFIED[locale]
  }
  return cleaned
}

function normalizeContact(value: string | null | undefined) {
  return String(value || '').trim().toLowerCase()
}

function confirmedIdentityKey(application: ApplicationSummary): string | null {
  const email = normalizeContact(application.grounded_contacts?.email || application.candidate?.email)
  if (email && !/^imp-/i.test(email) && email.includes('@')) return `email:${email}`

  const phone = normalizeContact(application.grounded_contacts?.phone || application.phone)
  if (phone && !/^imp-/i.test(phone) && phone.replace(/\D/g, '').length >= 8) {
    return `phone:${phone.replace(/\D/g, '')}`
  }
  return null
}

function applicationPriority(application: ApplicationSummary) {
  if (isGeneralCandidate(application)) return 0
  const stage = String(application.canonical_stage || application.status || '').toLowerCase()
  const rank: Record<string, number> = {
    hired: 90,
    offer_sent: 80,
    offered: 80,
    interview: 70,
    scheduled: 70,
    shortlisted: 60,
    ready_for_review: 50,
    screening_complete: 50,
    review_pending: 50,
    cv_processing: 30,
    awaiting_cv: 20,
    rejected: 10,
    withdrawn: 5,
  }
  return 100 + (rank[stage] || 0)
}

function isActiveJobApplication(application: ApplicationSummary) {
  if (isGeneralCandidate(application)) return false
  const stage = String(application.canonical_stage || application.status || '').toLowerCase()
  if (['rejected', 'withdrawn', 'hired', 'import_archived'].includes(stage)) return false
  if (application.record_state === 'archived' || application.record_state === 'restricted') return false
  return Boolean(application.position?.title || application.position?.code || application.job_display)
}

export function candidateListJobLabel(application: ApplicationSummary, locale: RecruitingLocale, additionalActiveJobs = 0) {
  return candidateListJobPresentation(application, locale, additionalActiveJobs).title
}

/** Raw DB / legacy statuses included when the toolbar Stage filter is applied. */
export const CANDIDATE_LIST_STAGE_FILTER_STATUSES = CANDIDATE_STAGE_FILTER_STATUSES

/** Expand a Stage toolbar value (or raw alias) to every matching application.status. */
export function candidateListStageFilterStatuses(filterValue: string): string[] {
  return expandStageFilterStatuses(filterValue)
}

/**
 * Display bucket used by the Stage column.
 * Must match filter membership for lifecycle rows (shared candidates stage contract).
 * Talent Pool / no-job held rows use quiet `none` (—), never New.
 */
export function candidateListStageBucket(application: ApplicationSummary): string {
  if (application.record_state === 'archived' || application.status === 'import_archived') {
    return STAGE_BUCKET_ARCHIVED
  }
  if (isTalentPoolStageExempt(application) || isGeneralCandidate(application)) {
    if (application.record_state === 'archived') return STAGE_BUCKET_ARCHIVED
    return STAGE_BUCKET_NONE
  }

  const status = String(application.status || '').toLowerCase()
  const canonical = String(application.canonical_stage || '').toLowerCase()
  const bucket = lifecycleBucketForStatus(status) || lifecycleBucketForStatus(canonical)
  if (bucket) return bucket
  return STAGE_BUCKET_UNKNOWN
}

function listStageKey(application: ApplicationSummary): string {
  return candidateListStageBucket(application)
}

export function candidateListStageLabel(application: ApplicationSummary, locale: RecruitingLocale) {
  const key = listStageKey(application)
  return LIST_STAGE_LABELS[locale][key] || LIST_STAGE_LABELS[locale].unknown || LIST_STAGE_LABELS.en.unknown
}

export function candidateListStageTone(
  application: ApplicationSummary,
): 'default' | 'success' | 'warning' | 'danger' | 'muted' | 'priority' | 'review' | 'follow' | 'assess' {
  const key = listStageKey(application)
  if (key === STAGE_BUCKET_HIRED) return 'priority'
  if (key === STAGE_BUCKET_REJECTED || key === STAGE_BUCKET_WITHDRAWN) return 'danger'
  if (key === STAGE_BUCKET_READY) return 'review'
  // Quiet list: most stages stay muted; color only for attention outcomes.
  return 'muted'
}

export function normalizeListSourceKey(application: ApplicationSummary): keyof (typeof LIST_SOURCE_LABELS)['en'] {
  const raw = String(application.intake_source || application.data_source || '').toLowerCase().trim()
  if (!raw || raw === 'unknown' || raw === 'source_not_recorded') return 'unknown'
  if (['email', 'recruiting_email', 'inbound_email', 'gmail', 'postmark'].includes(raw)) return 'email'
  if (['whatsapp', 'wa', 'octopus_whatsapp'].includes(raw)) return 'whatsapp'
  if (['manual', 'dashboard', 'bulk', 'bulk_import', 'import', 'upload', 'manual_upload'].includes(raw)) return 'manual'
  if (['job', 'job_application', 'apply', 'application', 'qr', 'public_apply'].includes(raw)) return 'job_application'
  // Live applications with no channel often arrived through a job apply path.
  if (!isGeneralCandidate(application) && application.position?.code) return 'job_application'
  return 'unknown'
}

export function formatReceivedRelative(value: string | null | undefined, locale: RecruitingLocale, now = new Date()) {
  if (!value) return locale === 'ar' ? 'تاريخ غير معروف' : 'Unknown date'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const today = startOfDay(now)
  const target = startOfDay(date)
  const diffDays = Math.round((today.getTime() - target.getTime()) / 86_400_000)

  if (diffDays === 0) return locale === 'ar' ? 'اليوم' : 'Today'
  if (diffDays === 1) return locale === 'ar' ? 'أمس' : 'Yesterday'
  if (diffDays > 1 && diffDays < 7) {
    return locale === 'ar' ? `منذ ${diffDays} أيام` : `${diffDays} days ago`
  }
  return date.toLocaleDateString(locale === 'ar' ? 'ar-KW' : 'en-GB', { day: 'numeric', month: 'short' })
}

export function candidateListReceivedLabel(application: ApplicationSummary, locale: RecruitingLocale, now = new Date()) {
  const source = LIST_SOURCE_LABELS[locale][normalizeListSourceKey(application)]
  const when = formatReceivedRelative(application.ingested_at || application.updated_at, locale, now)
  return `${source} · ${when}`
}

export function identityReviewWarningLabel(locale: RecruitingLocale) {
  return IDENTITY_REVIEW[locale]
}

/** Default Stage filter values shown in the simplified Candidates toolbar. */
export const CANDIDATE_LIST_STAGE_FILTERS: Array<{ value: string; en: string; ar: string }> = [
  { value: '', en: 'All stages', ar: 'كل المراحل' },
  { value: 'awaiting_cv', en: 'New', ar: 'جديد' },
  { value: 'ready_for_review', en: 'Ready for review', ar: 'جاهز للمراجعة' },
  { value: 'shortlisted', en: 'Shortlisted', ar: 'القائمة المختصرة' },
  { value: 'interview', en: 'Interview', ar: 'المقابلة' },
  { value: 'hired', en: 'Hired', ar: 'تم التعيين' },
  { value: 'rejected', en: 'Rejected', ar: 'مرفوض' },
  { value: 'withdrawn', en: 'Withdrawn', ar: 'منسحب' },
]

/**
 * Person-first aggregation for the loaded Candidates page.
 * Confirmed identity only: grounded email or non-surrogate phone.
 * Name-only similarity never merges silently.
 */
export function aggregateCandidatesForList(applications: ApplicationSummary[]): CandidateListPerson[] {
  const groups = new Map<string, ApplicationSummary[]>()
  const order: string[] = []

  for (const application of applications) {
    const confirmed = confirmedIdentityKey(application)
    const key = confirmed || `singleton:${application.app_key}`
    if (!groups.has(key)) {
      groups.set(key, [])
      order.push(key)
    }
    groups.get(key)!.push(application)
  }

  const nameBuckets = new Map<string, string[]>()
  for (const key of order) {
    const apps = groups.get(key) || []
    const name = String(apps[0]?.candidate?.name || '').trim().toLowerCase()
    if (!name || key.startsWith('email:') || key.startsWith('phone:')) continue
    const bucket = nameBuckets.get(name) || []
    bucket.push(key)
    nameBuckets.set(name, bucket)
  }
  const warnKeys = new Set<string>()
  for (const keys of nameBuckets.values()) {
    if (keys.length > 1) keys.forEach((key) => warnKeys.add(key))
  }

  return order.map((listKey) => {
    const apps = [...(groups.get(listKey) || [])].sort((a, b) => applicationPriority(b) - applicationPriority(a))
    const primary = apps[0]
    const activeJobs = apps.filter(isActiveJobApplication)
    const uniqueJobCodes = new Set(
      activeJobs
        .map((app) => app.position?.code || app.position?.title || app.job_display || '')
        .filter(Boolean),
    )
    const additionalActiveJobs = Math.max(0, uniqueJobCodes.size - (isGeneralCandidate(primary) ? 0 : 1))
    return {
      listKey,
      primary,
      applications: apps,
      additionalActiveJobs,
      identityReviewWarning: warnKeys.has(listKey),
    }
  })
}
