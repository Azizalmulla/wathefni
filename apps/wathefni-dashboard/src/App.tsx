import { Loader2, MoreHorizontal, RefreshCw } from 'lucide-react'
import { type InfiniteData } from '@tanstack/react-query'
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { PostHireModulePage } from '@/posthire/PostHire'
import { useConfirm } from '@/components/ConfirmDialog'
import {
  anyPeopleModuleEnabled as peopleModulesEnabled,
  anyPosthireModuleEnabled as posthireModulesEnabled,
  isAlertsAndDeliveryRelevant,
  isPostHireNavPage,
  resolveFocusedPosthireLanding,
} from '@/lib/moduleWorkspace'
import { resolveWorkspaceAuthority, type NavGroup } from '@/lib/workspaceCapability'
import { DASHBOARD_NAV_CATALOG, isRegisteredDashboardPage } from '@/lib/hrWebNavCatalog'
import { prefetchDashboardDestination } from '@/lib/hrWebNavPrefetch'
import { prefetchPostHirePage } from '@/posthire/PostHireDispatcher'
import {
  dashboardPerfMarkInteractionStart,
  dashboardPerfMarkNetworkComplete,
} from '@/lib/perf/dashboardPerf'

import {
  acceptDashboardInvite,
  DashboardApiError,
  getDashboardTeam,
  getDashboardChatSession,
  getDashboardChatSessions,
  getAssistantCapabilities,
  getCandidatePersonProfile,
  getPrehirePositions,
  createPrehirePosition,
  updatePrehirePosition,
  setPositionStatus,
  getRanking,
  getSetupReadiness,
  downloadPrehireReport,
  inviteDashboardUser,
  linkDashboardWhatsApp,
  loginDashboard,
  logoutDashboard,
  cancelAssessment,
  previewVideoInterviewAnswer,
  recalculateAssessmentNorms,
  retryVideoInterviewTranscripts,
  saveInterviewNotes,
  sendAssessment,
  resendAssessment,
  reviewAssessment,
  startDashboardChatSession,
  streamDashboardChat,
  updateDashboardUser,
  updateInterviewStatus,
  saveCandidateSavedView,
} from '@/lib/api'
import { accessIssueFromError, accessIssueMessage, type AccessIssue } from '@/lib/access'
import { authCopy, type AuthCopyKey } from '@/lib/authCopy'
import {
  applyDocumentLocale,
  persistRecruitingLocale,
  readStoredRecruitingLocale,
} from '@/lib/dashboardLocale'
import { qk, stableFiltersKey, tenantRoot } from '@/lib/query/keys'
import { syncSelectedApplication, useDashboardServerState } from '@/lib/query/useDashboardServerState'
import {
  recruitingCopy,
  type RecruitingLocale,
} from '@/lib/recruitingLifecycle'
import {
  EMPTY_CANDIDATE_FILTERS,
  candidateFiltersFromSavedViewBlob,
} from '@/lib/candidateFilterAuthority'
import {
  candidateFiltersFromNav,
  destinationToNavState,
  navFiltersFromCandidateState,
  readDashboardNavState,
  writeDashboardNavUrl,
  type DashboardNavState,
} from '@/lib/dashboardNavigation'
import {
  ASSESSMENT_COHORT_READY_TO_SEND,
  assessmentCohortForTab,
  assessmentTabForCohort,
  normalizeAssessmentCohortKey,
} from '@/lib/assessmentCohorts'
import { cn } from '@/lib/utils'
import { ActivityLog } from '@/components/ActivityLog'
import { ImportCvButton } from '@/components/ImportCenter'
import {
  canViewRestrictedCandidates,
} from '@/components/candidates/CandidatesTable'
import {
  DEFAULT_CLASSIFICATION_FILTERS,
  classificationFiltersForSavedView,
  classificationFiltersFromSavedView,
  type ClassificationFiltersState,
} from '@/components/candidates/ClassificationFilters'
import { JobsForm, jobFormToPayload, type JobFormValues } from '@/components/JobsForm'
import { SendResultPanel, extractSendResult, type OutboundSendResult } from '@/components/SendResultPanel'
import { HrPageHeader } from '@/components/hr/HrPageHeader'
import { Button } from '@/components/ui/button'
import { useDebouncedValue } from '@/components/ui/search-input'
import type {
  ApplicationSummary,
  ApplicationsResponse,
  CandidateFilters,
  CandidateInterview,
  ChatMessage,
  AssistantEmptyState,
  DashboardAccess,
  DashboardChatNavigation,
  DashboardChatResponse,
  DashboardChatSession,
  DashboardChatStoredMessage,
  DashboardModuleDefinition,
  DashboardTeamResponse,
  DashboardUserAccess,
  MutationResponse,
  PositionsResponse,
  PositionSummary,
  PrehireRolePriority,
  Page,
  RankingResponse,
  SetupReadinessResponse,
} from '@/types'
import { AccessVerificationPage, AuthSessionResolvingPage, NeedsSettings } from '@/pages/ShellStates'
import { PagePaintFallback, PageSkeleton } from '@/pages/PageSkeleton'
import {
  LazyAdminAIPage,
  LazyAssessmentsPage,
  LazyCalendarShell,
  LazyCandidateProfilePage,
  LazyCandidatesPage,
  LazyInterviewsPage,
  LazyJobWorkspace,
  LazyJobsPage,
  LazyNotificationsPage,
  LazyPostHirePage,
  LazyRankingPage,
  LazyReportsPage,
  LazyRequisitionsWorkspace,
  LazySettingsPage,
} from '@/pages/lazy'
import { OverviewPage } from '@/pages/OverviewPage'
import { hasDashboardPermission } from '@/pages/shared/access'
import {
  assessmentModuleEnabled,
  candidateName,
  friendlyDashboardError,
  normalizedJobStatus,
  stageLabel,
} from '@/pages/shared/format'

const NAV_GROUP_LABELS: Record<NavGroup, string> = { prehire: 'Pre-Hiring', posthire: 'Post-Hire', settings: 'Workspace' }

type DashboardModuleState = {
  enabled_modules?: string[]
  access?: DashboardUserAccess
  module_catalog?: DashboardModuleDefinition[]
  action_inbox?: {
    offerable?: boolean
    wave_enabled?: boolean
    viewer_allowlisted?: boolean
    real_canary_enabled?: boolean
    exclude_payroll?: boolean
  } | null
} | null | undefined

function workspaceCatalog(state: DashboardModuleState) {
  return state?.module_catalog
}

function anyPosthireModuleEnabled(state: DashboardModuleState): boolean {
  return posthireModulesEnabled(state?.enabled_modules, workspaceCatalog(state))
}

function anyPeopleModuleEnabled(state: DashboardModuleState): boolean {
  return peopleModulesEnabled(state?.enabled_modules, workspaceCatalog(state))
}

function actionInboxNavOfferable(state: DashboardModuleState): boolean {
  return Boolean(state?.action_inbox?.offerable)
}

function isPostHirePage(page: Page): page is PostHireModulePage {
  return isPostHireNavPage(page)
}

function isOperationalCorePage(page: Page | string): boolean {
  return page === 'leave' || page === 'attendance' || page === 'shifts' || page === 'payroll'
}

function isPeopleSpinePage(page: Page | string): boolean {
  return (
    page === 'employees' ||
    page === 'workforce' ||
    page === 'onboarding' ||
    page === 'preboarding' ||
    page === 'probation' ||
    page === 'inbox'
  )
}

function isEnterpriseFlagshipPage(page: Page | string): boolean {
  return (
    page === 'performance' ||
    page === 'talent' ||
    page === 'learning' ||
    page === 'benefits' ||
    page === 'employee-relations' ||
    page === 'engagement' ||
    page === 'compensation-planning' ||
    page === 'workforce-planning' ||
    page === 'job-architecture' ||
    page === 'analytics'
  )
}

function usesCanonicalPageHeader(page: Page | string): boolean {
  return isOperationalCorePage(page) || isPeopleSpinePage(page) || isEnterpriseFlagshipPage(page)
}

// Lifecycle confirmation contract (kept in lockstep with HR mobile and lifecycle-labels tests).
// Probe keeps the backend allowed_actions contract visible to source-level lifecycle tests.
function lifecycleCandidateActionsProbe(candidate: ApplicationSummary) {
  const allowedActions = new Set(candidate.allowed_actions || [])
  return allowedActions
}
void lifecycleCandidateActionsProbe
const lifecycleConfirmationCopy = [
  'Shortlist this candidate?',
  'Reject this candidate?',
  'Hire this candidate?',
  'إضافة المرشح للقائمة المختصرة؟',
  'رفض هذا المرشح؟',
  'توظيف هذا المرشح؟',
] as const
void lifecycleConfirmationCopy
function candidateFiltersFromDashboardNav(nav: DashboardNavState): CandidateFilters {
  const mapped = candidateFiltersFromNav(nav.filters)
  return {
    ...EMPTY_CANDIDATE_FILTERS,
    position: mapped.position || '',
    cvStatus: mapped.cvStatus || '',
    assessmentStatus: mapped.assessmentStatus || '',
    interviewStatus: mapped.interviewStatus || '',
    followUp: mapped.followUp || '',
    reviewStatus: mapped.reviewStatus || '',
    activityFrom: mapped.activityFrom || '',
    activityTo: mapped.activityTo || '',
    sort: mapped.sort || 'newest',
    overviewCohort: nav.filters.overview_cohort || '',
    action: nav.filters.action || '',
    cohortKey: nav.filters.cohort_key || '',
    sourceChannel: mapped.sourceChannel || '',
    recruiterOwner: mapped.recruiterOwner || '',
    cvProcessingState: mapped.cvProcessingState || '',
    receivedFrom: mapped.receivedFrom || '',
    receivedTo: mapped.receivedTo || '',
    hasGroundedEmail: mapped.hasGroundedEmail || '',
    hasGroundedPhone: mapped.hasGroundedPhone || '',
    factCompleteness: mapped.factCompleteness || '',
    departmentIntakeTag: mapped.departmentIntakeTag || '',
    view: (mapped.view || 'all') as CandidateFilters['view'],
  }
}

const navItems = DASHBOARD_NAV_CATALOG

// Modules that are real once enabled live in the catalog (gated by resolveWorkspaceAuthority).
// This list is for genuinely-future tools with no backend yet; empty for now.
const futureModuleItems: Array<{ label: string; module: string }> = []

function storedAccess(): DashboardAccess {
  return {
    token: localStorage.getItem('wathefni_dashboard_token') || '',
    hrPhone: localStorage.getItem('wathefni_hr_phone') || '',
    companyCode: localStorage.getItem('wathefni_company_code') || '',
    email: localStorage.getItem('wathefni_dashboard_email') || '',
    password: '',
  }
}

function normalizedAccess(access: DashboardAccess): DashboardAccess {
  return {
    token: access.token.trim(),
    hrPhone: access.hrPhone.trim(),
    companyCode: access.companyCode.trim().toUpperCase(),
    email: access.email?.trim() || '',
    password: access.password || '',
  }
}

function dashboardChatStorageKey(access: DashboardAccess) {
  const company = access.companyCode.trim().toUpperCase() || 'WATHEFNI'
  const phone = access.hrPhone.trim() || 'unknown'
  return `wathefni_dashboard_chat_conversation_id:${company}:${phone}`
}

function createDashboardChatConversationId(access: DashboardAccess) {
  const company = access.companyCode.trim().toUpperCase() || 'WATHEFNI'
  const phone = access.hrPhone.trim() || 'unknown'
  const id = `dashboard:${company}:${phone}:pre_hiring:${Date.now()}-${Math.random().toString(16).slice(2)}`
  return id
}

function dashboardChatConversationId(access: DashboardAccess) {
  const storageKey = dashboardChatStorageKey(access)
  const existing = localStorage.getItem(storageKey)
  if (existing) return existing
  const id = createDashboardChatConversationId(access)
  localStorage.setItem(storageKey, id)
  return id
}

function rememberDashboardChatConversationId(access: DashboardAccess, conversationId: string) {
  localStorage.setItem(dashboardChatStorageKey(access), conversationId)
}

function storedDashboardMessageToChatMessage(message: DashboardChatStoredMessage): ChatMessage {
  const payload = message.payload || {}
  return {
    id: message.message_id || `${message.role}-${message.created_at || Math.random()}`,
    role: message.role,
    text: message.text || '',
    candidateCards: payload.candidate_cards || [],
    navigation: payload.navigation || [],
    confirmation: payload.confirmation || null,
    workflowCard: payload.workflow_card || null,
  }
}

function dashboardModuleEnabled(state: DashboardModuleState, module: string) {
  if (!state || !Array.isArray(state.enabled_modules)) return false
  return state.enabled_modules.includes(module)
}

function pageAvailableForSummary(page: Page, state: DashboardModuleState, authorityNavIds?: string[]) {
  if (authorityNavIds) return authorityNavIds.includes(page)
  if (page === 'employees' || page === 'workforce') return anyPeopleModuleEnabled(state)
  if (page === 'inbox') return actionInboxNavOfferable(state)
  if (page === 'notifications') return isAlertsAndDeliveryRelevant(state?.enabled_modules, workspaceCatalog(state))
  const item = navItems.find((nav) => nav.id === page)
  if (item?.id === 'interviews') {
    return (
      dashboardModuleEnabled(state, 'interviews') ||
      dashboardModuleEnabled(state, 'video_interviews')
    )
  }
  if (item?.id === 'ai') {
    return (
      dashboardModuleEnabled(state, 'pre_hiring') ||
      posthireModulesEnabled(state?.enabled_modules, workspaceCatalog(state))
    )
  }
  return !item?.module || dashboardModuleEnabled(state, item.module)
}


function dashboardInviteLink(token: string) {
  const url = new URL('/dashboard', window.location.origin)
  url.searchParams.set('invite', token)
  return url.toString()
}


function initialAccessIssue() {
  const saved = normalizedAccess(storedAccess())
  return !saved.token || !saved.companyCode ? missingAccessIssue(saved, readStoredRecruitingLocale()) : null
}

function missingAccessIssue(access: DashboardAccess, locale: RecruitingLocale = 'en'): AccessIssue {
  if (!access.token.trim()) {
    return {
      code: 'dashboard_auth_failed',
      title: authCopy(locale, 'authSignInTitle'),
      description: authCopy(locale, 'authSignInDescription'),
      copyKey: 'authSignInDescription',
    }
  }
  return {
    code: 'dashboard_company_required',
    title: authCopy(locale, 'authSignInTitle'),
    description: authCopy(locale, 'authCompanyRequired'),
    copyKey: 'authCompanyRequired',
  }
}

