import type {
  ApplicationSummary,
  CandidateEducationFact,
  CandidateEmploymentFact,
  CandidatePersonProfileResponse,
  CandidateProfileResponse,
  PositionSummary,
} from '@/types'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import { canonicalStageLabel } from '@/lib/recruitingLifecycle'
import {
  candidateListJobPresentation,
  candidateListStageLabel,
  formatCandidateDisplayName,
  formatReceivedRelative,
  isGeneralCandidate,
  normalizeListSourceKey,
} from '@/lib/candidatesListPresentation'

export { isGeneralCandidate }

const SOURCE_LABELS: Record<RecruitingLocale, Record<string, string>> = {
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

export type ProfileSectionId =
  | 'overview'
  | 'applications'
  | 'cv'
  | 'interviews'
  | 'activity'

export const PROFILE_SECTIONS: Array<{ id: ProfileSectionId; en: string; ar: string }> = [
  { id: 'overview', en: 'Overview', ar: 'نظرة عامة' },
  { id: 'applications', en: 'Applications', ar: 'الطلبات' },
  { id: 'cv', en: 'CV', ar: 'السيرة الذاتية' },
  { id: 'interviews', en: 'Interviews & assessments', ar: 'المقابلات والتقييمات' },
  { id: 'activity', en: 'Activity', ar: 'النشاط' },
]

const NO_JOB: Record<RecruitingLocale, string> = {
  en: 'No job assigned',
  ar: 'غير مرتبط بوظيفة',
}

export function profileCopy(locale: RecruitingLocale) {
  if (locale === 'ar') {
    return {
      back: 'رجوع',
      backToRanking: 'العودة إلى الترتيب',
      addToJob: 'إضافة إلى وظيفة',
      noJobAssigned: NO_JOB.ar,
      selectJob: 'اختر وظيفة مفتوحة',
      confirmAdd: 'تأكيد الإضافة',
      cancel: 'إلغاء',
      confirmTitle: 'إضافة المرشح إلى وظيفة؟',
      confirmBody: 'راجع المرشح والوظيفة والسيرة الذاتية قبل التأكيد. لن يتم التعيين تلقائياً.',
      candidate: 'المرشح',
      job: 'الوظيفة',
      cv: 'السيرة الذاتية',
      cvOnFile: 'سيرة ذاتية متوفرة',
      cvMissing: 'لا توجد سيرة ذاتية',
      adding: 'جاري الإضافة…',
      added: 'تمت إضافة المرشح إلى الوظيفة.',
      duplicateJob: 'هذا المرشح لديه طلب بالفعل لهذه الوظيفة.',
      permissionDenied: 'ليس لديك صلاحية لإضافة مرشحين إلى الوظائف.',
      previewCv: 'معاينة السيرة',
      downloadCv: 'تنزيل السيرة',
      currentCv: 'السيرة الحالية',
      previousCvs: 'إصدارات سابقة',
      noPreviousCvs: 'لا توجد إصدارات سابقة.',
      summary: 'الملخص',
      profileDetails: 'تفاصيل الملف',
      topSkills: 'أبرز المهارات',
      experience: 'الخبرة',
      education: 'التعليم',
      languages: 'اللغات',
      professionalHighlights: 'أبرز الإنجازات المهنية',
      certifications: 'الشهادات',
      publications: 'المنشورات',
      trainingCourses: 'التدريب والدورات',
      membershipsActivities: 'العضويات والأنشطة',
      awardsHonors: 'الجوائز والتكريمات',
      projects: 'المشاريع',
      volunteerWork: 'العمل التطوعي',
      gpa: 'المعدل',
      contact: 'بيانات التواصل',
      source: 'المصدر',
      received: 'تاريخ الاستلام',
      stage: 'المرحلة',
      nextAction: 'الإجراء التالي',
      openOffer: 'إنشاء عرض وظيفي',
      offerTitle: 'عرض وظيفي',
      closeOffer: 'إغلاق',
      emptyOverview: 'لا تتوفر تفاصيل إضافية بعد.',
      emptyApplications: 'لا توجد طلبات مرتبطة بعد.',
      emptyInterviews: 'لا توجد مقابلات أو تقييمات بعد.',
      emptyNotes: 'ستظهر الملاحظات هنا أثناء سير التوظيف.',
      emptyActivity: 'لا يوجد نشاط للعرض بعد.',
      working: 'جاري العمل…',
      moreActions: 'إجراءات أخرى',
      optionalNote: 'ملاحظة اختيارية',
      expertise: 'التخصص',
      location: 'الموقع',
      email: 'البريد',
      phone: 'الهاتف',
      currentJob: 'الوظيفة الحالية',
      selectApplication: 'اختر طلباً',
      loadError: 'تعذر تحميل ملف المرشح.',
    }
  }
  return {
    back: 'Back',
    backToRanking: 'Back to Ranking',
    addToJob: 'Add to job',
    noJobAssigned: NO_JOB.en,
    selectJob: 'Select an open job',
    confirmAdd: 'Confirm add',
    cancel: 'Cancel',
    confirmTitle: 'Add candidate to a job?',
    confirmBody: 'Review the candidate, job, and CV before confirming. Nothing is assigned automatically.',
    candidate: 'Candidate',
    job: 'Job',
    cv: 'CV',
    cvOnFile: 'CV on file',
    cvMissing: 'No CV on file',
    adding: 'Adding…',
    added: 'Candidate added to the job.',
    duplicateJob: 'This candidate already has an application for that job.',
    permissionDenied: 'You do not have permission to add candidates to jobs.',
    previewCv: 'Preview CV',
    downloadCv: 'Download CV',
    currentCv: 'Current CV',
    previousCvs: 'Previous versions',
    noPreviousCvs: 'No previous versions.',
    summary: 'Summary',
    profileDetails: 'Profile details',
    topSkills: 'Top skills',
    experience: 'Experience',
    education: 'Education',
    languages: 'Languages',
    professionalHighlights: 'Professional highlights',
    certifications: 'Certifications',
    publications: 'Publications',
    trainingCourses: 'Training & courses',
    membershipsActivities: 'Memberships & activities',
    awardsHonors: 'Awards & honors',
    projects: 'Projects',
    volunteerWork: 'Volunteer work',
    gpa: 'GPA',
    contact: 'Contact details',
    source: 'Source',
    received: 'Received',
    stage: 'Stage',
    nextAction: 'Next action',
    openOffer: 'Create offer',
    offerTitle: 'Employment offer',
    closeOffer: 'Close',
    emptyOverview: 'No additional details yet.',
    emptyApplications: 'No applications yet.',
    emptyInterviews: 'No interviews or assessments yet.',
    emptyNotes: 'Notes will appear here as you add them during hiring.',
    emptyActivity: 'No activity to show yet.',
    working: 'Working…',
    moreActions: 'More actions',
    optionalNote: 'Optional note',
    expertise: 'Expertise',
    location: 'Location',
    email: 'Email',
    phone: 'Phone',
    currentJob: 'Current job',
    selectApplication: 'Select application',
    loadError: 'Could not load this candidate profile.',
  }
}

function asStringList(value: unknown, limit = 12): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  for (const item of value) {
    if (typeof item !== 'string' && typeof item !== 'number') continue
    const text = String(item).trim()
    if (!text || out.includes(text)) continue
    out.push(text)
    if (out.length >= limit) break
  }
  return out
}

