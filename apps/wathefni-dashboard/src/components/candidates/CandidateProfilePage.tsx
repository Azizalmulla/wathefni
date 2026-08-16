import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ArrowLeft,
  Award,
  BookOpen,
  BriefcaseBusiness,
  CalendarDays,
  ClipboardList,
  Clock3,
  FileText,
  FolderKanban,
  GraduationCap,
  Languages,
  Loader2,
  Mail,
  MapPin,
  Medal,
  Send,
  Tags,
  UserCheck,
  Users,
  Video,
} from 'lucide-react'

import type {
  ApplicationSummary,
  DashboardAccess,
  MutationResponse,
  PositionSummary,
} from '@/types'
import {
  hireCandidate,
  notifyCandidate,
  previewAssessmentReport,
  previewCandidateCv,
  downloadCandidateCv,
  rejectCandidate,
  resendAssessment,
  sendAssessment,
  sendVideoInterview,
  shortlistCandidate,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { useCandidateProfileQuery } from '@/lib/query/hooks'
import { actionLabel as recruitingActionLabel, type RecruitingLocale } from '@/lib/recruitingLifecycle'
import {
  applicationNextActionLabel,
  candidateContactLines,
  candidateJobHeaderLabel,
  candidateStageHeaderLabel,
  cvVersionsFromProfile,
  headerMetaParts,
  humanActivityItems,
  offerEligible,
  overviewFromProfile,
  profileOverviewDetails,
  PROFILE_SECTIONS,
  profileCopy,
  type ProfileSectionId,
} from '@/lib/candidateProfilePresentation'
import {
  candidateInitials,
  candidateListStageTone,
  isGeneralCandidate as isGeneral,
} from '@/lib/candidatesListPresentation'
import { AddToJobDialog } from '@/components/candidates/AddToJobDialog'
import { OfferPanel } from '@/components/OfferPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/field'
import { useBodyScrollLock, useOverlayFocus } from '@/hooks/useOverlayA11y'
import { useConfirm } from '@/components/ConfirmDialog'

function profileErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function DetailRow({
  icon,
  label,
  value,
}: {
  icon: ReactNode
  label: string
  value?: string | null
}) {
  return (
    <div className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/70 text-subtle">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-subtle">{label}</div>
        <div className="mt-1 break-words text-sm font-medium text-text">{value || '—'}</div>
      </div>
    </div>
  )
}

function SectionTitle({
  icon,
  title,
  count,
}: {
  icon: ReactNode
  title: string
  count?: number
}) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/75 text-text">
        {icon}
      </div>
      <h2 className="text-[15px] font-semibold tracking-tight text-text">{title}</h2>
      {count ? <span className="text-xs font-medium text-subtle">{count}</span> : null}
    </div>
  )
}

function HighlightGroup({
  icon,
  label,
  items,
}: {
  icon: ReactNode
  label: string
  items: string[]
}) {
  if (!items.length) return null
  return (
    <div className="rounded-2xl border border-line/45 bg-white/32 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-text">
        <span className="text-subtle">{icon}</span>
        {label}
      </div>
      <ul className="mt-3 space-y-2">
        {items.slice(0, 4).map((item) => (
          <li key={item} className="line-clamp-2 text-[13px] leading-5 text-text/80">
            {item}
          </li>
        ))}
      </ul>
      {items.length > 4 ? (
        <div className="mt-2 text-xs font-medium text-subtle">+{items.length - 4}</div>
      ) : null}
    </div>
  )
}