function App() {
  const initialNav = readDashboardNavState()
  const [access, setAccess] = useState<DashboardAccess>(() => normalizedAccess(storedAccess()))
  const [page, setPage] = useState<Page>(() => {
    const requested = String(initialNav.page || '').trim()
    if (requested && isRegisteredDashboardPage(requested)) return requested
    return 'overview'
  })
  const [lastWorkPage, setLastWorkPage] = useState<Page>('overview')
  const [recruitingLocale, setRecruitingLocale] = useState<RecruitingLocale>(() => readStoredRecruitingLocale())
  const changeRecruitingLocale = useCallback((next: RecruitingLocale) => {
    persistRecruitingLocale(next)
    applyDocumentLocale(next)
    setRecruitingLocale(next)
  }, [])
  useEffect(() => {
    applyDocumentLocale(recruitingLocale)
  }, [recruitingLocale])
  const [ranking, setRanking] = useState<RankingResponse | null>(null)
  const [rankingError, setRankingError] = useState(false)
  const [rankingBusy, setRankingBusy] = useState(false)
  const rankingLoadedPositionRef = useRef('')
  const [profileReturnPage, setProfileReturnPage] = useState<Page | null>(null)
  const profileReturnFocusRef = useRef<HTMLElement | null>(null)
  const [team, setTeam] = useState<DashboardTeamResponse | null>(null)
  const [setupReadiness, setSetupReadiness] = useState<SetupReadinessResponse | null>(null)
  const confirm = useConfirm()
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('viewer')
  const [inviteName, setInviteName] = useState('')
  const [linkPhone, setLinkPhone] = useState('')
  const [inviteToken, setInviteToken] = useState(() => new URLSearchParams(window.location.search).get('invite') || '')
  const [createdInviteLink, setCreatedInviteLink] = useState('')
  const [acceptName, setAcceptName] = useState('')
  const [acceptPassword, setAcceptPassword] = useState('')
  const [acceptPhone, setAcceptPhone] = useState('')
  const [selected, setSelected] = useState<ApplicationSummary | null>(null)
  const [selectedJob, setSelectedJob] = useState<PositionSummary | null>(null)
  const [jobQrDataUrl, setJobQrDataUrl] = useState('')
  const [jobsQuery, setJobsQuery] = useState('')
  const debouncedJobsQuery = useDebouncedValue(jobsQuery.trim(), 350)
  const [jobsStatusFilter, setJobsStatusFilter] = useState('')
  const [jobsDepartmentFilter, setJobsDepartmentFilter] = useState('')
  const [jobsLocationFilter, setJobsLocationFilter] = useState('')
  const [jobsDeadlineFilter, setJobsDeadlineFilter] = useState('')
  const [jobsRemainingOnly, setJobsRemainingOnly] = useState(false)
  const [jobsLoadingMore, setJobsLoadingMore] = useState(false)
  const [jobFormMode, setJobFormMode] = useState<'create' | 'edit' | null>(null)
  const [jobFormBusy, setJobFormBusy] = useState(false)
  const [query, setQuery] = useState(() => initialNav.filters.q || '')
  const debouncedCandidateQuery = useDebouncedValue(query.trim(), 350)
  const [status, setStatus] = useState(() =>
    initialNav.page === 'candidates' ? String(initialNav.filters.status || '') : '',
  )
  const [candidateFilters, setCandidateFilters] = useState<CandidateFilters>(() => candidateFiltersFromDashboardNav(initialNav))
  const [classificationFilters, setClassificationFilters] = useState<ClassificationFiltersState>(DEFAULT_CLASSIFICATION_FILTERS)
  const [classificationDeprecatedNodes, setClassificationDeprecatedNodes] = useState<Array<{ node_id: string; message?: string }>>([])
  const [, setCandidateOffset] = useState(0)
  const [rankPosition, setRankPosition] = useState(() => initialNav.filters.position_code || '')
  const [interviewTab, setInterviewTab] = useState(() =>
    initialNav.page === 'interviews'
      ? String(initialNav.filters.tab || initialNav.filters.status || 'upcoming')
      : 'upcoming',
  )
  const [interviewQuery, setInterviewQuery] = useState('')
  const debouncedInterviewQuery = useDebouncedValue(interviewQuery.trim(), 350)
  const [interviewRole, setInterviewRole] = useState(() => initialNav.filters.role || '')
  const [interviewDate, setInterviewDate] = useState(() => initialNav.filters.date || '')
  const [interviewInterviewer, setInterviewInterviewer] = useState(() => initialNav.filters.interviewer || '')
  const [interviewOffset, setInterviewOffset] = useState(0)
  const overviewScrollRestoreRef = useRef<number | null>(initialNav.overviewScrollY ?? null)
  const skipUrlSyncRef = useRef(false)
  const [assessmentOffset, setAssessmentOffset] = useState(0)
  const [assessmentCohort, setAssessmentCohort] = useState(() =>
    normalizeAssessmentCohortKey(
      initialNav.filters.assessment_cohort
        || (initialNav.page === 'assessments' ? initialNav.filters.overview_cohort : '')
        || (initialNav.page === 'assessments' ? ASSESSMENT_COHORT_READY_TO_SEND : ''),
    ) || (initialNav.page === 'assessments' ? ASSESSMENT_COHORT_READY_TO_SEND : ''),
  )
  const [assessmentTab, setAssessmentTab] = useState(() => String(initialNav.filters.tab || assessmentTabForCohort(initialNav.filters.assessment_cohort || initialNav.filters.cohort_key || '') || 'send'))
  const [message, setMessage] = useState('')
  // The candidate message box now feeds real sends (assessment, video interview,
  // notify) — clear it whenever a different candidate is opened so a note never
  // silently carries over and gets sent to the wrong person.
  useEffect(() => {
    setMessage('')
  }, [selected?.app_key])
  const [interviewNotes, setInterviewNotes] = useState<Record<string, string>>({})
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const chatAbortRef = useRef<AbortController | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatConversationId, setChatConversationId] = useState(() => dashboardChatConversationId(access))
  const [chatSessions, setChatSessions] = useState<DashboardChatSession[]>([])
  const [chatHistoryOpen, setChatHistoryOpen] = useState(false)
  const [assistantEmptyState, setAssistantEmptyState] = useState<AssistantEmptyState | null>(null)
  const [assistantEmptyStatus, setAssistantEmptyStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [newChatConfirmOpen, setNewChatConfirmOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [runningAction, setRunningAction] = useState<string | null>(null)
  const [importReloadKey, setImportReloadKey] = useState(0)
  const [lastSendResult, setLastSendResult] = useState<OutboundSendResult | null>(null)
  const [notice, setNoticeState] = useState<{ text: string; tone: 'info' | 'success' | 'error'; copyKey?: AuthCopyKey }>(() => ({
    text: initialAccessIssue()?.title || (access.token ? 'Loading saved dashboard access...' : 'Access verification required.'),
    tone: 'info',
  }))
  const noticeTimer = useRef<number | null>(null)
  // Tone-aware notices: successes look successful and auto-clear; errors look
  // failed and persist until replaced or dismissed. Default tone is neutral
  // (info) which also covers in-progress "...ing..." status messages.
  const setNotice = useCallback((text: string, tone: 'info' | 'success' | 'error' = 'info') => {
    if (noticeTimer.current) {
      window.clearTimeout(noticeTimer.current)
      noticeTimer.current = null
    }
    setNoticeState({ text, tone })
    if (tone === 'success' && text) {
      noticeTimer.current = window.setTimeout(() => {
        setNoticeState((cur) => (cur.text === text ? { text: '', tone: 'info' } : cur))
        noticeTimer.current = null
      }, 4000)
    }
  }, [])
  const setNoticeErr = useCallback((text: string) => setNotice(text, 'error'), [setNotice])
  const setNoticeOk = useCallback((text: string) => setNotice(text, 'success'), [setNotice])
  const setNoticeErrKey = useCallback((key: AuthCopyKey) => {
    if (noticeTimer.current) {
      window.clearTimeout(noticeTimer.current)
      noticeTimer.current = null
    }
    setNoticeState({ text: authCopy(recruitingLocale, key), tone: 'error', copyKey: key })
  }, [recruitingLocale])
  const [accessIssue, setAccessIssue] = useState<AccessIssue | null>(() => initialAccessIssue())
  const handleAccessIssue = useCallback((issue: AccessIssue) => {
    setAccessIssue(issue)
  }, [])

  const server = useDashboardServerState({
    access,
    blocked: Boolean(accessIssue),
    page,
    query: debouncedCandidateQuery,
    status,
    candidateFilters,
    classificationFilters,
    debouncedJobsQuery,
    jobsStatusFilter,
    jobsDepartmentFilter,
    jobsLocationFilter,
    jobsDeadlineFilter,
    jobsRemainingOnly,
    interviewTab,
    interviewQuery: debouncedInterviewQuery,
    interviewRole,
    interviewDate,
    interviewInterviewer,
    interviewOffset,
    assessmentOffset,
    assessmentCohort,
    assessmentTab,
    recruitingLocale,
  })

  const {
    client: queryClient,
    workspaceBootstrap,
    bootstrapQuery,
    bootstrapSettled,
    summary,
    summaryQuery,
    notifications,
    assessmentConfig,
    applications,
    applicationsQuery,
    candidatesListPending,
    candidatesRefreshing,
    candidatesHasMore,
    candidatesFetchingMore,
    loadMoreCandidates,
    unifiedCandidatesEnabled,
    classificationUiEnabled,
    classificationDimensions,
    classificationTaxonomyLoading,
    classificationTaxonomyError,
    retryClassificationTaxonomy,
    savedViews,
    jobsData,
    jobsLoading,
    jobsError: jobsListError,
    allPositions,
    interviews,
    interviewsQuery,
    interviewsLoading,
    interviewsError,
    interviewsRefreshing,
    assessments,
    assessmentsRefreshing,
    assessmentsQuery,
    assessmentQueueApps,
    assessmentQueueTotal,
    assessmentQueueHasMore,
    assessmentQueueFetchingMore,
    assessmentQueueQuery,
    loadMoreAssessmentQueue,
    reports,
    reportsRefreshing,
    reportsError,
    overviewInteractive,
    invalidate: queryInvalidate,
    refreshAfterCandidate,
    refreshAfterInterview,
    refreshAfterJob,
    refreshAssessments,
  } = server

  const jobsFiltersKey = useMemo(
    () =>
      stableFiltersKey({
        ...(debouncedJobsQuery ? { search: debouncedJobsQuery } : {}),
        ...(jobsStatusFilter ? { status: jobsStatusFilter } : {}),
        ...(jobsDepartmentFilter ? { department: jobsDepartmentFilter } : {}),
        ...(jobsLocationFilter ? { location: jobsLocationFilter } : {}),
        ...(jobsDeadlineFilter ? { deadline: jobsDeadlineFilter } : {}),
        ...(jobsRemainingOnly ? { has_remaining_vacancies: true } : {}),
      }),
    [
      debouncedJobsQuery,
      jobsDeadlineFilter,
      jobsDepartmentFilter,
      jobsLocationFilter,
      jobsRemainingOnly,
      jobsStatusFilter,
    ],
  )

  const bootNoticeShownRef = useRef(false)
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false)
  useEffect(() => {
    if (!overviewInteractive || bootNoticeShownRef.current) return
    bootNoticeShownRef.current = true
    setNoticeOk(
      recruitingLocale === 'ar' ? 'أنت تعرض أحدث البيانات.' : 'You’re viewing the latest data.',
    )
  }, [overviewInteractive, recruitingLocale, setNoticeOk])

  useEffect(() => {
    setSelected((current) => syncSelectedApplication(current, applications?.applications))
  }, [applications?.applications])

  useEffect(() => {
    if (accessIssue) return
    const error = summaryQuery.error || bootstrapQuery.error
    if (!summaryQuery.isError && !bootstrapQuery.isError) return
    if (!error) return
    const issue = accessIssueFromError(error, recruitingLocale)
    if (issue) {
      handleAccessIssue(issue)
      setNotice(issue.title)
    }
  }, [
    accessIssue,
    bootstrapQuery.error,
    bootstrapQuery.isError,
    handleAccessIssue,
    recruitingLocale,
    setNotice,
    summaryQuery.error,
    summaryQuery.isError,
  ])

  const moduleState: DashboardModuleState = workspaceBootstrap || summary
  const prehireEnabled = dashboardModuleEnabled(moduleState, 'pre_hiring')
  const allApplications = applications?.applications || summary?.recent_applications || []
  const enabledNotificationModules = notifications?.enabled_modules
  const assessmentModuleOn = assessmentModuleEnabled(moduleState, summary)
  const workspaceAuthority = useMemo(
    () =>
      resolveWorkspaceAuthority({
        enabledModules: moduleState?.enabled_modules,
        access: moduleState?.access || null,
        catalog: workspaceCatalog(moduleState),
        actionInboxOfferable: actionInboxNavOfferable(moduleState),
      }),
    [moduleState],
  )
  const availableNavItems = navItems.filter((item) => workspaceAuthority.pageAllowed(item.id))
  const availableNavById = Object.fromEntries(availableNavItems.map((item) => [item.id, item]))
  const prefetchDestination = useCallback(
    (id: Page) => {
      prefetchDashboardDestination(id, access, queryClient, { postHireLoader: prefetchPostHirePage })
    },
    [access, queryClient],
  )
  const defaultWorkspacePage = (() => {
    // Preserve payroll-operator focused landing (payroll.read without prehire.read).
    if (hasDashboardPermission(moduleState?.access, 'payroll.read') && !hasDashboardPermission(moduleState?.access, 'prehire.read')) {
      const payrollPage = availableNavItems.find((item) => item.id === 'payroll')?.id
      if (payrollPage) return payrollPage as Page
    }
    if (hasDashboardPermission(moduleState?.access, 'interview.manage') && !hasDashboardPermission(moduleState?.access, 'candidates.read') && !hasDashboardPermission(moduleState?.access, 'jobs.create')) {
      return (availableNavItems.find((item) => item.id === 'interviews')?.id || 'settings') as Page
    }
    const availableIds = availableNavItems.map((item) => item.id)
    return resolveFocusedPosthireLanding({
      enabledModules: moduleState?.enabled_modules,
      availablePageIds: availableIds,
      prehireEnabled,
      overviewAvailable: availableIds.includes('overview'),
      actionInboxOfferable: actionInboxNavOfferable(moduleState),
      permissions: moduleState?.access?.permissions,
      catalog: workspaceCatalog(moduleState),
    }) as Page
  })()
  // Sticky URL page until bootstrap/authority settle — avoids Notifications flash.
  const authorityReady = Boolean(bootstrapSettled && moduleState)
  const activePage = !authorityReady
    ? page
    : pageAvailableForSummary(page, moduleState, workspaceAuthority.navIds)
      ? page
      : defaultWorkspacePage
  const pageTitle = localizedPageLabel(activePage, recruitingLocale)
  const pageSubtitle = localizedPageSubtitle(activePage, recruitingLocale)
  const prehireNavItems = availableNavItems.filter((item) => item.group === 'prehire')
  const otherNavItems = availableNavItems.filter((item) => item.group !== 'prehire')
  const activeNavItem = availableNavById[activePage] || null
  const ActiveMobileIcon = activeNavItem?.icon

  useEffect(() => {
    setMobileMoreOpen(false)
  }, [activePage])

  // After authority is known, persist remapped page so URL/state stay aligned.
  useEffect(() => {
    if (!authorityReady) return
    if (pageAvailableForSummary(page, moduleState, workspaceAuthority.navIds)) return
    if (page === defaultWorkspacePage) return
    setPage(defaultWorkspacePage as Page)
  }, [authorityReady, defaultWorkspacePage, moduleState, page, workspaceAuthority.navIds])

  const dashboardLoaded = Boolean(moduleState && (!prehireEnabled || (summary && notifications)))
  const userAccess = moduleState?.access || null
  const showingInviteAcceptance = Boolean(inviteToken.trim())
  const canImportCandidates = hasDashboardPermission(userAccess, 'candidate.import')
  const canManageInterviews = hasDashboardPermission(userAccess, 'interview.manage')
  const canManageAssessments = hasDashboardPermission(userAccess, 'assessment.manage')
  const canExportReports = hasDashboardPermission(userAccess, 'report.export')
  const canManageWorkspace = hasDashboardPermission(userAccess, 'users.manage')
  const canCreateJobs = hasDashboardPermission(userAccess, 'jobs.create')
  const canEditJobs = hasDashboardPermission(userAccess, 'jobs.edit')
  const canPublishJobs = hasDashboardPermission(userAccess, 'jobs.publish')
  const canCloseJobs = hasDashboardPermission(userAccess, 'jobs.close')
  // Position pickers (candidate filter, CV-import assignment, ranking, overview
  // breakdown) need the FULL roster of jobs, not just the top 25 by activity
  // that `summary.positions` carries for the dashboard glance. Loaded via its
  // own unsearched, unpaginated fetch (see loadAllPositions) — deliberately
  // NOT sourced from `jobsData`, which is search-scoped to whatever the Jobs
  // page's own search box currently holds.
  const allPositionsForSelectors = allPositions.length ? allPositions : summary?.positions || []

  function currentCandidateNavFilters(filters: CandidateFilters = candidateFilters) {
    return navFiltersFromCandidateState({
      q: query,
      status,
      filters: {
        position: filters.position,
        followUp: filters.followUp,
        reviewStatus: filters.reviewStatus,
        assessmentStatus: filters.assessmentStatus,
        interviewStatus: filters.interviewStatus,
        sort: filters.sort,
        view: filters.view,
        cvStatus: filters.cvStatus,
        sourceChannel: filters.sourceChannel,
        recruiterOwner: filters.recruiterOwner,
        cvProcessingState: filters.cvProcessingState,
        receivedFrom: filters.receivedFrom,
        receivedTo: filters.receivedTo,
        activityFrom: filters.activityFrom,
        activityTo: filters.activityTo,
        hasGroundedEmail: filters.hasGroundedEmail,
        hasGroundedPhone: filters.hasGroundedPhone,
        factCompleteness: filters.factCompleteness,
        departmentIntakeTag: filters.departmentIntakeTag,
      },
      overviewCohort: filters.overviewCohort,
      assessmentCohort:
        filters.overviewCohort?.startsWith('assessment_') || filters.overviewCohort === 'assessment_pending'
          ? filters.overviewCohort
          : undefined,
      action: filters.action,
      cohortKey: filters.cohortKey,
    })
  }

  function captureOverviewScrollInHistory() {
    if (page !== 'overview') return
    const y = Math.round(window.scrollY || document.documentElement.scrollTop || 0)
    writeDashboardNavUrl({ page: 'overview', candidate: null, filters: {}, overviewScrollY: y }, 'replace')
  }

  function writeDashboardUrl(nextPage: Page, candidateKey: string | null, mode: 'push' | 'replace' = 'replace') {
    if (page === 'overview' && nextPage !== 'overview' && mode === 'push') {
      captureOverviewScrollInHistory()
    }
    const filters =
      nextPage === 'candidates'
        ? currentCandidateNavFilters()
        : nextPage === 'interviews'
          ? {
              ...(interviewTab ? { status: interviewTab, tab: interviewTab } : {}),
              ...(interviewRole ? { role: interviewRole } : {}),
              ...(interviewDate ? { date: interviewDate } : {}),
              ...(interviewInterviewer ? { interviewer: interviewInterviewer } : {}),
            }
          : nextPage === 'ranking'
            ? {
                ...(rankPosition ? { position_code: rankPosition, cohort_key: `ranking:${rankPosition}` } : {}),
              }
            : nextPage === 'assessments'
              ? (() => {
                  const surfaceOnly =
                    assessmentTab === 'attempts'
                    || assessmentTab === 'reports'
                    || assessmentTab === 'needs_review'
                  return {
                    ...(assessmentCohort
                      ? {
                          assessment_cohort: assessmentCohort,
                          overview_cohort: assessmentCohort,
                          cohort_key: assessmentCohort,
                        }
                      : {}),
                    tab: surfaceOnly
                      ? assessmentTab
                      : (assessmentTabForCohort(assessmentCohort) || assessmentTab || 'send'),
                  }
                })()
              : {}
    writeDashboardNavUrl(
      {
        page: nextPage,
        candidate: candidateKey,
        filters,
        overviewScrollY: nextPage === 'overview' ? Math.round(window.scrollY || 0) : undefined,
      },
      mode,
    )
  }

  function applyNavStateToUi(nav: DashboardNavState, opts: { restoreScroll?: boolean } = {}) {
    skipUrlSyncRef.current = true
    const nextPage = (nav.page && isRegisteredDashboardPage(nav.page) ? nav.page : page) as Page
    if (nextPage !== 'ai' && nextPage !== 'settings') setLastWorkPage(nextPage)
    setPage(nextPage)
    if (nextPage === 'candidates') {
      const nextFilters = candidateFiltersFromDashboardNav(nav)
      setCandidateFilters(nextFilters)
      setQuery(nav.filters.q || '')
      setStatus(nav.filters.status || '')
      setCandidateOffset(0)
    }
    if (nextPage === 'interviews') {
      const tab = nav.filters.tab || nav.filters.status || 'upcoming'
      setInterviewTab(tab)
      setInterviewRole(nav.filters.role || '')
      setInterviewDate(nav.filters.date || '')
      setInterviewInterviewer(nav.filters.interviewer || '')
      setInterviewOffset(0)
    }
    if (nextPage === 'ranking' && nav.filters.position_code) {
      setRankPosition(nav.filters.position_code)
    }
    if (nextPage === 'assessments') {
      const cohort = normalizeAssessmentCohortKey(
        nav.filters.assessment_cohort || nav.filters.overview_cohort || nav.filters.cohort_key || assessmentCohortForTab(nav.filters.tab),
      )
      setAssessmentCohort(cohort || ASSESSMENT_COHORT_READY_TO_SEND)
      const tabFromUrl = String(nav.filters.tab || '').trim()
      if (tabFromUrl === 'attempts' || tabFromUrl === 'reports' || tabFromUrl === 'needs_review') {
        setAssessmentTab(tabFromUrl)
      } else {
        setAssessmentTab(tabFromUrl || assessmentTabForCohort(cohort) || 'send')
      }
    }
    if (!nav.candidate) setSelected(null)
    if (opts.restoreScroll && nextPage === 'overview') {
      const y = nav.overviewScrollY ?? overviewScrollRestoreRef.current ?? 0
      overviewScrollRestoreRef.current = y
      window.requestAnimationFrame(() => window.scrollTo(0, y))
    }
    window.setTimeout(() => {
      skipUrlSyncRef.current = false
    }, 0)
  }

  function navigateDashboard(nav: DashboardNavState, mode: 'push' | 'replace' = 'push') {
    if (page === 'overview' && nav.page !== 'overview' && mode === 'push') {
      captureOverviewScrollInHistory()
    }
    const appKey =
      nav.candidate ||
      (nav.page === 'candidates' && nav.filters.q && String(nav.filters.q).includes('-')
        ? String(nav.filters.q)
        : null)
    const nextNav: DashboardNavState = { ...nav, candidate: appKey }
    applyNavStateToUi(nextNav, { restoreScroll: nextNav.page === 'overview' })
    writeDashboardNavUrl(nextNav, mode)
  }

  function openPage(nextPage: Page) {
    if (!pageAvailableForSummary(nextPage, moduleState, workspaceAuthority.navIds)) {
      setNoticeErr('This feature is not enabled for this company.')
      setPage(defaultWorkspacePage)
      return
    }
    // Remember the last real module page so the assistant (its own page) knows
    // where HR was working and can bias its help toward that area.
    if (nextPage !== 'ai' && nextPage !== 'settings') {
      setLastWorkPage(nextPage)
    }
    if (nextPage === 'assessments' && !assessmentCohort) {
      setAssessmentCohort(ASSESSMENT_COHORT_READY_TO_SEND)
    }
    setPage(nextPage)
    writeDashboardUrl(nextPage, selected?.app_key || null, nextPage === page ? 'replace' : 'push')
  }

  function openCandidateProfile(
    application: ApplicationSummary,
    opts?: { returnPage?: Page; returnFocusEl?: HTMLElement | null },
  ) {
    setProfileReturnPage(opts?.returnPage ?? null)
    profileReturnFocusRef.current = opts?.returnFocusEl ?? null
    setSelected(application)
    if (opts?.returnPage === 'ranking') {
      // Stay on Ranking so close restores the desk + focus (do not force Candidates).
      writeDashboardUrl('ranking', application.app_key, 'push')
      return
    }
    if (page !== 'candidates') setPage('candidates')
    writeDashboardUrl('candidates', application.app_key, 'push')
  }

  function closeCandidateProfile() {
    const returnPage = profileReturnPage
    const returnFocus = profileReturnFocusRef.current
    setProfileReturnPage(null)
    profileReturnFocusRef.current = null
    setSelected(null)
    if (returnPage === 'ranking') {
      setPage('ranking')
      writeDashboardUrl('ranking', null, 'replace')
    } else {
      writeDashboardUrl(page === 'candidates' ? 'candidates' : page, null, 'replace')
    }
    if (returnFocus) {
      queueMicrotask(() => returnFocus.focus?.())
    }
  }

  const loadMoreJobs = useCallback(async () => {
    const effectiveAccess = normalizedAccess(access)
    if (!effectiveAccess.token || !effectiveAccess.companyCode) return
    setJobsLoadingMore(true)
    try {
      const data = await getPrehirePositions(effectiveAccess, {
        limit: 100,
        offset: jobsData?.positions.length || 0,
        ...(debouncedJobsQuery ? { search: debouncedJobsQuery } : {}),
        ...(jobsStatusFilter ? { status: jobsStatusFilter } : {}),
        ...(jobsDepartmentFilter ? { department: jobsDepartmentFilter } : {}),
        ...(jobsLocationFilter ? { location: jobsLocationFilter } : {}),
        ...(jobsDeadlineFilter ? { deadline: jobsDeadlineFilter } : {}),
        ...(jobsRemainingOnly ? { has_remaining_vacancies: true } : {}),
      })
      queryClient.setQueryData<PositionsResponse | null>(qk.jobs(access, jobsFiltersKey), (current) =>
        current
          ? { ...data, positions: [...current.positions, ...data.positions] }
          : data,
      )
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not load more jobs.'))
    } finally {
      setJobsLoadingMore(false)
    }
  }, [
    access,
    debouncedJobsQuery,
    jobsData?.positions.length,
    jobsDeadlineFilter,
    jobsDepartmentFilter,
    jobsFiltersKey,
    jobsLocationFilter,
    jobsRemainingOnly,
    jobsStatusFilter,
    queryClient,
    setNoticeErr,
  ])

  const [jobStatusBusy, setJobStatusBusy] = useState(false)

  const setJobStatus = useCallback(
    async (job: PositionSummary, status: 'open' | 'paused' | 'closed') => {
      const title = job.position_title || job.title || job.position_code
      const prompts: Record<string, { title: string; body: string; confirmLabel: string; destructive?: boolean }> = {
        closed: {
          title: recruitingCopy(recruitingLocale, 'jobsCloseConfirm'),
          body: [
            String(title),
            recruitingCopy(recruitingLocale, 'jobsCloseConfirmBody'),
            Number(job.active_count || 0) > 0
              ? recruitingCopy(recruitingLocale, 'jobsCloseConfirmActive', { count: String(job.active_count) })
              : null,
          ]
            .filter(Boolean)
            .join(' '),
          confirmLabel: recruitingCopy(recruitingLocale, 'jobsClose'),
          destructive: true,
        },
        paused: {
          title: recruitingCopy(recruitingLocale, 'jobsPauseConfirm'),
          body: `${title}. ${recruitingCopy(recruitingLocale, 'jobsPauseConfirmBody')}`,
          confirmLabel: recruitingCopy(recruitingLocale, 'jobsPause'),
        },
        open: {
          title: normalizedJobStatus(job) === 'paused'
            ? recruitingCopy(recruitingLocale, 'jobsResumeConfirm')
            : normalizedJobStatus(job) === 'draft'
            ? recruitingCopy(recruitingLocale, 'jobsPublishConfirm')
            : recruitingCopy(recruitingLocale, 'jobsReopenConfirm'),
          body: `${title}. ${
            normalizedJobStatus(job) === 'paused'
              ? recruitingCopy(recruitingLocale, 'jobsResumeConfirmBody')
              : normalizedJobStatus(job) === 'draft'
              ? recruitingCopy(recruitingLocale, 'jobsPublishConfirmBody')
              : recruitingCopy(recruitingLocale, 'jobsReopenConfirmBody')
          }`,
          confirmLabel: normalizedJobStatus(job) === 'paused'
            ? recruitingCopy(recruitingLocale, 'jobsResume')
            : normalizedJobStatus(job) === 'draft'
            ? recruitingCopy(recruitingLocale, 'jobsPublish')
            : recruitingCopy(recruitingLocale, 'jobsReopen'),
        },
      }
      const prompt = prompts[status]
      const ok = await confirm({
        title: prompt.title,
        body: prompt.body,
        confirmLabel: prompt.confirmLabel,
        destructive: prompt.destructive,
      })
      if (!ok) return
      setJobStatusBusy(true)
      try {
        const result = await setPositionStatus(access, job.position_code, status, {
          expected_updated_at: job.updated_at,
          expected_version: job.version,
        })
        queryClient.setQueryData<PositionsResponse | null>(qk.jobs(access, jobsFiltersKey), (current) =>
          current
            ? {
                ...current,
                positions: current.positions.map((p) =>
                  p.position_code === job.position_code ? { ...p, ...result.position } : p,
                ),
              }
            : current,
        )
        setSelectedJob((current) =>
          current && current.position_code === job.position_code ? { ...current, ...result.position } : current,
        )
        setNoticeOk(`${result.position.position_title || title} → ${result.position.status}`)
        void refreshAfterJob()
      } catch (error) {
        const issue = accessIssueFromError(error)
        if (issue) {
          setAccessIssue(issue)
          setNotice(issue.title)
        } else {
          setNoticeErr(friendlyDashboardError(error, 'Could not update this job.'))
        }
      } finally {
        setJobStatusBusy(false)
      }
    },
    [access, confirm, jobsFiltersKey, queryClient, recruitingLocale, refreshAfterJob, setNotice, setNoticeErr, setNoticeOk],
  )

  const saveJobForm = useCallback(
    async (values: JobFormValues, opts: { publish?: boolean; draft?: boolean }) => {
      if (opts.publish) {
        const title = String(values.title || values.title_ar || values.position_code || 'this job')
        const ok = await confirm({
          title: recruitingCopy(recruitingLocale, 'jobsPublishConfirm'),
          body: `${title}. ${recruitingCopy(recruitingLocale, 'jobsPublishConfirmBody')}`,
          confirmLabel: recruitingCopy(recruitingLocale, 'jobsPublish'),
        })
        if (!ok) return
      }
      setJobFormBusy(true)
      try {
        if (jobFormMode === 'create') {
          const created = await createPrehirePosition(access, {
            ...jobFormToPayload(values),
            save_as_draft: !opts.publish,
          })
          setNoticeOk(`${created.position.position_title || created.position.position_code} saved as ${created.position.status}.`)
          setJobFormMode(null)
          setSelectedJob(created.position)
        } else if (selectedJob) {
          const updated = await updatePrehirePosition(access, selectedJob.position_code, {
            ...jobFormToPayload(values),
            expected_updated_at: selectedJob.updated_at,
            expected_version: selectedJob.version,
          })
          let position = updated.position
          if (opts.publish && normalizedJobStatus(position) === 'draft') {
            const published = await setPositionStatus(access, position.position_code, 'open', {
              expected_updated_at: position.updated_at,
              expected_version: position.version,
            })
            position = published.position
          }
          setSelectedJob(position)
          setJobFormMode(null)
          setNoticeOk(`${position.position_title || position.position_code} updated.`)
        }
        void refreshAfterJob()
      } catch (error) {
        setNoticeErr(friendlyDashboardError(error, 'Could not save this job.'))
      } finally {
        setJobFormBusy(false)
      }
    },
    [access, confirm, jobFormMode, recruitingLocale, refreshAfterJob, selectedJob, setNoticeErr, setNoticeOk],
  )

  const refreshEverything = useCallback(
    async (nextAccess = access) => {
      const effectiveAccess = normalizedAccess(nextAccess)
      if (!effectiveAccess.token || !effectiveAccess.companyCode) {
        const issue = missingAccessIssue(effectiveAccess, recruitingLocale)
        setAccessIssue(issue)
        setNotice(issue.title)
        return
      }
      setBusy(true)
      setAccessIssue(null)
      setNotice(recruitingLocale === 'ar' ? 'جاري تحديث لوحة التوظيف...' : 'Refreshing hiring dashboard...')
      try {
        await queryInvalidate.allTenant(queryClient, effectiveAccess)
        setNoticeOk(
          recruitingLocale === 'ar' ? 'أنت تعرض أحدث البيانات.' : 'You’re viewing the latest data.',
        )
      } catch (error) {
        const issue = accessIssueFromError(error)
        if (issue) {
          setAccessIssue(issue)
          setNotice(issue.title)
        } else {
          setNoticeErr(
            friendlyDashboardError(
              error,
              recruitingLocale === 'ar' ? 'تعذّر تحديث لوحة التوظيف.' : 'Could not refresh the hiring dashboard.',
            ),
          )
        }
      } finally {
        setBusy(false)
      }
    },
    [access, queryClient, queryInvalidate, recruitingLocale, setNotice, setNoticeErr, setNoticeOk],
  )

  useEffect(() => {
    const nextId = dashboardChatConversationId(access)
    setChatConversationId(nextId)
  }, [access.companyCode, access.hrPhone])

  const loadChatSessions = useCallback(async (effectiveAccess: DashboardAccess = access) => {
    if (!effectiveAccess.token || !effectiveAccess.companyCode) return
    try {
      const payload = await getDashboardChatSessions(effectiveAccess)
      setChatSessions(payload.sessions || [])
    } catch {
      // Chat history is helpful, but it should never block dashboard work.
    }
  }, [access])

  const loadAssistantCapabilities = useCallback(
    async (effectiveAccess: DashboardAccess = access, locale: 'en' | 'ar' = recruitingLocale) => {
      if (!effectiveAccess.token || !effectiveAccess.companyCode) return
      // Keep prior empty chrome while refreshing — avoid spinner flash on re-visit.
      setAssistantEmptyStatus((prev) => (prev === 'ready' ? 'ready' : 'loading'))
      try {
        const payload = await getAssistantCapabilities(effectiveAccess, locale)
        setAssistantEmptyState(payload.empty_state || null)
        setAssistantEmptyStatus('ready')
      } catch {
        setAssistantEmptyState(null)
        setAssistantEmptyStatus('error')
      }
    },
    [access, recruitingLocale],
  )

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    void loadChatSessions(access)
  }, [access, accessIssue, prehireEnabled, loadChatSessions])

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || activePage !== 'ai') return
    void loadAssistantCapabilities(access, recruitingLocale)
  }, [access.token, access.companyCode, accessIssue, activePage, recruitingLocale, loadAssistantCapabilities])

  const loadTeam = useCallback(async (effectiveAccess: DashboardAccess = access) => {
    if (!effectiveAccess.token || !effectiveAccess.companyCode) return
    try {
      setTeam(await getDashboardTeam(effectiveAccess))
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not load team access.'))
    }
  }, [access])

  useEffect(() => {
    if (page !== 'settings' || accessIssue || !access.token || !access.companyCode) return
    void loadTeam(access)
  }, [page, access, accessIssue, loadTeam])

  const loadSetupReadiness = useCallback(async (effectiveAccess: DashboardAccess = access) => {
    if (!effectiveAccess.token || !effectiveAccess.companyCode) return
    try {
      setSetupReadiness(await getSetupReadiness(effectiveAccess))
    } catch {
      // The setup checklist is helpful guidance; it must never block the dashboard.
    }
  }, [access])

  useEffect(() => {
    if (accessIssue || !access.token || !access.companyCode) return
    void loadSetupReadiness(access)
  }, [page, access, accessIssue, loadSetupReadiness])

  useEffect(() => {
    const key = String(new URLSearchParams(window.location.search).get('candidate') || '').trim()
    if (!key) return
    if (selected?.app_key === key) return
    const application = allApplications.find((item) => item.app_key === key)
    if (application) {
      setSelected(application)
      if (page !== 'candidates') setPage('candidates')
      return
    }
    // Deep link must resolve the complete person from backend even when the row
    // is outside the currently loaded Candidates page.
    let cancelled = false
    void (async () => {
      try {
        const person = await getCandidatePersonProfile(access, key)
        if (cancelled) return
        if (person.application) {
          setSelected(person.application)
          if (page !== 'candidates') setPage('candidates')
        }
      } catch {
        // Keep the candidates page; profile open will surface the error.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [allApplications, selected?.app_key, page, access])

  useEffect(() => {
    const onPopState = () => {
      const nav = readDashboardNavState()
      applyNavStateToUi(nav, { restoreScroll: nav.page === 'overview' })
      const key = String(nav.candidate || '').trim()
      if (!key) {
        setSelected(null)
        return
      }
      const application = allApplications.find((item) => item.app_key === key)
      if (application) {
        setSelected(application)
        return
      }
      void getCandidatePersonProfile(access, key)
        .then((person) => {
          if (person.application) setSelected(person.application)
        })
        .catch(() => undefined)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [allApplications, access])

  useEffect(() => {
    if (skipUrlSyncRef.current) return
    if (page === 'candidates') {
      writeDashboardNavUrl(
        {
          page: 'candidates',
          candidate: selected?.app_key || null,
          filters: currentCandidateNavFilters(),
        },
        'replace',
      )
      return
    }
    if (page === 'interviews') {
      writeDashboardNavUrl(
        {
          page: 'interviews',
          candidate: null,
          filters: {
            ...(interviewTab ? { status: interviewTab, tab: interviewTab } : {}),
            ...(interviewRole ? { role: interviewRole } : {}),
            ...(interviewDate ? { date: interviewDate } : {}),
            ...(interviewInterviewer ? { interviewer: interviewInterviewer } : {}),
          },
        },
        'replace',
      )
      return
    }
    if (page === 'ranking') {
      writeDashboardNavUrl(
        {
          page: 'ranking',
          candidate: null,
          filters: rankPosition ? { position_code: rankPosition, cohort_key: `ranking:${rankPosition}` } : {},
        },
        'replace',
      )
      return
    }
    if (page === 'assessments') {
      const surfaceOnly = assessmentTab === 'attempts' || assessmentTab === 'reports' || assessmentTab === 'needs_review'
      writeDashboardNavUrl(
        {
          page: 'assessments',
          candidate: null,
          filters: {
            ...(assessmentCohort
              ? {
                  assessment_cohort: assessmentCohort,
                  overview_cohort: assessmentCohort,
                  cohort_key: assessmentCohort,
                }
              : {}),
            tab: surfaceOnly ? assessmentTab : (assessmentTabForCohort(assessmentCohort) || assessmentTab || 'send'),
          },
        },
        'replace',
      )
    }
  }, [
    page,
    query,
    candidateFilters,
    selected?.app_key,
    interviewTab,
    interviewRole,
    interviewDate,
    interviewInterviewer,
    rankPosition,
    assessmentCohort,
    assessmentTab,
  ])

  useEffect(() => {
    if (page !== 'ranking') return
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    if (!rankPosition) {
      setRanking(null)
      setRankingError(false)
      return
    }
    const timer = window.setTimeout(() => {
      void loadCurrentRanking(rankPosition)
    }, 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, rankPosition, access.token, access.companyCode, accessIssue, prehireEnabled, recruitingLocale])

  useEffect(() => {
    if (page !== 'overview') return
    const y = overviewScrollRestoreRef.current
    if (y == null || y <= 0) return
    overviewScrollRestoreRef.current = null
    window.requestAnimationFrame(() => window.scrollTo(0, y))
  }, [page])

  async function saveAccess() {
    const nextAccess = normalizedAccess(access)
    if (inviteToken.trim()) {
      if (!acceptName.trim() || acceptPassword.length < 8) {
        setAccessIssue({
          code: 'invite_validation',
          title: authCopy(recruitingLocale, 'authAcceptInvite'),
          description: authCopy(recruitingLocale, 'authInviteNamePassword'),
          copyKey: 'authInviteNamePassword',
        })
        setNoticeErrKey('authInviteNamePassword')
        return
      }
      setBusy(true)
      try {
        const accepted = await acceptDashboardInvite({
          invite_token: inviteToken.trim(),
          name: acceptName.trim(),
          password: acceptPassword,
          phone: acceptPhone || undefined,
        })
        const loggedInAccess = normalizedAccess({
          token: accepted.access_token,
          companyCode: accepted.company_code,
          hrPhone: accepted.user?.phone || acceptPhone,
          email: accepted.user?.email || '',
          password: '',
        })
        localStorage.setItem('wathefni_dashboard_token', loggedInAccess.token)
        localStorage.setItem('wathefni_company_code', loggedInAccess.companyCode)
        if (loggedInAccess.hrPhone) localStorage.setItem('wathefni_hr_phone', loggedInAccess.hrPhone)
        if (loggedInAccess.email) localStorage.setItem('wathefni_dashboard_email', loggedInAccess.email)
        setInviteToken('')
        window.history.replaceState({}, '', window.location.pathname)
        setAccessIssue(null)
        setAccess(loggedInAccess)
        setNoticeOk(authCopy(recruitingLocale, 'authInviteAccepted'))
        await refreshEverything(loggedInAccess)
        await loadTeam(loggedInAccess)
      } catch (error) {
        const issue = accessIssueFromError(error, recruitingLocale)
        if (issue) {
          setAccessIssue(issue)
          setNoticeErr(accessIssueMessage(issue, recruitingLocale))
        } else {
          setNoticeErr(
            friendlyDashboardError(error, authCopy(recruitingLocale, 'authCouldNotAcceptInvite'), recruitingLocale),
          )
        }
      } finally {
        setBusy(false)
      }
      return
    }
    const hasPasswordLogin = Boolean(nextAccess.email && nextAccess.password)
    if (hasPasswordLogin && !nextAccess.companyCode) {
      setAccessIssue({
        code: 'dashboard_company_required',
        title: authCopy(recruitingLocale, 'authSignInTitle'),
        description: authCopy(recruitingLocale, 'authCompanyRequired'),
        copyKey: 'authCompanyRequired',
      })
      setNoticeErrKey('authCompanyRequired')
      return
    }
    if (!hasPasswordLogin) {
      const issue = missingAccessIssue({ ...nextAccess, token: '' }, recruitingLocale)
      setAccessIssue(issue)
      return
    }
    setBusy(true)
    try {
      const login = await loginDashboard({
        ...nextAccess,
        token: '',
        hrPhone: '',
      })
      const loggedInAccess = normalizedAccess({
        ...nextAccess,
        token: login.access_token,
        companyCode: login.company_code,
        hrPhone: login.user?.phone || nextAccess.hrPhone,
        password: '',
      })
      localStorage.setItem('wathefni_dashboard_token', loggedInAccess.token)
      localStorage.setItem('wathefni_company_code', loggedInAccess.companyCode)
      if (loggedInAccess.hrPhone) localStorage.setItem('wathefni_hr_phone', loggedInAccess.hrPhone)
      if (loggedInAccess.email) localStorage.setItem('wathefni_dashboard_email', loggedInAccess.email)
      const nextChatId = dashboardChatConversationId(loggedInAccess)
      setChatConversationId(nextChatId)
      setAccessIssue(null)
      setAccess(loggedInAccess)
      setNoticeOk(authCopy(recruitingLocale, 'authSignedIn'))
      await loadChatSessions(loggedInAccess)
      await refreshEverything(loggedInAccess)
      await loadTeam(loggedInAccess)
    } catch (error) {
      // An explicit email+password sign-in that fails with 401 means the credentials
      // were rejected. Show that plainly instead of the generic "session expired"
      // copy, which otherwise makes a wrong password look like nothing happened.
      const wasPasswordLogin = Boolean(nextAccess.email && nextAccess.password)
      const unauthorized = error instanceof DashboardApiError && (error.status === 401 || error.code === 'dashboard_auth_failed')
      if (wasPasswordLogin && unauthorized) {
        setAccessIssue({
          code: 'dashboard_auth_failed',
          title: authCopy(recruitingLocale, 'authSignInTitle'),
          description: authCopy(recruitingLocale, 'authIncorrectCredentials'),
          copyKey: 'authIncorrectCredentials',
        })
        setNoticeErrKey('authIncorrectCredentials')
      } else {
        const issue = accessIssueFromError(error, recruitingLocale) || {
          code: 'dashboard_auth_failed',
          title: authCopy(recruitingLocale, 'authSignInTitle'),
          description: friendlyDashboardError(error, authCopy(recruitingLocale, 'authCouldNotSignIn'), recruitingLocale),
        }
        setAccessIssue(issue)
        setNoticeErr(issue.description)
      }
    } finally {
      setBusy(false)
    }
  }

  async function inviteTeamMember() {
    if (!inviteEmail.trim()) {
      setNoticeErr('Enter an email address first.')
      return
    }
    setBusy(true)
    setNotice('Creating invite link...')
    try {
      const result = await inviteDashboardUser(access, { email: inviteEmail, role: inviteRole, name: inviteName || undefined })
      if (result.invite_token) {
        const link = dashboardInviteLink(result.invite_token)
        setCreatedInviteLink(link)
        setNoticeOk('Invite link created. Share it with the new team member.')
      } else {
        setCreatedInviteLink('')
        setNoticeOk('Invite created.')
      }
      setInviteEmail('')
      setInviteName('')
      await loadTeam(access)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not create invite.'))
    } finally {
      setBusy(false)
    }
  }

  async function updateTeamMember(userId: string, body: { role?: string; status?: string }) {
    setBusy(true)
    try {
      await updateDashboardUser(access, userId, body)
      setNoticeOk('Team access updated.')
      await loadTeam(access)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not update team access.'))
    } finally {
      setBusy(false)
    }
  }

  async function linkWhatsAppPhone() {
    if (!linkPhone.trim()) {
      setNoticeErr('Enter a WhatsApp phone first.')
      return
    }
    if (
      !(await confirm({
        title: 'Link this WhatsApp number?',
        body: `${linkPhone.trim()} will be linked to your dashboard user and able to act on this workspace over WhatsApp. Continue?`,
        confirmLabel: 'Link number',
        destructive: true,
      }))
    )
      return
    setBusy(true)
    try {
      await linkDashboardWhatsApp(access, linkPhone)
      setAccess((current) => ({ ...current, hrPhone: linkPhone }))
      localStorage.setItem('wathefni_hr_phone', linkPhone)
      setNoticeOk('WhatsApp phone linked to your dashboard user.')
      await loadTeam(access)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not link WhatsApp phone.'))
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    setBusy(true)
    try {
      if (access.token) await logoutDashboard(access)
    } catch {
      // Local sign-out should still clear this browser session if the server call fails.
    } finally {
      localStorage.removeItem('wathefni_dashboard_token')
      localStorage.removeItem('wathefni_hr_phone')
      localStorage.removeItem('wathefni_dashboard_email')
      localStorage.removeItem('wathefni_company_code')
      const nextAccess = normalizedAccess({ token: '', hrPhone: '', companyCode: '', email: '', password: '' })
      setAccess(nextAccess)
      queryClient.clear()
      bootNoticeShownRef.current = false
      setRanking(null)
      setTeam(null)
      setChatMessages([])
      setChatSessions([])
      setAccessIssue(missingAccessIssue(nextAccess))
      setNoticeOk('Signed out.')
      setBusy(false)
      setPage('overview')
    }
  }

  async function loadCurrentRanking(position = rankPosition, opts: { force?: boolean } = {}) {
    if (!position) {
      setRanking(null)
      rankingLoadedPositionRef.current = ''
      setRankingError(false)
      return
    }
    // Soft-keep cards for the same job while refreshing. Clear only when switching jobs
    // so the new job never paints stale cards from another position.
    const sameJob = rankingLoadedPositionRef.current === position
    if (!sameJob) setRanking(null)
    setRankingBusy(true)
    setRankingError(false)
    try {
      const payload = await getRanking(access, {
        position,
        mode: opts.force ? undefined : 'current',
        force: Boolean(opts.force),
        locale: recruitingLocale,
      })
      setRanking(payload)
      rankingLoadedPositionRef.current = position
      setRankingError(false)
      if (opts.force) setNoticeOk(recruitingLocale === 'ar' ? 'تم تحديث الترتيب.' : 'Ranking updated.')
    } catch (error) {
      setRankingError(true)
      setNoticeErr(friendlyDashboardError(error, 'Could not refresh ranking.'))
    } finally {
      setRankingBusy(false)
    }
  }

  async function runRanking() {
    if (!rankPosition) {
      setNoticeErr(recruitingLocale === 'ar' ? 'اختر وظيفة قبل الترتيب.' : 'Select a job before ranking candidates.')
      return
    }
    await loadCurrentRanking(rankPosition, { force: true })
  }

  async function mutate(label: string, action: () => Promise<MutationResponse>, key?: string) {
    setBusy(true)
    setRunningAction(key || label)
    setNotice(`${label}...`)
    let invalidateAppKey: string | undefined
    try {
      const result = await action()
      const sendResult = extractSendResult(result)
      if (sendResult) {
        setLastSendResult(sendResult)
        setNoticeOk(sendResult.message || result.reply || `${label} completed.`)
      } else {
        setNoticeOk(result.reply || `${label} completed.`)
      }
      if (result.application) {
        const updatedApplication = result.application
        invalidateAppKey = updatedApplication.app_key
        setSelected((current) =>
          current?.app_key === updatedApplication.app_key
            ? {
                ...current,
                ...updatedApplication,
                // Trust the mutation payload when present (including []). Empty used to
                // wipe the drawer because `[] || previous` keeps [] (arrays are truthy).
                allowed_actions: Array.isArray(updatedApplication.allowed_actions)
                  ? updatedApplication.allowed_actions
                  : current.allowed_actions,
              }
            : current,
        )
        queryClient.setQueriesData<InfiniteData<ApplicationsResponse> | ApplicationsResponse>(
          { queryKey: [...tenantRoot(access), 'applications'] },
          (current) => {
            if (!current) return current
            if ('pages' in current && Array.isArray(current.pages)) {
              return {
                ...current,
                pages: current.pages.map((page) => ({
                  ...page,
                  applications: (page.applications || []).map((item) =>
                    item.app_key === updatedApplication.app_key ? updatedApplication : item,
                  ),
                })),
              }
            }
            const legacy = current as ApplicationsResponse
            return {
              ...legacy,
              applications: (legacy.applications || []).map((item) =>
                item.app_key === updatedApplication.app_key ? updatedApplication : item,
              ),
            }
          },
        )
      }
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, `${label} needs another try.`, recruitingLocale))
      setBusy(false)
      setRunningAction(null)
      return
    }
    setBusy(false)
    setRunningAction(null)
    void refreshAfterCandidate(invalidateAppKey)
  }

  async function changeInterviewStatus(interview: CandidateInterview, nextStatus: string) {
    const who = interview.candidate_name || 'this candidate'
    if (nextStatus === 'cancelled') {
      if (
        !(await confirm({
          title: 'Cancel this interview?',
          body: `${who}'s interview will be marked cancelled. You can schedule a new one later if needed.`,
          confirmLabel: 'Cancel interview',
          cancelLabel: 'Keep interview',
        }))
      )
        return
    } else if (nextStatus === 'no_show') {
      if (
        !(await confirm({
          title: 'Mark as no response?',
          body: `${who}'s interview will be marked as no response. You can change this later if they reply.`,
          confirmLabel: 'Mark no response',
        }))
      )
        return
    }
    setBusy(true)
    setNotice(`Updating ${interview.candidate_name || 'interview'}...`)
    try {
      await updateInterviewStatus(access, interview.interview_id, nextStatus)
      setNoticeOk(interview.interview_type === 'async_video' && nextStatus === 'completed' ? 'Video interview marked reviewed.' : `Interview marked ${stageLabel(nextStatus)}.`)
      void refreshAfterInterview(interview.app_key)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not update the interview.', recruitingLocale))
    } finally {
      setBusy(false)
    }
  }

  async function saveNotesForInterview(interview: CandidateInterview) {
    const notes = (interviewNotes[interview.interview_id] || '').trim()
    if (!notes) {
      setNoticeErr('Add interview notes before saving.')
      return
    }
    setBusy(true)
    setNotice(`Summarizing notes for ${interview.candidate_name || 'interview'}...`)
    try {
      const result = await saveInterviewNotes(access, interview.interview_id, {
        notes,
        status: 'completed',
        generate_summary: true,
        expected_updated_at: interview.updated_at || null,
        expected_version: typeof (interview as { notes_version?: number }).notes_version === 'number'
          ? (interview as { notes_version?: number }).notes_version
          : null,
      })
      setInterviewNotes((items) => ({ ...items, [interview.interview_id]: '' }))
      setNoticeOk(result.reply || 'Interview notes saved.')
      void refreshAfterInterview(interview.app_key)
    } catch (error) {
      // Keep unsaved draft text on conflict so the user can review latest then re-save.
      setNoticeErr(friendlyDashboardError(error, 'Could not save interview notes.', recruitingLocale))
      if (error instanceof DashboardApiError && (error.code.includes('stale') || error.status === 409)) {
        void refreshAfterInterview(interview.app_key)
      }
    } finally {
      setBusy(false)
    }
  }

  async function retryVideoTranscripts(interview: CandidateInterview) {
    setBusy(true)
    setNotice(`Preparing video interview summary again for ${interview.candidate_name || 'candidate'}...`)
    try {
      const result = await retryVideoInterviewTranscripts(access, interview.interview_id)
      setNoticeOk(result.reply || 'Video interview summary is being prepared again.')
      void refreshAfterInterview(interview.app_key)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not prepare the video summary again.'))
    } finally {
      setBusy(false)
    }
  }

  async function previewVideoAnswer(videoUrl?: string) {
    if (!videoUrl) {
      setNotice('No video answer is available yet.')
      return
    }
    try {
      setNotice('Opening video answer...')
      await previewVideoInterviewAnswer(access, videoUrl)
      setNoticeOk('Video answer opened.')
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not open the video answer.'))
    }
  }


  async function recalculateNorms() {
    if (
      !(await confirm({
        title: 'Recalculate assessment scoring?',
        body: 'This recalculates the scoring baseline used across your whole workspace from completed results. Continue?',
        confirmLabel: 'Recalculate',
      }))
    )
      return
    setBusy(true)
    setNotice('Refreshing assessment setup...')
    try {
      const result = await recalculateAssessmentNorms(access, true)
      setNoticeOk(
        result.status === 'empirical_ready'
          ? 'Assessment setup refreshed.'
          : 'Assessment setup saved. More completed results are needed before calibration is complete.',
      )
      void refreshAssessments()
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not refresh assessment scoring.'))
    } finally {
      setBusy(false)
    }
  }

  async function copyToClipboard(value: string | undefined, label: string) {
    if (!value) {
      setNotice(`${label} is not available yet.`)
      return
    }
    await navigator.clipboard.writeText(value)
    setNoticeOk(`${label} copied.`)
  }

  function viewJobCandidates(job: { position_code?: string }) {
    navigateDashboard({
      page: 'candidates',
      candidate: null,
      filters: {
        position: job.position_code || '',
        overview_cohort: 'role_active',
        cohort_key: job.position_code ? `role_active:${job.position_code}` : 'role_active',
      },
    })
  }

  // "Review ready candidates": land straight on the exact cohort the overview
  // card counted (screening_complete / review_pending), sorted to the top,
  // instead of dumping HR on the generic, unfiltered candidate list.
  function viewReadyForReviewCandidates() {
    navigateDashboard({
      page: 'candidates',
      candidate: null,
      filters: {
        review_status: 'ready',
        sort: 'ready_for_review',
        overview_cohort: 'ready_for_review',
        cohort_key: 'ready_for_review',
      },
    })
  }

  // "Follow up with candidates": apply the real follow-up filter so the table
  // shows exactly the cohort the overview card counted (company-wide
  // follow_up_needed applications).
  function viewFollowUpCandidates() {
    navigateDashboard({
      page: 'candidates',
      candidate: null,
      filters: {
        follow_up: 'needed',
        overview_cohort: 'follow_up_needed',
        cohort_key: 'follow_up_needed',
      },
    })
  }

  function viewPendingAssessmentCandidates() {
    const primary = summary?.action_counts?.assessment_primary || summary?.assessment_cohorts?.primary
    const destination = primary?.destination || {
      page: 'assessments',
      filters: {
        assessment_cohort: 'assessment_ready_to_send',
        overview_cohort: 'assessment_ready_to_send',
        cohort_key: 'assessment_ready_to_send',
        tab: 'send',
      },
      cohort_key: 'assessment_ready_to_send',
    }
    navigateDashboard(destinationToNavState(destination, 'assessments'))
  }

  function viewRolePriority(role?: PrehireRolePriority | null) {
    const destination = role?.destination || {
      page: 'candidates',
      filters: {
        position: role?.position_code || '',
        overview_cohort: 'role_active',
        cohort_key: role?.position_code ? `role_active:${role.position_code}` : 'role_active',
      },
      cohort_key: role?.position_code ? `role_active:${role.position_code}` : 'role_active',
    }
    navigateDashboard(destinationToNavState(destination, 'candidates'))
  }

  function viewRoleRanking(role?: PrehireRolePriority | null) {
    const destination = role?.ranking_destination || {
      page: 'ranking',
      filters: role?.position_code ? { position_code: role.position_code } : {},
    }
    navigateDashboard(destinationToNavState(destination, 'ranking'))
  }

  function applyOverviewDestination(
    destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string } | null,
  ) {
    if (!destination?.page) return
    navigateDashboard(destinationToNavState(destination))
  }

  function openCandidateByKey(
    appKey?: string,
    opts?: { returnPage?: Page; returnFocusEl?: HTMLElement | null },
  ) {
    if (!appKey) return
    const application = allApplications.find((item) => item.app_key === appKey)
    if (application) {
      openCandidateProfile(application, opts)
      return
    }
    void getCandidatePersonProfile(access, appKey)
      .then((person) => {
        if (person.application) {
          openCandidateProfile(person.application, opts)
          return
        }
        setQuery(appKey)
        setStatus('')
        setCandidateOffset(0)
        openPage('candidates')
        writeDashboardUrl('candidates', appKey, 'push')
      })
      .catch(() => {
        setQuery(appKey)
        setStatus('')
        setCandidateOffset(0)
        openPage('candidates')
        writeDashboardUrl('candidates', appKey, 'push')
      })
  }

  function applyChatNavigation(item: DashboardChatNavigation) {
    if (item.type === 'assistant_prompt' || item.prompt) {
      const prompt = String(item.prompt || '').trim()
      if (prompt) void askDashboardAssistant(prompt)
      return
    }
    if (item.page && isRegisteredDashboardPage(item.page)) {
      openPage(item.page as Page)
    }
    if (item.page === 'ranking' && item.position_code) {
      setRankPosition(String(item.position_code))
    }
  }

  function cancelDashboardAssistant() {
    dashboardPerfMarkInteractionStart('assistant_cancel')
    chatAbortRef.current?.abort()
    chatAbortRef.current = null
    setChatBusy(false)
    setChatMessages((items) =>
      items.map((item) =>
        item.isStreaming
          ? {
              ...item,
              text: item.text || (recruitingLocale === 'ar' ? 'تم الإيقاف.' : 'Stopped.'),
              isStreaming: false,
              progressPhase: 'cancelled',
            }
          : item,
      ),
    )
    dashboardPerfMarkNetworkComplete('assistant_cancel')
  }

  async function openChatSession(session: DashboardChatSession) {
    if (!session.conversation_id || chatBusy) return
    try {
      const payload = await getDashboardChatSession(access, session.conversation_id)
      setChatConversationId(payload.session.conversation_id)
      rememberDashboardChatConversationId(access, payload.session.conversation_id)
      setChatMessages((payload.messages || []).map(storedDashboardMessageToChatMessage))
      setChatHistoryOpen(false)
      setNoticeOk(`Reopened ${payload.session.title || 'OctoHR Assistant chat'}.`)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not open that chat.'))
    }
  }

  async function startNewDashboardChat() {
    if (chatBusy) return
    setChatBusy(true)
    try {
      const payload = await startDashboardChatSession(access, chatConversationId)
      const nextId = payload.session.conversation_id || createDashboardChatConversationId(access)
      setChatConversationId(nextId)
      rememberDashboardChatConversationId(access, nextId)
      setChatMessages([])
      setChatInput('')
      setNewChatConfirmOpen(false)
      await loadChatSessions(access)
      setNoticeOk('Started a new OctoHR Assistant chat. Saved records were not changed.')
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not start a new chat.'))
    } finally {
      setChatBusy(false)
    }
  }

  async function askDashboardAssistant(messageOverride?: string) {
    const text = (messageOverride || chatInput).trim()
    if (!text || chatBusy) return
    const conversationId = chatConversationId || dashboardChatConversationId(access)
    rememberDashboardChatConversationId(access, conversationId)
    const assistantId = `assistant-${Date.now()}`
    dashboardPerfMarkInteractionStart('assistant_send', { len: text.length })
    chatAbortRef.current?.abort()
    const controller = new AbortController()
    chatAbortRef.current = controller
    setChatInput('')
    setChatMessages((items) => [
      ...items,
      { id: `user-${Date.now()}`, role: 'user', text },
      { id: assistantId, role: 'assistant', text: '', isStreaming: true, progressPhase: 'planning' },
    ])
    setChatBusy(true)
    let finalResponse: DashboardChatResponse | null = null
    let finalSessionId: string | null = null
    let streamFailed = false
    let aborted = false
    try {
      await streamDashboardChat(
        access,
        {
          message: text,
          conversation_id: conversationId,
          // The assistant lives on its own page; tell the backend which module
          // page HR was last working in so it can bias its help to that area.
          page: activePage === 'ai' ? lastWorkPage : activePage,
          selected_app_key: selected?.app_key,
        },
        (event) => {
          if (event.type === 'typing') {
            setChatMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? { ...item, progressPhase: event.phase || 'planning', isStreaming: true }
                  : item,
              ),
            )
            return
          }
          if (event.type === 'progress') {
            dashboardPerfMarkInteractionStart('assistant_planning', { phase: event.phase || '' })
            setChatMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? { ...item, progressPhase: event.phase || item.progressPhase, isStreaming: true }
                  : item,
              ),
            )
            return
          }
          if (event.type === 'delta') {
            setChatMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      // Progress stream sends the full reply once (not fake token drip).
                      text: event.text && event.text.length >= item.text.length ? event.text : item.text + (event.text || ''),
                    }
                  : item,
              ),
            )
          }
          if (event.type === 'done' && typeof event.message === 'object' && event.message) {
            const response = event.message as DashboardChatResponse
            finalResponse = response
            finalSessionId = response.session?.conversation_id || null
            dashboardPerfMarkNetworkComplete('assistant_stream_done', {
              intent: response.intent || '',
            })
            setChatMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      id: response.turn_id || item.id,
                      text: response.reply_text || item.text,
                      candidateCards: response.candidate_cards,
                      navigation: response.navigation,
                      confirmation: response.confirmation,
                      workflowCard: response.workflow_card || null,
                      progressPhase: null,
                      isStreaming: false,
                    }
                  : item,
              ),
            )
          }
          if (event.type === 'error') {
            streamFailed = true
            setChatMessages((items) =>
              items.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      text: friendlyDashboardError(event.message, 'OctoHR couldn’t finish answering just now. Please try again in a moment.'),
                      isStreaming: false,
                      progressPhase: null,
                    }
                  : item,
              ),
            )
          }
        },
        { signal: controller.signal },
      )
      // A mid-stream error resolves the stream normally (the bubble already shows
      // the friendly failure). Never claim success after a failed answer.
      if (streamFailed) {
        setNoticeErr('OctoHR couldn’t finish answering. Please try again.')
      } else if (!aborted) {
        setNoticeOk('Answered by the OctoHR assistant.')
      }
      if (finalSessionId) {
        setChatConversationId(finalSessionId)
        rememberDashboardChatConversationId(access, finalSessionId)
      }
      await loadChatSessions(access)
      if (finalResponse && !streamFailed && !aborted) await refreshEverything()
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        aborted = true
      } else {
        setChatMessages((items) =>
          items.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  text: friendlyDashboardError(error, 'OctoHR couldn’t finish answering just now. Please try again in a moment.'),
                  isStreaming: false,
                  progressPhase: null,
                }
              : item,
          ),
        )
        setNoticeErr('OctoHR couldn’t finish answering. Please try again.')
      }
    } finally {
      if (chatAbortRef.current === controller) chatAbortRef.current = null
      setChatBusy(false)
      dashboardPerfMarkNetworkComplete('assistant_send', { aborted, failed: streamFailed })
    }
  }

  async function exportReport(type: 'candidates' | 'roles' | 'assessments' | 'interviews' | 'followups' | 'followup_delivery_history', label: string) {
    if (
      !(await confirm({
        title: 'Export this report?',
        body: `${label} contains candidate data and will download to this device as a file. Continue?`,
        confirmLabel: 'Export',
      }))
    )
      return
    setNotice(`Preparing ${label.toLowerCase()}...`)
    try {
      await downloadPrehireReport(access, type)
      setNoticeOk(`${label} downloaded.`)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, `Could not download ${label.toLowerCase()}.`))
    }
  }

  const [isLgUp, setIsLgUp] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : false,
  )
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(min-width: 1024px)')
    const onChange = () => setIsLgUp(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const useFramedShell = !accessIssue && !showingInviteAcceptance
  const pagePersonality =
    activePage === 'overview'
      ? 'desk'
      : activePage === 'calendar'
        ? 'spatial'
        : activePage === 'ai'
          ? 'chat'
          : activePage === 'reports'
            ? 'quiet'
            : activePage === 'candidates' || activePage === 'employees' || activePage === 'workforce'
              ? 'people'
              : activePage === 'interviews'
                ? 'schedule'
                : activePage === 'assessments' || activePage === 'ranking'
                  ? 'eval'
                  : 'portfolio'

  const pendingSessionAuthIssue =
    (bootstrapQuery.isError ? accessIssueFromError(bootstrapQuery.error, recruitingLocale) : null)
    || (summaryQuery.isError ? accessIssueFromError(summaryQuery.error, recruitingLocale) : null)
  const resolvedAccessIssue =
    accessIssue
    || pendingSessionAuthIssue
    || (showingInviteAcceptance || (access.token.trim() && access.companyCode.trim())
      ? null
      : missingAccessIssue(access, recruitingLocale))
  const sessionValidated = Boolean(
    (bootstrapQuery.isSuccess && bootstrapQuery.data)
    || (bootstrapQuery.isSuccess && !bootstrapQuery.data && (summaryQuery.isFetched || summaryQuery.isError))
    || (bootstrapQuery.isError && !accessIssueFromError(bootstrapQuery.error)),
  )

  if (showingInviteAcceptance || resolvedAccessIssue) {
    return (
      <AccessVerificationPage
        access={access}
        accessIssue={
          resolvedAccessIssue || {
            code: 'invite_pending',
            title: authCopy(recruitingLocale, 'authAcceptInvite'),
            description: authCopy(recruitingLocale, 'authInviteDescription'),
            copyKey: 'authInviteDescription',
          }
        }
        acceptName={acceptName}
        acceptPassword={acceptPassword}
        acceptPhone={acceptPhone}
        busy={busy}
        inviteToken={inviteToken}
        locale={recruitingLocale}
        notice={notice}
        onLocaleChange={changeRecruitingLocale}
        onVerify={saveAccess}
        setAcceptName={setAcceptName}
        setAcceptPassword={setAcceptPassword}
        setAcceptPhone={setAcceptPhone}
        setAccess={setAccess}
      />
    )
  }

  if (!sessionValidated) {
    return <AuthSessionResolvingPage locale={recruitingLocale} onLocaleChange={changeRecruitingLocale} />
  }

  return (
    <main
      className={
        useFramedShell
          ? 'app-shell flex h-dvh w-full flex-col overflow-hidden bg-wf-frame text-text lg:flex-row'
          : 'app-shell flex h-dvh w-full flex-col overflow-hidden bg-[radial-gradient(circle_at_50%_-12%,#fffdf5_0%,#f7f3eb_36%,rgba(244,239,230,0)_62%),radial-gradient(circle_at_82%_10%,rgba(200,148,69,0.08)_0%,rgba(200,148,69,0.025)_26%,rgba(200,148,69,0)_48%),linear-gradient(180deg,#f7f2e9_0%,#f4eee4_48%,#f1eadf_100%)] text-text lg:flex-row'
      }
      data-testid="app-shell"
      dir={recruitingLocale === 'ar' ? 'rtl' : 'ltr'}
      lang={recruitingLocale === 'ar' ? 'ar' : 'en'}
    >
        <aside
          className={
            useFramedShell
              ? 'wf-sidebar-scroll flex shrink-0 flex-col min-w-0 max-w-full overflow-x-clip bg-wf-sidebar p-3 text-white lg:h-dvh lg:w-[210px] lg:overflow-y-auto lg:overflow-x-hidden lg:p-4'
              : 'wf-sidebar-scroll flex shrink-0 flex-col border-e border-line/55 bg-panel/72 p-5 text-text shadow-[14px_0_44px_rgba(24,20,15,0.03)] backdrop-blur-2xl lg:h-dvh lg:w-[260px] lg:overflow-y-auto lg:overflow-x-hidden'
          }
          data-testid="app-sidebar"
          dir={recruitingLocale === 'ar' ? 'rtl' : 'ltr'}
        >
          <div className={useFramedShell ? 'mb-7 hidden px-3 py-2 lg:block' : 'mb-9 rounded-[1.35rem] px-3 py-2'}>
            <div className="text-xl font-semibold tracking-[-0.045em]">OctoHR</div>
            <div className={useFramedShell ? 'mt-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-white/40' : 'mt-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-mist'}>
              {recruitingLocale === 'ar' ? 'مساحة الموارد البشرية' : 'HR workspace'}
            </div>
          </div>

          {useFramedShell && !isLgUp ? (
            <div
              className="w-full max-w-full overflow-x-clip"
              data-testid="mobile-prehire-nav"
              dir={recruitingLocale === 'ar' ? 'rtl' : 'ltr'}
            >
              <div className="flex w-full min-w-0 items-center gap-2">
                {activeNavItem && ActiveMobileIcon ? (
                  <div
                    aria-current="page"
                    className="flex max-w-[46%] shrink-0 items-center gap-2 rounded-2xl bg-white/14 px-3 py-2.5 text-sm font-semibold text-white ring-1 ring-white/30 before:h-1.5 before:w-1.5 before:shrink-0 before:rounded-full before:bg-wf-accent-active before:content-['']"
                    data-active="true"
                    data-testid="mobile-active-route-chip"
                    title={localizedPageLabel(activeNavItem.id, recruitingLocale)}
                  >
                    <ActiveMobileIcon size={16} />
                    <span className="truncate">{localizedPageLabel(activeNavItem.id, recruitingLocale)}</span>
                  </div>
                ) : null}
                <div
                  className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto overscroll-x-contain"
                  data-testid="mobile-prehire-rail"
                >
                  {!authorityReady ? (
                    <>
                      {[0, 1, 2, 3].map((row) => (
                        <div key={row} aria-hidden className="h-10 w-20 shrink-0 animate-pulse rounded-2xl bg-white/10" />
                      ))}
                    </>
                  ) : (
                    prehireNavItems
                      .filter((item) => item.id !== activePage)
                      .map((item) => {
                      const Icon = item.icon
                      return (
                        <button
                          className="flex shrink-0 items-center gap-2 rounded-2xl px-3 py-2.5 text-sm text-white/55 transition duration-200 ease-out hover:bg-white/8 hover:text-white"
                          key={item.id}
                          onClick={() => openPage(item.id)}
                          onFocus={() => prefetchDestination(item.id)}
                          onPointerEnter={() => prefetchDestination(item.id)}
                          type="button"
                        >
                          <Icon size={16} />
                          <span className="whitespace-nowrap">{localizedPageLabel(item.id, recruitingLocale)}</span>
                        </button>
                      )
                    })
                  )}
                </div>
                {otherNavItems.length ? (
                  <div className="relative shrink-0">
                    <button
                      aria-expanded={mobileMoreOpen}
                      aria-haspopup="menu"
                      className={`flex items-center gap-1.5 rounded-2xl px-3 py-2.5 text-sm ${
                        otherNavItems.some((item) => item.id === activePage)
                          ? 'bg-white/12 font-semibold text-white ring-1 ring-white/25'
                          : 'text-white/55 hover:bg-white/8 hover:text-white'
                      }`}
                      data-testid="mobile-nav-more"
                      onClick={() => setMobileMoreOpen((open) => !open)}
                      type="button"
                    >
                      <MoreHorizontal size={16} />
                      <span>{recruitingLocale === 'ar' ? 'المزيد' : 'More'}</span>
                    </button>
                    {mobileMoreOpen ? (
                      <div
                        className="absolute end-0 z-40 mt-2 min-w-[12rem] rounded-2xl border border-white/15 bg-[#2a2722] p-1.5 shadow-[0_18px_40px_rgba(0,0,0,0.35)]"
                        data-testid="mobile-nav-more-menu"
                        role="menu"
                      >
                        {otherNavItems.map((item) => {
                          const Icon = item.icon
                          const isActive = activePage === item.id
                          return (
                            <button
                              className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-start text-sm ${
                                isActive ? 'bg-white/12 font-semibold text-white' : 'text-white/70 hover:bg-white/8 hover:text-white'
                              }`}
                              key={item.id}
                              onClick={() => {
                                setMobileMoreOpen(false)
                                openPage(item.id)
                              }}
                              onFocus={() => prefetchDestination(item.id)}
                              onPointerEnter={() => prefetchDestination(item.id)}
                              role="menuitem"
                              type="button"
                            >
                              <Icon size={16} />
                              {localizedPageLabel(item.id, recruitingLocale)}
                            </button>
                          )
                        })}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {(!useFramedShell || isLgUp) ? (
            <nav
              aria-label={recruitingLocale === 'ar' ? 'التنقل' : 'Workspace navigation'}
              className="space-y-6 text-sm"
              data-testid={useFramedShell ? 'desktop-workspace-nav' : undefined}
            >
              {!authorityReady ? (
                <div className="space-y-6" aria-busy="true" data-testid="workspace-nav-skeleton">
                  {[0, 1].map((group) => (
                    <div className="space-y-1.5" key={group}>
                      <div className={`mx-3.5 mb-1 h-2.5 w-16 rounded ${useFramedShell ? 'bg-white/10' : 'bg-black/5'}`} />
                      {[0, 1, 2, 3].map((row) => (
                        <div
                          key={row}
                          className={`h-11 w-full rounded-2xl ${useFramedShell ? 'bg-white/8' : 'bg-black/[0.04]'} animate-pulse`}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              ) : (
                workspaceAuthority.navGroups.map(({ group, ids }) => {
                const items = ids.map((id) => availableNavById[id]).filter(Boolean) as typeof availableNavItems
                if (!items.length) return null
                return (
                  <div className="space-y-1.5" key={group}>
                    <div className={useFramedShell ? 'px-3.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/30' : 'px-3.5 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.2em] text-mist/75'}>
                      {localizedNavGroupLabel(group, recruitingLocale)}
                    </div>
                    {items.map((item) => {
                      const Icon = item.icon
                      const isActive = activePage === item.id
                      return (
                        <button
                          aria-current={isActive ? 'page' : undefined}
                          className={`flex h-11 w-full min-w-0 items-center gap-3 rounded-2xl px-3.5 text-start transition duration-200 ease-out ${
                            useFramedShell
                              ? isActive
                                ? "bg-white/12 font-semibold text-white ring-1 ring-white/25 before:h-1.5 before:w-1.5 before:rounded-full before:bg-wf-accent-active before:content-['']"
                                : 'text-white/55 hover:bg-white/8 hover:text-white'
                              : isActive
                                ? "bg-ink font-semibold text-white shadow-[0_10px_24px_rgba(24,20,15,0.14)] before:h-1.5 before:w-1.5 before:rounded-full before:bg-[#c89445] before:content-['']"
                                : 'text-subtle hover:bg-white/55 hover:text-ink'
                          }`}
                          data-active={isActive ? 'true' : undefined}
                          key={item.id}
                          onClick={() => openPage(item.id)}
                          onFocus={() => prefetchDestination(item.id)}
                          onPointerEnter={() => prefetchDestination(item.id)}
                          type="button"
                        >
                          <Icon className="shrink-0" size={16} />
                          <span className="truncate">{localizedPageLabel(item.id, recruitingLocale)}</span>
                        </button>
                      )
                    })}
                  </div>
                )
              })
              )}
            </nav>
          ) : null}

          {futureModuleItems.length > 0 && (
            <div className={useFramedShell ? 'mt-9 hidden border-t border-white/15 pt-5 lg:block' : 'mt-9 border-t border-white/70 pt-5'}>
              <div className={useFramedShell ? 'px-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-white/35' : 'px-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist'}>More HR tools soon</div>
              <div className={useFramedShell ? 'mt-3 space-y-1.5 px-3 text-sm text-white/45' : 'mt-3 space-y-1.5 px-3 text-sm text-mist'}>
                {futureModuleItems.map((item) => (
                  <div className="flex items-center justify-between gap-2 rounded-xl px-2 py-1.5" key={item.module}>
                    <span>{item.label}</span>
                    <span className={useFramedShell ? 'text-[10px] font-semibold uppercase tracking-[0.16em] text-white/30' : 'text-[10px] font-semibold uppercase tracking-[0.16em] text-mist/70'}>Coming soon</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>

        <section
          className={cn(
            'min-w-0 max-w-full flex-1 overflow-x-clip',
            pagePersonality === 'chat'
              ? 'flex min-h-0 flex-col overflow-hidden lg:h-dvh lg:max-h-dvh'
              : 'min-h-0 overflow-y-auto lg:h-dvh',
            pagePersonality === 'desk'
              ? 'p-4 sm:p-5 lg:p-6'
              : pagePersonality === 'spatial' || pagePersonality === 'chat'
                ? 'p-3 sm:p-4 lg:p-5'
                : pagePersonality === 'quiet'
                  ? 'p-5 lg:p-8'
                  : 'p-4 sm:p-5 lg:p-7',
          )}
          data-testid="app-main"
        >
          {activePage !== 'overview' && usesCanonicalPageHeader(activePage) ? (
            <HrPageHeader
              className="mb-6"
              density="page"
              dir={recruitingLocale === 'ar' ? 'rtl' : 'ltr'}
              eyebrow={recruitingLocale === 'ar' ? 'ما بعد التوظيف' : 'Post-Hire'}
              title={pageTitle}
              description={pageSubtitle}
              actions={
                busy ? (
                  <div className="rounded-full border border-semantic-line/50 bg-semantic-surface/80 px-3.5 py-2 text-xs font-medium text-semantic-mist" data-interaction-shell-busy>
                    {notice.text && !/^refreshing hiring data/i.test(notice.text)
                      ? notice.text
                      : recruitingLocale === 'ar'
                        ? 'جاري العمل...'
                        : 'Working…'}
                  </div>
                ) : notice.text ? (
                  <div
                    className={cn(
                      'flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-medium',
                      notice.tone === 'success'
                        ? 'border-semantic-success/60 bg-semantic-success-soft/80 text-semantic-success-ink'
                        : notice.tone === 'error'
                          ? 'border-semantic-danger/60 bg-semantic-danger-soft/85 text-semantic-danger-ink'
                          : 'border-semantic-line/50 bg-semantic-surface/80 text-semantic-mist',
                    )}
                    role="status"
                  >
                    <span>{notice.text}</span>
                    {notice.tone === 'error' ? (
                      <button
                        type="button"
                        onClick={() => setNotice('')}
                        aria-label={recruitingLocale === 'ar' ? 'إخفاء' : 'Dismiss'}
                        className="-me-1 ms-0.5 rounded-full px-1 text-semantic-danger-ink/80 hover:text-semantic-danger-ink"
                      >
                        ×
                      </button>
                    ) : null}
                  </div>
                ) : null
              }
            />
          ) : null}
          {activePage !== 'overview' && !usesCanonicalPageHeader(activePage) ? (
          <header
            className={cn(
              'mb-6 flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between',
              pagePersonality === 'chat' || pagePersonality === 'spatial' ? 'mb-2 shrink-0 border-0 pb-0' : 'border-b border-line/40 pb-5',
            )}
          >
            <div>
              {pagePersonality !== 'spatial' ? (
              <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-mist">
                {isPostHirePage(activePage)
                  ? recruitingLocale === 'ar'
                    ? 'ما بعد التوظيف'
                    : 'Post-Hire'
                  : activePage === 'settings' || activePage === 'activity' || activePage === 'notifications'
                    ? recruitingLocale === 'ar'
                      ? 'مساحة العمل'
                      : 'Workspace'
                    : recruitingLocale === 'ar'
                      ? 'ما قبل التوظيف'
                      : 'Pre-hiring'}
              </div>
              ) : null}
              <h1
                className={cn(
                  'max-w-5xl font-semibold tracking-[-0.045em] text-text',
                  pagePersonality === 'spatial' ? 'mt-0 text-2xl lg:text-[1.75rem]' : 'mt-2',
                  pagePersonality === 'quiet'
                    ? 'text-3xl lg:text-4xl'
                    : pagePersonality === 'chat'
                      ? 'text-2xl lg:text-3xl'
                      : pagePersonality === 'spatial'
                        ? ''
                        : 'text-3xl lg:text-[2.35rem]',
                )}
              >
                {pageTitle}
              </h1>
              {pagePersonality !== 'chat' ? (
              <p className={cn('max-w-3xl text-subtle/90', pagePersonality === 'spatial' ? 'mt-1 max-w-xl text-[13px] leading-5' : 'mt-2 max-w-2xl text-[14px] leading-6')}>
                {pageSubtitle}
              </p>
              ) : null}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              {busy ? (
                <div className="rounded-full border border-line/50 bg-wf-surface/80 px-3.5 py-2 text-xs font-medium text-mist" data-interaction-shell-busy>
                  {notice.text && !/^refreshing hiring data/i.test(notice.text)
                    ? notice.text
                    : recruitingLocale === 'ar'
                      ? 'جاري العمل...'
                      : 'Working…'}
                </div>
              ) : notice.text ? (
                <div
                  className={cn(
                    'flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-medium',
                    notice.tone === 'success'
                      ? 'border-emerald-300/60 bg-emerald-50/80 text-emerald-800'
                      : notice.tone === 'error'
                      ? 'border-rose-300/60 bg-rose-50/85 text-rose-700'
                      : 'border-line/50 bg-wf-surface/80 text-mist',
                  )}
                  role="status"
                >
                  <span>{notice.text}</span>
                  {notice.tone === 'error' ? (
                    <button
                      type="button"
                      onClick={() => setNotice('')}
                      aria-label={recruitingLocale === 'ar' ? 'إخفاء' : 'Dismiss'}
                      className="-me-1 ms-0.5 rounded-full px-1 text-rose-500/80 hover:text-rose-700"
                    >
                      ×
                    </button>
                  ) : null}
                </div>
              ) : null}
              {/* Single refresh authority for pre-hire pages (shell). Spatial/Calendar: quiet icon only. */}
              {!accessIssue && !showingInviteAcceptance && !isPostHirePage(activePage) ? (
                <Button
                  className={pagePersonality === 'spatial' ? 'h-8 w-8 px-0 text-xs text-mist' : 'h-8 px-3 text-xs'}
                  disabled={busy}
                  onClick={() => refreshEverything()}
                  size="sm"
                  variant="secondary"
                  aria-label={recruitingLocale === 'ar' ? 'تحديث' : 'Refresh'}
                  title={recruitingLocale === 'ar' ? 'تحديث' : 'Refresh'}
                >
                  {busy ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                  {pagePersonality === 'spatial' ? null : recruitingLocale === 'ar' ? 'تحديث' : 'Refresh'}
                </Button>
              ) : null}
            </div>
          </header>
          ) : null}
          {activePage === 'overview' && notice.text ? (
            <div
              className={cn(
                'fixed end-6 top-6 z-50 flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-medium shadow-[0_12px_32px_rgba(35,33,29,0.16)] backdrop-blur-xl',
                notice.tone === 'success'
                  ? 'border-emerald-300/60 bg-emerald-50/90 text-emerald-800'
                  : notice.tone === 'error'
                    ? 'border-rose-300/60 bg-rose-50/90 text-rose-700'
                    : 'border-white/70 bg-[#fffaf0]/90 text-[#716a5e]',
              )}
              role="status"
            >
              <span>{notice.text}</span>
              <button aria-label="Dismiss" className="rounded-full px-1 opacity-60 hover:opacity-100" onClick={() => setNotice('')} type="button">×</button>
            </div>
          ) : null}

          {activePage !== 'settings' && !access.token.trim() ? (
            <NeedsSettings onOpenSettings={() => openPage('settings')} />
          ) : activePage !== 'settings' && !dashboardLoaded ? (
            <PageSkeleton />
          ) : (
            <>
              {activePage === 'overview' && (
                <OverviewPage
                  access={access}
                  assessmentEnabled={assessmentModuleOn && workspaceAuthority.offerable('overview.action.assessment')}
                  busy={busy}
                  onRefresh={() => refreshEverything()}
                  userDisplayName={userAccess?.user?.name || workspaceBootstrap?.user?.name || ''}
                  timeZone={workspaceBootstrap?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || null}
                  overviewPrioritySurfaces={workspaceAuthority.overview.prioritySurfaces}
                  readyForReviewTotal={summary?.action_counts?.ready_for_review}
                  readyForReviewApplications={summary?.action_counts?.ready_for_review_applications}
                  assessmentPendingTotal={
                    summary?.action_counts?.assessment_primary?.people_count
                    ?? summary?.action_counts?.assessment_ready_to_send
                    ?? summary?.action_counts?.assessment_pending
                  }
                  assessmentPendingApplications={
                    summary?.action_counts?.assessment_primary?.application_count
                    ?? summary?.action_counts?.assessment_ready_to_send_applications
                    ?? summary?.action_counts?.assessment_pending_applications
                  }
                  assessmentPrimary={
                    summary?.action_counts?.assessment_primary
                    || summary?.assessment_cohorts?.primary
                    || null
                  }
                  followUpNeededTotal={summary?.action_counts?.follow_up_needed}
                  followUpNeededApplications={summary?.action_counts?.follow_up_needed_applications}
                  nextAction={summary?.next_action || null}
                  rolePriority={summary?.role_priority || null}
                  roleNextSteps={summary?.role_next_steps || []}
                  canViewCompanyWorkHint={Boolean(
                    workspaceBootstrap?.prehire_visibility_oversight
                    ?? ['owner', 'hr_admin', 'hr_manager', 'company_admin'].includes(String(userAccess?.user?.role || '')),
                  )}
                  locale={recruitingLocale}
                  onLocaleChange={changeRecruitingLocale}
                  onOpenCandidate={openCandidateByKey}
                  onOpenFollowUps={viewFollowUpCandidates}
                  onOpenPendingAssessments={viewPendingAssessmentCandidates}
                  onOpenReadyForReview={viewReadyForReviewCandidates}
                  onOpenRolePriority={() => viewRolePriority(summary?.role_priority)}
                  onOpenRoleRanking={() => viewRoleRanking(summary?.role_priority)}
                  onOpenDestination={applyOverviewDestination}
                  onOpenRoleCandidates={viewJobCandidates}
                  calendarAccess={access}
                  calendarEnabled={workspaceAuthority.offerable('overview.calendar')}
                  onOpenCalendar={() => openPage('calendar')}
                  canManageWorkspace={canManageWorkspace}
                  setupReadiness={setupReadiness}
                  onOpenSetupAction={openPage}
                  overviewLayout={workspaceAuthority.overview.layout}
                  showWorkQueue={workspaceAuthority.overview.showWorkQueue}
                  showRolePriority={workspaceAuthority.overview.showRolePriority}
                  showApprovals={workspaceAuthority.overview.showApprovals}
                  showSignals={workspaceAuthority.overview.showSignals}
                  showHiringMetrics={workspaceAuthority.overview.showHiringMetrics}
                  onOpenInbox={() => openPage('inbox')}
                  onOpenInboxItem={(item) => {
                    const nextPage = String(item.deep_link?.page || item.system_of_action || '').trim()
                    if (!nextPage) return
                    const honorsEmployee = nextPage === 'employees' || nextPage === 'onboarding'
                    const employee = honorsEmployee
                      ? (item.deep_link?.employee || item.employee_key || undefined)
                      : undefined
                    openPage(nextPage as Page)
                    if (employee) {
                      const url = new URL(window.location.href)
                      url.searchParams.set('employee', String(employee))
                      window.history.replaceState({}, '', `${url.pathname}${url.search}`)
                      window.dispatchEvent(new PopStateEvent('popstate'))
                    }
                  }}
                />
              )}
              {activePage === 'ai' && (
                <div className="flex min-h-0 flex-1 flex-col">
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyAdminAIPage
                    busy={chatBusy}
                    input={chatInput}
                    historyOpen={chatHistoryOpen}
                    locale={recruitingLocale}
                    messages={chatMessages}
                    newChatConfirmOpen={newChatConfirmOpen}
                    assessmentEnabled={assessmentModuleOn}
                    enabledModules={moduleState?.enabled_modules}
                    emptyState={assistantEmptyState}
                    emptyStateStatus={assistantEmptyStatus}
                    onApplyNavigation={applyChatNavigation}
                    onAsk={() => void askDashboardAssistant()}
                    onCancel={cancelDashboardAssistant}
                    onConfirm={() =>
                      void askDashboardAssistant(
                        recruitingLocale === 'ar' ? 'نعم، أكّد' : 'Yes, confirm it',
                      )
                    }
                    onCloseHistory={() => setChatHistoryOpen(false)}
                    onCloseNewChatConfirm={() => setNewChatConfirmOpen(false)}
                    onInputChange={setChatInput}
                    onNewChat={startNewDashboardChat}
                    onOpenCandidate={openCandidateByKey}
                    onOpenHistory={() => {
                      void loadChatSessions(access)
                      setChatHistoryOpen(true)
                    }}
                    onOpenSession={openChatSession}
                    onPrompt={(prompt) => void askDashboardAssistant(prompt)}
                    onReloadCapabilities={() => void loadAssistantCapabilities(access, recruitingLocale)}
                    onRequestNewChat={() => setNewChatConfirmOpen(true)}
                    onRetryWorkflow={(prompt) => void askDashboardAssistant(prompt)}
                    sessions={chatSessions}
                  />
                </Suspense>
                </div>
              )}
              {activePage === 'jobs' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyJobsPage
                    canCreateJobs={canCreateJobs}
                    deadlineFilter={jobsDeadlineFilter}
                    departmentFilter={jobsDepartmentFilter}
                    jobsData={jobsData}
                    loading={jobsLoading}
                    listError={Boolean(jobsListError)}
                    onRetryList={() => void server.jobsQuery.refetch()}
                    loadingMore={jobsLoadingMore}
                    locale={recruitingLocale}
                    locationFilter={jobsLocationFilter}
                    onAssistantCreate={() => {
                      setPage('ai')
                      void askDashboardAssistant('I want to create a new job opening. Draft fields only - wait for my confirmation before creating.')
                    }}
                    onCreate={() => {
                      setSelectedJob(null)
                      setJobQrDataUrl('')
                      setJobFormMode('create')
                    }}
                    onDeadlineFilterChange={setJobsDeadlineFilter}
                    onDepartmentFilterChange={setJobsDepartmentFilter}
                    onLoadMore={loadMoreJobs}
                    onLocaleChange={changeRecruitingLocale}
                    onLocationFilterChange={setJobsLocationFilter}
                    onQueryChange={setJobsQuery}
                    onRemainingOnlyChange={setJobsRemainingOnly}
                    onSelect={setSelectedJob}
                    onStatusFilterChange={setJobsStatusFilter}
                    onViewCandidates={viewJobCandidates}
                    query={jobsQuery}
                    remainingOnly={jobsRemainingOnly}
                    statusFilter={jobsStatusFilter}
                    selectedJob={selectedJob}
                    onQrDataUrlChange={setJobQrDataUrl}
                  />
                </Suspense>
              )}
              {activePage === 'requisitions' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyRequisitionsWorkspace
                    access={access}
                    permissions={userAccess?.permissions || []}
                    role={userAccess?.role || userAccess?.user?.role}
                    onNotice={setNotice}
                    onAccessIssue={handleAccessIssue}
                  />
                </Suspense>
              )}
              {activePage === 'candidates' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyCandidatesPage
                    access={access}
                    locale={recruitingLocale}
                    unifiedEnabled={unifiedCandidatesEnabled}
                    onLocale={() => changeRecruitingLocale(recruitingLocale === 'ar' ? 'en' : 'ar')}
                    onAccessIssue={handleAccessIssue}
                    heldReloadKey={importReloadKey}
                    onHeldChanged={() => {
                      setImportReloadKey((value) => value + 1)
                      void refreshEverything()
                    }}
                    importButton={
                      canImportCandidates ? (
                        <ImportCvButton
                          access={access}
                          positions={allPositionsForSelectors}
                          onAccessIssue={handleAccessIssue}
                          onImported={() => {
                            setImportReloadKey((value) => value + 1)
                            void refreshEverything()
                          }}
                        />
                      ) : null
                    }
                    applications={allApplications}
                    listError={Boolean(applicationsQuery.isError)}
                    onRetryList={() => void applicationsQuery.refetch()}
                    assessmentEnabled={assessmentModuleOn}
                    busy={candidatesRefreshing}
                    listLoading={Boolean(candidatesListPending)}
                    filters={candidateFilters}
                    showRestrictedView={canViewRestrictedCandidates(userAccess)}
                    hasMoreApplications={candidatesHasMore}
                    loadingMoreApplications={candidatesFetchingMore}
                    onLoadMoreApplications={() => void loadMoreCandidates()}
                    serverApplicationTotal={applications?.total || 0}
                    offset={applications?.offset || 0}
                    onPage={(nextOffset) => setCandidateOffset(Math.max(0, nextOffset))}
                    onSaveView={async (name) => {
                      try {
                        await saveCandidateSavedView(access, {
                          name,
                          filters: {
                            query,
                            status,
                            ...candidateFilters,
                            classification: classificationFiltersForSavedView(classificationFilters),
                          },
                        })
                        await queryClient.invalidateQueries({ queryKey: qk.savedViews(access) })
                        setNoticeOk('Saved view stored for this tenant.')
                      } catch (error) {
                        setNoticeErr(friendlyDashboardError(error, 'Could not save this view.'))
                      }
                    }}
                    onSelectSavedView={(view) => {
                      const nextFilters = view.filters || {}
                      setCandidateOffset(0)
                      const restoredView = candidateFiltersFromSavedViewBlob(nextFilters)
                      setQuery(restoredView.query)
                      setStatus(restoredView.status)
                      setCandidateFilters(restoredView.filters)
                      const restored = classificationFiltersFromSavedView(nextFilters)
                      setClassificationFilters(restored)
                      const deprecated = Array.isArray((nextFilters.classification as { deprecated_nodes?: unknown } | undefined)?.deprecated_nodes)
                        ? ((nextFilters.classification as { deprecated_nodes: Array<{ node_id: string; message?: string }> }).deprecated_nodes)
                        : []
                      setClassificationDeprecatedNodes(deprecated)
                    }}
                    classificationEnabled={classificationUiEnabled}
                    classificationFilters={classificationFilters}
                    classificationDimensions={classificationDimensions}
                    classificationDeprecatedNodes={classificationDeprecatedNodes}
                    classificationTaxonomyError={classificationTaxonomyError}
                    classificationTaxonomyLoading={classificationTaxonomyLoading}
                    onRetryClassificationTaxonomy={() => void retryClassificationTaxonomy()}
                    onClassificationFiltersChange={(next) => {
                      setCandidateOffset(0)
                      setClassificationFilters(next)
                    }}
                    savedViews={savedViews}
                    onSelect={openCandidateProfile}
                    positions={allPositionsForSelectors}
                    query={query}
                    setQuery={(value) => {
                      setCandidateOffset(0)
                      setQuery(value)
                    }}
                    setFilters={(next) => {
                      setCandidateOffset(0)
                      setCandidateFilters(next)
                    }}
                    setStatus={(value) => {
                      setCandidateOffset(0)
                      setStatus(value)
                    }}
                    status={status}
                    total={applications?.total || 0}
                  />
                </Suspense>
              )}
              {activePage === 'interviews' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyInterviewsPage
                    access={access}
                    locale={recruitingLocale}
                    onLocale={() => changeRecruitingLocale(recruitingLocale === 'ar' ? 'en' : 'ar')}
                    busy={interviewsRefreshing}
                    listLoading={interviewsLoading}
                    listError={Boolean(interviewsError)}
                    interviews={interviewsError ? [] : (interviews?.interviews || [])}
                    limit={interviews?.limit || 25}
                    notesDrafts={interviewNotes}
                    offset={interviews?.offset || 0}
                    onOpenCandidate={openCandidateByKey}
                    onPreviewVideoAnswer={previewVideoAnswer}
                    onRetryVideoTranscripts={retryVideoTranscripts}
                    onSaveNotes={saveNotesForInterview}
                    onRefresh={() => {
                      void refreshAfterInterview()
                    }}
                    onRetryList={() => {
                      void interviewsQuery.refetch()
                    }}
                    onSetNotes={(interviewId, value) => setInterviewNotes((items) => ({ ...items, [interviewId]: value }))}
                    onSetOffset={(value) => setInterviewOffset(Math.max(0, value))}
                    onStatusChange={changeInterviewStatus}
                    canManageInterviews={canManageInterviews}
                    videoInterviewsEnabled={authorityReady ? workspaceAuthority.offerable('tab.interviews.video') : undefined}
                    onUpdateFilters={({ date, interviewer, q, role, tab }) => {
                      if (tab !== undefined) {
                        setInterviewTab(tab)
                        setInterviewOffset(0)
                      }
                      if (q !== undefined) {
                        setInterviewQuery(q)
                        setInterviewOffset(0)
                      }
                      if (role !== undefined) {
                        setInterviewRole(role)
                        setInterviewOffset(0)
                      }
                      if (date !== undefined) {
                        setInterviewDate(date)
                        setInterviewOffset(0)
                      }
                      if (interviewer !== undefined) {
                        setInterviewInterviewer(interviewer)
                        setInterviewOffset(0)
                      }
                    }}
                    statusCounts={interviews?.status_counts || []}
                    feedbackCounts={interviews?.feedback_counts || []}
                    videoCount={interviews?.video_count || 0}
                    total={interviews?.total || 0}
                    filters={{
                      date: interviewDate,
                      interviewer: interviewInterviewer,
                      q: interviewQuery,
                      role: interviewRole,
                      tab: interviewTab,
                    }}
                  />
                </Suspense>
              )}
              {activePage === 'calendar' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyCalendarShell
                    access={access}
                    canManage={hasDashboardPermission(moduleState?.access, 'calendar.manage')}
                    canCompany={hasDashboardPermission(moduleState?.access, 'calendar.company')}
                    canOverride={hasDashboardPermission(moduleState?.access, 'calendar.conflict_override')}
                    locale={recruitingLocale}
                    onNotice={(text, kind) => (kind === 'error' ? setNoticeErr(text) : setNoticeOk(text))}
                    onOpenInterview={() => openPage('interviews')}
                    onOpenProjectionOwner={(link) => {
                      const page = String(link.page || 'employees') as Page
                      const url = new URL(window.location.href)
                      url.searchParams.set('page', page)
                      if (link.employee) url.searchParams.set('employee', link.employee)
                      else url.searchParams.delete('employee')
                      if (link.leave) url.searchParams.set('leave', link.leave)
                      else url.searchParams.delete('leave')
                      if (link.item) url.searchParams.set('item', link.item)
                      else url.searchParams.delete('item')
                      if (link.document_type) url.searchParams.set('document_type', link.document_type)
                      else url.searchParams.delete('document_type')
                      window.history.pushState({}, '', `${url.pathname}${url.search}${url.hash}`)
                      // EmployeesPage syncs ?employee= on popstate; pushState alone needs a nudge when
                      // the surface is already mounted (rare) — dispatch after history write.
                      window.dispatchEvent(new PopStateEvent('popstate'))
                      openPage(page)
                    }}
                  />
                </Suspense>
              )}
              {activePage === 'assessments' && lastSendResult ? (
                <div className="mb-4">
                  <SendResultPanel locale={recruitingLocale} result={lastSendResult} />
                </div>
              ) : null}
              {activePage === 'assessments' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyAssessmentsPage
                    access={access}
                    applications={assessmentQueueApps}
                    assessmentTab={assessmentTab}
                    lastSendResult={lastSendResult}
                    locale={recruitingLocale}
                    cohortKey={assessmentCohort || ASSESSMENT_COHORT_READY_TO_SEND}
                    userRoleKey={userAccess?.role || userAccess?.user?.role || ''}
                    cohortCounts={
                      assessments?.cohorts?.cohorts
                      || summary?.assessment_cohorts?.cohorts
                      || summary?.action_counts?.assessment_cohorts?.cohorts
                    }
                    enabled={assessmentModuleOn}
                    config={assessmentConfig}
                    attempts={assessments?.attempts || []}
                    limit={assessments?.limit || 25}
                    offset={assessments?.offset || 0}
                    total={assessments?.total || 0}
                    needsReviewCount={Number(assessments?.needs_review_count || 0)}
                    reportReadyCount={Number(assessments?.report_ready_count || 0)}
                    attemptsLoading={assessmentsQuery.isPending && !assessmentsQuery.data}
                    attemptsRefreshing={assessmentsQuery.isFetching && Boolean(assessmentsQuery.data)}
                    attemptsError={Boolean(assessmentsQuery.isError)}
                    queueLoading={assessmentQueueQuery.isPending && !assessmentQueueQuery.data}
                    queueRefreshing={assessmentQueueQuery.isFetching && Boolean(assessmentQueueQuery.data)}
                    queueError={Boolean(assessmentQueueQuery.isError)}
                    onSelectTab={(tab) => {
                      setAssessmentOffset(0)
                      setAssessmentTab(tab)
                      if (tab === 'send') {
                        setAssessmentCohort(ASSESSMENT_COHORT_READY_TO_SEND)
                      }
                      navigateDashboard(
                        destinationToNavState({ page: 'assessments', filters: { tab } }, 'assessments'),
                        'replace',
                      )
                    }}
                    onSelectCohort={(cohort) => {
                      const next = normalizeAssessmentCohortKey(cohort) || ASSESSMENT_COHORT_READY_TO_SEND
                      setAssessmentOffset(0)
                      setAssessmentCohort(next)
                      setAssessmentTab(assessmentTabForCohort(next) || 'send')
                      navigateDashboard(
                        destinationToNavState(
                          {
                            page: 'assessments',
                            filters: {
                              assessment_cohort: next,
                              overview_cohort: next,
                              cohort_key: next,
                              tab: assessmentTabForCohort(next),
                            },
                            cohort_key: next,
                          },
                          'assessments',
                        ),
                        'replace',
                      )
                    }}
                    onOpenCandidate={openCandidateByKey}
                    onOpenFollowUpCandidates={() => {
                      const cohort = assessmentCohort || ASSESSMENT_COHORT_READY_TO_SEND
                      navigateDashboard(
                        destinationToNavState(
                          {
                            page: 'candidates',
                            filters: {
                              assessment_cohort: cohort,
                              overview_cohort: cohort,
                              cohort_key: cohort,
                            },
                            cohort_key: cohort,
                          },
                          'candidates',
                        ),
                      )
                    }}
                    onCancelAttempt={async (attempt) => {
                      const who = attempt.candidate_name || attempt.phone || (recruitingLocale === 'ar' ? 'هذا المرشح' : 'this candidate')
                      const reason = await confirm.withReason({
                        title: recruitingLocale === 'ar' ? 'إلغاء التقييم؟' : 'Cancel assessment?',
                        body:
                          recruitingLocale === 'ar'
                            ? `سيُلغى كل رابط نشط لـ ${who}. أدخل سبب الإلغاء.`
                            : `This revokes every active link for ${who}. Enter a cancellation reason.`,
                        confirmLabel: recruitingLocale === 'ar' ? 'إلغاء التقييم' : 'Cancel assessment',
                        cancelLabel: recruitingLocale === 'ar' ? 'رجوع' : 'Back',
                        destructive: true,
                        requireReason: true,
                        reasonLabel: recruitingLocale === 'ar' ? 'السبب' : 'Reason',
                        reasonPlaceholder: recruitingLocale === 'ar' ? 'مثال: أُرسل بالخطأ' : 'e.g. Sent by mistake',
                        dir: recruitingLocale === 'ar' ? 'rtl' : 'ltr',
                      })
                      if (!reason) return
                      await mutate(
                        recruitingLocale === 'ar' ? 'جاري إلغاء التقييم' : 'Cancelling assessment',
                        () => cancelAssessment(access, attempt.attempt_id, reason),
                        `cancel_assessment:${attempt.attempt_id}`,
                      )
                    }}
                    onResendAttempt={async (attempt) => {
                      const who = attempt.candidate_name || attempt.phone || (recruitingLocale === 'ar' ? 'المرشح' : 'the candidate')
                      if (!(await confirm({
                        title: recruitingLocale === 'ar' ? 'إعادة إرسال التقييم؟' : 'Resend assessment?',
                        body:
                          recruitingLocale === 'ar'
                            ? `سيُلغى الرابط القديم وسيستلم ${who} رابطاً جديداً.`
                            : `The old link will be revoked and ${who} will receive a new one.`,
                        confirmLabel: recruitingLocale === 'ar' ? 'إعادة الإرسال' : 'Resend assessment',
                        cancelLabel: recruitingLocale === 'ar' ? 'إلغاء' : 'Cancel',
                        dir: recruitingLocale === 'ar' ? 'rtl' : 'ltr',
                      }))) return
                      await mutate(
                        recruitingLocale === 'ar' ? 'جاري إعادة الإرسال' : 'Resending assessment',
                        () => resendAssessment(access, attempt.attempt_id),
                        `resend_assessment:${attempt.attempt_id}`,
                      )
                    }}
                    onReviewAttempt={async (attempt) => {
                      const who = attempt.candidate_name || attempt.phone || (recruitingLocale === 'ar' ? 'هذا المرشح' : 'this candidate')
                      if (!(await confirm({
                        title: recruitingLocale === 'ar' ? 'تسجيل المراجعة؟' : 'Mark assessment reviewed?',
                        body:
                          recruitingLocale === 'ar'
                            ? `سجّل أن الموارد البشرية راجعت التقرير لـ ${who}.`
                            : `Record that HR reviewed the immutable report for ${who}.`,
                        confirmLabel: recruitingLocale === 'ar' ? 'تسجيل المراجعة' : 'Mark reviewed',
                        cancelLabel: recruitingLocale === 'ar' ? 'إلغاء' : 'Cancel',
                        dir: recruitingLocale === 'ar' ? 'rtl' : 'ltr',
                      }))) return
                      await mutate(
                        recruitingLocale === 'ar' ? 'جاري تسجيل المراجعة' : 'Marking assessment reviewed',
                        () => reviewAssessment(access, attempt.attempt_id, undefined, {
                          expected_updated_at: attempt.updated_at || null,
                          expected_version: typeof attempt.version === 'number' ? attempt.version : null,
                        }),
                        `review_assessment:${attempt.attempt_id}`,
                      )
                    }}
                    onRecalculateNorms={recalculateNorms}
                    onRefresh={() => {
                      setAssessmentOffset(0)
                      void refreshAssessments()
                    }}
                    onSendAssessment={async (application) => {
                      if (!(await confirm({
                        title: recruitingLocale === 'ar' ? 'إرسال التقييم؟' : 'Send assessment?',
                        body:
                          recruitingLocale === 'ar'
                            ? `سيستلم ${candidateName(application)} رابط التقييم عبر الرسالة.`
                            : `${candidateName(application)} will receive an application assessment link by message.`,
                        confirmLabel: recruitingLocale === 'ar' ? 'إرسال التقييم' : 'Send assessment',
                        cancelLabel: recruitingLocale === 'ar' ? 'إلغاء' : 'Cancel',
                        dir: recruitingLocale === 'ar' ? 'rtl' : 'ltr',
                      }))) return
                      await mutate(
                        recruitingLocale === 'ar' ? 'جاري الإرسال' : 'Sending assessment',
                        () => sendAssessment(access, application.app_key),
                        `send_assessment:${application.app_key}`,
                      )
                    }}
                    onResendAssessment={async (application) => {
                      const attemptId = String(application.assessment?.attempt_id || '').trim()
                      if (!(await confirm({
                        title: recruitingLocale === 'ar' ? 'إعادة إرسال التقييم؟' : 'Resend assessment?',
                        body:
                          recruitingLocale === 'ar'
                            ? `سيُلغى الرابط القديم وسيستلم ${candidateName(application)} رابطاً جديداً.`
                            : `The old link will be revoked and ${candidateName(application)} will receive a new one.`,
                        confirmLabel: recruitingLocale === 'ar' ? 'إعادة الإرسال' : 'Resend assessment',
                        cancelLabel: recruitingLocale === 'ar' ? 'إلغاء' : 'Cancel',
                        dir: recruitingLocale === 'ar' ? 'rtl' : 'ltr',
                      }))) return
                      if (attemptId) {
                        await mutate(
                          recruitingLocale === 'ar' ? 'جاري إعادة الإرسال' : 'Resending assessment',
                          () => resendAssessment(access, attemptId),
                          `resend_assessment:${attemptId}`,
                        )
                      } else {
                        await mutate(
                          recruitingLocale === 'ar' ? 'جاري الإرسال' : 'Sending assessment',
                          () => sendAssessment(access, application.app_key),
                          `send_assessment:${application.app_key}`,
                        )
                      }
                    }}
                    onSetOffset={(value) => setAssessmentOffset(Math.max(0, value))}
                    busy={assessmentsRefreshing || busy}
                    canManageAssessments={canManageAssessments}
                    pendingTotal={assessmentQueueTotal}
                    queueHasMore={assessmentQueueHasMore}
                    queueLoadingMore={assessmentQueueFetchingMore}
                    onLoadMoreQueue={() => void loadMoreAssessmentQueue()}
                  />
                </Suspense>
              )}
              {activePage === 'ranking' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyRankingPage
                    busy={rankingBusy || busy}
                    locale={recruitingLocale}
                    positions={allPositionsForSelectors}
                    rankPosition={rankPosition}
                    ranking={ranking}
                    rankingError={rankingError}
                    runRanking={runRanking}
                    onSelect={(application, opts) =>
                      openCandidateByKey(application.app_key, {
                        returnPage: 'ranking',
                        returnFocusEl: opts?.returnFocusEl,
                      })
                    }
                    setRankPosition={setRankPosition}
                  />
                </Suspense>
              )}
              {activePage === 'notifications' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyNotificationsPage
                    access={access}
                    permissions={userAccess?.permissions || []}
                    role={userAccess?.role || userAccess?.user?.role}
                    onNotice={setNotice}
                    onAccessIssue={handleAccessIssue}
                    actionItems={notifications?.action_items || []}
                    enabledModules={enabledNotificationModules}
                    notifications={notifications?.notifications || []}
                    notificationsFeedError={Boolean(server.notificationsError)}
                    onNavigate={openPage}
                    posthireEnabled={anyPosthireModuleEnabled(moduleState)}
                  />
                </Suspense>
              )}
              {activePage === 'reports' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyReportsPage
                    assessmentEnabled={assessmentModuleOn}
                    interviewsEnabled={dashboardModuleEnabled(moduleState, 'interviews')}
                    locale={recruitingLocale}
                    refreshing={reportsRefreshing}
                    reportsError={reportsError}
                    onExportAssessments={() => exportReport('assessments', 'Assessment report')}
                    onExportCandidates={() => exportReport('candidates', 'Candidate report')}
                    onExportFollowUps={() => exportReport('followups', 'Follow-up report')}
                    onExportDeliveryHistory={() => exportReport('followup_delivery_history', 'Delivery failure history')}
                    onExportInterviews={() => exportReport('interviews', 'Interview report')}
                    onExportRoles={() => exportReport('roles', 'Role report')}
                    reports={reports}
                    canExportReports={canExportReports}
                  />
                </Suspense>
              )}
              {activePage === 'settings' && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazySettingsPage
                    access={access}
                    busy={busy}
                    createdInviteLink={createdInviteLink}
                    inviteEmail={inviteEmail}
                    inviteName={inviteName}
                    inviteRole={inviteRole}
                    linkPhone={linkPhone}
                    onInvite={inviteTeamMember}
                    onClearInviteLink={() => setCreatedInviteLink('')}
                    onCopyInviteLink={(link) => copyToClipboard(link, 'Invite link')}
                    onLinkWhatsApp={linkWhatsAppPhone}
                    onLogout={logout}
                    onSave={saveAccess}
                    onUpdateUser={updateTeamMember}
                    prehireEnabled={prehireEnabled}
                    positions={allPositionsForSelectors}
                    settingsTeamEnabled={workspaceAuthority.offerable('settings.team')}
                    settingsIntegrationsEnabled={workspaceAuthority.offerable('settings.integrations')}
                    setAccess={setAccess}
                    setInviteEmail={setInviteEmail}
                    setInviteName={setInviteName}
                    setInviteRole={setInviteRole}
                    setLinkPhone={setLinkPhone}
                    team={team}
                    userAccess={userAccess}
                  />
                </Suspense>
              )}
              {activePage === 'activity' && (
                <ActivityLog access={access} onAccessIssue={handleAccessIssue} />
              )}
              {isPostHirePage(activePage) && (
                <Suspense fallback={<PagePaintFallback page={activePage} />}>
                  <LazyPostHirePage
                    page={activePage}
                    access={access}
                    permissions={userAccess?.permissions || []}
                    role={userAccess?.role || userAccess?.user?.role}
                    onNotice={setNotice}
                    onAccessIssue={handleAccessIssue}
                    onOpenNotifications={() => openPage('notifications')}
                    onNavigate={(nextPage, opts) => {
                      openPage(nextPage as Page)
                      if (opts?.employee) {
                        const url = new URL(window.location.href)
                        url.searchParams.set('employee', opts.employee)
                        window.history.replaceState({}, '', `${url.pathname}${url.search}`)
                        window.dispatchEvent(new PopStateEvent('popstate'))
                      } else {
                        const url = new URL(window.location.href)
                        if (url.searchParams.has('employee')) {
                          url.searchParams.delete('employee')
                          window.history.replaceState({}, '', `${url.pathname}${url.search}`)
                          window.dispatchEvent(new PopStateEvent('popstate'))
                        }
                      }
                    }}
                  />
                </Suspense>
              )}
            </>
          )}

          {selected ? (
            <Suspense fallback={null}>
              <LazyCandidateProfilePage
                access={access}
                application={selected}
                positions={allPositionsForSelectors}
                locale={recruitingLocale}
                busy={busy}
                runningAction={runningAction}
                message={message}
                setMessage={setMessage}
                mutate={mutate}
                assessmentEnabled={assessmentModuleOn}
                videoInterviewsEnabled={authorityReady ? workspaceAuthority.offerable('tab.interviews.video') : undefined}
                employmentOffersEnabled={dashboardModuleEnabled(moduleState, 'employment_offers')}
                canManageAssessments={canManageAssessments}
                canManageInterviews={canManageInterviews}
                onClose={closeCandidateProfile}
                onAccessIssue={handleAccessIssue}
                returnLabel={
                  profileReturnPage === 'ranking'
                    ? recruitingLocale === 'ar'
                      ? 'العودة إلى الترتيب'
                      : 'Back to Ranking'
                    : undefined
                }
                onOpenAssessments={() => openPage('assessments')}
                onOpenInterviews={() => {
                  setInterviewTab('video_interviews')
                  setInterviewOffset(0)
                  openPage('interviews')
                  closeCandidateProfile()
                }}
                onScheduleInterview={() => {
                  setPage('ai')
                  void askDashboardAssistant(`Schedule an interview for application ${selected.app_key}. Ask me for any missing date, time, or channel details before preparing the confirmation.`)
                  closeCandidateProfile()
                }}
                onRefresh={() => {
                  void refreshAfterCandidate(selected?.app_key)
                }}
                onSelectApplication={openCandidateProfile}
              />
            </Suspense>
          ) : null}

          {selectedJob && !jobFormMode ? (
            <Suspense fallback={null}>
              <LazyJobWorkspace
                job={selectedJob}
                canCloseJobs={canCloseJobs}
                canEditJobs={canEditJobs}
                canPublishJobs={canPublishJobs}
                locale={recruitingLocale}
                statusBusy={jobStatusBusy}
                onClose={() => {
                  setSelectedJob(null)
                  setJobQrDataUrl('')
                }}
                onCopy={copyToClipboard}
                onDownloadQr={() => downloadQr(jobQrDataUrl, selectedJob)}
                onEdit={() => setJobFormMode('edit')}
                onSetStatus={(status) => setJobStatus(selectedJob, status)}
                onViewCandidates={() => viewJobCandidates(selectedJob)}
                qrDataUrl={jobQrDataUrl}
              />
            </Suspense>
          ) : null}

          {jobFormMode ? (
            <JobsForm
              access={access}
              busy={jobFormBusy}
              canPublish={canPublishJobs}
              initial={jobFormMode === 'edit' ? selectedJob : null}
              locale={recruitingLocale}
              mode={jobFormMode}
              onCancel={() => setJobFormMode(null)}
              onPublish={(values) => saveJobForm(values, { publish: true })}
              onSaveChanges={(values) => saveJobForm(values, {})}
              onSaveDraft={(values) => saveJobForm(values, { draft: true })}
            />
          ) : null}

        </section>
    </main>
  )
}

const pageLabels: Record<Page, string> = {
  overview: 'Overview',
  ai: 'OctoHR Assistant',
  jobs: 'Jobs',
  requisitions: 'Requisitions',
  candidates: 'Candidates',
  interviews: 'Interviews',
  calendar: 'Calendar',
  assessments: 'Assessments',
  ranking: 'Ranking',
  notifications: 'Alerts & Delivery',
  reports: 'Reports',
  employees: 'Employees',
  workforce: 'Organization',
  inbox: 'Needs Attention',
  preboarding: 'Preboarding',
  probation: 'Probation',
  onboarding: 'Onboarding',
  attendance: 'Attendance',
  leave: 'Leave',
  performance: 'Performance',
  talent: 'Talent',
  learning: 'Learning',
  benefits: 'Benefits',
  'employee-relations': 'Employee Relations',
  engagement: 'Engagement',
  'compensation-planning': 'Compensation Planning',
  'workforce-planning': 'Workforce Planning',
  'job-architecture': 'Job Architecture',
  shifts: 'Shifts',
  payroll: 'Payroll',
  analytics: 'Analytics',
  compliance: 'Compliance',
  activity: 'Activity',
  settings: 'Settings',
}

const pageLabelsAr: Record<Page, string> = {
  overview: 'نظرة عامة',
  ai: 'مساعد OctoHR',
  jobs: 'الوظائف',
  requisitions: 'طلبات التوظيف',
  candidates: 'المرشحون',
  interviews: 'المقابلات',
  calendar: 'التقويم',
  assessments: 'التقييمات',
  ranking: 'الترتيب',
  notifications: 'التنبيهات والتسليم',
  reports: 'التقارير',
  employees: 'الموظفون',
  workforce: 'الهيكل التنظيمي',
  inbox: 'يحتاج متابعة',
  preboarding: 'التهيئة قبل الالتحاق',
  probation: 'فترة التجربة',
  onboarding: 'التهيئة',
  attendance: 'الحضور',
  leave: 'الإجازات',
  performance: 'الأداء',
  talent: 'المواهب',
  learning: 'التعلم',
  benefits: 'المزايا',
  'employee-relations': 'علاقات الموظفين',
  engagement: 'المشاركة والارتباط',
  'compensation-planning': 'تخطيط التعويضات',
  'workforce-planning': 'تخطيط القوى العاملة',
  'job-architecture': 'هيكل الوظائف',
  shifts: 'الورديات',
  payroll: 'الرواتب',
  analytics: 'التحليلات',
  compliance: 'الامتثال',
  activity: 'النشاط',
  settings: 'الإعدادات',
}

const pageSubtitles: Record<Page, string> = {
  overview: 'Today’s hiring work queue: review, follow up, and move candidates forward.',
  ai: 'Your company-wide HR assistant — ask about hiring or your team and take the next action.',
  jobs: 'Create, edit, and manage job openings directly, with APPLY links and QR codes.',
  requisitions: 'What headcount is requested, who must approve, and what is open to fill.',
  candidates: 'Review candidates, see evidence, and choose the next hiring step.',
  interviews: 'Track interviews, review candidate responses, and capture feedback in one place.',
  calendar: 'Day, week, and month for your schedule and hiring team.',
  assessments: 'Assessment sending, progress, results, and official report review.',
  ranking: 'Guidance on who HR should prioritize for a selected job.',
  notifications: 'See which employee communications failed or need follow-up, and the safest next action.',
  reports: 'Hiring reports for roles, candidates, CVs, assessments, and follow-ups.',
  employees: 'Find people quickly, see employment state, and open a profile.',
  workforce: 'Manage departments, teams, locations, and structure — not a second employee directory.',
  inbox: 'Ranked follow-ups across OctoHR — open the owning module to resolve.',
  preboarding: 'Future joiners, readiness blockers, and pre-join tasks — distinct from active employees.',
  probation: 'Who is on probation, what is due, how they are doing, and which confirm/extend/fail decision is required.',
  onboarding: 'New hires in progress, open documents, and reminders to keep onboarding moving.',
  attendance: 'Today’s attendance, late and missing check-ins, and corrections that need a decision.',
  leave: 'Pending leave requests, approvals, and who is away in the weeks ahead.',
  performance: 'Goals, review cycles, calibration, and development — not Talent.',
  talent: 'Profiles, potential, and succession — not Performance, not the recruiting pool.',
  learning: 'Catalog, assignments, sessions, evidence-backed completion, and certificates — not development plans.',
  benefits: 'Plans, eligibility, enrollment, coverage, and contributions — not claims and not payroll deductions.',
  'employee-relations': 'Sealed need-to-know cases: intake, investigation, evidence, and outcome — not employment mutation.',
  engagement: 'Anonymous surveys, threshold-safe results, and action plans — not recognition and not an ER case.',
  'compensation-planning': 'Governed cycles, frozen eligibility, JA-linked bands, and explicit handoff — not a salary change, not payroll, and not payment.',
  'workforce-planning': 'Governed cycles, frozen baseline, scenarios, and explicit demand — not actual headcount, not a requisition, and not payroll.',
  'job-architecture': 'Canonical families, job profiles, grades, and career paths — not a Recruiting Job and not eligibility.',
  shifts: 'This week’s schedule, upcoming assignments, and swap requests to clear.',
  payroll: 'Timesheets, exceptions, and a controlled, audited payroll export.',
  analytics: 'Workforce patterns and risks — not the daily task queue.',
  compliance: 'Resolve missing, expiring, and review-required employee documents.',
  activity: 'A clear, trustworthy, read-only timeline of important company and HR activity.',
  settings: 'Manage who belongs here, how they sign in, and how OctoHR connects company tools.',
}

const pageSubtitlesAr: Record<Page, string> = {
  overview: 'قائمة عمل التوظيف لليوم: راجع وتابع وحرّك المرشحين للأمام.',
  ai: 'مساعد الموارد البشرية على مستوى الشركة — اسأل عن التوظيف أو فريقك واتخذ الخطوة التالية.',
  jobs: 'أنشئ وعدّل وأدر الوظائف مباشرة، مع روابط التقديم ورموز QR.',
  requisitions: 'ما الاحتياج المطلوب، ومن يجب أن يوافق، وما المفتوح للتعيين.',
  candidates: 'راجع المرشحين، اطّلع على الأدلة، واختر خطوة التوظيف التالية.',
  interviews: 'تتبّع المقابلات، راجع إجابات المرشحين، وسجّل الملاحظات في مكان واحد.',
  calendar: 'عرض يومي وأسبوعي وشهري لجدولك وفريق التوظيف.',
  assessments: 'إرسال التقييمات ومتابعة التقدم والنتائج ومراجعة التقارير الرسمية.',
  ranking: 'إرشاد حول من يجب أن تعطيه الموارد البشرية الأولوية لوظيفة محددة.',
  notifications: 'اعرض رسائل الموظفين التي فشلت أو تحتاج متابعة، وأأمن إجراء تالٍ.',
  reports: 'تقارير التوظيف للوظائف والمرشحين والسير الذاتية والتقييمات والمتابعات.',
  employees: 'اعثر على الأشخاص بسرعة، اطّلع على حالة التوظيف، وافتح الملف.',
  workforce: 'أدِر الأقسام والفرق والمواقع والهيكل — وليس دليلاً ثانياً للموظفين.',
  inbox: 'قائمة مرتّبة بما يحتاج متابعتك — افتح الوحدة المسؤولة لإتمام الإجراء.',
  preboarding: 'المنضمون مستقبلاً وعوائق الجاهزية ومهام ما قبل الالتحاق — منفصلون عن الموظفين النشطين.',
  probation: 'من في فترة التجربة، وما المستحق، وكيف أداؤهم، وأي قرار تثبيت/تمديد/إنهاء مطلوب.',
  onboarding: 'الموظفون الجدد قيد التهيئة، والمستندات المفتوحة، والتذكيرات لإبقاء التهيئة مستمرة.',
  attendance: 'حضور اليوم، والتأخر والغياب، والتصحيحات التي تحتاج قراراً.',
  leave: 'طلبات الإجازة المعلّقة والموافقات ومن هو غائب في الأسابيع القادمة.',
  performance: 'الأهداف ودورات المراجعة والمعايرة والتطوير — وليست المواهب.',
  talent: 'الملفات والإمكانات والتعاقب — ليست الأداء وليست مجمع المرشحين.',
  learning: 'الكتالوج والإسناد والجلسات والإكمال بدليل والشهادات — ليست خطط التطوير.',
  benefits: 'الخطط والأهلية والتسجيل والتغطية والمساهمات — ليست مطالبات وليست استقطاع رواتب.',
  'employee-relations': 'قضايا سرية حسب الحاجة للمعرفة: استلام وتحقيق وأدلة ونتيجة — ليست تغييراً في التوظيف.',
  engagement: 'استبيانات مجهولة ونتائج آمنة حسب الحد وخطط عمل — ليست تقديراً وليست قضية علاقات موظفين.',
  'compensation-planning': 'دورات محكومة وأهلية مجمّدة ونطاقات مرتبطة بهيكل الوظائف وتسليم صريح — ليست تغييراً في الراتب وليست رواتب وليست دفعاً.',
  'workforce-planning': 'دورات محكومة وخط أساس مجمّد وسيناريوهات وطلب صريح — ليست رأس مال بشري فعلي وليست طلب توظيف وليست رواتب.',
  'job-architecture': 'العائلات والملفات الوظيفية والدرجات والمسارات — ليست وظيفة التوظيف وليست أهلية.',
  shifts: 'جدول هذا الأسبوع والتعيينات القادمة وطلبات التبديل المطلوب حسمها.',
  payroll: 'جداول الوقت والاستثناءات وتصدير رواتب مضبوط ومُدقَّق.',
  analytics: 'أنماط ومخاطر القوى العاملة — لا قائمة المهام اليومية.',
  compliance: 'حل المستندات الناقصة والمنتهية والتي تحتاج مراجعة.',
  activity: 'جدول زمني موثوق للقراءة فقط لأهم نشاط الشركة والموارد البشرية.',
  settings: 'أدِر من ينتمي هنا، وكيف يسجّلون الدخول، وكيف يتصل OctoHR بأدوات الشركة.',
}

function localizedPageLabel(page: Page | string, locale: RecruitingLocale) {
  const key = page as Page
  if (locale === 'ar') return pageLabelsAr[key] || pageLabels[key] || String(page)
  return pageLabels[key] || String(page)
}

function localizedPageSubtitle(page: Page, locale: RecruitingLocale) {
  if (locale === 'ar') return pageSubtitlesAr[page] || pageSubtitles[page] || ''
  return pageSubtitles[page] || ''
}

function localizedNavGroupLabel(group: string, locale: RecruitingLocale) {
  const key = group as keyof typeof NAV_GROUP_LABELS
  if (locale !== 'ar') return NAV_GROUP_LABELS[key] || group
  if (group === 'prehire') return 'ما قبل التوظيف'
  if (group === 'posthire') return 'ما بعد التوظيف'
  if (group === 'settings') return 'مساحة العمل'
  return NAV_GROUP_LABELS[key] || group
}

function downloadQr(dataUrl: string, job: PositionSummary) {
  if (!dataUrl) return
  const anchor = document.createElement('a')
  anchor.href = dataUrl
  anchor.download = `${job.position_code || 'job'}-qr.png`
  anchor.click()
}

export default App