function cleanText(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number'
    ? String(value).trim()
    : ''
}

function structuredList<T>(value: unknown): T[] {
  if (!Array.isArray(value)) return []
  return value.filter((item) => Boolean(item) && typeof item === 'object') as T[]
}

function yearsLabel(years: unknown, locale: RecruitingLocale): string {
  if (typeof years !== 'number' || !Number.isFinite(years)) return ''
  if (Number.isInteger(years)) {
    const n = years
    if (locale === 'ar') return n === 1 ? 'سنة واحدة' : `${n} سنوات`
    return n === 1 ? '1 year' : `${n} years`
  }
  return locale === 'ar' ? `${years} سنوات` : `${years} years`
}

/** Canonical profile facts only — never parse raw `{ value }` extraction shapes. */
export function canonicalProfileFacts(
  profile: CandidatePersonProfileResponse | CandidateProfileResponse | null,
): {
  skills: string[]
  education: string[]
  employment: string[]
  languages: string[]
  location: string
  professional_summary: string
  primary_expertise: string
  experience_years: number | null
  certifications: string[]
  projects: string[]
  publications: string[]
  training_courses: string[]
  memberships_activities: string[]
  awards_honors: string[]
  volunteer_work: string[]
  structuredEmployment: CandidateEmploymentFact[]
  structuredEducation: CandidateEducationFact[]
} {
  const facts = (profile as CandidatePersonProfileResponse | null)?.profile_facts
  if (facts && typeof facts === 'object') {
    return {
      skills: asStringList(facts.skills, 12),
      education: asStringList(facts.education, 8),
      employment: asStringList(facts.employment, 8),
      languages: asStringList(facts.languages, 8),
      location: typeof facts.location === 'string' ? facts.location.trim() : '',
      professional_summary: typeof facts.professional_summary === 'string' ? facts.professional_summary.trim() : '',
      primary_expertise: typeof facts.primary_expertise === 'string' ? facts.primary_expertise.trim() : '',
      experience_years: typeof facts.experience_years === 'number' ? facts.experience_years : null,
      certifications: asStringList(facts.certifications, 12),
      projects: asStringList(facts.projects, 12),
      publications: asStringList(facts.publications, 12),
      training_courses: asStringList(facts.training_courses, 12),
      memberships_activities: asStringList(facts.memberships_activities, 12),
      awards_honors: asStringList(facts.awards_honors, 12),
      volunteer_work: asStringList(facts.volunteer_work, 12),
      structuredEmployment: structuredList<CandidateEmploymentFact>(
        facts.structured?.employment,
      ),
      structuredEducation: structuredList<CandidateEducationFact>(
        facts.structured?.education,
      ),
    }
  }
  return {
    skills: [],
    education: [],
    employment: [],
    languages: [],
    location: '',
    professional_summary: '',
    primary_expertise: '',
    experience_years: null,
    certifications: [],
    projects: [],
    publications: [],
    training_courses: [],
    memberships_activities: [],
    awards_honors: [],
    volunteer_work: [],
    structuredEmployment: [],
    structuredEducation: [],
  }
}