function primaryActionFor(
  application: ApplicationSummary,
  assessmentEnabled: boolean,
  videoInterviewsEnabled: boolean | undefined,
) {
  if (isGeneral(application)) {
    return { id: 'add_to_job', label: 'Add to job', icon: 'user' as const }
  }
  const allowed = new Set(application.allowed_actions || [])
  const interview = application.interview
  const asyncReady =
    interview?.interview_type === 'async_video'
    && String(interview.async_status || interview.video_review_status || '').toLowerCase().includes('ready')
  if (asyncReady && allowed.has('schedule_interview')) {
    return { id: 'review_video', label: 'Review video response', icon: 'video' as const }
  }
  if (assessmentEnabled && allowed.has('send_assessment') && application.cv?.received) {
    return { id: 'send_assessment', label: 'Send assessment', icon: 'send' as const }
  }
  if (assessmentEnabled && allowed.has('resend_assessment') && application.cv?.received) {
    return { id: 'resend_assessment', label: 'Resend assessment', icon: 'send' as const }
  }
  if (videoInterviewsEnabled && allowed.has('send_video_interview') && application.cv?.received && interview?.interview_type !== 'async_video') {
    return { id: 'send_video_interview', label: 'Send video interview', icon: 'video' as const }
  }
  if (allowed.has('shortlist')) return { id: 'shortlist', label: 'Shortlist', icon: 'user' as const }
  if (allowed.has('schedule_interview')) return { id: 'schedule_interview', label: 'Schedule interview', icon: 'user' as const }
  if (allowed.has('hire')) return { id: 'hire', label: 'Hire', icon: 'user' as const }
  if (allowed.has('reject')) return { id: 'reject', label: 'Reject', icon: 'user' as const }
  if (allowed.has('notify')) return { id: 'notify', label: 'Contact candidate', icon: 'send' as const }
  return { id: 'none', label: '', icon: 'user' as const }
}

export function CandidateProfilePage({
  access,
  application,
  positions,
  locale,
  busy,
  runningAction,
  message,
  setMessage,
  mutate,
  assessmentEnabled,
  videoInterviewsEnabled,
  employmentOffersEnabled,
  canManageAssessments,
  canManageInterviews,
  onClose,
  onAccessIssue,
  onOpenAssessments,
  onOpenInterviews,
  onScheduleInterview,
  onRefresh,
  onSelectApplication,
  returnLabel,
}: {
  access: DashboardAccess
  application: ApplicationSummary
  positions: PositionSummary[]
  locale: RecruitingLocale
  busy: boolean
  runningAction: string | null
  message: string
  setMessage: (value: string) => void
  mutate: (label: string, action: () => Promise<MutationResponse>, key?: string) => Promise<void>
  assessmentEnabled: boolean
  /** Undefined while workspace authority is still settling — omit video actions until known. */
  videoInterviewsEnabled: boolean | undefined
  employmentOffersEnabled: boolean
  canManageAssessments: boolean
  canManageInterviews: boolean
  onClose: () => void
  onAccessIssue?: (issue: AccessIssue) => void
  onOpenAssessments: () => void
  onOpenInterviews: () => void
  onScheduleInterview: () => void
  onRefresh: () => void
  onSelectApplication: (application: ApplicationSummary) => void
  /** Overrides default Back label (e.g. Back to Ranking). */
  returnLabel?: string
}) {
  const t = profileCopy(locale)
  const confirm = useConfirm()
  const panelRef = useRef<HTMLDivElement>(null)
  const [section, setSection] = useState<ProfileSectionId>('overview')
  const [addToJobOpen, setAddToJobOpen] = useState(false)
  const [offerOpen, setOfferOpen] = useState(false)
  const profileQuery = useCandidateProfileQuery(access, application.app_key)
  const personProfile = profileQuery.data ?? null
  const loading = profileQuery.isLoading && !personProfile
  const loadError = profileQuery.isError && !personProfile ? t.loadError : ''

  useEffect(() => {
    if (!profileQuery.isError || personProfile) return
    const issue = accessIssueFromError(profileQuery.error)
    if (issue) onAccessIssue?.(issue)
  }, [onAccessIssue, personProfile, profileQuery.error, profileQuery.isError])

  const activeApplication = useMemo(() => {
    const fromPerson = personProfile?.applications?.find((item) => item.app_key === application.app_key)
    return fromPerson || personProfile?.application || application
  }, [personProfile, application])

  const related = useMemo(
    () => (personProfile?.applications?.length ? personProfile.applications : [activeApplication]),
    [personProfile, activeApplication],
  )

  const overview = overviewFromProfile(activeApplication, personProfile, locale)
  const overviewDetails = profileOverviewDetails(personProfile)
  const headerMeta = headerMetaParts(activeApplication, personProfile, locale)
  const contact = candidateContactLines(activeApplication)
  const primary = primaryActionFor(activeApplication, assessmentEnabled, videoInterviewsEnabled)
  const actionKey = (id: string) => `${id}:${activeApplication.app_key}`
  const cvVersions = cvVersionsFromProfile(personProfile)
  const activityItems = (personProfile?.activity?.length
    ? personProfile.activity
    : humanActivityItems(activeApplication, locale))
  const showOffer = offerEligible(activeApplication, employmentOffersEnabled)
  const highlightGroups = [
    { label: t.awardsHonors, items: overviewDetails.awardsHonors, icon: <Medal size={15} /> },
    { label: t.publications, items: overviewDetails.publications, icon: <BookOpen size={15} /> },
    { label: t.trainingCourses, items: overviewDetails.trainingCourses, icon: <ClipboardList size={15} /> },
    { label: t.certifications, items: overviewDetails.certifications, icon: <Award size={15} /> },
    { label: t.projects, items: overviewDetails.projects, icon: <FolderKanban size={15} /> },
    { label: t.membershipsActivities, items: overviewDetails.membershipsActivities, icon: <Users size={15} /> },
    { label: t.volunteerWork, items: overviewDetails.volunteerWork, icon: <UserCheck size={15} /> },
  ].filter((group) => group.items.length)

  const previewCv = async () => {
    try {
      setMessage(locale === 'ar' ? 'جاري فتح السيرة…' : 'Opening CV…')
      await previewCandidateCv(access, activeApplication.app_key)
      setMessage(locale === 'ar' ? 'تم فتح السيرة.' : 'CV opened.')
    } catch (error) {
      setMessage(profileErrorMessage(error, t.loadError))
    }
  }

  const downloadCv = async () => {
    try {
      setMessage(locale === 'ar' ? 'جاري تنزيل السيرة…' : 'Downloading CV…')
      await downloadCandidateCv(access, activeApplication.app_key, activeApplication.cv?.filename || `${overview.name}-cv`)
      setMessage(locale === 'ar' ? 'تم تنزيل السيرة.' : 'CV downloaded.')
    } catch (error) {
      setMessage(profileErrorMessage(error, locale === 'ar' ? 'تعذر تنزيل السيرة.' : 'Could not download the CV.'))
    }
  }

  const runPrimary = async () => {
    const who = overview.name
    if (primary.id === 'add_to_job') {
      setAddToJobOpen(true)
      return
    }
    if (primary.id === 'review_video') {
      onOpenInterviews()
      return
    }
    if (primary.id === 'schedule_interview') {
      onScheduleInterview()
      return
    }
    if (primary.id === 'send_assessment') {
      if (!(await confirm({ title: locale === 'ar' ? 'إرسال تقييم؟' : 'Send assessment?', body: locale === 'ar' ? `سيستلم ${who} رابط التقييم.` : `${who} will receive an assessment link.`, confirmLabel: locale === 'ar' ? 'إرسال' : 'Send assessment' }))) return
      await mutate('Sending assessment', () => sendAssessment(access, activeApplication.app_key, message), actionKey('send_assessment'))
      return
    }
    if (primary.id === 'resend_assessment') {
      if (!(await confirm({ title: locale === 'ar' ? 'إعادة إرسال التقييم؟' : 'Resend assessment?', body: locale === 'ar' ? `سيُلغى الرابط القديم ويُرسل رابط جديد لـ ${who}.` : `The old link will be revoked and ${who} will receive a new one.`, confirmLabel: locale === 'ar' ? 'إعادة الإرسال' : 'Resend assessment' }))) return
      const attemptId = String(activeApplication.assessment?.attempt_id || '').trim()
      if (attemptId) {
        await mutate('Resending assessment', () => resendAssessment(access, attemptId, message), actionKey('resend_assessment'))
      } else {
        await mutate('Sending assessment', () => sendAssessment(access, activeApplication.app_key, message), actionKey('send_assessment'))
      }
      return
    }
    if (primary.id === 'send_video_interview') {
      if (!(await confirm({ title: locale === 'ar' ? 'إرسال مقابلة فيديو؟' : 'Send video interview?', body: locale === 'ar' ? `سيستلم ${who} دعوة الفيديو.` : `${who} will receive a video interview invite.`, confirmLabel: locale === 'ar' ? 'إرسال' : 'Send invite' }))) return
      await mutate('Sending video interview', () => sendVideoInterview(access, activeApplication.app_key, message), actionKey('send_video_interview'))
      return
    }
    if (primary.id === 'shortlist') {
      if (!(await confirm({ title: locale === 'ar' ? 'إضافة للقائمة المختصرة؟' : 'Shortlist this candidate?', body: locale === 'ar' ? `نقل ${who} إلى القائمة المختصرة.` : `Move ${who} to the shortlist.`, confirmLabel: locale === 'ar' ? 'تأكيد' : 'Shortlist' }))) return
      await mutate('Shortlisting candidate', () => shortlistCandidate(access, activeApplication, message), actionKey('shortlist'))
      return
    }
    if (primary.id === 'hire') {
      if (!(await confirm({ title: locale === 'ar' ? 'توظيف هذا المرشح؟' : 'Hire this candidate?', body: locale === 'ar' ? `سيتم توظيف ${who}.` : `This will hire ${who}.`, confirmLabel: locale === 'ar' ? 'توظيف' : 'Hire', destructive: true }))) return
      await mutate('Hiring candidate', () => hireCandidate(access, activeApplication, message), actionKey('hire'))
      return
    }
    if (primary.id === 'reject') {
      if (!(await confirm({ title: locale === 'ar' ? 'رفض هذا المرشح؟' : 'Reject this candidate?', body: locale === 'ar' ? `سيتم إخراج ${who} من المسار النشط.` : `This will move ${who} out of the active pipeline.`, confirmLabel: locale === 'ar' ? 'رفض' : 'Reject', destructive: true }))) return
      await mutate('Rejecting candidate', () => rejectCandidate(access, activeApplication, message), actionKey('reject'))
      return
    }
    if (primary.id === 'notify') {
      if (!(await confirm({ title: locale === 'ar' ? 'إرسال رسالة؟' : 'Notify candidate?', body: locale === 'ar' ? `سيستلم ${who} رسالة الآن.` : `${who} will receive a message now.`, confirmLabel: locale === 'ar' ? 'إرسال' : 'Send message' }))) return
      await mutate('Notifying candidate', () => notifyCandidate(access, activeApplication.app_key, message), actionKey('notify'))
    }
  }

  const primaryRunning = runningAction === actionKey(primary.id)
  const primaryLabel = primary.id === 'add_to_job'
    ? t.addToJob
    : primary.id === 'none'
      ? ''
      : recruitingActionLabel(primary.id, locale)

  // Keep wheel/trackpad/keyboard/touch scroll inside the profile layer only.
  useBodyScrollLock(true)
  useOverlayFocus(true, onClose, panelRef)

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-40 overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.72),_transparent_42%),linear-gradient(180deg,rgba(248,244,236,0.96),rgba(243,236,224,0.98))]"
      dir={locale === 'ar' ? 'rtl' : 'ltr'}
      ref={panelRef}
      role="dialog"
    >
      <div className="mx-auto flex h-full w-full max-w-6xl flex-col px-3 py-3 sm:px-5 sm:py-4">
        <div className="flex items-center gap-2">
          <Button onClick={onClose} size="sm" type="button" variant="secondary">
            <ArrowLeft size={16} className={locale === 'ar' ? 'rotate-180' : undefined} />
            {returnLabel || t.back}
          </Button>
        </div>

        <header className="mt-3 rounded-[1.6rem] border border-white/70 bg-panel/80 p-4 shadow-[0_1px_0_rgba(255,255,255,0.82)_inset,0_12px_30px_rgba(24,20,15,0.055)] backdrop-blur sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 gap-3">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white/70 text-lg font-semibold text-text">
                {candidateInitials(overview.name)}
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-2xl font-semibold tracking-tight text-text sm:text-[1.75rem]">{overview.name}</h1>
                {headerMeta.length ? (
                  <p className="mt-1 text-sm text-subtle">{headerMeta.join(' · ')}</p>
                ) : null}
                <p className="mt-1 text-sm text-subtle">
                  {[contact.email, contact.phone].filter(Boolean).join(' · ') || '—'}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge tone="muted">{candidateJobHeaderLabel(activeApplication, locale)}</Badge>
                  <Badge tone={candidateListStageTone(activeApplication)}>{candidateStageHeaderLabel(activeApplication, locale)}</Badge>
                </div>
              </div>
            </div>

            <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-[220px]">
              {primary.id !== 'none' ? (
                <Button disabled={busy || primaryRunning} onClick={() => void runPrimary()} type="button">
                  {primaryRunning ? (
                    <Loader2 className="animate-spin" size={16} />
                  ) : primary.icon === 'video' ? (
                    <Video size={16} />
                  ) : primary.icon === 'send' ? (
                    <Send size={16} />
                  ) : (
                    <UserCheck size={16} />
                  )}
                  {primaryRunning ? t.working : primaryLabel}
                </Button>
              ) : null}
              {!isGeneral(activeApplication) ? (
                <Textarea
                  className="min-h-12 text-[13px]"
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder={t.optionalNote}
                  rows={2}
                  value={message}
                />
              ) : null}
            </div>
          </div>
        </header>

        <nav className="mt-3 flex gap-1 overflow-x-auto pb-1">
          {PROFILE_SECTIONS.map((item) => {
            const active = section === item.id
            return (
              <button
                key={item.id}
                className={[
                  'whitespace-nowrap rounded-full px-3.5 py-2 text-sm font-semibold transition',
                  active ? 'bg-ink text-white' : 'bg-white/45 text-subtle hover:bg-white/70 hover:text-text',
                ].join(' ')}
                onClick={() => setSection(item.id)}
                type="button"
              >
                {locale === 'ar' ? item.ar : item.en}
              </button>
            )
          })}
        </nav>

        <div className="mt-3 min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-[1.6rem] border border-white/70 bg-panel/70 p-4 shadow-[0_1px_0_rgba(255,255,255,0.82)_inset] backdrop-blur sm:p-5">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-subtle">
              <Loader2 className="animate-spin" size={16} />
              {locale === 'ar' ? 'جاري التحميل…' : 'Loading…'}
            </div>
          ) : null}
          {loadError ? <p className="text-sm font-medium text-red-700">{loadError}</p> : null}

          {!loading && section === 'overview' ? (
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.7fr)_minmax(270px,0.72fr)]">
              <div className="min-w-0 space-y-5">
                {overview.summary ? (
                  <section className="rounded-2xl border border-line/45 bg-white/32 p-5">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-subtle">
                      {t.summary}
                    </div>
                    <p className="mt-2.5 max-w-3xl text-[15px] leading-7 text-text/90">
                      {overview.summary}
                    </p>
                  </section>
                ) : null}

                <section className="rounded-2xl border border-line/45 bg-white/32 p-5">
                  <SectionTitle
                    count={overviewDetails.experience.length}
                    icon={<BriefcaseBusiness size={17} />}
                    title={t.experience}
                  />
                  {overviewDetails.experience.length ? (
                    <div className="relative mt-5 space-y-5 before:absolute before:bottom-2 before:start-[5px] before:top-2 before:w-px before:bg-line/80">
                      {overviewDetails.experience.map((item) => (
                        <article key={item.id} className="relative ps-7">
                          <span className="absolute start-0 top-1.5 h-[11px] w-[11px] rounded-full border-[3px] border-panel bg-text" />
                          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                            <div className="min-w-0">
                              <h3 className="text-[15px] font-semibold leading-5 text-text">{item.title}</h3>
                              {item.company ? (
                                <p className="mt-1 text-sm font-medium text-text/70">{item.company}</p>
                              ) : null}
                            </div>
                            {item.period ? (
                              <div className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-subtle">
                                <CalendarDays size={13} />
                                {item.period}
                              </div>
                            ) : null}
                          </div>
                          {item.location ? (
                            <div className="mt-1.5 flex items-center gap-1.5 text-xs text-subtle">
                              <MapPin size={13} />
                              {item.location}
                            </div>
                          ) : null}
                          {item.description ? (
                            <p className="mt-2 text-[13px] leading-5 text-text/75">{item.description}</p>
                          ) : null}
                          {item.achievements.length ? (
                            <ul className="mt-2 space-y-1 text-[13px] leading-5 text-text/70">
                              {item.achievements.slice(0, 3).map((achievement) => (
                                <li key={achievement} className="flex gap-2">
                                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-subtle/70" />
                                  <span>{achievement}</span>
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-4 text-sm text-subtle">
                      {locale === 'ar' ? 'لا توجد خبرات مستخرجة.' : 'No experience extracted yet.'}
                    </p>
                  )}
                </section>

                <section className="rounded-2xl border border-line/45 bg-white/32 p-5">
                  <SectionTitle
                    count={overviewDetails.education.length}
                    icon={<GraduationCap size={18} />}
                    title={t.education}
                  />
                  {overviewDetails.education.length ? (
                    <div className="mt-4 grid gap-3">
                      {overviewDetails.education.map((item) => (
                        <article key={item.id} className="rounded-2xl border border-line/45 bg-white/42 p-4">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                            <div className="min-w-0">
                              <h3 className="text-[15px] font-semibold leading-5 text-text">{item.degree}</h3>
                              {item.institution ? (
                                <p className="mt-1 text-sm font-medium text-text/70">{item.institution}</p>
                              ) : null}
                            </div>
                            {item.period ? (
                              <div className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-subtle">
                                <CalendarDays size={13} />
                                {item.period}
                              </div>
                            ) : null}
                          </div>
                          <div className="mt-3 flex flex-wrap items-center gap-2">
                            {item.location ? (
                              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/65 px-2.5 py-1 text-xs text-subtle">
                                <MapPin size={12} />
                                {item.location}
                              </span>
                            ) : null}
                            {item.gpa ? (
                              <span className="rounded-full bg-white/65 px-2.5 py-1 text-xs font-medium text-text/75">
                                {t.gpa} {item.gpa}
                              </span>
                            ) : null}
                          </div>
                          {item.details.length ? (
                            <div className="mt-3 border-t border-line/40 pt-3">
                              {item.details.map((detail) => (
                                <p key={detail} className="text-[13px] leading-5 text-text/65">{detail}</p>
                              ))}
                            </div>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-4 text-sm text-subtle">
                      {locale === 'ar' ? 'لا يوجد تعليم مستخرج.' : 'No education extracted yet.'}
                    </p>
                  )}
                </section>

                {highlightGroups.length ? (
                  <section className="rounded-2xl border border-line/45 bg-white/32 p-5">
                    <SectionTitle icon={<Award size={17} />} title={t.professionalHighlights} />
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      {highlightGroups.map((group) => (
                        <HighlightGroup
                          icon={group.icon}
                          items={group.items}
                          key={group.label}
                          label={group.label}
                        />
                      ))}
                    </div>
                  </section>
                ) : null}
              </div>

              <aside className="space-y-4 lg:sticky lg:top-0">
                <section className="rounded-2xl border border-line/45 bg-white/32 p-4">
                  <SectionTitle icon={<UserCheck size={17} />} title={t.profileDetails} />
                  <div className="mt-4 divide-y divide-line/40">
                    <DetailRow icon={<Mail size={15} />} label={t.contact} value={[overview.email, overview.phone].filter(Boolean).join(' · ')} />
                    <DetailRow icon={<Clock3 size={15} />} label={t.received} value={overview.received} />
                    <DetailRow icon={<FolderKanban size={15} />} label={t.source} value={overview.source} />
                  </div>
                </section>

                <section className="rounded-2xl border border-line/45 bg-white/32 p-4">
                  <SectionTitle icon={<Tags size={17} />} title={t.topSkills} />
                  <div className="mt-4 flex flex-wrap gap-2">
                    {overview.skills.length
                      ? overview.skills.map((skill) => <Badge key={skill} tone="muted">{skill}</Badge>)
                      : <p className="text-sm text-subtle">{locale === 'ar' ? 'لا توجد مهارات مستخرجة.' : 'No skills extracted yet.'}</p>}
                  </div>
                </section>

                <section className="rounded-2xl border border-line/45 bg-white/32 p-4">
                  <SectionTitle icon={<Languages size={17} />} title={t.languages} />
                  <div className="mt-4 flex flex-wrap gap-2">
                    {overview.languages.length
                      ? overview.languages.map((language) => <Badge key={language} tone="muted">{language}</Badge>)
                      : <p className="text-sm text-subtle">{locale === 'ar' ? 'لا توجد لغات مستخرجة.' : 'No languages extracted yet.'}</p>}
                  </div>
                </section>
              </aside>

              {!overview.summary && !overview.skills.length && !overviewDetails.experience.length && !overviewDetails.education.length ? (
                <p className="text-sm text-subtle">{t.emptyOverview}</p>
              ) : null}
            </div>
          ) : null}

          {!loading && section === 'applications' ? (
            <div className="space-y-3">
              {related.map((app) => {
                const active = app.app_key === activeApplication.app_key
                const next = applicationNextActionLabel(app, locale, {
                  assessmentEnabled,
                  videoInterviewsEnabled: Boolean(videoInterviewsEnabled),
                })
                return (
                  <button
                    key={app.app_key}
                    className={[
                      'w-full rounded-2xl border p-4 text-start transition',
                      active ? 'border-[#c89445]/35 bg-white/70' : 'border-line/55 bg-white/35 hover:bg-white/55',
                    ].join(' ')}
                    onClick={() => onSelectApplication(app)}
                    type="button"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold text-text">{candidateJobHeaderLabel(app, locale)}</div>
                        <div className="mt-1 text-sm text-subtle">{candidateStageHeaderLabel(app, locale)}</div>
                      </div>
                      <Badge tone={candidateListStageTone(app)}>{next}</Badge>
                    </div>
                    {active && showOffer ? (
                      <div className="mt-3">
                        <Button
                          onClick={(event) => {
                            event.stopPropagation()
                            setOfferOpen(true)
                          }}
                          size="sm"
                          type="button"
                          variant="secondary"
                        >
                          {t.openOffer}
                        </Button>
                      </div>
                    ) : null}
                  </button>
                )
              })}
              {!related.length ? <p className="text-sm text-subtle">{t.emptyApplications}</p> : null}
            </div>
          ) : null}

          {!loading && section === 'cv' ? (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-2">
                <Button disabled={!activeApplication.cv?.received} onClick={() => void previewCv()} type="button" variant="secondary">
                  <FileText size={16} /> {t.previewCv}
                </Button>
                <Button disabled={!activeApplication.cv?.received} onClick={() => void downloadCv()} type="button" variant="secondary">
                  {t.downloadCv}
                </Button>
              </div>
              <section>
                <h2 className="text-sm font-semibold text-text">{t.currentCv}</h2>
                <p className="mt-2 text-sm text-text">
                  {cvVersions.current?.filename
                    || activeApplication.cv?.filename
                    || (activeApplication.cv?.received ? t.cvOnFile : t.cvMissing)}
                </p>
              </section>
              <section>
                <h2 className="text-sm font-semibold text-text">{t.previousCvs}</h2>
                {cvVersions.previous.length ? (
                  <ul className="mt-2 space-y-2 text-sm text-text">
                    {cvVersions.previous.map((item) => (
                      <li key={item.id}>
                        • {item.filename}
                        {item.createdAt ? ` · ${item.createdAt}` : ''}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-subtle">{t.noPreviousCvs}</p>
                )}
              </section>
            </div>
          ) : null}

          {!loading && section === 'interviews' ? (
            <div className="space-y-4">
              {activeApplication.interview ? (
                <div className="rounded-2xl border border-line/55 bg-white/35 p-4">
                  <div className="font-semibold text-text">{locale === 'ar' ? 'المقابلة' : 'Interview'}</div>
                  <p className="mt-1 text-sm text-subtle">
                    {activeApplication.interview.status || '—'}
                    {activeApplication.interview.scheduled_start ? ` · ${activeApplication.interview.scheduled_start}` : ''}
                  </p>
                  {activeApplication.interview.summary ? (
                    <p className="mt-3 text-sm leading-6 text-text">{activeApplication.interview.summary}</p>
                  ) : null}
                  {canManageInterviews ? (
                    <Button className="mt-3" onClick={onOpenInterviews} size="sm" type="button" variant="secondary">
                      {locale === 'ar' ? 'فتح المقابلات' : 'Open interviews'}
                    </Button>
                  ) : null}
                </div>
              ) : null}
              {assessmentEnabled && activeApplication.assessment?.status ? (
                <div className="rounded-2xl border border-line/55 bg-white/35 p-4">
                  <div className="font-semibold text-text">{locale === 'ar' ? 'التقييم' : 'Assessment'}</div>
                  <p className="mt-1 text-sm text-subtle">
                    {activeApplication.assessment.status}
                    {activeApplication.assessment.percent != null ? ` · ${Math.round(activeApplication.assessment.percent)}%` : ''}
                  </p>
                  {activeApplication.assessment.summary ? (
                    <p className="mt-3 text-sm leading-6 text-text">{activeApplication.assessment.summary}</p>
                  ) : null}
                  {canManageAssessments && activeApplication.assessment.attempt_id && activeApplication.assessment.status === 'completed' ? (
                    <Button
                      className="mt-3"
                      onClick={() => void previewAssessmentReport(access, activeApplication.assessment!.attempt_id!).then(() => setMessage(locale === 'ar' ? 'تم فتح تقرير التقييم.' : 'Assessment report opened.')).catch((error) => setMessage(profileErrorMessage(error, 'Could not open assessment report.')))}
                      size="sm"
                      type="button"
                      variant="secondary"
                    >
                      {locale === 'ar' ? 'معاينة التقرير' : 'Preview report'}
                    </Button>
                  ) : canManageAssessments ? (
                    <Button className="mt-3" onClick={onOpenAssessments} size="sm" type="button" variant="secondary">
                      {locale === 'ar' ? 'فتح التقييمات' : 'Open assessments'}
                    </Button>
                  ) : null}
                </div>
              ) : null}
              {!activeApplication.interview && !(assessmentEnabled && activeApplication.assessment?.status) && !personProfile?.interviews?.length && !personProfile?.assessments?.length ? (
                <p className="text-sm text-subtle">{t.emptyInterviews}</p>
              ) : null}
            </div>
          ) : null}

          {!loading && section === 'activity' ? (
            <div>
              {activityItems.length ? (
                <ul className="space-y-2 text-sm text-text">
                  {activityItems.map((item) => <li key={item}>• {item}</li>)}
                </ul>
              ) : (
                <p className="text-sm text-subtle">{t.emptyActivity}</p>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {addToJobOpen ? (
        <AddToJobDialog
          access={access}
          application={activeApplication}
          locale={locale}
          onAccessIssue={onAccessIssue}
          onClose={() => setAddToJobOpen(false)}
          onSuccess={(msg) => {
            setMessage(msg)
            onRefresh()
          }}
          positions={positions}
          personProfile={personProfile}
          related={related}
        />
      ) : null}

      {offerOpen && showOffer ? (
        <div className="fixed inset-0 z-[60] flex items-end justify-center bg-ink/30 p-3 backdrop-blur-[2px] sm:items-center" onClick={() => setOfferOpen(false)}>
          <div
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-[1.6rem] border border-white/70 bg-panel/95 p-5 shadow-[0_28px_90px_rgba(24,20,15,0.18)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-text">{t.offerTitle}</h2>
              <Button onClick={() => setOfferOpen(false)} size="sm" type="button" variant="ghost">{t.closeOffer}</Button>
            </div>
            <OfferPanel
              access={access}
              appKey={activeApplication.app_key}
              busy={busy}
              enabled={employmentOffersEnabled}
              onMessage={setMessage}
              onRefresh={onRefresh}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