export function headerMetaParts(
  _application: ApplicationSummary,
  profile: CandidatePersonProfileResponse | null,
  locale: RecruitingLocale,
): string[] {
  const facts = canonicalProfileFacts(profile)
  const parts: string[] = []
  if (facts.primary_expertise) parts.push(facts.primary_expertise)
  const years = yearsLabel(facts.experience_years, locale)
  if (years) parts.push(years)
  if (facts.location) parts.push(facts.location)
  return parts
}

export type ProfileExperienceItem = {
  id: string
  title: string
  company: string
  location: string
  period: string
  description: string
  achievements: string[]
}

export type ProfileEducationItem = {
  id: string
  degree: string
  institution: string
  location: string
  period: string
  gpa: string
  details: string[]
}

function datePeriod(start: unknown, end: unknown): string {
  const from = cleanText(start)
  const to = cleanText(end)
  if (from && to) return `${from} – ${to}`
  return from || to
}

function splitCanonicalLine(value: string): string[] {
  return value
    .split(/\s+·\s+/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function fallbackExperience(value: string, index: number): ProfileExperienceItem {
  const parts = splitCanonicalLine(value)
  const periodIndex = parts.findIndex((part) => /\b(?:19|20)\d{2}\b|present|current/i.test(part))
  return {
    id: `employment-flat-${index}-${value}`,
    title: parts[0] || value,
    company: parts[1] && periodIndex !== 1 ? parts[1] : '',
    location: '',
    period: periodIndex >= 0 ? parts.slice(periodIndex).join(' · ') : '',
    description: '',
    achievements: [],
  }
}

function fallbackEducation(value: string, index: number): ProfileEducationItem {
  const parts = splitCanonicalLine(value)
  const detailStart = parts.findIndex((part) => /^(?:GPA:|honou?r|member|activities?:)/i.test(part))
  const core = detailStart >= 0 ? parts.slice(0, detailStart) : parts
  const details = detailStart >= 0 ? parts.slice(detailStart) : []
  const periodIndex = core.findIndex((part) => /\b(?:19|20)\d{2}\b/.test(part))
  const locationIndex = core.findIndex((part, partIndex) =>
    partIndex > 1 && partIndex !== periodIndex && !/\b(?:19|20)\d{2}\b/.test(part),
  )
  const gpa = details.find((part) => /^GPA:/i.test(part))?.replace(/^GPA:\s*/i, '') || ''
  return {
    id: `education-flat-${index}-${value}`,
    degree: core[0] || value,
    institution: core[1] || '',
    location: locationIndex >= 0 ? core[locationIndex] : '',
    period: periodIndex >= 0 ? core[periodIndex] : '',
    gpa,
    details: details.filter((part) => !/^GPA:/i.test(part)),
  }
}

/** Presentation-only structure over the same canonical profile-facts authority. */
export function profileOverviewDetails(
  profile: CandidatePersonProfileResponse | null,
): {
  experience: ProfileExperienceItem[]
  education: ProfileEducationItem[]
  certifications: string[]
  projects: string[]
  publications: string[]
  trainingCourses: string[]
  membershipsActivities: string[]
  awardsHonors: string[]
  volunteerWork: string[]
} {
  const facts = canonicalProfileFacts(profile)
  const experience = facts.structuredEmployment.length
    ? facts.structuredEmployment.map((item, index) => ({
        id: `employment-${index}-${cleanText(item.title)}-${cleanText(item.company)}`,
        title: cleanText(item.title) || cleanText(item.company) || 'Experience',
        company: cleanText(item.company),
        location: cleanText(item.location),
        period: datePeriod(item.start_date, item.end_date),
        description: cleanText(item.description),
        achievements: asStringList(item.achievements, 6),
      }))
    : facts.employment.map(fallbackExperience)

  const education = facts.structuredEducation.length
    ? facts.structuredEducation.map((item, index) => {
        const honors = cleanText(item.honors)
        return {
          id: `education-${index}-${cleanText(item.degree)}-${cleanText(item.institution)}`,
          degree: cleanText(item.degree) || cleanText(item.institution) || 'Education',
          institution: cleanText(item.institution),
          location: cleanText(item.location),
          period: datePeriod(item.start_date, item.end_date),
          gpa: cleanText(item.gpa),
          details: honors
            .split(/\s*;\s*/)
            .map((part) => part.trim())
            .filter(Boolean),
        }
      })
    : facts.education.map(fallbackEducation)

  return {
    experience,
    education,
    certifications: facts.certifications,
    projects: facts.projects,
    publications: facts.publications,
    trainingCourses: facts.training_courses,
    membershipsActivities: facts.memberships_activities,
    awardsHonors: facts.awards_honors,
    volunteerWork: facts.volunteer_work,
  }
}

export function candidateContactLines(application: ApplicationSummary) {
  const email = String(application.grounded_contacts?.email || application.candidate?.email || '').trim()
  const phone = String(application.grounded_contacts?.phone || application.phone || '').trim()
  const cleanEmail = email && !/^imp-/i.test(email) ? email : ''
  const cleanPhone = phone && !/^imp-/i.test(phone) ? phone : ''
  return { email: cleanEmail, phone: cleanPhone }
}

export function candidateJobHeaderLabel(application: ApplicationSummary, locale: RecruitingLocale) {
  if (isGeneralCandidate(application)) return NO_JOB[locale]
  const title = candidateListJobPresentation(application, locale, 0).title
  if (!title || title === NO_JOB[locale] || title === 'Not linked') return NO_JOB[locale]
  return title
}

export function candidateStageHeaderLabel(application: ApplicationSummary, locale: RecruitingLocale) {
  return candidateListStageLabel(application, locale)
}

export function relatedApplicationsFor(
  selected: ApplicationSummary,
  applications: ApplicationSummary[],
): ApplicationSummary[] {
  // Person-profile already returns live applications only; do not re-aggregate by name.
  if (!applications.length) return []
  if (applications.some((app) => app.app_key === selected.app_key)) return applications
  return applications
}

export function openAssignableJobs(
  positions: PositionSummary[],
  related: ApplicationSummary[],
): PositionSummary[] {
  const taken = new Set(
    related
      .filter((app) => !isGeneralCandidate(app))
      .map((app) => String(app.position?.code || '').trim())
      .filter(Boolean),
  )
  return positions.filter((job) => {
    const code = String(job.position_code || '').trim()
    if (!code) return false
    if (String(job.status || '').toLowerCase() !== 'open') return false
    if (taken.has(code)) return false
    return true
  })
}

export function hasDuplicateJobApplication(related: ApplicationSummary[], positionCode: string) {
  const code = String(positionCode || '').trim()
  if (!code) return false
  return related.some((app) => {
    if (isGeneralCandidate(app)) return false
    return String(app.position?.code || '').trim() === code
  })
}

export function overviewFromProfile(
  application: ApplicationSummary,
  profile: CandidatePersonProfileResponse | null,
  locale: RecruitingLocale,
) {
  const facts = canonicalProfileFacts(profile)
  const contact = candidateContactLines(application)
  const sourceKey = normalizeListSourceKey(application)
  const source = SOURCE_LABELS[locale][sourceKey] || SOURCE_LABELS.en.unknown
  const received = formatReceivedRelative(application.ingested_at || application.updated_at, locale)
  const personName = profile?.person?.display_name || application.candidate?.name

  return {
    summary: facts.professional_summary,
    skills: facts.skills,
    experience: facts.employment,
    education: facts.education,
    languages: facts.languages,
    email: contact.email,
    phone: contact.phone,
    source,
    received,
    location: facts.location,
    experienceYears: yearsLabel(facts.experience_years, locale),
    expertise: facts.primary_expertise,
    name: formatCandidateDisplayName(personName, locale),
  }
}

export function applicationNextActionLabel(
  application: ApplicationSummary,
  locale: RecruitingLocale,
  opts: { assessmentEnabled: boolean; videoInterviewsEnabled: boolean },
) {
  if (isGeneralCandidate(application)) {
    return locale === 'ar' ? 'إضافة إلى وظيفة' : 'Add to job'
  }
  const allowed = new Set(application.allowed_actions || [])
  const interview = application.interview
  const asyncReady =
    interview?.interview_type === 'async_video'
    && String(interview.async_status || '').toLowerCase().includes('ready')
  if (asyncReady && allowed.has('schedule_interview')) {
    return locale === 'ar' ? 'مراجعة رد الفيديو' : 'Review video response'
  }
  if (opts.assessmentEnabled && allowed.has('send_assessment') && application.cv?.received) {
    return locale === 'ar' ? 'إرسال تقييم' : 'Send assessment'
  }
  if (opts.assessmentEnabled && allowed.has('resend_assessment') && application.cv?.received) {
    return locale === 'ar' ? 'إعادة إرسال التقييم' : 'Resend assessment'
  }
  if (opts.videoInterviewsEnabled && allowed.has('send_video_interview') && application.cv?.received) {
    return locale === 'ar' ? 'إرسال مقابلة فيديو' : 'Send video interview'
  }
  if (allowed.has('shortlist')) return locale === 'ar' ? 'إضافة للقائمة المختصرة' : 'Shortlist'
  if (allowed.has('schedule_interview')) return locale === 'ar' ? 'جدولة مقابلة' : 'Schedule interview'
  if (allowed.has('hire')) return locale === 'ar' ? 'توظيف' : 'Hire'
  if (allowed.has('reject')) return locale === 'ar' ? 'رفض' : 'Reject'
  if (allowed.has('notify')) return locale === 'ar' ? 'التواصل مع المرشح' : 'Contact candidate'
  return canonicalStageLabel(application.canonical_stage || application.status, locale)
}

export function offerEligible(application: ApplicationSummary, employmentOffersEnabled: boolean) {
  if (!employmentOffersEnabled) return false
  if (isGeneralCandidate(application)) return false
  if (!application.position?.code && !application.position?.title) return false
  const stage = String(application.canonical_stage || application.status || '').toLowerCase()
  if (['rejected', 'withdrawn', 'archived', 'hired'].includes(stage)) return false
  return ['shortlisted', 'interview', 'scheduled', 'offer', 'offered', 'offer_sent', 'ready_for_review'].includes(stage)
    || (application.allowed_actions || []).includes('hire')
}

export function cvVersionsFromProfile(profile: CandidatePersonProfileResponse | null) {
  const bundle = profile?.cv_versions
  if (bundle && !Array.isArray(bundle) && typeof bundle === 'object') {
    const current = bundle.current
      ? {
          id: String(bundle.current.id || 'current'),
          filename: String(bundle.current.filename || 'CV'),
          createdAt: bundle.current.created_at || null,
        }
      : null
    const previous = (bundle.previous || [])
      .filter((item) => item && String(item.id || '') !== String(current?.id || ''))
      .map((item, index) => ({
        id: String(item.id || `prev-${index}`),
        filename: String(item.filename || `CV ${index + 1}`),
        createdAt: item.created_at || null,
      }))
    return { current, previous }
  }
  return { current: null, previous: [] }
}

export function humanActivityItems(application: ApplicationSummary, locale: RecruitingLocale): string[] {
  const blocked = /held|intake|needs_role|provenance|taxonomy|completeness|privacy|retention|classifier|talent.?pool|raw.?id|future.?action/i
  const raw = [
    ...(application.automatic_activity || []),
    ...(application.waiting_for_hr || []).map((item) =>
      locale === 'ar' ? `بانتظار الموارد البشرية: ${item}` : `Waiting on HR: ${item}`,
    ),
  ]
  return raw
    .map((item) => String(item || '').trim())
    .filter((item) => item && !blocked.test(item))
    .slice(0, 12)
}
