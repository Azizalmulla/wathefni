import {
  Activity,
  AlertTriangle,
  ArrowUp,
  BarChart3,
  Bell,
  BriefcaseBusiness,
  CalendarCheck,
  CalendarClock,
  CheckCircle2,
  Circle,
  ClipboardCheck,
  Clock,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Inbox,
  LayoutDashboard,
  LogOut,
  Loader2,
  Medal,
  MessageCircle,
  PauseCircle,
  Pencil,
  Plus,
  QrCode,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  UserCheck,
  Users,
  Video,
  Wallet,
} from 'lucide-react'
import QRCode from 'qrcode'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'

import { PostHireDeliveryCenter, PostHirePage, type PostHireModulePage } from '@/posthire/PostHire'
import { useConfirm } from '@/components/ConfirmDialog'
import {
  anyPeopleModuleEnabled as peopleModulesEnabled,
  anyPosthireModuleEnabled as posthireModulesEnabled,
  isAlertsAndDeliveryRelevant,
  isPostHireNavPage,
} from '@/lib/moduleWorkspace'

import {
  acceptDashboardInvite,
  DashboardApiError,
  getDashboardBootstrap,
  getDashboardTeam,
  getDashboardChatSession,
  getDashboardChatSessions,
  getApplications,
  getAssessmentConfig,
  getAssessments,
  getImportSettings,
  updateImportSettings,
  getPrehireReports,
  getPrehirePositions,
  setPositionStatus,
  getInterviews,
  getNotifications,
  getPrehireWorkQueue,
  getRanking,
  getSetupReadiness,
  getSummary,
  downloadPrehireReport,
  generateCandidateEvaluation,
  checkMailboxNow,
  connectMailbox,
  disconnectMailbox,
  getMailboxConnections,
  getMailboxLabels,
  hireCandidate,
  inviteDashboardUser,
  linkDashboardWhatsApp,
  updateMailbox,
  loginDashboard,
  logoutDashboard,
  notifyCandidate,
  cancelAssessment,
  previewVideoInterviewAnswer,
  previewAssessmentReport,
  previewCandidateCv,
  recalculateAssessmentNorms,
  rejectCandidate,
  retryVideoInterviewTranscripts,
  saveInterviewNotes,
  sendVideoInterview,
  sendAssessment,
  resendAssessment,
  reviewAssessment,
  shortlistCandidate,
  startDashboardChatSession,
  streamDashboardChat,
  updateDashboardUser,
  updateInterviewStatus,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  actionLabel as recruitingActionLabel,
  canonicalStageLabel,
  communicationLabel,
  facetStatusLabel,
  intakeSourceLabel,
  recruitingCopy,
  workflowItemLabel,
  type RecruitingLocale,
} from '@/lib/recruitingLifecycle'
import {
  dedupeWorkQueueItems,
  roleActiveBadge,
  roleBottleneckLabel,
  workQueueDisplayTotal,
} from '@/lib/prehireOverviewPresentation'
import { cn, compactNumber, formatDateTime, statusTone } from '@/lib/utils'
import { ActivityLog } from '@/components/ActivityLog'
import { ImportCvButton, ImportReviewQueue } from '@/components/ImportCenter'
import { OfferPanel } from '@/components/OfferPanel'
import { Product2AuthoringPanel } from '@/components/Product2AuthoringPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/field'
import { SearchInput, useDebouncedValue } from '@/components/ui/search-input'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import type {
  ApplicationSummary,
  ApplicationsResponse,
  AssessmentConfigResponse,
  AssessmentsResponse,
  AssessmentAttempt,
  CandidateInterview,
  DashboardAccess,
  DashboardBootstrapResponse,
  DashboardChatCandidateCard,
  DashboardChatNavigation,
  DashboardChatResponse,
  DashboardChatSession,
  DashboardChatStoredMessage,
  DashboardModuleDefinition,
  DashboardTeamResponse,
  DashboardTeamUser,
  DashboardUserAccess,
  MailboxConnection,
  MailboxFeatureStatus,
  MutationResponse,
  InterviewsResponse,
  NotificationActionItem,
  NotificationsResponse,
  NotificationRow,
  PositionsResponse,
  PositionSummary,
  PrehireNextAction,
  PrehireReportsResponse,
  PrehireRolePriority,
  PrehireWorkQueueItem,
  PrehireWorkQueueResponse,
  RankingCandidate,
  RankingResponse,
  SetupReadinessResponse,
  SummaryResponse,
} from '@/types'

type Page =
  | 'overview'
  | 'ai'
  | 'jobs'
  | 'candidates'
  | 'interviews'
  | 'assessments'
  | 'ranking'
  | 'notifications'
  | 'reports'
  | 'employees'
  | 'onboarding'
  | 'attendance'
  | 'leave'
  | 'shifts'
  | 'payroll'
  | 'analytics'
  | 'compliance'
  | 'activity'
  | 'settings'
type NavGroup = 'prehire' | 'posthire' | 'settings'
type DashboardNavItem = { id: Page; label: string; icon: typeof LayoutDashboard; module?: string; group: NavGroup }

const NAV_GROUP_LABELS: Record<NavGroup, string> = { prehire: 'Pre-Hiring', posthire: 'Post-Hire', settings: 'Workspace' }

type DashboardModuleState = {
  enabled_modules?: string[]
  access?: DashboardUserAccess
  module_catalog?: DashboardModuleDefinition[]
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

function isPostHirePage(page: Page): page is PostHireModulePage {
  return isPostHireNavPage(page)
}
type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  candidateCards?: DashboardChatCandidateCard[]
  navigation?: DashboardChatNavigation[]
  confirmation?: { label?: string | null; summary?: string | null; status?: string | null; is_active?: boolean; pending_action_id?: string } | null
  isStreaming?: boolean
}
type InterviewTruth = CandidateInterview | NonNullable<ApplicationSummary['interview']>
type CandidateFilters = {
  position: string
  cvStatus: string
  assessmentStatus: string
  interviewStatus: string
  followUp: string
  reviewStatus: string
  activityFrom: string
  activityTo: string
  sort: string
}
const statuses = [
  '',
  'awaiting_cv',
  'cv_processing',
  'ready_for_review',
  'shortlisted',
  'interview',
  'hired',
  'rejected',
  'withdrawn',
  // Legacy aliases still filterable until data is remapped.
  'cv_received',
  'screening',
  'screening_complete',
  'review_pending',
]

const navItems: DashboardNavItem[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, module: 'pre_hiring', group: 'prehire' },
  { id: 'ai', label: 'Wathefni Assistant', icon: MessageCircle, module: 'pre_hiring', group: 'prehire' },
  { id: 'jobs', label: 'Jobs', icon: BriefcaseBusiness, module: 'pre_hiring', group: 'prehire' },
  { id: 'candidates', label: 'Candidates', icon: Users, module: 'pre_hiring', group: 'prehire' },
  { id: 'interviews', label: 'Interviews', icon: CalendarCheck, module: 'pre_hiring', group: 'prehire' },
  { id: 'assessments', label: 'Assessments', icon: ClipboardCheck, module: 'assessments', group: 'prehire' },
  { id: 'ranking', label: 'Ranking', icon: Medal, module: 'pre_hiring', group: 'prehire' },
  { id: 'notifications', label: 'Alerts & Delivery', icon: Bell, group: 'settings' },
  { id: 'reports', label: 'Reports', icon: BarChart3, module: 'pre_hiring', group: 'prehire' },
  { id: 'employees', label: 'Employees', icon: Users, group: 'posthire' },
  { id: 'onboarding', label: 'Onboarding', icon: UserCheck, module: 'onboarding', group: 'posthire' },
  { id: 'attendance', label: 'Attendance', icon: CalendarCheck, module: 'attendance', group: 'posthire' },
  { id: 'leave', label: 'Leave', icon: CalendarClock, module: 'leave', group: 'posthire' },
  { id: 'shifts', label: 'Shifts', icon: Clock, module: 'shifts', group: 'posthire' },
  { id: 'payroll', label: 'Payroll', icon: Wallet, module: 'payroll', group: 'posthire' },
  { id: 'analytics', label: 'Analytics', icon: BarChart3, module: 'analytics', group: 'posthire' },
  { id: 'compliance', label: 'Compliance', icon: ShieldCheck, module: 'compliance', group: 'posthire' },
  { id: 'activity', label: 'Activity', icon: Activity, group: 'settings' },
  { id: 'settings', label: 'Settings', icon: Settings, group: 'settings' },
]

// Modules that are real once enabled live in navItems (gated by enabled_modules).
// This list is for genuinely-future tools with no backend yet; empty for now.
const futureModuleItems: Array<{ label: string; module: string }> = []

function storedAccess(): DashboardAccess {
  return {
    token: localStorage.getItem('wathefni_dashboard_token') || '',
    hrPhone: localStorage.getItem('wathefni_hr_phone') || '',
    companyCode: localStorage.getItem('wathefni_company_code') || 'WATHEFNI',
    email: localStorage.getItem('wathefni_dashboard_email') || '',
    password: '',
  }
}

function normalizedAccess(access: DashboardAccess): DashboardAccess {
  return {
    token: access.token.trim(),
    hrPhone: access.hrPhone.trim(),
    companyCode: access.companyCode.trim().toUpperCase() || 'WATHEFNI',
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
  }
}

function hasDashboardPermission(access: DashboardUserAccess | null | undefined, permission: string) {
  return Boolean(access?.permissions?.includes(permission))
}

function dashboardModuleEnabled(state: DashboardModuleState, module: string) {
  if (!state || !Array.isArray(state.enabled_modules)) return false
  return state.enabled_modules.includes(module)
}

// Suggested starter prompts for the assistant, scoped to the modules the company
// has actually enabled. When modules are unknown we fall back to recruiting prompts
// (pre-hiring is always present), so an unconfigured workspace still has guidance.
function assistantPromptChips(enabledModules: string[] | undefined, assessmentEnabled: boolean): string[] {
  const known = Array.isArray(enabledModules)
  const has = (module: string) => !known || enabledModules!.includes(module)
  const chips: string[] = []
  if (has('pre_hiring')) chips.push('Review candidates', 'Show rankings')
  if (assessmentEnabled) chips.push('Who needs an assessment?')
  if (has('onboarding')) chips.push('Who is still onboarding?')
  if (has('attendance')) chips.push('Who was late today?')
  if (has('leave')) chips.push('Pending leave requests')
  if (has('shifts')) chips.push('Open shifts this week')
  if (has('payroll')) chips.push('Payroll exceptions to review')
  if (has('compliance')) chips.push('Documents expiring soon')
  if (has('analytics')) chips.push('Headcount summary')
  if (chips.length === 0) chips.push('What can you help me with?')
  return chips.slice(0, 6)
}

function pageAvailableForSummary(page: Page, state: DashboardModuleState) {
  if (page === 'employees') return anyPeopleModuleEnabled(state)
  // Alerts & Delivery is a shared Workspace surface (page id: notifications).
  if (page === 'notifications') return isAlertsAndDeliveryRelevant(state?.enabled_modules, workspaceCatalog(state))
  const item = navItems.find((nav) => nav.id === page)
  return !item?.module || dashboardModuleEnabled(state, item.module)
}

const PERMISSION_CAPABILITY_LABELS: Record<string, string> = {
  'prehire.read': 'View hiring dashboards, candidates, and reports',
  'candidate.manage': 'Manage candidate profiles and application details',
  'candidate.import': 'Bulk import candidate CVs',
  'candidate.decide': 'Make final candidate decisions',
  'interview.manage': 'Schedule interviews and manage video interview reviews',
  'assessment.manage': 'Send assessments and review candidate results',
  'report.export': 'Download hiring reports and exports',
  'settings.manage': 'Manage company hiring settings',
  'users.manage': 'Manage team access',
  'employees.read': 'View the employee directory and profiles',
  'employees.manage': 'Create, edit, and import employees',
  'employees.status.approve': 'Approve employee status transitions',
  'onboarding.read': 'View employee onboarding progress',
  'onboarding.manage': 'Manage onboarding and send reminders',
  'attendance.read': 'View attendance records',
  'attendance.manage': 'Correct and manage attendance',
  'leave.read': 'View leave requests and balances',
  'leave.request': 'Submit leave requests',
  'leave.decide': 'Approve or decline leave requests',
  'shifts.read': 'View shift schedules',
  'shifts.manage': 'Schedule shifts and approve swaps',
  'payroll.read': 'View timesheets and payroll',
  'payroll.manage': 'Review and approve timesheets',
  'payroll.export': 'Export payroll runs',
  'analytics.read': 'View workforce analytics',
  'compliance.read': 'View employee document compliance',
  'compliance.manage': 'Manage compliance and send document reminders',
}

const ROLE_LABELS_UI: Record<string, string> = {
  owner: 'Owner / Admin',
  hr_manager: 'HR Manager',
  manager: 'Team Manager',
  recruiter: 'Recruiter / HR Officer',
  hiring_manager: 'Hiring Manager',
  viewer: 'Viewer',
}

// Humanize an unmapped permission key like "payroll.export" -> "Payroll export"
// so we never surface raw backend keys in the UI.
function humanizePermission(permission: string): string {
  return permission
    .split('.')
    .map((part) => part.replace(/_/g, ' '))
    .join(' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function readableCapabilities(access: DashboardUserAccess | null | undefined) {
  return (access?.permissions || []).map((permission) => PERMISSION_CAPABILITY_LABELS[permission] || humanizePermission(permission)).filter(Boolean)
}

function isRecoveryAccess(access: DashboardUserAccess | null | undefined) {
  const email = access?.user?.email || ''
  return Boolean(access?.is_recovery_access || access?.user?.is_recovery_access || email.endsWith('.wathefni.local'))
}

function currentUserTeamRow(access: DashboardUserAccess | null | undefined): DashboardTeamUser | null {
  const user = access?.user
  if (!user?.user_id || !user.email) return null
  return {
    user_id: user.user_id,
    company_code: user.company_code || 'WATHEFNI',
    email: user.email,
    name: user.name,
    phone: user.phone,
    role: user.role || access?.role || 'viewer',
    role_label: user.role_label || access?.role_label,
    status: user.status || 'active',
    last_active_at: user.last_active_at,
    permissions: access?.permissions,
    auth_source: user.auth_source || access?.auth_source,
    is_recovery_access: user.is_recovery_access || access?.is_recovery_access,
  }
}

function dashboardInviteLink(token: string) {
  const url = new URL('/dashboard', window.location.origin)
  url.searchParams.set('invite', token)
  return url.toString()
}

function safeDeliveryErrorLabel(value: string | null | undefined) {
  const normalized = String(value || '').toLowerCase()
  if (normalized.includes('invalid_grant') || normalized.includes('token') || normalized.includes('gmail_auth')) return 'Email needs reconnecting'
  if (normalized.includes('no_usable_conversation_id') || normalized.includes('conversation_closed') || normalized.includes('conversation_inactive')) {
    return 'WhatsApp conversation is not active'
  }
  return value ? 'Delivery needs attention' : 'No issue reported'
}

function transcriptStatusLabel(value: string | null | undefined) {
  const normalized = String(value || '').toLowerCase()
  if (['completed', 'ready'].includes(normalized)) return 'Ready'
  if (['failed', 'error'].includes(normalized)) return 'Needs retry'
  return 'Preparing summary'
}

function initialAccessIssue() {
  const saved = normalizedAccess(storedAccess())
  return !saved.token || !saved.companyCode ? missingAccessIssue(saved) : null
}

function missingAccessIssue(access: DashboardAccess): AccessIssue {
  if (!access.token.trim()) {
    return {
      code: 'dashboard_auth_failed',
      title: 'Sign in to Wathefni',
      description: 'Use your workspace email and password to open the company dashboard.',
    }
  }
  return {
    code: 'dashboard_company_required',
    title: 'Sign in to Wathefni',
    description: 'Add your company code once so Wathefni can verify the workspace before loading hiring data.',
  }
}

function App() {
  const [access, setAccess] = useState<DashboardAccess>(() => normalizedAccess(storedAccess()))
  const [page, setPage] = useState<Page>(() => (new URLSearchParams(window.location.search).get('page') === 'settings' ? 'settings' : 'overview'))
  const [lastWorkPage, setLastWorkPage] = useState<Page>('overview')
  const [recruitingLocale, setRecruitingLocale] = useState<RecruitingLocale>(() =>
    localStorage.getItem('wathefni_recruiting_locale') === 'ar' ? 'ar' : 'en',
  )
  const [workspaceBootstrap, setWorkspaceBootstrap] = useState<DashboardBootstrapResponse | null>(null)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [applications, setApplications] = useState<ApplicationsResponse | null>(null)
  const [interviews, setInterviews] = useState<InterviewsResponse | null>(null)
  const [assessments, setAssessments] = useState<AssessmentsResponse | null>(null)
  const [assessmentConfig, setAssessmentConfig] = useState<AssessmentConfigResponse | null>(null)
  const [ranking, setRanking] = useState<RankingResponse | null>(null)
  const [notifications, setNotifications] = useState<NotificationsResponse | null>(null)
  const [reports, setReports] = useState<PrehireReportsResponse | null>(null)
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
  const [jobsData, setJobsData] = useState<PositionsResponse | null>(null)
  const [allPositions, setAllPositions] = useState<PositionSummary[]>([])
  const [jobsQuery, setJobsQuery] = useState('')
  const debouncedJobsQuery = useDebouncedValue(jobsQuery.trim(), 350)
  const [jobsLoadingMore, setJobsLoadingMore] = useState(false)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [candidateFilters, setCandidateFilters] = useState<CandidateFilters>({
    position: '',
    cvStatus: '',
    assessmentStatus: '',
    interviewStatus: '',
    followUp: '',
    reviewStatus: '',
    activityFrom: '',
    activityTo: '',
    sort: 'newest',
  })
  const [workQueue, setWorkQueue] = useState<PrehireWorkQueueResponse | null>(null)
  const [candidateOffset, setCandidateOffset] = useState(0)
  const [rankPosition, setRankPosition] = useState('')
  const [interviewTab, setInterviewTab] = useState('upcoming')
  const [interviewQuery, setInterviewQuery] = useState('')
  const [interviewRole, setInterviewRole] = useState('')
  const [interviewDate, setInterviewDate] = useState('')
  const [interviewInterviewer, setInterviewInterviewer] = useState('')
  const [interviewOffset, setInterviewOffset] = useState(0)
  const [assessmentOffset, setAssessmentOffset] = useState(0)
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
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatConversationId, setChatConversationId] = useState(() => dashboardChatConversationId(access))
  const [chatSessions, setChatSessions] = useState<DashboardChatSession[]>([])
  const [chatHistoryOpen, setChatHistoryOpen] = useState(false)
  const [newChatConfirmOpen, setNewChatConfirmOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [runningAction, setRunningAction] = useState<string | null>(null)
  const [importReloadKey, setImportReloadKey] = useState(0)
  const [notice, setNoticeState] = useState<{ text: string; tone: 'info' | 'success' | 'error' }>(() => ({
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
  const [accessIssue, setAccessIssue] = useState<AccessIssue | null>(() => initialAccessIssue())
  const handleAccessIssue = useCallback((issue: AccessIssue) => {
    setAccessIssue(issue)
  }, [])

  const moduleState: DashboardModuleState = workspaceBootstrap || summary
  const prehireEnabled = dashboardModuleEnabled(moduleState, 'pre_hiring')
  const allApplications = applications?.applications || summary?.recent_applications || []
  const enabledNotificationModules = notifications?.enabled_modules
  const assessmentModuleOn = assessmentModuleEnabled(moduleState, summary)
  const availableNavItems = navItems.filter((item) => {
    if (item.id === 'employees') return anyPeopleModuleEnabled(moduleState)
    if (item.id === 'notifications') return isAlertsAndDeliveryRelevant(moduleState?.enabled_modules, workspaceCatalog(moduleState))
    if (item.id === 'activity') return hasDashboardPermission(moduleState?.access, 'audit.read')
    return !item.module || dashboardModuleEnabled(moduleState, item.module)
  })
  const defaultWorkspacePage = prehireEnabled
    ? 'overview'
    : availableNavItems.find((item) => item.group === 'posthire')?.id || 'settings'
  const activePage = pageAvailableForSummary(page, moduleState) ? page : defaultWorkspacePage
  const pageTitle = pageLabels[activePage]
  const dashboardLoaded = Boolean(moduleState && (!prehireEnabled || (summary && applications && notifications && interviews && reports)))
  const userAccess = moduleState?.access || null
  const showingInviteAcceptance = Boolean(inviteToken.trim())
  const canImportCandidates = hasDashboardPermission(userAccess, 'candidate.import')
  const canManageInterviews = hasDashboardPermission(userAccess, 'interview.manage')
  const canManageAssessments = hasDashboardPermission(userAccess, 'assessment.manage')
  const canExportReports = hasDashboardPermission(userAccess, 'report.export')
  const canManageWorkspace = hasDashboardPermission(userAccess, 'users.manage')
  const canManageJobs = hasDashboardPermission(userAccess, 'settings.manage')
  // Position pickers (candidate filter, CV-import assignment, ranking, overview
  // breakdown) need the FULL roster of jobs, not just the top 25 by activity
  // that `summary.positions` carries for the dashboard glance. Loaded via its
  // own unsearched, unpaginated fetch (see loadAllPositions) — deliberately
  // NOT sourced from `jobsData`, which is search-scoped to whatever the Jobs
  // page's own search box currently holds.
  const allPositionsForSelectors = allPositions.length ? allPositions : summary?.positions || []

  useEffect(() => {
    let cancelled = false
    async function renderQr() {
      const value = selectedJob?.qr_value || selectedJob?.application_link || ''
      if (!value) {
        setJobQrDataUrl('')
        return
      }
      const dataUrl = await QRCode.toDataURL(value, { margin: 2, width: 220 })
      if (!cancelled) setJobQrDataUrl(dataUrl)
    }
    renderQr().catch(() => setJobQrDataUrl(''))
    return () => {
      cancelled = true
    }
  }, [selectedJob])

  function openPage(nextPage: Page) {
    if (!pageAvailableForSummary(nextPage, moduleState)) {
      setNoticeErr('This feature is not enabled for this company.')
      setPage(defaultWorkspacePage)
      return
    }
    // Remember the last real module page so the assistant (its own page) knows
    // where HR was working and can bias its help toward that area.
    if (nextPage !== 'ai' && nextPage !== 'settings') {
      setLastWorkPage(nextPage)
    }
    setPage(nextPage)
  }

  // Candidate list: fetched on its own so filter/search/pagination changes only
  // refetch this list, never the whole dashboard.
  const loadApplications = useCallback(
    async (nextAccess = access, opts: { silent?: boolean } = {}) => {
      const effectiveAccess = normalizedAccess(nextAccess)
      if (!effectiveAccess.token || !effectiveAccess.companyCode) return
      try {
        const applicationsData = await getApplications(effectiveAccess, {
          q: query,
          status,
          position: candidateFilters.position,
          cv_status: candidateFilters.cvStatus,
          assessment_status: candidateFilters.assessmentStatus,
          interview_status: candidateFilters.interviewStatus,
          follow_up: candidateFilters.followUp,
          review_status: candidateFilters.reviewStatus,
          activity_from: candidateFilters.activityFrom,
          activity_to: candidateFilters.activityTo,
          sort: candidateFilters.sort,
          limit: 50,
          offset: candidateOffset,
        })
        setApplications(applicationsData)
        setSelected((current) => {
          if (!current) return null
          return applicationsData.applications.find((item) => item.app_key === current.app_key) || current
        })
      } catch (error) {
        if (opts.silent) return
        const issue = accessIssueFromError(error)
        if (issue) {
          setAccessIssue(issue)
          setNotice(issue.title)
        } else {
          setNoticeErr(friendlyDashboardError(error, 'Could not load candidates.'))
        }
      }
    },
    [access, query, status, candidateFilters, candidateOffset],
  )

  // Jobs list: fetched on its own (not from the summary card, which only
  // returns a capped top-N glance) so the Jobs page can search/page through
  // every posting a company has, instead of silently truncating.
  const loadJobs = useCallback(
    async (nextAccess = access, opts: { silent?: boolean } = {}) => {
      const effectiveAccess = normalizedAccess(nextAccess)
      if (!effectiveAccess.token || !effectiveAccess.companyCode) return
      try {
        const data = await getPrehirePositions(effectiveAccess, {
          limit: 100,
          ...(debouncedJobsQuery ? { search: debouncedJobsQuery } : {}),
        })
        setJobsData(data)
      } catch (error) {
        if (opts.silent) return
        const issue = accessIssueFromError(error)
        if (issue) {
          setAccessIssue(issue)
          setNotice(issue.title)
        } else {
          setNoticeErr(friendlyDashboardError(error, 'Could not load jobs.'))
        }
      }
    },
    [access, debouncedJobsQuery],
  )

  // Full, unsearched, unpaginated position roster for the pickers reused
  // elsewhere (candidate filter, CV-import assignment, ranking, overview
  // breakdown). Deliberately independent of `jobsData`/`loadJobs`, which is
  // scoped to whatever the Jobs page's own search box currently holds — those
  // pickers must never go empty just because HR is mid-search on the Jobs page.
  // 200 is the backend's own ceiling for this endpoint; a single company
  // realistically never has more open+closed job postings than that.
  const loadAllPositions = useCallback(async (nextAccess = access) => {
    const effectiveAccess = normalizedAccess(nextAccess)
    if (!effectiveAccess.token || !effectiveAccess.companyCode) return
    try {
      const data = await getPrehirePositions(effectiveAccess, { limit: 200 })
      setAllPositions(data.positions)
    } catch {
      // Best-effort: pickers fall back to the summary glance on failure.
    }
  }, [access])

  const loadMoreJobs = useCallback(async () => {
    const effectiveAccess = normalizedAccess(access)
    if (!effectiveAccess.token || !effectiveAccess.companyCode) return
    setJobsLoadingMore(true)
    try {
      const data = await getPrehirePositions(effectiveAccess, {
        limit: 100,
        offset: jobsData?.positions.length || 0,
        ...(debouncedJobsQuery ? { search: debouncedJobsQuery } : {}),
      })
      setJobsData((current) =>
        current
          ? { ...data, positions: [...current.positions, ...data.positions] }
          : data,
      )
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not load more jobs.'))
    } finally {
      setJobsLoadingMore(false)
    }
  }, [access, jobsData, debouncedJobsQuery])

  const [jobStatusBusy, setJobStatusBusy] = useState(false)

  // Close stops new WhatsApp/QR applicants; reopen resumes the same
  // apply_code/QR unchanged. Existing candidates in the pipeline are never
  // affected either way.
  const setJobStatus = useCallback(
    async (job: PositionSummary, status: 'open' | 'closed') => {
      if (status === 'closed') {
        const ok = await confirm({
          title: `Close ${job.position_title || job.position_code}?`,
          body: Number(job.active_count || 0) > 0
            ? `This stops new applicants from applying. ${job.active_count} candidate${Number(job.active_count) === 1 ? ' is' : 's are'} still active in this pipeline — closing won’t affect them.`
            : 'This stops new applicants from applying. You can reopen it anytime.',
          confirmLabel: 'Close job',
          destructive: true,
        })
        if (!ok) return
      }
      setJobStatusBusy(true)
      try {
        const result = await setPositionStatus(access, job.position_code, status)
        setJobsData((current) =>
          current
            ? {
                ...current,
                positions: current.positions.map((p) => (p.position_code === job.position_code ? { ...p, status: result.position.status } : p)),
              }
            : current,
        )
        setSelectedJob((current) => (current && current.position_code === job.position_code ? { ...current, status: result.position.status } : current))
        setNoticeOk(status === 'closed' ? `${job.position_title || job.position_code} is closed to new applicants.` : `${job.position_title || job.position_code} is reopened.`)
        void loadJobs(access, { silent: true })
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
    [access, confirm, loadJobs, setNoticeErr, setNoticeOk],
  )

  // Interviews list: fetched on its own so the tab/search/date filters only
  // refetch interviews.
  const loadInterviews = useCallback(
    async (nextAccess = access, opts: { silent?: boolean } = {}) => {
      const effectiveAccess = normalizedAccess(nextAccess)
      if (!effectiveAccess.token || !effectiveAccess.companyCode) return
      try {
        const interviewsData = await getInterviews(effectiveAccess, {
          status: interviewTab,
          q: interviewQuery,
          role: interviewRole,
          date: interviewDate,
          interviewer: interviewInterviewer,
          offset: interviewOffset,
          limit: 25,
        })
        setInterviews(interviewsData)
      } catch (error) {
        if (!opts.silent) setNoticeErr(friendlyDashboardError(error, 'Could not load interviews.'))
      }
    },
    [access, interviewTab, interviewQuery, interviewRole, interviewDate, interviewInterviewer, interviewOffset],
  )

  // Assessment attempts: fetched on its own (like interviews) so paging through
  // history doesn't reload the whole dashboard. Company-wide status counts and
  // average score come back from the backend regardless of the current page, so
  // the headline metrics never drift once a company has more than one page of
  // attempts.
  const loadAssessments = useCallback(
    async (nextAccess = access, opts: { silent?: boolean } = {}) => {
      const effectiveAccess = normalizedAccess(nextAccess)
      if (!effectiveAccess.token || !effectiveAccess.companyCode) return
      // Wait for the summary to know whether the module is enabled at all —
      // `assessmentModuleEnabled` defaults permissive when summary is still
      // null, which would otherwise fire a doomed fetch before we know better.
      if (!summary) return
      if (!assessmentModuleEnabled(summary, summary)) {
        setAssessments(disabledAssessmentsResponse(effectiveAccess.companyCode))
        return
      }
      try {
        const assessmentsData = await getAssessments(effectiveAccess, { limit: 50, offset: assessmentOffset })
        setAssessments(assessmentsData)
      } catch (error) {
        if (isModuleDisabledError(error, 'assessments')) {
          setAssessments(disabledAssessmentsResponse(effectiveAccess.companyCode))
          return
        }
        if (!opts.silent) setNoticeErr(friendlyDashboardError(error, 'Could not load assessments.'))
      }
    },
    [access, assessmentOffset, summary],
  )

  // Core dashboard data (summary, notifications, reports, assessments). This is
  // independent of list filters, so navigating or filtering never reloads it.
  const refreshAll = useCallback(
    async (nextAccess = access, opts: { silent?: boolean } = {}) => {
      const effectiveAccess = normalizedAccess(nextAccess)
      if (!effectiveAccess.token || !effectiveAccess.companyCode) {
        const issue = missingAccessIssue(effectiveAccess)
        setAccessIssue(issue)
        setNotice(issue.title)
        return
      }
      const silent = Boolean(opts.silent)
      if (!silent) {
        setBusy(true)
        setAccessIssue(null)
        setNotice('Refreshing hiring dashboard...')
      }
      try {
        let bootstrapData: DashboardBootstrapResponse | null = null
        try {
          bootstrapData = await getDashboardBootstrap(effectiveAccess)
        } catch (error) {
          // WATHEFNI_WORKSPACE_BOOT defaults OFF. A 404 is the intentional
          // dark-launch signal: preserve the existing pre-hiring boot exactly.
          if (!(error instanceof DashboardApiError) || error.status !== 404) throw error
        }

        if (bootstrapData) {
          setWorkspaceBootstrap(bootstrapData)
          const hasPrehire = bootstrapData.enabled_modules.includes('pre_hiring')
          if (!hasPrehire) {
            const hasAlertsAndDelivery = isAlertsAndDeliveryRelevant(
              bootstrapData.enabled_modules,
              bootstrapData.module_catalog,
            )
            const notificationsData = hasAlertsAndDelivery
              ? await getNotifications(effectiveAccess)
              : {
                  company_code: bootstrapData.company_code,
                  enabled_modules: bootstrapData.enabled_modules,
                  notifications: [],
                  action_items: [],
                }
            setSummary(null)
            setApplications(null)
            setInterviews(null)
            setAssessments(null)
            setAssessmentConfig(null)
            setReports(null)
            setNotifications(notificationsData)
            if (!silent) setNoticeOk('You’re viewing the latest workspace data.')
            return
          }
        } else {
          setWorkspaceBootstrap(null)
        }

        const [summaryData, notificationsData, reportsData, workQueueData] = await Promise.all([
          getSummary(effectiveAccess),
          getNotifications(effectiveAccess),
          getPrehireReports(effectiveAccess),
          getPrehireWorkQueue(effectiveAccess, { limit: 25 }).catch(() => null),
        ])
        let assessmentConfigData: AssessmentConfigResponse | null = null
        if (assessmentModuleEnabled(bootstrapData || summaryData, summaryData)) {
          try {
            assessmentConfigData = await getAssessmentConfig(effectiveAccess)
          } catch (error) {
            if (!isModuleDisabledError(error, 'assessments')) throw error
          }
        }
        setSummary(summaryData)
        setAssessmentConfig(assessmentConfigData)
        setNotifications(notificationsData)
        setReports(reportsData)
        setWorkQueue(workQueueData)
        if (!silent) setNoticeOk('You’re viewing the latest data.')
      } catch (error) {
        if (!silent) {
          const issue = accessIssueFromError(error)
          if (issue) {
            setAccessIssue(issue)
            setNotice(issue.title)
          } else {
            setNoticeErr(friendlyDashboardError(error, 'Could not refresh the hiring dashboard.'))
          }
        }
      } finally {
        if (!silent) setBusy(false)
      }
    },
    [access],
  )

  // Revalidate everything quietly after an action, without freezing the UI.
  const revalidatePrehire = useCallback(() => {
    if (!prehireEnabled) return
    void refreshAll(access, { silent: true })
    void loadApplications(access, { silent: true })
    void loadInterviews(access, { silent: true })
    void loadAssessments(access, { silent: true })
    void loadJobs(access, { silent: true })
    void loadAllPositions(access)
  }, [access, prehireEnabled, refreshAll, loadApplications, loadInterviews, loadAssessments, loadJobs, loadAllPositions])

  // Explicit "Refresh" button: reload core data (with visible feedback) and the
  // lists alongside it.
  const refreshEverything = useCallback(
    (nextAccess = access) => {
      if (prehireEnabled) {
        void loadApplications(nextAccess, { silent: true })
        void loadInterviews(nextAccess, { silent: true })
        void loadAssessments(nextAccess, { silent: true })
        void loadJobs(nextAccess, { silent: true })
        void loadAllPositions(nextAccess)
      }
      return refreshAll(nextAccess)
    },
    [access, prehireEnabled, refreshAll, loadApplications, loadInterviews, loadAssessments, loadJobs, loadAllPositions],
  )

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue) return
    const timer = window.setTimeout(() => {
      void refreshAll(access)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [access, accessIssue, refreshAll])

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    const timer = window.setTimeout(() => {
      void loadApplications(access, { silent: true })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [access, accessIssue, prehireEnabled, loadApplications])

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    const timer = window.setTimeout(() => {
      void loadInterviews(access, { silent: true })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [access, accessIssue, prehireEnabled, loadInterviews])

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    const timer = window.setTimeout(() => {
      void loadAssessments(access, { silent: true })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [access, accessIssue, prehireEnabled, loadAssessments])

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    const timer = window.setTimeout(() => {
      void loadJobs(access, { silent: true })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [access, accessIssue, prehireEnabled, loadJobs])

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    const timer = window.setTimeout(() => {
      void loadAllPositions(access)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [access, accessIssue, prehireEnabled, loadAllPositions])

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

  useEffect(() => {
    if (!access.token || !access.companyCode || accessIssue || !prehireEnabled) return
    void loadChatSessions(access)
  }, [access, accessIssue, prehireEnabled, loadChatSessions])

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

  async function saveAccess() {
    const nextAccess = normalizedAccess(access)
    if (inviteToken.trim()) {
      if (!acceptName.trim() || acceptPassword.length < 8) {
        setNoticeErr('Enter your name and a password with at least 8 characters.')
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
        setNoticeOk('Invite accepted. You’re signed in.')
        await refreshEverything(loggedInAccess)
        await loadTeam(loggedInAccess)
      } catch (error) {
        setNoticeErr(friendlyDashboardError(error, 'Could not accept invite.'))
      } finally {
        setBusy(false)
      }
      return
    }
    if ((!nextAccess.email || !nextAccess.password) && (!nextAccess.token || !nextAccess.companyCode)) {
      const issue = missingAccessIssue(nextAccess)
      setAccessIssue(issue)
      setNotice(issue.title)
      return
    }
    setBusy(true)
    try {
      const login = await loginDashboard(nextAccess)
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
      setNoticeOk('You’re signed in.')
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
        setAccessIssue({ code: 'dashboard_auth_failed', title: 'Sign in to Wathefni', description: 'Incorrect email or password. Please try again.' })
        setNoticeErr('Incorrect email or password. Please try again.')
      } else {
        const issue = accessIssueFromError(error) || { code: 'dashboard_auth_failed', title: 'Verify your access', description: friendlyDashboardError(error, 'Access needs to be verified.') }
        setAccessIssue(issue)
        setNotice(issue.title)
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
      const nextAccess = normalizedAccess({ token: '', hrPhone: '', companyCode: 'WATHEFNI', email: '', password: '' })
      setAccess(nextAccess)
      setWorkspaceBootstrap(null)
      setSummary(null)
      setApplications(null)
      setInterviews(null)
      setJobsData(null)
      setAllPositions([])
      setAssessments(null)
      setAssessmentConfig(null)
      setRanking(null)
      setNotifications(null)
      setReports(null)
      setTeam(null)
      setChatMessages([])
      setChatSessions([])
      setAccessIssue(missingAccessIssue(nextAccess))
      setNoticeOk('Signed out.')
      setBusy(false)
      setPage('overview')
    }
  }

  async function runRanking() {
    if (!rankPosition) {
      setNoticeErr('Select a job before ranking candidates.')
      return
    }
    setBusy(true)
    try {
      setRanking(await getRanking(access, { position: rankPosition }))
      setNoticeOk('Ranking updated.')
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not refresh ranking.'))
    } finally {
      setBusy(false)
    }
  }

  async function mutate(label: string, action: () => Promise<MutationResponse>, key?: string) {
    setBusy(true)
    setRunningAction(key || label)
    setNotice(`${label}...`)
    try {
      const result = await action()
      setNoticeOk(result.reply || `${label} completed.`)
      if (result.application) {
        const updatedApplication = result.application
        setSelected((current) =>
          current?.app_key === updatedApplication.app_key
            ? {
                ...current,
                ...updatedApplication,
                allowed_actions: updatedApplication.allowed_actions || current.allowed_actions,
              }
            : current,
        )
        setApplications((current) =>
          current
            ? { ...current, applications: current.applications.map((item) => (item.app_key === updatedApplication.app_key ? updatedApplication : item)) }
            : current,
        )
      }
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, `${label} needs another try.`, recruitingLocale))
      setBusy(false)
      setRunningAction(null)
      return
    }
    // Action succeeded: release the button immediately, then reconcile counts
    // and lists in the background so nothing feels frozen.
    setBusy(false)
    setRunningAction(null)
    revalidatePrehire()
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
      revalidatePrehire()
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
      const result = await saveInterviewNotes(access, interview.interview_id, { notes, status: 'completed', generate_summary: true })
      setInterviewNotes((items) => ({ ...items, [interview.interview_id]: '' }))
      setNoticeOk(result.reply || 'Interview notes saved.')
      revalidatePrehire()
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not save interview notes.', recruitingLocale))
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
      revalidatePrehire()
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

  async function previewCv(application: ApplicationSummary) {
    if (!application.cv?.received) {
      setNotice('No CV file is available for this candidate yet.')
      return
    }
    try {
      setNotice(`Opening CV for ${candidateName(application)}...`)
      await previewCandidateCv(access, application.app_key)
      setNoticeOk(`CV preview opened for ${candidateName(application)}.`)
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not open the CV preview.'))
    }
  }

  async function previewReport(attempt: AssessmentAttempt) {
    try {
      setNotice(`Opening assessment report for ${attempt.candidate_name || attempt.phone || 'candidate'}...`)
      await previewAssessmentReport(access, attempt.attempt_id)
      setNoticeOk('Assessment report opened.')
    } catch (error) {
      setNoticeErr(friendlyDashboardError(error, 'Could not open the assessment report.'))
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
      revalidatePrehire()
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

  function viewJobCandidates(job: PositionSummary) {
    setQuery('')
    setStatus('')
    setCandidateOffset(0)
    setCandidateFilters((current) => ({ ...current, position: job.position_code || '', cvStatus: '', assessmentStatus: '', interviewStatus: '', followUp: '', reviewStatus: '', activityFrom: '', activityTo: '', sort: 'newest' }))
    openPage('candidates')
  }

  // "Review ready candidates": land straight on the exact cohort the overview
  // card counted (screening_complete / review_pending), sorted to the top,
  // instead of dumping HR on the generic, unfiltered candidate list.
  function viewReadyForReviewCandidates() {
    setQuery('')
    setStatus('')
    setCandidateOffset(0)
    setCandidateFilters((current) => ({
      ...current,
      position: '',
      cvStatus: '',
      assessmentStatus: '',
      interviewStatus: '',
      followUp: '',
      reviewStatus: 'ready',
      activityFrom: '',
      activityTo: '',
      sort: 'ready_for_review',
    }))
    openPage('candidates')
  }

  // "Follow up with candidates": apply the real follow-up filter so the table
  // shows exactly the cohort the overview card counted (company-wide
  // follow_up_needed applications).
  function viewFollowUpCandidates() {
    setQuery('')
    setStatus('')
    setCandidateOffset(0)
    setCandidateFilters((current) => ({
      ...current,
      position: '',
      cvStatus: '',
      assessmentStatus: '',
      interviewStatus: '',
      followUp: 'needed',
      reviewStatus: '',
      activityFrom: '',
      activityTo: '',
      sort: 'newest',
    }))
    openPage('candidates')
  }

  // "Awaiting assessment": same cohort as action_counts.assessment_pending.
  function viewPendingAssessmentCandidates() {
    setQuery('')
    setStatus('')
    setCandidateOffset(0)
    setCandidateFilters((current) => ({
      ...current,
      position: '',
      cvStatus: '',
      assessmentStatus: 'awaiting',
      interviewStatus: '',
      followUp: '',
      reviewStatus: '',
      activityFrom: '',
      activityTo: '',
      sort: 'newest',
    }))
    openPage('candidates')
  }

  function viewRolePriority(role?: PrehireRolePriority | null) {
    if (!role?.position_code) {
      openPage('ranking')
      return
    }
    setRankPosition(role.position_code)
    openPage('ranking')
  }

  function applyOverviewDestination(destination?: { page?: string; filters?: Record<string, string> } | null) {
    if (!destination?.page) return
    const filters = destination.filters || {}
    if (destination.page === 'candidates') {
      setQuery(filters.q || '')
      setStatus('')
      setCandidateOffset(0)
      setCandidateFilters((current) => ({
        ...current,
        position: filters.position || '',
        cvStatus: '',
        assessmentStatus: filters.assessment_status || '',
        interviewStatus: '',
        followUp: filters.follow_up || '',
        reviewStatus: filters.review_status || '',
        activityFrom: '',
        activityTo: '',
        sort: filters.sort || 'newest',
      }))
      openPage('candidates')
      return
    }
    if (destination.page === 'ranking') {
      if (filters.position_code) setRankPosition(filters.position_code)
      openPage('ranking')
      return
    }
    if (destination.page === 'interviews') {
      openPage('interviews')
      return
    }
    if (destination.page === 'assessments') {
      viewPendingAssessmentCandidates()
      return
    }
    openPage(destination.page as Page)
  }

  function openCandidateByKey(appKey?: string) {
    if (!appKey) return
    const application = allApplications.find((item) => item.app_key === appKey)
    if (application) {
      setSelected(application)
      return
    }
    setQuery(appKey)
    setStatus('')
    setCandidateOffset(0)
    openPage('candidates')
    // The candidate-filter change above triggers loadApplications automatically.
  }

  function applyChatNavigation(item: DashboardChatNavigation) {
    if (item.page && navItems.some((nav) => nav.id === item.page)) {
      openPage(item.page as Page)
    }
    if (item.page === 'ranking' && item.position_code) {
      setRankPosition(String(item.position_code))
    }
  }

  async function openChatSession(session: DashboardChatSession) {
    if (!session.conversation_id || chatBusy) return
    try {
      const payload = await getDashboardChatSession(access, session.conversation_id)
      setChatConversationId(payload.session.conversation_id)
      rememberDashboardChatConversationId(access, payload.session.conversation_id)
      setChatMessages((payload.messages || []).map(storedDashboardMessageToChatMessage))
      setChatHistoryOpen(false)
      setNoticeOk(`Reopened ${payload.session.title || 'Wathefni Assistant chat'}.`)
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
      setNoticeOk('Started a new Wathefni Assistant chat. Saved records were not changed.')
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
    setChatInput('')
    setChatMessages((items) => [
      ...items,
      { id: `user-${Date.now()}`, role: 'user', text },
      { id: assistantId, role: 'assistant', text: '', isStreaming: true },
    ])
    setChatBusy(true)
    let finalResponse: DashboardChatResponse | null = null
    let finalSessionId: string | null = null
    let streamFailed = false
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
          if (event.type === 'typing') return
          if (event.type === 'delta') {
            setChatMessages((items) =>
              items.map((item) => (item.id === assistantId ? { ...item, text: item.text + (event.text || '') } : item)),
            )
          }
          if (event.type === 'done' && typeof event.message === 'object' && event.message) {
            const response = event.message as DashboardChatResponse
            finalResponse = response
            finalSessionId = response.session?.conversation_id || null
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
                      text: friendlyDashboardError(event.message, 'Wathefni couldn’t finish answering just now. Please try again in a moment.'),
                      isStreaming: false,
                    }
                  : item,
              ),
            )
          }
        },
      )
      // A mid-stream error resolves the stream normally (the bubble already shows
      // the friendly failure). Never claim success after a failed answer.
      if (streamFailed) {
        setNoticeErr('Wathefni couldn’t finish answering. Please try again.')
      } else {
        setNoticeOk('Answered by the Wathefni assistant.')
      }
      if (finalSessionId) {
        setChatConversationId(finalSessionId)
        rememberDashboardChatConversationId(access, finalSessionId)
      }
      await loadChatSessions(access)
      if (finalResponse && !streamFailed) await refreshEverything()
    } catch (error) {
      setChatMessages((items) =>
        items.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                text: friendlyDashboardError(error, 'Wathefni couldn’t finish answering just now. Please try again in a moment.'),
                isStreaming: false,
              }
            : item,
        ),
      )
      setNoticeErr('Wathefni couldn’t finish answering. Please try again.')
    } finally {
      setChatBusy(false)
    }
  }

  async function exportReport(type: 'candidates' | 'roles' | 'assessments' | 'interviews' | 'followups', label: string) {
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

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_50%_-12%,#fffdf5_0%,#f7f3eb_36%,rgba(244,239,230,0)_62%),radial-gradient(circle_at_82%_10%,rgba(200,148,69,0.08)_0%,rgba(200,148,69,0.025)_26%,rgba(200,148,69,0)_48%),linear-gradient(180deg,#f7f2e9_0%,#f4eee4_48%,#f1eadf_100%)] text-text">
      <div className="grid min-h-screen lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="border-r border-line/55 bg-panel/72 p-5 text-text shadow-[14px_0_44px_rgba(24,20,15,0.03)] backdrop-blur-2xl">
          <div className="mb-9 rounded-[1.35rem] px-3 py-2">
            <div className="text-xl font-semibold tracking-[-0.045em]">Wathefni</div>
            <div className="mt-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-mist">HR workspace</div>
          </div>
          <nav className="space-y-6 text-sm">
            {(['prehire', 'posthire', 'settings'] as NavGroup[]).map((group) => {
              const items = availableNavItems.filter((item) => item.group === group)
              if (!items.length) return null
              return (
                <div className="space-y-1.5" key={group}>
                  <div className="px-3.5 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.2em] text-mist/75">{NAV_GROUP_LABELS[group]}</div>
                  {items.map((item) => {
                    const Icon = item.icon
                    return (
                      <button
                        className={`flex w-full items-center gap-3 rounded-2xl px-3.5 py-3 text-left transition duration-200 ease-out ${
                          activePage === item.id
                            ? 'bg-ink text-white shadow-[0_10px_24px_rgba(24,20,15,0.14)] font-semibold before:h-1.5 before:w-1.5 before:rounded-full before:bg-[#c89445] before:content-[\'\']'
                            : 'text-subtle hover:bg-white/55 hover:text-ink'
                        }`}
                        key={item.id}
                        onClick={() => openPage(item.id)}
                        type="button"
                      >
                        <Icon size={16} />
                        {item.label}
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </nav>

          {futureModuleItems.length > 0 && (
            <div className="mt-9 border-t border-white/70 pt-5">
              <div className="px-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">More HR tools soon</div>
              <div className="mt-3 space-y-1.5 px-3 text-sm text-mist">
                {futureModuleItems.map((item) => (
                  <div className="flex items-center justify-between gap-2 rounded-xl px-2 py-1.5" key={item.module}>
                    <span>{item.label}</span>
                    <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-mist/70">Coming soon</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>

        <section className="p-5 lg:p-9">
          <header className="mb-9 flex flex-col gap-5 border-b border-line/50 pb-8 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-mist">{accessIssue || showingInviteAcceptance ? 'Access' : isPostHirePage(activePage) ? 'Post-Hire' : activePage === 'settings' || activePage === 'activity' || activePage === 'notifications' ? 'Workspace' : 'Pre-hiring'}</div>
              <h1 className="mt-3 max-w-5xl text-4xl font-semibold tracking-[-0.055em] text-text lg:text-5xl" dir={activePage === 'overview' && recruitingLocale === 'ar' ? 'rtl' : undefined}>
                {showingInviteAcceptance
                  ? 'Complete your Wathefni invite'
                  : accessIssue
                  ? 'Verify your Wathefni access'
                  : activePage === 'overview'
                  ? recruitingCopy(recruitingLocale, 'overviewPageTitle')
                  : pageTitle}
              </h1>
              <p className="mt-4 max-w-3xl text-[15px] leading-7 text-subtle/90" dir={activePage === 'overview' && recruitingLocale === 'ar' ? 'rtl' : undefined}>
                {showingInviteAcceptance
                  ? 'Create your workspace login to join this Wathefni company workspace.'
                  : accessIssue
                  ? 'Sign in with your workspace account, or use a backup access code only if you need to set up or recover the workspace.'
                  : activePage === 'overview'
                  ? recruitingCopy(recruitingLocale, 'overviewPageSubtitle')
                  : pageSubtitles[activePage]}
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              {busy ? (
                <div className="rounded-full border border-white/70 bg-panel/65 px-3.5 py-2 text-xs font-medium text-mist shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_10px_28px_rgba(24,20,15,0.04)] backdrop-blur-xl">
                  Refreshing hiring data...
                </div>
              ) : notice.text ? (
                <div
                  className={cn(
                    'flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-medium shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_10px_28px_rgba(24,20,15,0.04)] backdrop-blur-xl',
                    notice.tone === 'success'
                      ? 'border-emerald-300/60 bg-emerald-50/80 text-emerald-800'
                      : notice.tone === 'error'
                      ? 'border-rose-300/60 bg-rose-50/85 text-rose-700'
                      : 'border-white/70 bg-panel/65 text-mist',
                  )}
                  role="status"
                >
                  <span>{notice.text}</span>
                  {notice.tone === 'error' ? (
                    <button
                      type="button"
                      onClick={() => setNotice('')}
                      aria-label="Dismiss"
                      className="-mr-1 ml-0.5 rounded-full px-1 text-rose-500/80 hover:text-rose-700"
                    >
                      ×
                    </button>
                  ) : null}
                </div>
              ) : null}
              {/* Post-hire pages carry their own module Refresh (ModuleToolbar) that
                  reloads the data actually on screen. The global Refresh only reloads
                  pre-hiring data, so it is hidden there to avoid a misleading duplicate. */}
              {!accessIssue && !showingInviteAcceptance && !isPostHirePage(activePage) ? (
                <Button className="h-8 px-3 text-xs" disabled={busy} onClick={() => refreshEverything()} size="sm" variant="secondary">
                  {busy ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                  Refresh
                </Button>
              ) : null}
            </div>
          </header>

          {showingInviteAcceptance || accessIssue ? (
            <AccessVerificationPage
              access={access}
              accessIssue={accessIssue || { code: 'invite_pending', title: 'Complete your Wathefni invite', description: 'Create your workspace login. Your assigned role will apply after you accept the invite.' }}
              acceptName={acceptName}
              acceptPassword={acceptPassword}
              acceptPhone={acceptPhone}
              busy={busy}
              inviteToken={inviteToken}
              onVerify={saveAccess}
              setAcceptName={setAcceptName}
              setAcceptPassword={setAcceptPassword}
              setAcceptPhone={setAcceptPhone}
              setAccess={setAccess}
            />
          ) : activePage !== 'settings' && !access.token.trim() ? (
            <NeedsSettings onOpenSettings={() => openPage('settings')} />
          ) : activePage !== 'settings' && !dashboardLoaded ? (
            <LoadingDashboard busy={busy} notice={notice.text} onOpenSettings={() => openPage('settings')} onRefresh={() => refreshEverything()} />
          ) : (
            <>
              {activePage === 'overview' && canManageWorkspace && setupReadiness && !setupReadiness.ready && Array.isArray(setupReadiness.steps) && setupReadiness.steps.length > 0 ? (
                <SetupReadinessCard readiness={setupReadiness} onAction={(target) => openPage(target as Page)} />
              ) : null}
              {activePage === 'overview' && (
                <OverviewPage
                  assessmentEnabled={assessmentModuleOn}
                  readyForReviewTotal={summary?.action_counts?.ready_for_review}
                  assessmentPendingTotal={summary?.action_counts?.assessment_pending}
                  followUpNeededTotal={summary?.action_counts?.follow_up_needed}
                  nextAction={summary?.next_action || null}
                  rolePriority={summary?.role_priority || null}
                  workQueue={workQueue}
                  locale={recruitingLocale}
                  onLocaleChange={(next) => {
                    setRecruitingLocale(next)
                    localStorage.setItem('wathefni_recruiting_locale', next)
                  }}
                  onOpenCandidate={openCandidateByKey}
                  onOpenFollowUps={viewFollowUpCandidates}
                  onOpenPendingAssessments={viewPendingAssessmentCandidates}
                  onOpenReadyForReview={viewReadyForReviewCandidates}
                  onOpenRolePriority={() => viewRolePriority(summary?.role_priority)}
                  onOpenDestination={applyOverviewDestination}
                  onOpenRoleCandidates={viewJobCandidates}
                  positions={allPositionsForSelectors}
                />
              )}
              {activePage === 'ai' && (
                <AdminAIPage
                  busy={chatBusy}
                  input={chatInput}
                  historyOpen={chatHistoryOpen}
                  messages={chatMessages}
                  newChatConfirmOpen={newChatConfirmOpen}
                  assessmentEnabled={assessmentModuleOn}
                  enabledModules={moduleState?.enabled_modules}
                  onApplyNavigation={applyChatNavigation}
                  onAsk={askDashboardAssistant}
                  onConfirm={() => askDashboardAssistant('Yes, confirm it')}
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
                  onPrompt={(prompt) => askDashboardAssistant(prompt)}
                  onRequestNewChat={() => setNewChatConfirmOpen(true)}
                  sessions={chatSessions}
                />
              )}
              {activePage === 'jobs' && (
                <JobsPage
                  canExportReports={canExportReports}
                  canManageJobs={canManageJobs}
                  jobsData={jobsData}
                  loadingMore={jobsLoadingMore}
                  onCreate={() => {
                    setPage('ai')
                    void askDashboardAssistant('I want to create a new job opening.')
                  }}
                  onExport={() => exportReport('roles', 'Role report')}
                  onLoadMore={loadMoreJobs}
                  onQueryChange={setJobsQuery}
                  onRefresh={() => refreshEverything()}
                  onSelect={setSelectedJob}
                  onViewCandidates={viewJobCandidates}
                  query={jobsQuery}
                />
              )}
              {activePage === 'candidates' && (
                <CandidatesPage
                  locale={recruitingLocale}
                  onLocale={() => {
                    const next = recruitingLocale === 'ar' ? 'en' : 'ar'
                    localStorage.setItem('wathefni_recruiting_locale', next)
                    setRecruitingLocale(next)
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
                  importReview={
                    canImportCandidates ? (
                      <ImportReviewQueue
                        access={access}
                        positions={allPositionsForSelectors}
                        onAccessIssue={handleAccessIssue}
                        reloadKey={importReloadKey}
                        onChanged={() => {
                          setImportReloadKey((value) => value + 1)
                          void refreshEverything()
                        }}
                      />
                    ) : null
                  }
                  applications={allApplications}
                  assessmentEnabled={assessmentModuleOn}
                  busy={busy}
                  filters={candidateFilters}
                  offset={applications?.offset || 0}
                  onFilter={() => {
                    setCandidateOffset(0)
                    void loadApplications(access, { silent: true })
                  }}
                  onPage={(nextOffset) => setCandidateOffset(Math.max(0, nextOffset))}
                  onPreviewCv={previewCv}
                  onSelect={(application) => setSelected(application)}
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
              )}
              {activePage === 'interviews' && (
                <InterviewsPage
                  locale={recruitingLocale}
                  onLocale={() => {
                    const next = recruitingLocale === 'ar' ? 'en' : 'ar'
                    localStorage.setItem('wathefni_recruiting_locale', next)
                    setRecruitingLocale(next)
                  }}
                  busy={busy}
                  interviews={interviews?.interviews || []}
                  limit={interviews?.limit || 25}
                  notesDrafts={interviewNotes}
                  offset={interviews?.offset || 0}
                  onOpenCandidate={openCandidateByKey}
                  onPreviewVideoAnswer={previewVideoAnswer}
                  onRetryVideoTranscripts={retryVideoTranscripts}
                  onSaveNotes={saveNotesForInterview}
                  onSearch={() => {
                    setInterviewOffset(0)
                    void loadInterviews(access, { silent: true })
                  }}
                  onSetNotes={(interviewId, value) => setInterviewNotes((items) => ({ ...items, [interviewId]: value }))}
                  onSetOffset={(value) => setInterviewOffset(Math.max(0, value))}
                  onStatusChange={changeInterviewStatus}
                  canManageInterviews={canManageInterviews}
                  onUpdateFilters={({ date, interviewer, q, role, tab }) => {
                    if (tab !== undefined) setInterviewTab(tab)
                    if (q !== undefined) setInterviewQuery(q)
                    if (role !== undefined) setInterviewRole(role)
                    if (date !== undefined) setInterviewDate(date)
                    if (interviewer !== undefined) setInterviewInterviewer(interviewer)
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
              )}
              {activePage === 'assessments' && (
                <AssessmentsPage
                  access={access}
                  applications={allApplications}
                  enabled={assessmentModuleOn}
                  config={assessmentConfig}
                  attempts={assessments?.attempts || []}
                  averagePercent={assessments?.average_percent}
                  limit={assessments?.limit || 25}
                  offset={assessments?.offset || 0}
                  total={assessments?.total || 0}
                  onOpenCandidate={openCandidateByKey}
                  onOpenFollowUpCandidates={viewPendingAssessmentCandidates}
                  onPreviewReport={previewReport}
                  onCancelAttempt={async (attempt) => {
                    const reason = window.prompt('Why are you cancelling this assessment?')
                    if (!reason?.trim()) return
                    if (!(await confirm({ title: 'Cancel assessment?', body: `This revokes every active link for ${attempt.candidate_name || attempt.phone || 'this candidate'}.`, confirmLabel: 'Cancel assessment', destructive: true }))) return
                    await mutate('Cancelling assessment', () => cancelAssessment(access, attempt.attempt_id, reason.trim()), `cancel_assessment:${attempt.attempt_id}`)
                  }}
                  onResendAttempt={async (attempt) => {
                    if (!(await confirm({ title: 'Resend assessment?', body: `The old link will be revoked and ${attempt.candidate_name || attempt.phone || 'the candidate'} will receive a new one.`, confirmLabel: 'Resend assessment' }))) return
                    await mutate('Resending assessment', () => resendAssessment(access, attempt.attempt_id), `resend_assessment:${attempt.attempt_id}`)
                  }}
                  onReviewAttempt={async (attempt) => {
                    if (!(await confirm({ title: 'Mark assessment reviewed?', body: `Record that HR reviewed the immutable report for ${attempt.candidate_name || attempt.phone || 'this candidate'}.`, confirmLabel: 'Mark reviewed' }))) return
                    await mutate('Marking assessment reviewed', () => reviewAssessment(access, attempt.attempt_id), `review_assessment:${attempt.attempt_id}`)
                  }}
                  onRecalculateNorms={recalculateNorms}
                  onRefresh={() => {
                    setAssessmentOffset(0)
                    void refreshEverything()
                  }}
                  onSendAssessment={async (application) => {
                    if (!(await confirm({ title: 'Send assessment?', body: `${candidateName(application)} will receive an application assessment link by message.`, confirmLabel: 'Send assessment' }))) return
                    await mutate('Sending assessment', () => sendAssessment(access, application.app_key), `send_assessment:${application.app_key}`)
                  }}
                  onSetOffset={(value) => setAssessmentOffset(Math.max(0, value))}
                  busy={busy}
                  canManageAssessments={canManageAssessments}
                  statusCounts={assessments?.status_counts || []}
                  pendingTotal={summary?.action_counts?.assessment_pending}
                />
              )}
              {activePage === 'ranking' && (
                <RankingPage
                  busy={busy}
                  positions={allPositionsForSelectors}
                  rankPosition={rankPosition}
                  ranking={ranking}
                  runRanking={runRanking}
                  onSelect={(candidate) => setSelected(rankingCandidateApplication(candidate))}
                  setRankPosition={setRankPosition}
                />
              )}
              {activePage === 'notifications' && (
                <NotificationsPage
                  actionItems={notifications?.action_items || []}
                  deliveryCenter={
                    anyPosthireModuleEnabled(moduleState) ? (
                      <PostHireDeliveryCenter
                        access={access}
                        permissions={userAccess?.permissions || []}
                        role={userAccess?.role || userAccess?.user?.role}
                        onNotice={setNotice}
                        onAccessIssue={handleAccessIssue}
                      />
                    ) : null
                  }
                  enabledModules={enabledNotificationModules}
                  notifications={notifications?.notifications || []}
                  onNavigate={openPage}
                />
              )}
              {activePage === 'reports' && (
                <ReportsPage
                  assessmentEnabled={assessmentModuleOn}
                  onExportAssessments={() => exportReport('assessments', 'Assessment report')}
                  onExportCandidates={() => exportReport('candidates', 'Candidate report')}
                  onExportFollowUps={() => exportReport('followups', 'Follow-up report')}
                  onExportInterviews={() => exportReport('interviews', 'Interview report')}
                  onExportRoles={() => exportReport('roles', 'Role report')}
                  reports={reports}
                  canExportReports={canExportReports}
                />
              )}
              {activePage === 'settings' && (
                <SettingsPage
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
                  setAccess={setAccess}
                  setInviteEmail={setInviteEmail}
                  setInviteName={setInviteName}
                  setInviteRole={setInviteRole}
                  setLinkPhone={setLinkPhone}
                  team={team}
                  userAccess={userAccess}
                />
              )}
              {activePage === 'activity' && (
                <ActivityLog access={access} onAccessIssue={handleAccessIssue} />
              )}
              {isPostHirePage(activePage) && (
                <PostHirePage
                  page={activePage}
                  access={access}
                  permissions={userAccess?.permissions || []}
                  role={userAccess?.role || userAccess?.user?.role}
                  onNotice={setNotice}
                  onAccessIssue={handleAccessIssue}
                  onOpenNotifications={() => openPage('notifications')}
                />
              )}
            </>
          )}

          {selected ? (
            <CandidateDrawer
              locale={recruitingLocale}
              access={access}
              busy={busy}
              runningAction={runningAction}
              candidate={selected}
              assessmentEnabled={assessmentModuleOn}
              message={message}
              mutate={mutate}
              onClose={() => setSelected(null)}
              onOpenAssessments={() => openPage('assessments')}
              onOpenInterviews={() => {
                setInterviewTab('video_interviews')
                setInterviewOffset(0)
                openPage('interviews')
                setSelected(null)
              }}
              onScheduleInterview={() => {
                setPage('ai')
                void askDashboardAssistant(`Schedule an interview for application ${selected.app_key}. Ask me for any missing date, time, or channel details before preparing the confirmation.`)
                setSelected(null)
              }}
              onPreviewCv={previewCv}
              canManageAssessments={canManageAssessments}
              canManageInterviews={canManageInterviews}
              setMessage={setMessage}
              videoInterviewsEnabled={dashboardModuleEnabled(moduleState, 'video_interviews')}
              employmentOffersEnabled={dashboardModuleEnabled(moduleState, 'employment_offers')}
            />
          ) : null}

          {selectedJob ? (
            <JobDrawer
              job={selectedJob}
              canManageJobs={canManageJobs}
              statusBusy={jobStatusBusy}
              onClose={() => setSelectedJob(null)}
              onCopy={copyToClipboard}
              onDownloadQr={() => downloadQr(jobQrDataUrl, selectedJob)}
              onSetStatus={(status) => setJobStatus(selectedJob, status)}
              onViewCandidates={() => viewJobCandidates(selectedJob)}
              qrDataUrl={jobQrDataUrl}
            />
          ) : null}

        </section>
      </div>
    </main>
  )
}

function SetupReadinessCard({
  readiness,
  onAction,
}: {
  readiness: SetupReadinessResponse
  onAction: (page: string) => void
}) {
  const steps = Array.isArray(readiness.steps) ? readiness.steps : []
  const remaining = steps.filter((step) => !step.done && !step.optional).length
  return (
    <Card className="mb-7 border-[#e8c47d]/55 bg-[#fffaf0]/70">
      <CardHeader>
        <CardTitle>Get your workspace ready</CardTitle>
        <CardDescription>
          {remaining > 0
            ? `${remaining} step${remaining === 1 ? '' : 's'} left before your HR team can run day-to-day on Wathefni — here is what to do next, and why.`
            : 'A couple of optional recommendations to get the most out of Wathefni.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {steps.map((step) => (
          <div
            key={step.key}
            className="flex flex-col gap-3 rounded-2xl border border-line/70 bg-panel/60 p-4 sm:flex-row sm:items-center"
          >
            {step.done ? (
              <CheckCircle2 className="mt-0.5 shrink-0 text-[#15803d]" size={20} />
            ) : (
              <Circle className="mt-0.5 shrink-0 text-mist" size={20} />
            )}
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-text">{step.title}</span>
                {step.optional ? <Badge tone="muted">Recommended</Badge> : null}
              </div>
              <p className="mt-1 text-[13px] leading-6 text-subtle/90">{step.why}</p>
            </div>
            {!step.done ? (
              <Button onClick={() => onAction(step.action_page)} variant="secondary">
                {step.action_label}
              </Button>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

const pageLabels: Record<Page, string> = {
  overview: 'Overview',
  ai: 'Wathefni Assistant',
  jobs: 'Jobs',
  candidates: 'Candidates',
  interviews: 'Interviews',
  assessments: 'Assessments',
  ranking: 'Ranking',
  notifications: 'Alerts & Delivery',
  reports: 'Reports',
  employees: 'Employees',
  onboarding: 'Onboarding',
  attendance: 'Attendance',
  leave: 'Leave',
  shifts: 'Shifts',
  payroll: 'Payroll',
  analytics: 'Analytics',
  compliance: 'Compliance',
  activity: 'Activity',
  settings: 'Settings',
}

const pageSubtitles: Record<Page, string> = {
  overview: 'Today’s hiring work queue: review, follow up, and move candidates forward.',
  ai: 'Your company-wide HR assistant — ask about hiring or your team and take the next action.',
  jobs: 'See which openings need attention, share application links and QR codes, and track applicants.',
  candidates: 'Review candidates, see evidence, and choose the next hiring step.',
  interviews: 'Track interviews, review candidate responses, and capture feedback in one place.',
  assessments: 'Assessment sending, progress, results, and official report review.',
  ranking: 'Guidance on who HR should prioritize for a selected job.',
  notifications: 'Shared workspace alerts and employee message delivery — see who needs another channel and follow up in one place.',
  reports: 'Hiring reports for roles, candidates, CVs, assessments, and follow-ups.',
  employees: 'Your people directory — roles, departments, and onboarding status in one place.',
  onboarding: 'New hires in progress, open documents, and reminders to keep onboarding moving.',
  attendance: 'Today’s attendance, late and missing check-ins, and corrections that need a decision.',
  leave: 'Pending leave requests, approvals, and who is away in the weeks ahead.',
  shifts: 'This week’s schedule, upcoming assignments, and swap requests to clear.',
  payroll: 'Timesheets, exceptions, and a controlled, audited payroll export.',
  analytics: 'A calm executive view of workforce, attendance, and post-hire trends.',
  compliance: 'Track missing, expired, and expiring employee documents.',
  activity: 'A read-only record of who did what across your workspace.',
  settings: 'Manage your workspace, team access, and account settings.',
}

function overviewCountDetail(
  locale: RecruitingLocale,
  count: number,
  oneKey: Parameters<typeof recruitingCopy>[1],
  manyKey: Parameters<typeof recruitingCopy>[1],
  emptyKey: Parameters<typeof recruitingCopy>[1],
) {
  if (!count) return recruitingCopy(locale, emptyKey)
  if (count === 1) return recruitingCopy(locale, oneKey)
  return recruitingCopy(locale, manyKey, { count })
}

function overviewDaysFromReason(reason?: string | null) {
  const match = String(reason || '').match(/(\d+)\s*day/i)
  if (match) return Math.max(1, Number(match[1]))
  const hours = String(reason || '').match(/~?(\d+)\s*h/i)
  if (hours) return Math.max(1, Math.round(Number(hours[1]) / 24))
  return null
}

function overviewHeroReason(nextAction: PrehireNextAction | null | undefined, locale: RecruitingLocale, fallback: string) {
  if (!nextAction || nextAction.action === 'none') return fallback
  const count = Number(nextAction.total_matching || 0)
  const days = overviewDaysFromReason(nextAction.reason)
  const action = String(nextAction.action || '')
  if (action === 'follow_up_failed_delivery') {
    if (count <= 1) return recruitingCopy(locale, 'overviewHeroFollowUpReasonOne')
    return recruitingCopy(locale, 'overviewHeroFollowUpReason', { count, days: days || 1 })
  }
  if (action === 'ready_for_review') {
    return count <= 1
      ? recruitingCopy(locale, 'overviewHeroReadyReasonOne')
      : recruitingCopy(locale, 'overviewHeroReadyReason', { count })
  }
  if (action === 'send_pending_assessments') {
    return count <= 1
      ? recruitingCopy(locale, 'overviewHeroAssessmentReasonOne')
      : recruitingCopy(locale, 'overviewHeroAssessmentReason', { count })
  }
  if (action === 'interview_scheduling_debt') {
    return count <= 1
      ? recruitingCopy(locale, 'overviewHeroInterviewReasonOne')
      : recruitingCopy(locale, 'overviewHeroInterviewReason', { count })
  }
  if (action === 'prioritize_role' && nextAction.role?.position_title) {
    return locale === 'ar'
      ? `وظيفة ${nextAction.role.position_title} تحتاج انتباهًا الآن.`
      : `${nextAction.role.position_title} needs attention now.`
  }
  return nextAction.reason || fallback
}

function overviewPrimaryCtaLabel(action: string | undefined, locale: RecruitingLocale) {
  if (action === 'follow_up_failed_delivery') return recruitingCopy(locale, 'overviewOpenFollowUps')
  if (action === 'ready_for_review') return recruitingCopy(locale, 'overviewOpenReady')
  if (action === 'send_pending_assessments') return recruitingCopy(locale, 'overviewOpenAssessments')
  if (action === 'prioritize_role') return recruitingCopy(locale, 'overviewOpenRoleRanking')
  return recruitingCopy(locale, 'overviewOpenWorkQueue')
}

function overviewQueueBadge(actionType: string, locale: RecruitingLocale) {
  if (actionType.includes('follow')) return recruitingCopy(locale, 'overviewBadgeFollowUp')
  if (actionType.includes('assessment')) return recruitingCopy(locale, 'overviewBadgeAssessment')
  if (actionType.includes('interview')) return recruitingCopy(locale, 'overviewBadgeInterview')
  if (actionType.includes('role')) return recruitingCopy(locale, 'overviewBadgeRole')
  return recruitingCopy(locale, 'overviewBadgeReady')
}

function overviewQueueReason(actionType: string, locale: RecruitingLocale) {
  if (actionType.includes('follow')) return recruitingCopy(locale, 'overviewQueueFollowUp')
  if (actionType.includes('assessment')) return recruitingCopy(locale, 'overviewQueueAssessment')
  if (actionType.includes('interview')) return recruitingCopy(locale, 'overviewQueueInterview')
  return recruitingCopy(locale, 'overviewQueueReady')
}

function overviewRoleReason(role: PrehireRolePriority, locale: RecruitingLocale) {
  const parts: string[] = []
  const follow = Number(role.follow_up_count || 0)
  const ready = Number(role.ready_count || 0)
  const pending = Number(role.assessment_pending_count || 0)
  const days = Math.max(1, Math.round(Number(role.oldest_ready_hours || 0) / 24))
  if (locale === 'ar') {
    if (follow === 1) parts.push('مرشح واحد يحتاج متابعة')
    else if (follow > 1) parts.push(`${follow} مرشحين يحتاجون متابعة`)
    if (ready === 1) parts.push('مرشح واحد جاهز للمراجعة')
    else if (ready > 1) parts.push(`${ready} مرشحين جاهزين للمراجعة`)
    if (pending === 1) parts.push('مرشح واحد بانتظار التقييم')
    else if (pending > 1) parts.push(`${pending} مرشحين بانتظار التقييم`)
    if (ready > 0 && Number(role.oldest_ready_hours || 0) >= 48) parts.push(`أقدمهم بانتظار منذ ${days} يومًا`)
    if (Number(role.active_count || 0) > 0 && Number(role.active_count || 0) <= 2) parts.push('معروض المرشحين منخفض')
  } else {
    if (follow === 1) parts.push('1 candidate needs follow-up')
    else if (follow > 1) parts.push(`${follow} candidates need follow-up`)
    if (ready === 1) parts.push('1 ready for review')
    else if (ready > 1) parts.push(`${ready} ready for review`)
    if (pending === 1) parts.push('1 awaiting assessment')
    else if (pending > 1) parts.push(`${pending} awaiting assessment`)
    if (ready > 0 && Number(role.oldest_ready_hours || 0) >= 48) parts.push(`oldest waiting ${days} day${days === 1 ? '' : 's'}`)
    if (Number(role.active_count || 0) > 0 && Number(role.active_count || 0) <= 2) parts.push('low candidate supply')
  }
  return parts.join(locale === 'ar' ? ' · ' : '; ') || role.reason
}

function OverviewPage({
  assessmentEnabled,
  readyForReviewTotal,
  assessmentPendingTotal,
  followUpNeededTotal,
  nextAction,
  rolePriority,
  workQueue,
  locale,
  onLocaleChange,
  onOpenCandidate,
  onOpenFollowUps,
  onOpenPendingAssessments,
  onOpenReadyForReview,
  onOpenRolePriority,
  onOpenDestination,
  onOpenRoleCandidates,
  positions,
}: {
  assessmentEnabled: boolean
  readyForReviewTotal?: number
  assessmentPendingTotal?: number
  followUpNeededTotal?: number
  nextAction?: PrehireNextAction | null
  rolePriority?: PrehireRolePriority | null
  workQueue?: PrehireWorkQueueResponse | null
  locale: RecruitingLocale
  onLocaleChange: (locale: RecruitingLocale) => void
  onOpenCandidate: (appKey?: string) => void
  onOpenFollowUps: () => void
  onOpenPendingAssessments: () => void
  onOpenReadyForReview: () => void
  onOpenRolePriority: () => void
  onOpenDestination: (destination?: { page?: string; filters?: Record<string, string> } | null) => void
  onOpenRoleCandidates: (job: PositionSummary) => void
  positions: PositionSummary[]
}) {
  const [expandedQueue, setExpandedQueue] = useState(false)
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) => recruitingCopy(locale, key, vars)
  const reviewCount = typeof readyForReviewTotal === 'number' ? readyForReviewTotal : 0
  const assessmentCount = typeof assessmentPendingTotal === 'number' ? assessmentPendingTotal : 0
  const followUpCount = typeof followUpNeededTotal === 'number' ? followUpNeededTotal : 0
  const roleAttentionValue = rolePriority
    ? Number(rolePriority.follow_up_count || 0) + Number(rolePriority.ready_count || 0) + Number(rolePriority.assessment_pending_count || 0)
    : 0
  const topActions = [
    {
      label: t('overviewReviewReady'),
      value: reviewCount,
      detail: overviewCountDetail(locale, reviewCount, 'overviewReviewReadyDetailOne', 'overviewReviewReadyDetail', 'overviewReviewReadyEmpty'),
      icon: UserCheck,
      tone: reviewCount ? ('warning' as const) : ('success' as const),
      onClick: onOpenReadyForReview,
    },
    ...(assessmentEnabled
      ? [
          {
            label: t('overviewSendAssessments'),
            value: assessmentCount,
            detail: overviewCountDetail(
              locale,
              assessmentCount,
              'overviewSendAssessmentsDetailOne',
              'overviewSendAssessmentsDetail',
              'overviewSendAssessmentsEmpty',
            ),
            icon: ClipboardCheck,
            tone: assessmentCount ? ('warning' as const) : ('success' as const),
            onClick: onOpenPendingAssessments,
          },
        ]
      : []),
    {
      label: t('overviewFollowUp'),
      value: followUpCount,
      detail: overviewCountDetail(locale, followUpCount, 'overviewFollowUpDetailOne', 'overviewFollowUpDetail', 'overviewFollowUpEmpty'),
      icon: Bell,
      tone: followUpCount ? ('danger' as const) : ('success' as const),
      onClick: onOpenFollowUps,
    },
    {
      label: rolePriority ? rolePriority.position_title || rolePriority.position_code : t('overviewPrioritizeRole'),
      value: roleAttentionValue,
      detail: rolePriority ? overviewRoleReason(rolePriority, locale) : t('overviewPrioritizeRoleEmpty'),
      icon: Medal,
      tone: rolePriority ? ('warning' as const) : ('default' as const),
      onClick: onOpenRolePriority,
      eyebrow: rolePriority ? t('overviewPrioritizeRole') : undefined,
    },
  ]
  const heroLabel = overviewHeroReason(nextAction, locale, topActions.find((item) => item.value > 0)?.detail || t('overviewEmptyQueue'))
  const heroTitle = (() => {
    const action = String(nextAction?.action || '')
    if (action === 'follow_up_failed_delivery') return t('overviewFollowUp')
    if (action === 'send_pending_assessments') return t('overviewSendAssessments')
    if (action === 'ready_for_review') return t('overviewReviewReady')
    if (action === 'prioritize_role') return rolePriority?.position_title || t('overviewPrioritizeRole')
    if (action === 'interview_scheduling_debt') return t('overviewScheduleInterviews')
    return topActions.find((item) => item.value > 0)?.label || t('overviewNextAction')
  })()
  const uniqueQueueItems = (() => {
    return dedupeWorkQueueItems(workQueue?.items || [])
  })()
  const queueTotal = workQueueDisplayTotal(workQueue?.total, (workQueue?.items || []).length, uniqueQueueItems.length)
  const visibleQueue = expandedQueue ? uniqueQueueItems : uniqueQueueItems.slice(0, 5)
  const canExpandQueue = uniqueQueueItems.length > 5
  const showRankingCta = String(nextAction?.action || '') === 'prioritize_role'
  const actionNone = !nextAction?.action || nextAction.action === 'none'
  const isQuietOverview =
    actionNone &&
    reviewCount === 0 &&
    assessmentCount === 0 &&
    followUpCount === 0 &&
    !rolePriority &&
    uniqueQueueItems.length === 0
  const quietHeroTitle = isQuietOverview ? t('overviewEmptyHeroTitle') : heroTitle
  const quietHeroLabel = isQuietOverview ? t('overviewEmptyHeroReason') : heroLabel
  return (
    <div className="space-y-6" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <div className="flex justify-end">
        <Button onClick={() => onLocaleChange(locale === 'ar' ? 'en' : 'ar')} type="button" variant="ghost">
          {t('language')}
        </Button>
      </div>
      <section className="relative overflow-hidden rounded-3xl border border-line/80 bg-ink text-white shadow-soft">
        <div className="pointer-events-none absolute -left-12 -top-16 h-52 w-52 rounded-full bg-[#c89445]/10 blur-3xl" />
        <div className="p-6 lg:p-8">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-white/45">{t('overviewNextAction')}</div>
          <h2 className="mt-4 max-w-2xl text-3xl font-semibold tracking-[-0.04em] lg:text-4xl">{quietHeroTitle}</h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-white/70">{quietHeroLabel}</p>
          {!isQuietOverview ? (
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                className="inline-flex h-10 items-center justify-center rounded-full bg-white px-4 text-sm font-semibold text-ink shadow-[0_14px_32px_rgba(0,0,0,0.24)] transition duration-200 hover:-translate-y-0.5 hover:bg-[#f4e7cf] hover:shadow-[0_16px_36px_rgba(0,0,0,0.25),0_0_0_1px_rgba(200,148,69,0.22)]"
                onClick={() => onOpenDestination(nextAction?.destination)}
                type="button"
              >
                {overviewPrimaryCtaLabel(nextAction?.action, locale)}
              </button>
              {showRankingCta ? (
                <button
                  className="inline-flex h-10 items-center justify-center rounded-full border border-white/15 bg-white/10 px-4 text-sm font-semibold text-white shadow-none transition duration-200 hover:-translate-y-0.5 hover:border-[#c89445]/35 hover:bg-white/15"
                  onClick={onOpenRolePriority}
                  type="button"
                >
                  {t('overviewCheckRanking')}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{t('overviewNeedsAttention')}</CardTitle>
          <CardDescription>{t('overviewNeedsAttentionDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {topActions.map((item) => (
            <ActionCard item={item} key={item.label} />
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>{t('overviewTopPriorities')}</CardTitle>
                <CardDescription>
                  {t('overviewPriorityQueueDescription')}
                  {queueTotal > 0 ? ` · ${t('overviewQueueCount', { count: queueTotal })}` : ''}
                </CardDescription>
              </div>
              {canExpandQueue ? (
                <Button onClick={() => setExpandedQueue((current) => !current)} type="button" variant="ghost">
                  {expandedQueue ? t('overviewShowLess') : t('overviewViewAll')}
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {visibleQueue.map((item) => {
              const clickable = Boolean(item.app_key)
              const body = (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">
                      {item.candidate_name || item.position_title || item.app_key || item.action_type}
                    </div>
                    <Badge tone={item.action_type.includes('follow') ? 'danger' : 'warning'}>
                      {overviewQueueBadge(item.action_type, locale)}
                    </Badge>
                  </div>
                  <div className="mt-1 text-sm text-subtle">{overviewQueueReason(item.action_type, locale)}</div>
                </>
              )
              return clickable ? (
                <button
                  type="button"
                  onClick={() => onOpenCandidate(item.app_key)}
                  className="block w-full rounded-3xl border border-white/70 bg-white/48 p-4 text-start shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_10px_26px_rgba(24,20,15,0.045)] backdrop-blur transition duration-200 hover:-translate-y-0.5 hover:bg-panel/85 hover:shadow-soft"
                  key={`${item.action_type}-${item.app_key}`}
                >
                  {body}
                </button>
              ) : (
                <div
                  className="rounded-3xl border border-white/70 bg-white/48 p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_10px_26px_rgba(24,20,15,0.045)] backdrop-blur"
                  key={`${item.action_type}-${item.position_code || item.reason}`}
                >
                  {body}
                </div>
              )
            })}
            {!uniqueQueueItems.length ? <EmptyState text={t('overviewEmptyQueue')} /> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('overviewRoleNextSteps')}</CardTitle>
            <CardDescription>{t('overviewRoleNextStepsDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {positions.slice(0, 5).map((position) => (
              <RoleBottleneck
                assessmentEnabled={assessmentEnabled}
                job={position}
                key={position.position_code}
                locale={locale}
                onOpenCandidates={() => onOpenRoleCandidates(position)}
              />
            ))}
            {!positions.length ? <EmptyState text={t('overviewNoRoles')} /> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function candidateAdvancedFilterCount(filters: CandidateFilters) {
  return [
    filters.position,
    filters.cvStatus,
    filters.assessmentStatus,
    filters.interviewStatus,
    filters.followUp,
    filters.reviewStatus,
    filters.activityFrom,
    filters.activityTo,
    filters.sort && filters.sort !== 'newest' ? filters.sort : '',
  ].filter(Boolean).length
}

function CandidatesPage({
  applications,
  assessmentEnabled,
  busy,
  filters,
  importButton,
  importReview,
  locale,
  offset,
  onFilter,
  onLocale,
  onPage,
  onPreviewCv,
  onSelect,
  positions,
  query,
  setFilters,
  setQuery,
  setStatus,
  status,
  total,
}: {
  applications: ApplicationSummary[]
  assessmentEnabled: boolean
  busy: boolean
  filters: CandidateFilters
  importButton?: ReactNode
  importReview?: ReactNode
  locale: RecruitingLocale
  offset: number
  onFilter: () => void
  onLocale: () => void
  onPage: (offset: number) => void
  onPreviewCv: (application: ApplicationSummary) => void
  onSelect: (application: ApplicationSummary) => void
  positions: PositionSummary[]
  query: string
  setFilters: (value: CandidateFilters | ((current: CandidateFilters) => CandidateFilters)) => void
  setQuery: (value: string) => void
  setStatus: (value: string) => void
  status: string
  total: number
}) {
  const [showMoreFilters, setShowMoreFilters] = useState(false)
  const activeMoreFilterCount = candidateAdvancedFilterCount(filters)
  const pageSize = 50
  const showingStart = total && applications.length ? offset + 1 : 0
  const showingEnd = Math.min(offset + applications.length, total)
  const updateFilter = (key: keyof CandidateFilters, value: string) => setFilters((current) => ({ ...current, [key]: value }))
  const clearAdvancedFilters = () => setFilters({
    position: '',
    cvStatus: '',
    assessmentStatus: '',
    interviewStatus: '',
    followUp: '',
    reviewStatus: '',
    activityFrom: '',
    activityTo: '',
    sort: 'newest',
  })
  return (
    <div className="space-y-6" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      {importReview}
      <Card>
      <CardHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>{recruitingCopy(locale, 'candidateList')}</CardTitle>
              <CardDescription>{recruitingCopy(locale, 'candidateListDescription')}</CardDescription>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button onClick={onLocale} size="sm" type="button" variant="secondary">
                {recruitingCopy(locale, 'language')}
              </Button>
              {importButton}
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
            <Input className="w-full sm:w-64" onChange={(event) => setQuery(event.target.value)} placeholder="Search candidates" value={query} />
            <Select onChange={(event) => setStatus(event.target.value)} value={status}>
              {statuses.map((item) => (
                <option key={item} value={item}>
                  {item ? stageLabel(item) : 'All stages'}
                </option>
              ))}
            </Select>
            <Button onClick={() => setShowMoreFilters((value) => !value)} type="button" variant="secondary">
              More filters{activeMoreFilterCount ? ` (${activeMoreFilterCount})` : ''}
            </Button>
            <Button disabled={busy} onClick={onFilter}>
              <Search size={16} /> Apply
            </Button>
          </div>
        </div>
        {showMoreFilters ? (
          <div className="mt-4 rounded-3xl border border-white/70 bg-white/42 p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_12px_30px_rgba(24,20,15,0.045)] backdrop-blur">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <Select onChange={(event) => updateFilter('position', event.target.value)} value={filters.position}>
                <option value="">All jobs</option>
                {positions.map((position) => (
                  <option key={position.position_code} value={position.position_code}>
                    {position.position_title || position.position_code}
                  </option>
                ))}
              </Select>
              <Select onChange={(event) => updateFilter('cvStatus', event.target.value)} value={filters.cvStatus}>
                <option value="">Applications with CVs</option>
                <option value="with_cv">CV received</option>
                <option value="incomplete">Started but no CV</option>
                <option value="all">All applications</option>
              </Select>
              {assessmentEnabled ? (
                <Select onChange={(event) => updateFilter('assessmentStatus', event.target.value)} value={filters.assessmentStatus}>
                  <option value="">Any assessment status</option>
                  <option value="awaiting">Awaiting assessment</option>
                  <option value="none">No assessment yet</option>
                  <option value="pending">Pending</option>
                  <option value="started">Started</option>
                  <option value="completed">Completed</option>
                  <option value="expired">Expired</option>
                </Select>
              ) : null}
              <Select onChange={(event) => updateFilter('interviewStatus', event.target.value)} value={filters.interviewStatus}>
                <option value="">Any interview status</option>
                <option value="none">No interview yet</option>
                <option value="scheduled">Scheduled</option>
                <option value="completed">Completed</option>
                <option value="no_show">No-show</option>
                <option value="cancelled">Cancelled</option>
              </Select>
              <Select onChange={(event) => updateFilter('followUp', event.target.value)} value={filters.followUp}>
                <option value="">Any follow-up status</option>
                <option value="needed">Follow-up needed</option>
              </Select>
              <Select onChange={(event) => updateFilter('sort', event.target.value)} value={filters.sort}>
                <option value="newest">Newest first</option>
                <option value="last_activity">Last activity</option>
                <option value="ready_for_review">Ready for review first</option>
                {assessmentEnabled ? <option value="assessment_complete">Assessment complete first</option> : null}
                <option value="ranking_score">Ranking score if available</option>
              </Select>
              <Input onChange={(event) => updateFilter('activityFrom', event.target.value)} type="date" value={filters.activityFrom} />
              <Input onChange={(event) => updateFilter('activityTo', event.target.value)} type="date" value={filters.activityTo} />
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-subtle">
              <span>Choose filters, then apply to update the list.</span>
              <Button onClick={clearAdvancedFilters} size="sm" type="button" variant="ghost">Clear advanced filters</Button>
            </div>
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        {applications.length === 0 ? (
          <EmptyState text="No candidates match the current filters. Try clearing filters, or share a job’s application link to start receiving applicants." />
        ) : (
          <>
        <div className="overflow-x-auto rounded-[1.35rem] border border-line/55 bg-panel/75 shadow-[0_10px_30px_rgba(24,20,15,0.035)]">
          <table className="w-full min-w-[1180px] text-left text-sm">
            <thead className="bg-[#f7f1e7]/72 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
              <tr>
                <th className="px-4 py-3">{recruitingCopy(locale, 'candidate')}</th>
                <th className="px-4 py-3">{recruitingCopy(locale, 'job')}</th>
                <th className="px-4 py-3">{recruitingCopy(locale, 'entryMethod')}</th>
                <th className="px-4 py-3">{recruitingCopy(locale, 'applicationStage')}</th>
                <th className="px-4 py-3">{recruitingCopy(locale, 'cvProcessing')}</th>
                {assessmentEnabled ? <th className="px-4 py-3">Assessment</th> : null}
                <th className="px-4 py-3">{recruitingCopy(locale, 'communication')}</th>
                <th className="px-4 py-3">{recruitingCopy(locale, 'nextHumanAction')}</th>
                <th className="px-4 py-3">{recruitingCopy(locale, 'operatorActions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/45 bg-panel/42">
              {applications.map((application) => (
                <CandidateRow
                  application={application}
                  assessmentEnabled={assessmentEnabled}
                  key={application.app_key}
                  locale={locale}
                  onPreviewCv={onPreviewCv}
                  onSelect={onSelect}
                />
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-subtle">
          <span>{total ? `Showing ${showingStart}-${showingEnd} of ${total} candidates` : 'No candidates to show'}</span>
          <div className="flex gap-2">
            <Button disabled={busy || offset <= 0} onClick={() => onPage(Math.max(0, offset - pageSize))} size="sm" variant="secondary">
              Previous
            </Button>
            <Button disabled={busy || offset + applications.length >= total} onClick={() => onPage(offset + pageSize)} size="sm" variant="secondary">
              Next
            </Button>
          </div>
        </div>
          </>
        )}
      </CardContent>
      </Card>
    </div>
  )
}

function CandidateDrawer({
  access,
  assessmentEnabled,
  busy,
  runningAction,
  canManageAssessments,
  canManageInterviews,
  candidate,
  locale,
  message,
  mutate,
  onClose,
  onOpenAssessments,
  onOpenInterviews,
  onScheduleInterview,
  onPreviewCv,
  setMessage,
  videoInterviewsEnabled,
  employmentOffersEnabled,
}: {
  access: DashboardAccess
  assessmentEnabled: boolean
  busy: boolean
  runningAction: string | null
  canManageAssessments: boolean
  canManageInterviews: boolean
  candidate: ApplicationSummary
  locale: RecruitingLocale
  message: string
  mutate: (label: string, action: () => Promise<MutationResponse>, key?: string) => Promise<void>
  onClose: () => void
  onOpenAssessments: () => void
  onOpenInterviews: () => void
  onScheduleInterview: () => void
  onPreviewCv: (application: ApplicationSummary) => void
  setMessage: (value: string) => void
  videoInterviewsEnabled: boolean
  employmentOffersEnabled: boolean
}) {
  const ranking = candidate.ranking
  const allowedActions = new Set(candidate.allowed_actions || [])
  const primaryAction = candidatePrimaryAction(candidate, assessmentEnabled, videoInterviewsEnabled, allowedActions)
  const actionKey = (id: string) => `${id}:${candidate.app_key}`
  const confirm = useConfirm()
  const who = candidateName(candidate)
  const runSendAssessment = async () => {
    if (!(await confirm({ title: 'Send assessment?', body: `${who} will receive an application assessment link by message.`, confirmLabel: 'Send assessment' }))) return
    await mutate('Sending assessment', () => sendAssessment(access, candidate.app_key, message), actionKey('send_assessment'))
  }
  const runSendVideoInterview = async () => {
    if (!(await confirm({ title: 'Send video interview?', body: `${who} will receive a video interview invite link by message.`, confirmLabel: 'Send invite' }))) return
    await mutate('Sending video interview', () => sendVideoInterview(access, candidate.app_key, message), actionKey('send_video_interview'))
  }
  const runNotify = async (key: string) => {
    if (!(await confirm({ title: 'Notify candidate?', body: `${who} will receive a message now.`, confirmLabel: 'Send message' }))) return
    await mutate('Notifying candidate', () => notifyCandidate(access, candidate.app_key, message), key)
  }
  const runPreviewAssessment = async () => {
    const attemptId = candidate.assessment?.attempt_id
    if (!attemptId || candidate.assessment?.status !== 'completed') {
      onOpenAssessments()
      return
    }
    try {
      setMessage('Opening this candidate’s assessment report…')
      await previewAssessmentReport(access, attemptId)
      setMessage('Assessment report opened.')
    } catch (error) {
      setMessage(friendlyDashboardError(error, 'Could not open this candidate’s assessment report.'))
    }
  }
  const runHire = async () => {
    if (
      !(await confirm({
        title: 'Hire this candidate?',
        body: `This will hire ${who}, create their employee record, and start onboarding. This is hard to undo.`,
        confirmLabel: 'Hire candidate',
        destructive: true,
      }))
    )
      return
    await mutate('Hiring candidate', () => hireCandidate(access, candidate.app_key), actionKey('hire'))
  }
  const runShortlist = async () => {
    if (
      !(await confirm({
        title: 'Shortlist this candidate?',
        body: `Move ${who} to the shortlist for ${candidate.position?.title || candidate.position?.code || 'this role'}.`,
        confirmLabel: 'Shortlist candidate',
      }))
    )
      return
    await mutate('Shortlisting candidate', () => shortlistCandidate(access, candidate.app_key), actionKey('shortlist'))
  }
  const runReject = async () => {
    if (
      !(await confirm({
        title: 'Reject this candidate?',
        body: `This will move ${who} out of the active pipeline. You can still find their record later.`,
        confirmLabel: 'Reject candidate',
        destructive: true,
      }))
    )
      return
    await mutate('Rejecting candidate', () => rejectCandidate(access, candidate.app_key), actionKey('reject'))
  }
  const runPrimaryAction = () => {
    if (primaryAction.id === 'send_assessment') return runSendAssessment()
    if (primaryAction.id === 'send_video_interview') return runSendVideoInterview()
    if (primaryAction.id === 'review_video') {
      onOpenInterviews()
      return
    }
    if (primaryAction.id === 'shortlist') return void runShortlist()
    if (primaryAction.id === 'hire') return void runHire()
    if (primaryAction.id === 'reject') return void runReject()
    if (primaryAction.id === 'notify') return runNotify(actionKey('notify'))
    if (primaryAction.id === 'schedule_interview') return onScheduleInterview()
  }
  const primaryRunning = runningAction === actionKey(primaryAction.id)
  const primaryDisabled =
    busy || primaryAction.id === 'none'
  return (
    <div className="fixed inset-0 z-30 bg-ink/25 backdrop-blur-[2px]" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-3xl animate-[drawerIn_220ms_ease-out] flex-col overflow-y-auto border-l border-white/70 bg-panel/95 p-6 shadow-[0_28px_90px_rgba(24,20,15,0.18)] backdrop-blur-2xl"
        dir={locale === 'ar' ? 'rtl' : 'ltr'}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(candidate.canonical_stage || candidate.status)}>
                {canonicalStageLabel(candidate.canonical_stage || candidate.status, locale)}
              </Badge>
              {ranking?.score != null ? <Badge>{Math.round(ranking.score)} / 100 fit</Badge> : null}
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">{candidateName(candidate)}</h2>
            <p className="mt-1 text-sm text-subtle">
              {recruitingCopy(locale, 'job')}: {candidate.position?.title || candidate.position?.code || (locale === 'ar' ? 'غير محددة' : 'Unassigned job')}
            </p>
          </div>
          <Button onClick={onClose} variant="secondary">
            Close
          </Button>
        </div>

        {candidate.communication?.stage_changed_without_contact ? (
          <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
            <AlertTriangle className="mr-2 inline" size={16} />
            {recruitingCopy(locale, 'notInformed')}
          </div>
        ) : null}

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Info label={recruitingCopy(locale, 'applicationStage')} value={canonicalStageLabel(candidate.canonical_stage || candidate.status, locale)} />
          <Info label={recruitingCopy(locale, 'entryMethod')} value={intakeSourceLabel(candidate.intake_source || candidate.data_source, locale)} />
          <Info label={recruitingCopy(locale, 'communication')} value={communicationLabel(candidate.communication?.status, locale)} />
          <Info label={recruitingCopy(locale, 'cvProcessing')} value={facetStatusLabel(candidate.cv_processing?.status || (candidate.cv?.received ? 'received' : 'not_received'), locale)} />
          <Info label={recruitingCopy(locale, 'screening')} value={facetStatusLabel(candidate.screening?.status || candidate.screening_status || 'not_started', locale)} />
          <Info label={recruitingCopy(locale, 'nextHumanAction')} value={candidate.waiting_for_hr?.[0] ? workflowItemLabel(candidate.waiting_for_hr[0], locale) : recruitingCopy(locale, 'noPendingHr')} />
        </div>

        <section className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-line/60 bg-white/45 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{recruitingCopy(locale, 'automaticActions')}</div>
            <ul className="mt-2 space-y-1 text-sm text-text">
              {(candidate.automatic_activity?.length ? candidate.automatic_activity : []).map((item) => <li key={item}>• {workflowItemLabel(item, locale)}</li>)}
              {!candidate.automatic_activity?.length ? <li className="text-subtle">{recruitingCopy(locale, 'noAutomaticActions')}</li> : null}
            </ul>
          </div>
          <div className="rounded-2xl border border-line/60 bg-white/45 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{recruitingCopy(locale, 'waitingForHr')}</div>
            <ul className="mt-2 space-y-1 text-sm text-text">
              {(candidate.waiting_for_hr?.length ? candidate.waiting_for_hr : []).map((item) => <li key={item}>• {workflowItemLabel(item, locale)}</li>)}
              {!candidate.waiting_for_hr?.length ? <li className="text-subtle">{recruitingCopy(locale, 'noPendingHr')}</li> : null}
            </ul>
          </div>
        </section>

        <section className="mt-5 rounded-[1.45rem] border border-white/70 bg-white/58 p-4 shadow-[0_1px_0_rgba(255,255,255,0.82)_inset,0_12px_30px_rgba(24,20,15,0.055)] backdrop-blur">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{recruitingCopy(locale, 'humanDecision')}</div>
              <div className="mt-1.5 text-[17px] font-semibold tracking-tight text-text">{recruitingActionLabel(primaryAction.id, locale)}</div>
              <p className="mt-1.5 text-[13px] leading-5 text-subtle">
                {primaryAction.detail}
              </p>
            </div>
            <Textarea
              className="min-h-16 text-[13px]"
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Optional note"
              rows={2}
              value={message}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {primaryAction.id !== 'none' ? <Button disabled={primaryDisabled} onClick={runPrimaryAction}>
              {primaryRunning ? (
                <Loader2 className="animate-spin" size={16} />
              ) : primaryAction.icon === 'video' ? (
                <Video size={16} />
              ) : primaryAction.icon === 'send' ? (
                <Send size={16} />
              ) : (
                <UserCheck size={16} />
              )}
              {primaryRunning ? 'Working…' : recruitingActionLabel(primaryAction.id, locale)}
            </Button> : null}
            {allowedActions.has('preview_cv') ? <Button disabled={!candidate.cv?.received} onClick={() => onPreviewCv(candidate)} title={!candidate.cv?.received ? 'CV not received yet' : undefined} variant="secondary">
              <FileText size={16} /> {recruitingActionLabel('preview_cv', locale)}
            </Button> : null}
            {candidate.allowed_actions?.length ? <details className="relative">
              <summary className="inline-flex h-11 cursor-pointer items-center rounded-full px-4 text-sm font-semibold text-subtle transition hover:bg-[#f4e7cf]/45 hover:text-text">
                {locale === 'ar' ? 'إجراءات أخرى' : 'More actions'}
              </summary>
              <div className="mt-2 grid gap-2 rounded-3xl border border-white/70 bg-panel/90 p-3 shadow-soft sm:grid-cols-2">
                {assessmentEnabled && allowedActions.has('send_assessment') ? (
                  <Button disabled={busy || !canManageAssessments} onClick={() => void runSendAssessment()} size="sm" variant="secondary">
                    {runningAction === actionKey('send_assessment') ? <><Loader2 className="animate-spin" size={14} /> Sending…</> : recruitingActionLabel('send_assessment', locale)}
                  </Button>
                ) : null}
                {videoInterviewsEnabled && allowedActions.has('send_video_interview') ? (
                  <Button disabled={busy || !canManageInterviews} onClick={() => void runSendVideoInterview()} size="sm" variant="secondary">
                    {runningAction === actionKey('send_video_interview') ? <><Loader2 className="animate-spin" size={14} /> Sending…</> : recruitingActionLabel('send_video_interview', locale)}
                  </Button>
                ) : null}
                {allowedActions.has('shortlist') ? <Button disabled={busy} onClick={() => void runShortlist()} size="sm" variant="secondary">
                  {runningAction === actionKey('shortlist') ? <><Loader2 className="animate-spin" size={14} /> Shortlisting…</> : recruitingActionLabel('shortlist', locale)}
                </Button> : null}
                {allowedActions.has('schedule_interview') ? <Button disabled={busy} onClick={onScheduleInterview} size="sm" variant="secondary">
                  {recruitingActionLabel('schedule_interview', locale)}
                </Button> : null}
                {allowedActions.has('notify') ? <Button disabled={busy} onClick={() => void runNotify(actionKey('notify'))} size="sm" variant="secondary">
                  {runningAction === actionKey('notify') ? <><Loader2 className="animate-spin" size={14} /> Notifying…</> : recruitingActionLabel('notify', locale)}
                </Button> : null}
                {allowedActions.has('hire') ? <Button disabled={busy} onClick={() => void runHire()} size="sm" variant="secondary">
                  {runningAction === actionKey('hire') ? <><Loader2 className="animate-spin" size={14} /> Hiring…</> : recruitingActionLabel('hire', locale)}
                </Button> : null}
                {allowedActions.has('reject') ? <Button disabled={busy} onClick={() => void runReject()} size="sm" variant="secondary">
                  {runningAction === actionKey('reject') ? <><Loader2 className="animate-spin" size={14} /> Rejecting…</> : recruitingActionLabel('reject', locale)}
                </Button> : null}
              </div>
            </details> : null}
          </div>
          {!candidate.allowed_actions?.length ? (
            <div className="mt-3 text-xs text-subtle">{recruitingCopy(locale, 'noPermittedActions')}</div>
          ) : null}
        </section>

        <DrawerDecisionContext
          application={candidate}
          busy={busy}
          canManageCandidates={allowedActions.has('generate_evaluation')}
          locale={locale}
          onGenerateEvaluation={() => mutate('Generating evaluation', () => generateCandidateEvaluation(access, candidate.app_key))}
        />

        <CandidateVideoInterviewCard application={candidate} onOpenInterviews={onOpenInterviews} />

        <OfferPanel
          access={access}
          appKey={candidate.app_key}
          enabled={employmentOffersEnabled}
          busy={busy}
          onMessage={setMessage}
        />

        <div className="mt-6 space-y-3">
          <details className="rounded-3xl border border-white/70 bg-white/42 p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_10px_26px_rgba(24,20,15,0.04)]">
            <summary className="cursor-pointer text-sm font-semibold text-text">History & details</summary>
            <div className="mt-4 space-y-3">
              <TimelineItem label="Application created" value={formatDateTime(candidate.ingested_at)} />
              <TimelineItem label="Current stage updated" value={formatDateTime(candidate.updated_at)} />
              <TimelineItem label="Screening" value={basicScreeningLabel(candidate)} />
              <Info label="Last activity" value={formatDateTime(candidate.updated_at || candidate.ingested_at)} />
            </div>
          </details>

          {assessmentEnabled && candidate.assessment?.status ? (
            <details className="rounded-3xl border border-white/70 bg-white/42 p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_10px_26px_rgba(24,20,15,0.04)]">
              <summary className="cursor-pointer text-sm font-semibold text-text">Assessment details</summary>
              <div className="mt-4 rounded-3xl border border-white/70 bg-panel/75 p-4 text-sm leading-6 shadow-soft">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold">{assessmentLabel(candidate)}</div>
                    <div className="mt-1 text-subtle">{candidate.assessment.summary || 'Report will appear here after completion.'}</div>
                  </div>
                  <Button onClick={() => void runPreviewAssessment()} size="sm" variant="secondary">
                    {candidate.assessment.status === 'completed' && candidate.assessment.attempt_id ? 'View report' : 'Open assessments'}
                  </Button>
                </div>
              </div>
            </details>
          ) : null}

          {candidate.interview?.status ? (
            <details className="rounded-3xl border border-white/70 bg-white/42 p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_10px_26px_rgba(24,20,15,0.04)]">
              <summary className="cursor-pointer text-sm font-semibold text-text">Interview details</summary>
              <div className="mt-4 rounded-3xl border border-white/70 bg-panel/75 p-4 text-sm leading-6 shadow-soft">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold">{interviewLabel(candidate)}</div>
                    <div className="mt-1 text-subtle">
                      {interviewSummaryText(candidate.interview) || 'Interview feedback will appear here after HR saves notes.'}
                    </div>
                  </div>
                  <Badge tone={candidate.interview.feedback_status === 'feedback_complete' ? 'success' : 'warning'}>
                    {stageLabel(candidate.interview.feedback_status)}
                  </Badge>
                </div>
                <InterviewTruthGrid interview={candidate.interview} />
                {candidate.interview.meet_link ? (
                  <Button className="mt-3" onClick={() => window.open(candidate.interview?.meet_link, '_blank', 'noopener,noreferrer')} size="sm" variant="secondary">
                    <ExternalLink size={14} /> Open Meet link
                  </Button>
                ) : null}
              </div>
            </details>
          ) : null}
        </div>
      </aside>
    </div>
  )
}

function candidatePrimaryAction(
  application: ApplicationSummary,
  assessmentEnabled: boolean,
  videoInterviewsEnabled: boolean,
  allowedActions: Set<string>,
) {
  const interview = application.interview
  const asyncStatus = interview?.interview_type === 'async_video' ? asyncVideoDisplayStatus(interview) : null
  if (asyncStatus?.label === 'Ready for review' && allowedActions.has('schedule_interview')) {
    return {
      id: 'review_video',
      label: 'Review video response',
      button: 'Review video',
      detail: 'The candidate has submitted a video interview. Review the answer, summary, and evidence before deciding the next step.',
      icon: 'video',
    }
  }
  if (assessmentEnabled && allowedActions.has('send_assessment') && application.cv?.received && !application.assessment?.status) {
    return {
      id: 'send_assessment',
      label: 'Send assessment',
      button: 'Send assessment',
      detail: 'The candidate has a CV on file and is ready for an application assessment.',
      icon: 'send',
    }
  }
  if (videoInterviewsEnabled && allowedActions.has('send_video_interview') && application.cv?.received && interview?.interview_type !== 'async_video') {
    return {
      id: 'send_video_interview',
      label: 'Send video interview',
      button: 'Send video interview',
      detail: 'Invite the candidate to answer the standard video interview questions in one video.',
      icon: 'video',
    }
  }
  if (allowedActions.has('shortlist')) {
    return {
      id: 'shortlist',
      label: 'Shortlist candidate',
      button: 'Shortlist',
      detail: 'The candidate has enough evidence for HR to decide whether to move forward.',
      icon: 'user',
    }
  }
  if (allowedActions.has('schedule_interview')) {
    return {
      id: 'schedule_interview',
      label: 'Schedule interview',
      button: 'Schedule interview',
      detail: 'Open interview scheduling. The interview is only created after a human confirms the details.',
      icon: 'user',
    }
  }
  if (allowedActions.has('hire')) {
    return {
      id: 'hire',
      label: 'Hire candidate',
      button: 'Hire',
      detail: 'Review all evidence before making the final human hiring decision.',
      icon: 'user',
    }
  }
  if (allowedActions.has('reject')) {
    return {
      id: 'reject',
      label: 'Reject candidate',
      button: 'Reject',
      detail: 'Review all evidence before making the final human rejection decision.',
      icon: 'user',
    }
  }
  if (allowedActions.has('notify')) {
    return {
      id: 'notify',
      label: 'Contact candidate',
      button: 'Contact candidate',
      detail: 'Send a message about the current application step.',
      icon: 'send',
    }
  }
  return {
    id: 'none',
    label: 'No permitted action',
    button: 'No permitted action',
    detail: 'No application action is permitted for this operator and current stage.',
    icon: 'user',
  }
}

function CandidateVideoInterviewCard({ application, onOpenInterviews }: { application: ApplicationSummary; onOpenInterviews: () => void }) {
  const interview = application.interview
  if (interview?.interview_type !== 'async_video') return null
  const review = interview.video_review_status
  const displayStatus = asyncVideoDisplayStatus(interview)
  const summary = interview.ai_summary?.overall_summary || interview.ai_summary?.summary
  const answerCount = interview.video_answers?.length || review?.response_count || 0
  const questionCount = interview.video_questions?.length || interview.video_processing?.question_count || review?.required_count || 0
  const answerLabel = interview.response_mode === 'single_video' ? `${answerCount ? '1 video' : 'No video'}${questionCount ? ` / ${questionCount} questions` : ''}` : `${answerCount}${review?.required_count ? ` of ${review.required_count}` : ''}`
  return (
    <section className="mt-6 rounded-3xl border border-white/70 bg-white/45 p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_12px_30px_rgba(24,20,15,0.05)] backdrop-blur">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold">Wathefni analysis · video interview</div>
            <Badge tone={displayStatus.tone}>{displayStatus.label}</Badge>
          </div>
          <div className="mt-1 text-sm leading-6 text-subtle">
            {displayStatus.description}
          </div>
        </div>
        <Button onClick={onOpenInterviews} size="sm" variant="secondary">
          Open review
        </Button>
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <Info label="Answers submitted" value={answerLabel} />
        <Info label="Processing" value={review?.pending_count ? `${review.pending_count} pending` : review?.failed_count ? `${review.failed_count} needs retry` : 'Synced'} />
        <Info label="HR summary" value={review?.summary_ready ? 'Ready' : 'Not ready yet'} />
      </div>
      {summary ? <p className="mt-3 line-clamp-3 text-sm leading-6 text-subtle">{summary}</p> : null}
    </section>
  )
}

function DrawerDecisionContext({
  application,
  busy,
  canManageCandidates,
  locale,
  onGenerateEvaluation,
}: {
  application: ApplicationSummary
  busy: boolean
  canManageCandidates: boolean
  locale: RecruitingLocale
  onGenerateEvaluation: () => void
}) {
  const evaluation = application.ranking?.gpt_evaluation
  const strengths = evaluation?.strengths || candidateRankingEvidenceUsed(application)
  const gaps = candidateRankingMissingEvidence(application)
  const risks = evaluation?.risks || []
  if (!evaluation) {
    return (
      <section className="mt-4 rounded-[1.35rem] border border-dashed border-line/70 bg-white/42 p-4 shadow-[0_1px_0_rgba(255,255,255,0.78)_inset]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{recruitingCopy(locale, 'analysis')}</div>
            <div className="mt-1 text-sm font-semibold text-text">No fit summary generated yet.</div>
            <p className="mt-1 max-w-xl text-[12.5px] leading-5 text-subtle">
              Generate a fit summary for {application.position?.title || application.position?.code || 'this role'} when you need deeper evidence.
            </p>
          </div>
          <Button disabled={busy || !canManageCandidates} onClick={onGenerateEvaluation} size="sm" variant="secondary">
            {busy ? <Loader2 className="animate-spin" size={14} /> : <Medal size={14} />} Generate
          </Button>
        </div>
      </section>
    )
  }
  return (
    <details className="mt-4 rounded-[1.35rem] border border-white/70 bg-white/42 p-4 shadow-[0_1px_0_rgba(255,255,255,0.78)_inset,0_8px_22px_rgba(24,20,15,0.035)]">
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{recruitingCopy(locale, 'analysis')}</div>
            <p className="mt-1 line-clamp-2 text-[13px] font-medium leading-5 text-text">
              {evaluation?.fit_summary || candidateSummary(application)}
            </p>
          </div>
          {application.ranking?.score != null ? <Badge>{Math.round(application.ranking.score)} / 100</Badge> : null}
        </div>
        <div className="mt-2 text-[12px] font-medium text-subtle">Open evidence details</div>
      </summary>
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <EvaluationPanel label={recruitingCopy(locale, 'sourceEvidence')} tone="strong" values={strengths} />
        <EvaluationPanel label={recruitingCopy(locale, 'missingInformation')} tone="warning" values={gaps} />
        <EvaluationPanel label={recruitingCopy(locale, 'concerns')} tone="danger" values={risks} />
      </div>
      <div className="mt-4 rounded-xl border border-ink/10 bg-ink px-4 py-3 text-sm text-white">
        <span className="font-semibold">{recruitingCopy(locale, 'recommendation')}: </span>
        {evaluation?.recommended_next_step || recommendedCandidateAction(application)}
      </div>
      <div className="mt-3 text-xs text-subtle">{recruitingCopy(locale, 'advisory')}</div>
    </details>
  )
}

function JobDrawer({
  job,
  canManageJobs,
  statusBusy,
  onClose,
  onCopy,
  onDownloadQr,
  onSetStatus,
  onViewCandidates,
  qrDataUrl,
}: {
  job: PositionSummary
  canManageJobs: boolean
  statusBusy: boolean
  onClose: () => void
  onCopy: (value: string | undefined, label: string) => void
  onDownloadQr: () => void
  onSetStatus: (status: 'open' | 'closed') => void
  onViewCandidates: () => void
  qrDataUrl: string
}) {
  const isOpen = normalizedJobStatus(job) === 'open'
  return (
    <div className="fixed inset-0 z-30 bg-ink/30" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-3xl flex-col overflow-y-auto border-l border-line bg-panel p-6 shadow-soft"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line pb-5">
          <div>
            <Badge tone={isOpen ? 'success' : 'muted'}>{stageLabel(normalizedJobStatus(job))}</Badge>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">{job.position_title || job.position_code}</h2>
            <p className="mt-1 text-sm text-subtle">{job.description || 'Application opening.'}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              disabled={!canManageJobs || statusBusy}
              onClick={() => onSetStatus(isOpen ? 'closed' : 'open')}
              title={!canManageJobs ? 'Managing job openings is disabled for your role' : undefined}
              variant="secondary"
            >
              {isOpen ? 'Close job' : 'Reopen job'}
            </Button>
            <Button onClick={onClose} variant="secondary">
              Close
            </Button>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <Info label="Status" value={stageLabel(normalizedJobStatus(job))} />
          <Info label="Candidate count" value={String(job.application_count || 0)} />
          <Info label="Latest applicant" value={job.latest_applicant || 'No applicants yet'} />
          <Info label="Created" value={formatDateTime(job.created_at || job.latest_application_at)} />
        </div>

        <details className="mt-6 rounded-2xl border border-line bg-panel-muted/60 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-text">Sharing details</summary>
          <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
            <Info label="Application code" value={job.apply_code || 'Not generated yet'} />
            <Info label="Application link" value={job.application_link || 'Not generated yet'} />
          </div>
        </details>

        <section className="mt-6 grid gap-6 xl:grid-cols-[260px_1fr]">
          <div className="rounded-lg border border-line bg-panel-muted/60 p-4">
            <div className="text-sm font-semibold">QR code</div>
            {qrDataUrl ? (
              <img alt={`QR code for ${job.position_title || job.position_code}`} className="mt-4 rounded-lg border border-line bg-white p-3" src={qrDataUrl} />
            ) : (
              <EmptyState text="QR link is not available for this job yet." />
            )}
            <div className="mt-4 grid gap-2">
              <Button disabled={!job.apply_code} onClick={() => onCopy(job.apply_code, 'Application code')} size="sm" variant="secondary">
                <Copy size={14} /> Copy code
              </Button>
              <Button disabled={!job.application_link} onClick={() => onCopy(job.application_link, 'Application link')} size="sm" variant="secondary">
                <Copy size={14} /> Copy link
              </Button>
              <Button disabled={!qrDataUrl} onClick={onDownloadQr} size="sm" variant="secondary">
                <Download size={14} /> Download QR
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-subtle">Requirements</h3>
              <div className="mt-3 rounded-lg border border-line bg-panel-muted/60 p-4 text-sm leading-6 text-subtle">
                {formatRequirements(job.requirements)}
              </div>
            </section>
            <section>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-subtle">Candidate funnel by stage</h3>
              <div className="mt-3 space-y-3">
                {(job.stage_counts?.length ? job.stage_counts : fallbackStatusCounts()).map((item) => (
                  <PipelineRow count={item.count} key={item.status} label={stageLabel(item.status)} />
                ))}
              </div>
            </section>
          </div>
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-subtle">Recent applicants</h3>
          <div className="mt-3 space-y-2">
            {(job.recent_applicants || []).map((applicant) => (
              <div className="rounded-lg border border-line bg-panel-muted/60 p-3" key={applicant.app_key}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{applicant.candidate_name || applicant.phone || 'Unknown applicant'}</div>
                  <Badge tone={statusTone(applicant.status)}>{stageLabel(applicant.status)}</Badge>
                </div>
                <div className="mt-1 text-sm text-subtle">{formatDateTime(applicant.ingested_at || applicant.updated_at)}</div>
              </div>
            ))}
            {!job.recent_applicants?.length ? <EmptyState text="No applicants have used this job link yet." /> : null}
          </div>
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-subtle">Candidate contact activity</h3>
          <div className="mt-3 space-y-2">
            {(job.notifications || []).map((item) => (
              <div className="rounded-lg border border-line bg-panel-muted/60 p-3" key={item.delivery_id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="font-medium">{item.target_phone || 'Candidate contact'}</div>
                  <Badge tone={statusTone(item.status)}>{stageLabel(item.status)}</Badge>
                </div>
                <div className="mt-1 text-sm text-subtle">{jobNotificationLabel(item)}</div>
              </div>
            ))}
            {!job.notifications?.length ? <EmptyState text="No recent candidate contact activity for this opening." /> : null}
          </div>
        </section>

        <section className="mt-6 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <Button onClick={onViewCandidates} variant="secondary">
            View candidates
          </Button>
          <Button disabled={!job.application_link} onClick={() => onCopy(job.application_link, 'Application link')} variant="secondary">
            <ExternalLink size={16} /> Copy link
          </Button>
        </section>
      </aside>
    </div>
  )
}

function JobsPage({
  canExportReports,
  canManageJobs,
  jobsData,
  loadingMore,
  onCreate,
  onExport,
  onLoadMore,
  onQueryChange,
  onRefresh,
  onSelect,
  onViewCandidates,
  query,
}: {
  canExportReports: boolean
  canManageJobs: boolean
  jobsData: PositionsResponse | null
  loadingMore: boolean
  onCreate: () => void
  onExport: () => void
  onLoadMore: () => void
  onQueryChange: (value: string) => void
  onRefresh: () => void
  onSelect: (job: PositionSummary) => void
  onViewCandidates: (job: PositionSummary) => void
  query: string
}) {
  const positions = jobsData?.positions || []
  const summary = jobsData?.summary
  const totalCount = jobsData?.total_count ?? positions.length
  const isSearching = query.trim().length > 0
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Jobs</h2>
          <p className="mt-1 text-sm text-subtle">Manage job openings, application links, QR codes, and applicant demand.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canManageJobs} onClick={onCreate} title={!canManageJobs ? 'Creating job openings is disabled for your role' : undefined}>
            <Plus size={16} /> Create with Assistant
          </Button>
          <Button onClick={onRefresh} variant="secondary">
            <RefreshCw size={16} /> Refresh
          </Button>
          <Button disabled={!canExportReports} onClick={onExport} title={!canExportReports ? 'Exports are disabled for your role' : undefined} variant="secondary">
            <Download size={16} /> Export
          </Button>
        </div>
      </div>

      <MetricGrid
        metrics={[
          { label: 'Open jobs', value: summary?.open_positions ?? 0, icon: BriefcaseBusiness },
          { label: 'Total applications', value: summary?.total_applications ?? 0, icon: Users },
          { label: 'Active QR codes', value: summary?.active_qr_codes ?? 0, icon: QrCode },
          { label: 'Closed jobs', value: summary?.closed_positions ?? 0, icon: PauseCircle },
        ]}
      />

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <div>
            <CardTitle>Job openings</CardTitle>
            <CardDescription>
              {isSearching
                ? `${totalCount} result${totalCount === 1 ? '' : 's'} for “${query.trim()}”`
                : 'Application links, QR codes, and applicant demand by role.'}
            </CardDescription>
          </div>
          <SearchInput onChange={onQueryChange} placeholder="Search jobs by title or code…" value={query} />
        </CardHeader>
        <CardContent>
          {positions.length === 0 ? (
            <EmptyState
              text={
                isSearching
                  ? `No job openings match “${query.trim()}”.`
                  : 'No job openings yet. Use “Create with Assistant” to add your first opening — you’ll get an application link and QR code to share.'
              }
            />
          ) : (
          <div className="overflow-x-auto rounded-[1.35rem] border border-line/55 bg-panel/75 shadow-[0_10px_30px_rgba(24,20,15,0.035)]">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-[#f7f1e7]/72 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                <tr>
                  <th className="px-4 py-3">Job</th>
                  <th className="px-4 py-3">Application code</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Applications</th>
                  <th className="px-4 py-3">Latest applicant</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/45 bg-panel/42">
                {positions.map((job) => (
                  <tr className="cursor-pointer transition duration-150 hover:bg-white/55" key={job.position_code} onClick={() => onSelect(job)}>
                    <td className="px-4 py-2.5">
                      <div className="font-semibold">{job.position_title || job.position_code}</div>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex max-w-[220px] items-center rounded-full border border-line bg-panel-muted px-2.5 py-1 font-mono text-xs text-text">
                        <span className="truncate">{job.apply_code || 'Not generated yet'}</span>
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={normalizedJobStatus(job) === 'open' ? 'success' : 'muted'}>
                        {stageLabel(normalizedJobStatus(job))}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <button className="font-semibold underline-offset-4 hover:underline" onClick={(event) => { event.stopPropagation(); onViewCandidates(job) }} type="button">
                        {job.application_count || 0}
                      </button>
                      {Number(job.active_count || 0) > 0 ? (
                        <div className="text-xs font-medium text-amber-600">{job.active_count} waiting for review</div>
                      ) : (
                        <div className="text-xs text-subtle">No one waiting</div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-subtle">{job.latest_applicant || 'No applicants yet'}</td>
                    <td className="px-4 py-2.5 text-subtle">{formatDateTime(job.created_at || job.latest_application_at)}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-2">
                        <Button onClick={(event) => { event.stopPropagation(); onSelect(job) }} size="sm" variant="secondary">
                          Manage
                        </Button>
                        {job.application_count ? (
                          <Button onClick={(event) => { event.stopPropagation(); onViewCandidates(job) }} size="sm" variant="ghost">
                            View candidates
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <LoadMoreBar loaded={positions.length} loading={loadingMore} noun="job" onLoadMore={onLoadMore} total={totalCount} />
          </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function InterviewsPage({
  busy,
  canManageInterviews,
  feedbackCounts,
  filters,
  interviews,
  limit,
  locale,
  notesDrafts,
  offset,
  onOpenCandidate,
  onLocale,
  onPreviewVideoAnswer,
  onRetryVideoTranscripts,
  onSaveNotes,
  onSearch,
  onSetNotes,
  onSetOffset,
  onStatusChange,
  onUpdateFilters,
  statusCounts,
  total,
  videoCount,
}: {
  busy: boolean
  canManageInterviews: boolean
  feedbackCounts: Array<{ feedback_status: string; count: number }>
  filters: { tab: string; q: string; role: string; date: string; interviewer: string }
  interviews: CandidateInterview[]
  limit: number
  locale: RecruitingLocale
  notesDrafts: Record<string, string>
  offset: number
  onOpenCandidate: (appKey?: string) => void
  onLocale: () => void
  onPreviewVideoAnswer: (videoUrl?: string) => void
  onRetryVideoTranscripts: (interview: CandidateInterview) => void
  onSaveNotes: (interview: CandidateInterview) => void
  onSearch: () => void
  onSetNotes: (interviewId: string, value: string) => void
  onSetOffset: (offset: number) => void
  onStatusChange: (interview: CandidateInterview, status: string) => void
  onUpdateFilters: (filters: Partial<{ tab: string; q: string; role: string; date: string; interviewer: string }>) => void
  statusCounts: Array<{ status: string; count: number }>
  total: number
  videoCount: number
}) {
  const [selectedInterview, setSelectedInterview] = useState<CandidateInterview | null>(null)
  // "Upcoming" tab table filters status IN ('scheduled','rescheduled'); count both so the
  // tab/metric number matches the rows shown.
  const scheduled = interviewStatusCount(statusCounts, 'scheduled') + interviewStatusCount(statusCounts, 'rescheduled')
  const completed = interviewStatusCount(statusCounts, 'completed')
  const noShows = interviewStatusCount(statusCounts, 'no_show')
  const notesPending = interviewFeedbackCount(feedbackCounts, 'notes_pending')
  const feedbackComplete = interviewFeedbackCount(feedbackCounts, 'feedback_complete')
  const tabs = [
    { id: 'upcoming', label: 'Upcoming', count: scheduled },
    { id: 'video_interviews', label: 'Video interviews', count: videoCount },
    { id: 'needs_feedback', label: 'Needs feedback', count: notesPending },
    { id: 'completed', label: 'Completed', count: completed },
    { id: 'no_show', label: 'No-shows', count: noShows },
    { id: 'cancelled', label: 'Cancelled', count: interviewStatusCount(statusCounts, 'cancelled') },
    { id: 'all', label: 'All', count: statusCounts.reduce((sum, item) => sum + Number(item.count || 0), 0) },
  ]
  const canGoBack = offset > 0
  const canGoNext = offset + limit < total
  return (
    <div className="space-y-6" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <MetricGrid
        metrics={[
          { label: 'Upcoming interviews', value: scheduled, icon: CalendarCheck },
          { label: 'Completed', value: completed, icon: CheckCircle2 },
          { label: 'No-shows', value: noShows, icon: AlertTriangle },
          { label: 'Need feedback', value: notesPending, icon: Pencil },
          { label: 'Video interviews', value: videoCount, icon: Video },
          { label: 'Feedback complete', value: feedbackComplete, icon: FileText },
        ]}
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{recruitingCopy(locale, 'interviewQueue')}</CardTitle>
              <CardDescription>{recruitingCopy(locale, 'interviewQueueDescription')}</CardDescription>
            </div>
            <Button onClick={onLocale} size="sm" type="button" variant="secondary">
              {recruitingCopy(locale, 'language')}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {tabs.map((tab) => (
              <button
                className={cn(
                  'rounded-full border px-3 py-1.5 text-sm transition',
                  filters.tab === tab.id ? 'border-ink bg-ink text-white' : 'border-line bg-panel-muted/60 text-subtle hover:border-ink/25 hover:text-text',
                )}
                key={tab.id}
                onClick={() => {
                  onUpdateFilters({ tab: tab.id })
                  onSetOffset(0)
                }}
                type="button"
              >
                {tab.label} <span className="ml-1 opacity-70">{tab.count}</span>
              </button>
            ))}
          </div>

          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-[1.2fr_1fr_180px_180px_auto]">
            <Input onChange={(event) => onUpdateFilters({ q: event.target.value })} placeholder="Search candidate or email" value={filters.q} />
            <Input onChange={(event) => onUpdateFilters({ role: event.target.value })} placeholder="Filter by role" value={filters.role} />
            <Input onChange={(event) => onUpdateFilters({ date: event.target.value })} type="date" value={filters.date} />
            <Input onChange={(event) => onUpdateFilters({ interviewer: event.target.value })} placeholder="Interviewer" value={filters.interviewer} />
            <Button disabled={busy} onClick={onSearch}>
              <Search size={16} /> Search
            </Button>
          </div>

          {interviews.length ? (
            <div className="overflow-x-auto rounded-[1.35rem] border border-line/55 bg-panel/75 shadow-[0_10px_30px_rgba(24,20,15,0.035)]">
              <div className="min-w-[1160px]">
                <div className="grid grid-cols-[minmax(170px,1.1fr)_minmax(140px,0.9fr)_minmax(130px,0.8fr)_minmax(130px,0.8fr)_minmax(150px,0.9fr)_minmax(160px,1fr)_auto] gap-3 border-b border-line/55 bg-[#f7f1e7]/72 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                  <div>{recruitingCopy(locale, 'candidate')}</div>
                  <div>{recruitingCopy(locale, 'job')}</div>
                  <div>{recruitingCopy(locale, 'applicationStage')}</div>
                  <div>{recruitingCopy(locale, 'interviewStatus')}</div>
                  <div>{recruitingCopy(locale, 'schedule')}</div>
                  <div>{recruitingCopy(locale, 'nextHumanAction')}</div>
                  <div></div>
                </div>
                {interviews.map((interview) => (
                  <InterviewQueueRow
                    interview={interview}
                    key={interview.interview_id}
                    locale={locale}
                    onOpen={() => setSelectedInterview(interview)}
                  />
                ))}
              </div>
            </div>
          ) : (
            <EmptyState text="No interviews match this queue. Try another tab or clear the filters." />
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-subtle">
            <div>
              Showing {total ? offset + 1 : 0}-{Math.min(offset + interviews.length, total)} of {total}
            </div>
            <div className="flex gap-2">
              <Button disabled={busy || !canGoBack} onClick={() => onSetOffset(Math.max(0, offset - limit))} size="sm" variant="secondary">
                Previous
              </Button>
              <Button disabled={busy || !canGoNext} onClick={() => onSetOffset(offset + limit)} size="sm" variant="secondary">
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      {selectedInterview ? (
        <InterviewDetailDrawer
          busy={busy}
          interview={selectedInterview}
          locale={locale}
          notesDraft={notesDrafts[selectedInterview.interview_id] || ''}
          onClose={() => setSelectedInterview(null)}
          onOpenCandidate={onOpenCandidate}
          onPreviewVideoAnswer={onPreviewVideoAnswer}
          onRetryVideoTranscripts={onRetryVideoTranscripts}
          onSaveNotes={onSaveNotes}
          onSetNotes={onSetNotes}
          onStatusChange={onStatusChange}
          canManageInterviews={canManageInterviews}
        />
      ) : null}
    </div>
  )
}

function InterviewQueueRow({ interview, locale, onOpen }: { interview: CandidateInterview; locale: RecruitingLocale; onOpen: () => void }) {
  return (
    <div
      className="grid cursor-pointer grid-cols-[minmax(170px,1.1fr)_minmax(140px,0.9fr)_minmax(130px,0.8fr)_minmax(130px,0.8fr)_minmax(150px,0.9fr)_minmax(160px,1fr)_auto] items-center gap-3 border-b border-line/45 px-4 py-3.5 text-sm transition hover:bg-white/42 last:border-b-0"
      onClick={onOpen}
    >
      <div className="min-w-0">
        <div className="truncate font-semibold">{interview.candidate_name || interview.phone || 'Candidate'}</div>
        <div className="truncate text-xs text-subtle">{interview.candidate_email || interview.phone || 'No contact'}</div>
      </div>
      <div className="truncate text-subtle">{interview.position_title || interview.position_code || 'Role'}</div>
      <div>
        <Badge tone={statusTone(interview.application_stage)}>
          {canonicalStageLabel(interview.application_stage, locale)}
        </Badge>
      </div>
      <div>
        <Badge tone={statusTone(interview.status)}>
          {facetStatusLabel(interview.status, locale)}
        </Badge>
      </div>
      <div className="text-subtle">{interview.scheduled_start ? formatDateTime(interview.scheduled_start) : recruitingCopy(locale, 'dateNotSet')}</div>
      <div className="text-subtle">{workflowItemLabel(interview.next_human_action || 'conduct_interview', locale)}</div>
      <Button onClick={onOpen} size="sm" variant="secondary">
        {recruitingCopy(locale, 'open')}
      </Button>
    </div>
  )
}

function InterviewDetailDrawer({
  busy,
  canManageInterviews,
  interview,
  locale,
  notesDraft,
  onClose,
  onOpenCandidate,
  onPreviewVideoAnswer,
  onRetryVideoTranscripts,
  onSaveNotes,
  onSetNotes,
  onStatusChange,
}: {
  busy: boolean
  canManageInterviews: boolean
  interview: CandidateInterview
  locale: RecruitingLocale
  notesDraft: string
  onClose: () => void
  onOpenCandidate: (appKey?: string) => void
  onPreviewVideoAnswer: (videoUrl?: string) => void
  onRetryVideoTranscripts: (interview: CandidateInterview) => void
  onSaveNotes: (interview: CandidateInterview) => void
  onSetNotes: (interviewId: string, value: string) => void
  onStatusChange: (interview: CandidateInterview, status: string) => void
}) {
  const isVideo = interview.interview_type === 'async_video'
  const videoStatus = asyncVideoDisplayStatus(interview)
  const mainStatus = facetStatusLabel(interview.status, locale)
  const allowedActions = new Set(interview.allowed_actions || [])
  const roleLabel = interview.position_title || interview.position_code || 'Role'
  const scheduleLabel = interview.scheduled_start ? formatDateTime(interview.scheduled_start) : recruitingCopy(locale, 'dateNotSet')
  const channelLocation = isVideo
    ? recruitingCopy(locale, 'recordedVideo')
    : interview.meet_link
      ? 'Google Meet'
      : interview.meeting_type
        ? stageLabel(interview.meeting_type)
        : notificationChannelLabel(interview.notification_channel)
  const followUpDraft = 'Add interview feedback or next-step notes...'
  const appendFollowUpNote = () => {
    const current = notesDraft.trim()
    onSetNotes(interview.interview_id, current ? `${current}\n\n${followUpDraft}` : followUpDraft)
  }
  return (
    <div className="fixed inset-0 z-30 bg-ink/30" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-3xl flex-col overflow-y-auto border-l border-line bg-panel p-6 shadow-soft"
        onClick={(event) => event.stopPropagation()}
      >
      <div className="flex flex-col gap-4 border-b border-line pb-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold tracking-tight">{interview.candidate_name || interview.phone || 'Candidate'}</h3>
            <Badge tone={statusTone(interview.application_stage)}>
              {recruitingCopy(locale, 'applicationStage')}: {canonicalStageLabel(interview.application_stage, locale)}
            </Badge>
            <Badge tone={isVideo ? videoStatus.tone : statusTone(interview.status)}>
              {recruitingCopy(locale, 'interviewStatus')}: {mainStatus}
            </Badge>
          </div>
          <div className="mt-1 text-sm text-subtle">
            {roleLabel} · {scheduleLabel}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Info label={recruitingCopy(locale, 'schedule')} value={scheduleLabel} />
            <Info label={recruitingCopy(locale, 'channelLocation')} value={channelLocation} />
            <Info label={recruitingCopy(locale, 'invitationStatus')} value={communicationLabel(interview.invitation_status, locale)} />
            <Info label={recruitingCopy(locale, 'candidateConfirmation')} value={facetStatusLabel(interview.candidate_confirmation, locale)} />
            <Info label={recruitingCopy(locale, 'notesStatus')} value={facetStatusLabel(interview.notes_status || notesStateLabel(interview), locale)} />
            <Info label={recruitingCopy(locale, 'nextHumanAction')} value={workflowItemLabel(interview.next_human_action || 'conduct_interview', locale)} />
          </div>
          <div className="mt-3 space-y-1 text-sm leading-6 text-subtle">
            <div>{interviewInviteLine(interview)}</div>
            {!isVideo ? <div>{interviewStateLine(interview)}</div> : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={onClose} size="sm" variant="secondary">
            Close
          </Button>
          {isVideo ? (
            <>
              {allowedActions.has('mark_completed') ? <Button disabled={busy || interview.feedback_status === 'feedback_complete'} onClick={() => onStatusChange(interview, 'completed')} size="sm" variant="secondary">
                {locale === 'ar' ? 'تحديد كمراجعة' : 'Mark reviewed'}
              </Button> : null}
              {allowedActions.has('write_notes') ? <Button disabled={busy} onClick={appendFollowUpNote} size="sm" variant="ghost">
                {locale === 'ar' ? 'طلب متابعة' : 'Request follow-up'}
              </Button> : null}
              {allowedActions.has('open_candidate') ? <Button onClick={() => onOpenCandidate(interview.app_key)} size="sm" variant="ghost">
                {recruitingActionLabel('open_candidate', locale)}
              </Button> : null}
              <details className="relative">
                <summary className="cursor-pointer rounded-full border border-line bg-panel-muted/60 px-3 py-1.5 text-sm text-subtle transition hover:border-ink/25 hover:text-text">
                  More
                </summary>
                <div className="absolute right-0 z-10 mt-2 grid w-44 gap-2 rounded-xl border border-line bg-panel p-2 shadow-soft">
                  {allowedActions.has('mark_no_show') ? <Button disabled={busy || interview.status === 'no_show'} onClick={() => onStatusChange(interview, 'no_show')} size="sm" variant="ghost">
                    {recruitingActionLabel('mark_no_show', locale)}
                  </Button> : null}
                  {allowedActions.has('cancel_interview') ? <Button disabled={busy || interview.status === 'cancelled'} onClick={() => onStatusChange(interview, 'cancelled')} size="sm" variant="ghost">
                    {recruitingActionLabel('cancel_interview', locale)}
                  </Button> : null}
                </div>
              </details>
            </>
          ) : (
            <>
              {allowedActions.has('mark_completed') ? <Button disabled={busy || interview.status === 'completed'} onClick={() => onStatusChange(interview, 'completed')} size="sm" variant="secondary">
                {recruitingActionLabel('mark_completed', locale)}
              </Button> : null}
              {interview.meet_link ? (
                <Button onClick={() => window.open(interview.meet_link, '_blank', 'noopener,noreferrer')} size="sm" variant="ghost">
                  <ExternalLink size={14} /> Meet
                </Button>
              ) : null}
              {allowedActions.has('open_candidate') ? <Button onClick={() => onOpenCandidate(interview.app_key)} size="sm" variant="ghost">
                {recruitingActionLabel('open_candidate', locale)}
              </Button> : null}
              <details className="relative">
                <summary className="cursor-pointer rounded-full border border-line bg-panel-muted/60 px-3 py-1.5 text-sm text-subtle transition hover:border-ink/25 hover:text-text">
                  More
                </summary>
                <div className="absolute right-0 z-10 mt-2 grid w-44 gap-2 rounded-xl border border-line bg-panel p-2 shadow-soft">
                  {allowedActions.has('mark_no_show') ? <Button disabled={busy || interview.status === 'no_show'} onClick={() => onStatusChange(interview, 'no_show')} size="sm" variant="ghost">
                    {recruitingActionLabel('mark_no_show', locale)}
                  </Button> : null}
                  {allowedActions.has('cancel_interview') ? <Button disabled={busy || interview.status === 'cancelled'} onClick={() => onStatusChange(interview, 'cancelled')} size="sm" variant="ghost">
                    {recruitingActionLabel('cancel_interview', locale)}
                  </Button> : null}
                </div>
              </details>
            </>
          )}
        </div>
      </div>

      {interview.ai_summary?.summary || interview.ai_summary?.overall_summary ? (
        <PracticalInterviewSummary interview={interview} locale={locale} />
      ) : (
        <div className="mt-4 rounded-xl border border-line bg-panel-muted/60 p-4">
          <div className="text-sm font-semibold">{recruitingCopy(locale, 'analysis')}</div>
          <p className="mt-2 text-sm leading-6 text-subtle">{recruitingCopy(locale, 'noAdvisoryAnalysis')}</p>
          <div className="mt-2 text-xs leading-5 text-subtle">{recruitingCopy(locale, 'advisory')}</div>
        </div>
      )}
      {isVideo ? (
        <VideoInterviewReview
          busy={busy}
          canManageInterviews={canManageInterviews}
          interview={interview}
          onPreviewVideoAnswer={onPreviewVideoAnswer}
          onRetryVideoTranscripts={onRetryVideoTranscripts}
        />
      ) : null}

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <Textarea
          onChange={(event) => onSetNotes(interview.interview_id, event.target.value)}
          placeholder="Add interview feedback or next-step notes..."
          value={notesDraft}
        />
        <Button disabled={busy || !allowedActions.has('write_notes')} onClick={() => onSaveNotes(interview)} variant="secondary">
          {busy ? <Loader2 className="animate-spin" size={14} /> : <Pencil size={14} />} {locale === 'ar' ? 'حفظ الملاحظات' : 'Save feedback'}
        </Button>
      </div>
      {!interview.allowed_actions?.length ? <div className="mt-2 text-xs text-subtle">{recruitingCopy(locale, 'noPermittedActions')}</div> : null}

      <div className="mt-4 space-y-2">
        <details className="rounded-xl border border-line bg-panel-muted/60 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-text">Invite details</summary>
          <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
            <Info label="Invite" value={inviteTruthLabel(interview)} />
            <Info label={recruitingCopy(locale, 'invitationStatus')} value={communicationLabel(interview.invitation_status, locale)} />
            <Info label={recruitingCopy(locale, 'candidateConfirmation')} value={stageLabel(interview.candidate_confirmation)} />
            <Info label="Meeting" value={isVideo ? 'Video interview link' : interview.meet_link ? 'Meet link available' : calendarEventLabel(interview)} />
            <Info label="Invite sent at" value={interview.invite_sent_at ? formatDateTime(interview.invite_sent_at) : 'Not recorded'} />
            <Info label="Contact" value={interview.candidate_email || interview.phone || 'Not recorded'} />
            <Info label="Channel" value={notificationChannelLabel(interview.notification_channel)} />
          </div>
        </details>
        {interview.sent_subject || interview.sent_body ? (
          <details className="rounded-xl border border-line bg-panel-muted/60 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-text">Sent message</summary>
            {interview.sent_subject ? <div className="mt-3 text-sm font-medium text-text">{interview.sent_subject}</div> : null}
            {interview.sent_body ? <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-subtle">{interview.sent_body}</div> : null}
          </details>
        ) : null}
        <details className="rounded-xl border border-line bg-panel-muted/60 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-text">Timeline</summary>
          <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
            <Info label={isVideo ? 'Latest activity' : 'Scheduled time'} value={scheduleLabel} />
            <Info label="Created" value={interview.created_at ? formatDateTime(interview.created_at) : 'Not recorded'} />
            <Info label="Updated" value={interview.updated_at ? formatDateTime(interview.updated_at) : 'Not recorded'} />
          </div>
        </details>
        <details className="rounded-xl border border-line bg-panel-muted/60 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-text">Status details</summary>
          <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
            <Info label="Interview state" value={isVideo ? mainStatus : stageLabel(interview.status)} />
            <Info label={recruitingCopy(locale, 'applicationStage')} value={canonicalStageLabel(interview.application_stage, locale)} />
            <Info label="Feedback state" value={stageLabel(interview.feedback_status || 'notes_pending')} />
            <Info label={recruitingCopy(locale, 'notesStatus')} value={stageLabel(interview.notes_status || notesStateLabel(interview))} />
          </div>
          {interview.notes ? <div className="mt-3 text-sm leading-6 text-subtle">Latest HR notes: {interview.notes}</div> : null}
        </details>
      </div>
      </aside>
    </div>
  )
}

function PracticalInterviewSummary({ interview, locale }: { interview: CandidateInterview; locale: RecruitingLocale }) {
  const summary = interview.ai_summary
  const overallSummary = summary?.overall_summary || summary?.summary || 'No AI summary is ready yet.'
  const strengths = summary?.strengths || []
  const concerns = summary?.gaps_or_risks || summary?.concerns || []
  const followUps = summary?.suggested_follow_up_questions || summary?.follow_up_questions || summary?.follow_up_points || []
  const recommended = summary?.recommended_next_step || summary?.recommendation || 'Review the available evidence and choose the next hiring step.'
  const overallFit = normalizeOverallImpression(summaryValue(summary, ['overall_fit', 'fit', 'fit_label'])) || 'Needs more evidence'
  const confidence = normalizeEvidenceConfidence(summaryValue(summary, ['confidence', 'confidence_label'])) || 'Limited'
  return (
    <div className="mt-4 rounded-xl border border-line bg-panel-muted/60 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-sm font-semibold">{recruitingCopy(locale, 'analysis')}</div>
          <p className="mt-2 text-sm leading-6 text-subtle">{overallSummary}</p>
        </div>
        <div className="grid min-w-[220px] gap-2 text-sm sm:grid-cols-2 md:grid-cols-1">
          <Info label="Overall impression" value={overallFit} />
          <Info label={recruitingCopy(locale, 'confidence')} value={confidence} />
        </div>
      </div>
      <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
        <InterviewSummaryList label="Key strengths" values={strengths} />
        <InterviewSummaryList label={recruitingCopy(locale, 'concerns')} values={concerns} />
        <InterviewSummaryList label={recruitingCopy(locale, 'recommendation')} values={[recommended]} />
      </div>
      {followUps.length ? (
        <div className="mt-4 rounded-lg border border-line bg-panel p-3">
          <div className="text-sm font-semibold">Follow-up questions</div>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-subtle">
            {followUps.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ol>
        </div>
      ) : null}
      <details className="mt-4 rounded-lg border border-line bg-panel p-3">
        <summary className="cursor-pointer text-sm font-semibold text-text">Detailed evidence</summary>
        <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
          <InterviewSummaryList label="Role-fit evidence" values={summary?.role_fit_evidence || []} />
          <InterviewSummaryList label="Communication notes" values={summary?.communication_notes || []} />
          <InterviewSummaryList label={recruitingCopy(locale, 'missingInformation')} values={summary?.missing_evidence || []} />
        </div>
      </details>
      <div className="mt-3 text-xs leading-5 text-subtle">{summary?.hr_decision_maker_note || summary?.decision_policy || recruitingCopy(locale, 'advisory')}</div>
    </div>
  )
}

function VideoInterviewReview({
  busy,
  canManageInterviews,
  interview,
  onPreviewVideoAnswer,
  onRetryVideoTranscripts,
}: {
  busy: boolean
  canManageInterviews: boolean
  interview: CandidateInterview
  onPreviewVideoAnswer: (videoUrl?: string) => void
  onRetryVideoTranscripts: (interview: CandidateInterview) => void
}) {
  const answers = interview.video_answers || []
  const questions = interview.video_questions || answers[0]?.covered_questions || []
  const singleVideo = interview.response_mode === 'single_video' || answers.some((answer) => answer.response_mode === 'single_video')
  const failed = answers.some((answer) => answer.transcript_status === 'failed')
  return (
    <div className="mt-4 rounded-xl border border-line bg-panel-muted/60 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold">Video interview evidence</div>
            <Badge tone={asyncVideoDisplayStatus(interview).tone}>{asyncVideoDisplayStatus(interview).label}</Badge>
          </div>
          <div className="mt-1 text-sm leading-6 text-subtle">{videoInterviewProcessingLine(interview)}</div>
        </div>
        {failed ? (
          <Button disabled={busy || !canManageInterviews} onClick={() => onRetryVideoTranscripts(interview)} size="sm" variant="secondary">
            Try again
          </Button>
        ) : null}
      </div>
      {singleVideo && questions.length ? (
        <div className="mt-4 rounded-lg border border-line bg-panel p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">Question list</div>
          <div className="mt-1 text-sm font-medium text-text">Candidate answered the full question list in one video.</div>
          <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm leading-6 text-subtle">
            {questions.map((question, index) => (
              <li key={question.question_id || index}>{question.prompt_text || 'Video interview question'}</li>
            ))}
          </ol>
        </div>
      ) : null}
      <div className="mt-4 space-y-3">
        {answers.length ? (
          answers.map((answer) => (
            <div className="rounded-lg border border-line bg-panel p-3" key={answer.response_id}>
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{singleVideo ? 'Video answer' : `Question ${answer.question_order || ''}`}</div>
                  <div className="mt-1 text-sm font-medium text-text">{singleVideo ? 'Candidate answered the full question list in one video.' : answer.question_text || 'Video interview question'}</div>
                  <div className="mt-1 text-xs text-subtle">Transcript: {transcriptStatusLabel(answer.transcript_status)}</div>
                </div>
                {answer.has_video ? (
                  <Button onClick={() => onPreviewVideoAnswer(answer.video_url)} size="sm" variant="ghost">
                    <ExternalLink size={14} /> Video
                  </Button>
                ) : null}
              </div>
              {answer.transcript_status === 'completed' && answer.transcript_text ? (
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-subtle">{answer.transcript_text}</p>
              ) : null}
              {answer.transcript_status === 'failed' ? (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  We could not prepare the written summary. The original video is still available for review.
                </div>
              ) : null}
            </div>
          ))
        ) : (
          <EmptyState text="No video answers have been submitted yet." />
        )}
      </div>
    </div>
  )
}

function InterviewTruthGrid({ interview }: { interview: InterviewTruth }) {
  const isVideo = interview.interview_type === 'async_video'
  const videoStatus = isVideo ? asyncVideoDisplayStatus(interview) : null
  return (
    <div className="mt-4 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
      <Info label="Interview status" value={videoStatus?.label || stageLabel(interview.status)} />
      {isVideo ? <Info label="Video review" value={videoStatus?.description || 'Video interview'} /> : null}
      <Info label={isVideo ? 'Latest activity' : 'Scheduled time'} value={isVideo ? asyncVideoActivityLabel(interview) : interview.scheduled_start ? formatDateTime(interview.scheduled_start) : 'Not set'} />
      <Info label={isVideo ? 'Video link' : 'Google Meet'} value={isVideo ? 'Candidate link sent' : interview.meet_link ? 'Link available' : calendarEventLabel(interview)} />
      <Info label="Calendar invite sent" value={isVideo ? 'Not applicable' : booleanTruthLabel(interview.calendar_invite_sent)} />
      <Info label="Candidate notified" value={candidateNotifiedLabel(interview)} />
      <Info label="Notification channel" value={notificationChannelLabel(interview.notification_channel)} />
      <Info label="Invite sent at" value={interview.invite_sent_at ? formatDateTime(interview.invite_sent_at) : 'Not recorded'} />
      <Info label="Notes state" value={notesStateLabel(interview)} />
      <Info label="Feedback state" value={stageLabel(interview.feedback_status || 'notes_pending')} />
      {interview.sent_subject || interview.sent_body ? (
        <div className="rounded-lg border border-line bg-panel p-3 md:col-span-2 xl:col-span-3">
          <div className="text-xs uppercase tracking-wide text-subtle">Last invite message</div>
          {interview.sent_subject ? <div className="mt-1 font-medium text-text">{interview.sent_subject}</div> : null}
          {interview.sent_body ? <div className="mt-1 line-clamp-3 text-sm leading-6 text-subtle">{interview.sent_body}</div> : null}
        </div>
      ) : null}
    </div>
  )
}

function InterviewSummaryList({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <div className="font-medium text-text">{label}</div>
      {values.length ? (
        <ul className="mt-1 list-disc space-y-1 pl-4 text-subtle">
          {values.slice(0, 4).map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}
        </ul>
      ) : (
        <div className="mt-1 text-subtle">None captured yet</div>
      )}
    </div>
  )
}

function AssessmentsPage({
  access,
  applications,
  canManageAssessments,
  enabled,
  config,
  attempts,
  averagePercent,
  busy,
  limit,
  offset,
  total,
  onOpenCandidate,
  onOpenFollowUpCandidates,
  onPreviewReport,
  onCancelAttempt,
  onResendAttempt,
  onReviewAttempt,
  onRecalculateNorms,
  onRefresh,
  onSendAssessment,
  onSetOffset,
  statusCounts,
  pendingTotal,
}: {
  access: DashboardAccess
  applications: ApplicationSummary[]
  canManageAssessments: boolean
  enabled: boolean
  config: AssessmentConfigResponse | null
  attempts: AssessmentAttempt[]
  averagePercent?: number | null
  busy: boolean
  limit: number
  offset: number
  total: number
  onOpenCandidate: (appKey: string) => void
  onOpenFollowUpCandidates: () => void
  onPreviewReport: (attempt: AssessmentAttempt) => void
  onCancelAttempt: (attempt: AssessmentAttempt) => void
  onResendAttempt: (attempt: AssessmentAttempt) => void
  onReviewAttempt: (attempt: AssessmentAttempt) => void
  onRecalculateNorms: () => void
  onRefresh: () => void
  onSendAssessment: (application: ApplicationSummary) => void
  onSetOffset: (offset: number) => void
  statusCounts: Array<{ status: string; count: number }>
  pendingTotal?: number
}) {
  const inProgress = assessmentStatusCount(statusCounts, 'in_progress')
  const completed = assessmentStatusCount(statusCounts, 'completed')
  const queue = assessmentQueue(applications)
  // Headline count is the company-wide total; the queue table below shows the loaded
  // candidates and discloses when more exist (kept separate from list loading).
  const pendingCount = typeof pendingTotal === 'number' ? pendingTotal : queue.length
  const needsReview = attempts.filter((attempt) => attempt.status === 'completed' && attempt.review_status !== 'reviewed').length
  const completedAttempts = attempts.filter((attempt) => attempt.status === 'completed')
  const reports = completedAttempts.slice(0, 6)
  const canGoBack = offset > 0
  const canGoNext = offset + limit < total
  const itemBank = config?.item_bank
  const roleProfileCount = Object.keys(config?.role_profiles || {}).length
  const competencyCount = Object.keys(config?.framework?.competencies || {}).length
  const sections = Object.keys(itemBank?.section_totals || {}).map(stageLabel).join(', ') || 'Ability + workplace judgment'
  const questionCount = itemBank?.total_items || 22
  const batteryName = String(config?.battery?.name || 'Wathefni Ability Assessment')
  const batteryVersion = String(config?.battery?.version || 'v1')
  return (
    <div className="space-y-6">
      {!enabled ? (
        <Card>
          <CardHeader>
            <CardTitle>Assessments</CardTitle>
            <CardDescription>
              Assessments are not enabled for this company yet. You can still review candidates, CVs, interviews, and ranking evidence.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            <Info label="Available now" value="Jobs, candidates, CV review, interviews, and ranking" />
            <Info label="Next step" value="Ask an Owner or HR Manager to enable assessments when ready." />
          </CardContent>
        </Card>
      ) : null}
      <MetricGrid
        metrics={[
          { label: 'Pending assessments', value: pendingCount, icon: ClipboardCheck },
          { label: 'In progress', value: inProgress, icon: Search },
          { label: 'Completed', value: completed, icon: CheckCircle2 },
          { label: 'Needs review', value: needsReview, icon: AlertTriangle },
          { label: 'Average score', value: assessmentAverageLabel(averagePercent), icon: Medal },
        ]}
      />

      {enabled ? (
        <Product2AuthoringPanel access={access} canManageAssessments={canManageAssessments} />
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Assessment queue</CardTitle>
              <CardDescription>
                Candidates who need an assessment sent, or have been sent one but have not started yet.
              </CardDescription>
            </div>
            <Button onClick={onRefresh} variant="secondary">
              <RefreshCw size={16} /> Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {queue.length ? (
            <div className="overflow-x-auto rounded-[1.35rem] border border-line/55 bg-panel/75 shadow-[0_10px_30px_rgba(24,20,15,0.035)]">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-[#f7f1e7]/72 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                  <tr>
                    <th className="px-4 py-3">Candidate</th>
                    <th className="px-4 py-3">Job</th>
                    <th className="px-4 py-3">Stage</th>
                    <th className="px-4 py-3">Assessment</th>
                    <th className="px-4 py-3">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/45 bg-panel/42">
                  {queue.map((application) => (
                    <tr className="transition duration-150 hover:bg-white/55" key={application.app_key}>
                      <td className="px-4 py-3">
                        <div className="font-medium">{candidateName(application)}</div>
                        <div className="text-xs text-subtle">{application.candidate?.email || application.phone}</div>
                      </td>
                      <td className="px-4 py-3 text-subtle">{application.position?.title || application.position?.code || '—'}</td>
                      <td className="px-4 py-3">
                        <Badge tone={statusTone(application.assessment?.status || application.status)}>
                          {application.assessment?.status ? `Assessment ${stageLabel(application.assessment.status)}` : stageLabel(application.status)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-subtle">{batteryName} {batteryVersion}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          <Button disabled={busy || !enabled || !canManageAssessments} onClick={() => onSendAssessment(application)} size="sm" variant="secondary">
                            Send assessment
                          </Button>
                          <Button onClick={() => onOpenCandidate(application.app_key)} size="sm" variant="ghost">
                            Open
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState text={enabled ? 'No pending assessment queue. New candidates needing assessment will appear here.' : 'Assessments are not enabled for this company.'} />
          )}
          {queue.length && pendingCount > queue.length ? (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-subtle">
              <span>Showing {queue.length} of {pendingCount} pending.</span>
              <Button onClick={onOpenFollowUpCandidates} size="sm" variant="secondary">
                Open all in Candidates
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent attempts</CardTitle>
          <CardDescription>Latest browser-based attempts, delivery state, and HR review state.</CardDescription>
        </CardHeader>
        <CardContent>
          {attempts.length ? (
            <div className="overflow-x-auto rounded-[1.35rem] border border-line/55 bg-panel/75 shadow-[0_10px_30px_rgba(24,20,15,0.035)]">
              <table className="w-full min-w-[960px] text-left text-sm">
                <thead className="bg-[#f7f1e7]/72 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                  <tr>
                    <th className="px-4 py-3">Candidate</th>
                    <th className="px-4 py-3">Job</th>
                    <th className="px-4 py-3">Assessment set</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Score</th>
                    <th className="px-4 py-3">Job match</th>
                    <th className="px-4 py-3">Completed</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/45 bg-panel/42">
                  {attempts.map((attempt) => (
                    <tr className="transition duration-150 hover:bg-white/55" key={attempt.attempt_id}>
                      <td className="px-4 py-3">
                        <div className="font-medium">{attempt.candidate_name || attempt.phone || 'Unknown candidate'}</div>
                        <div className="text-xs text-subtle">{attempt.candidate_email || attempt.phone || 'Candidate contact'}</div>
                      </td>
                      <td className="px-4 py-3 text-subtle">{attempt.position_title || attempt.position_code || '—'}</td>
                      <td className="px-4 py-3 text-subtle">{stageLabel(attempt.battery_key || 'Wathefni ability')}</td>
                      <td className="px-4 py-3">
                        <Badge tone={statusTone(attempt.status)}>{stageLabel(attempt.status)}</Badge>
                      </td>
                      <td className="px-4 py-3 font-medium">{attempt.percent == null ? '—' : `${attempt.percent}%`}</td>
                      <td className="px-4 py-3 text-subtle">{attempt.job_match?.job_match_percent == null ? '—' : `${attempt.job_match.job_match_percent}%`}</td>
                      <td className="px-4 py-3 text-subtle">{attempt.completed_at ? formatDateTime(attempt.completed_at) : '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          {attempt.status === 'completed' ? (
                            <>
                              <Button onClick={() => onPreviewReport(attempt)} size="sm" variant="secondary">View report</Button>
                              {attempt.review_status !== 'reviewed' && canManageAssessments ? (
                                <Button disabled={busy} onClick={() => onReviewAttempt(attempt)} size="sm" variant="ghost">Mark reviewed</Button>
                              ) : null}
                            </>
                          ) : ['pending', 'in_progress'].includes(String(attempt.status)) ? (
                            <>
                              <Button disabled={busy || !canManageAssessments} onClick={() => onResendAttempt(attempt)} size="sm" variant="secondary">Resend</Button>
                              <Button disabled={busy || !canManageAssessments} onClick={() => onCancelAttempt(attempt)} size="sm" variant="ghost">Cancel</Button>
                            </>
                          ) : null}
                          <Button onClick={() => onOpenCandidate(attempt.app_key)} size="sm" variant="ghost">Open</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState text="No assessment attempts yet." />
          )}
          {total ? (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-subtle">
              <div>
                Showing {offset + 1}-{Math.min(offset + attempts.length, total)} of {total}
              </div>
              <div className="flex gap-2">
                <Button disabled={busy || !canGoBack} onClick={() => onSetOffset(Math.max(0, offset - limit))} size="sm" variant="secondary">
                  Previous
                </Button>
                <Button disabled={busy || !canGoNext} onClick={() => onSetOffset(offset + limit)} size="sm" variant="secondary">
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Assessment setup</CardTitle>
          <CardDescription>How assessment results are grouped for HR review.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-line bg-panel-muted/60 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{batteryName} {batteryVersion}</div>
                <div className="mt-1 text-sm text-subtle">{sections}</div>
              </div>
              <Badge tone="success">Approved item bank</Badge>
            </div>
            <div className="mt-4 text-sm text-subtle">{questionCount} approved, versioned questions. No time limit is enforced.</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Reports</CardTitle>
          <CardDescription>Completed candidate reports ready for HR review.</CardDescription>
        </CardHeader>
        <CardContent>
          {reports.length ? (
            <div className="grid gap-3 xl:grid-cols-2">
              {reports.map((attempt) => (
                <div className="rounded-lg border border-line bg-panel-muted/60 p-4" key={`${attempt.attempt_id}-report-row`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold">{attempt.candidate_name || attempt.phone || 'Candidate'}</div>
                      <div className="mt-1 text-sm text-subtle">{attempt.position_title || attempt.position_code || 'Role'} / {attempt.job_match?.role_profile_label || 'General role'}</div>
                    </div>
                    <Badge tone={assessmentBandTone(attempt.band)}>{stageLabel(attempt.band)}</Badge>
                  </div>
                  <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
                    <Info label="Score" value={attempt.percent == null ? '—' : `${attempt.percent}%`} />
                    <Info label="Job match" value={attempt.job_match?.job_match_percent == null ? '—' : `${attempt.job_match.job_match_percent}%`} />
                    <Info label="Completed" value={attempt.completed_at ? formatDateTime(attempt.completed_at) : '—'} />
                  </div>
                  <div className="mt-4 flex justify-end">
                    <Button onClick={() => onPreviewReport(attempt)} size="sm" variant="secondary">
                      <ExternalLink size={14} /> View report
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState text="No completed assessment reports yet." />
          )}
        </CardContent>
      </Card>

      {enabled && config ? (
        <details className="rounded-2xl border border-line bg-panel-muted/60 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-text">Assessment setup details</summary>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="text-sm leading-6 text-subtle">
              Setup details are available for HR admins who need to check assessment calibration and content coverage.
            </div>
            <Button disabled={busy || !canManageAssessments} onClick={onRecalculateNorms} size="sm" variant="secondary">
              {busy ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />} Refresh setup
            </Button>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Info label="Questions" value={`${itemBank?.total_items ?? 0} items`} />
            <Info label="Evidence areas" value={`${competencyCount} indicators`} />
            <Info label="Fit profiles" value={`${roleProfileCount} profiles`} />
            <Info label="Calibration" value={setupCalibrationLabel(config.norms?.status)} />
            <Info label="Content check" value={itemBank?.validation?.ok ? 'Looks ready' : `${itemBank?.validation?.error_count || 0} issues need review`} />
            <Info label="Content source" value={itemBank?.content_policy ? stageLabel(itemBank.content_policy) : 'Wathefni items'} />
            <Info label="Setup version" value={config.norms?.active_norm_version || 'Not set'} />
            <Info label="Scoring" value={config.guardrails?.deterministic_scoring ? 'Structured scoring' : 'Needs review'} />
          </div>
        </details>
      ) : null}
    </div>
  )
}

function RankingPage({
  busy,
  onSelect,
  positions,
  rankPosition,
  ranking,
  runRanking,
  setRankPosition,
}: {
  busy: boolean
  onSelect: (candidate: RankingCandidate) => void
  positions: PositionSummary[]
  rankPosition: string
  ranking: RankingResponse | null
  runRanking: () => void
  setRankPosition: (value: string) => void
}) {
  const selectedPosition = positions.find((position) => position.position_code === rankPosition)
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Candidate ranking</CardTitle>
          <CardDescription>
            Select a job to see who HR should review first, with evidence and recommended next steps.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_auto]">
          <Select onChange={(event) => setRankPosition(event.target.value)} value={rankPosition}>
            <option value="">Select a job</option>
            {positions.map((position) => (
              <option key={position.position_code} value={position.position_code}>
                {position.position_title || position.position_code}
              </option>
            ))}
          </Select>
          <Button disabled={busy || !rankPosition} onClick={runRanking} title={!rankPosition ? 'Select a job first' : undefined}>
            <Search size={16} /> Rank
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ranked candidates</CardTitle>
          <CardDescription>
            {ranking
              ? (ranking.total_matching > ranking.candidates.length
                  ? `Showing the top ${ranking.candidates.length} of ${ranking.total_matching} matching candidates${selectedPosition ? ` for ${selectedPosition.position_title || selectedPosition.position_code}` : ''}.`
                  : `${ranking.total_matching} matching candidate${ranking.total_matching === 1 ? '' : 's'}${selectedPosition ? ` for ${selectedPosition.position_title || selectedPosition.position_code}` : ''}.`)
              : 'Choose a job and run ranking to populate this list.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {ranking?.role_profile ? (
            <div className="rounded-2xl border border-line bg-panel-muted/60 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">Fit profile: {ranking.role_profile.label || 'Role-specific fit'}</div>
                  <div className="mt-1 text-sm text-subtle">Ranking uses this hiring lens together with available candidate evidence.</div>
                </div>
                <Badge tone="muted">Fit profile</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(ranking.role_profile.criteria || []).slice(0, 6).map((criterion) => (
                  <Badge key={criterion.key || criterion.label} tone="muted">{criterion.label || criterion.key}</Badge>
                ))}
              </div>
            </div>
          ) : null}
          {(ranking?.candidates || []).map((candidate, index) => (
            <RankingCandidateCard candidate={candidate} index={index} key={candidate.app_key} onSelect={onSelect} />
          ))}
          {!ranking?.candidates?.length ? <EmptyState text="No ranked candidates yet." /> : null}
        </CardContent>
      </Card>
    </div>
  )
}

// Alerts whose action label points at a real dashboard destination become
// buttons that navigate there; everything else is rendered as plain guidance
// (so a static label never looks like a button that does nothing).
const NOTIFICATION_ACTION_TARGETS: Record<string, Page> = {
  'Open Assessments queue': 'assessments',
  'Open Interviews queue': 'interviews',
  'Review in Wathefni Assistant': 'ai',
  'Review completed screening': 'candidates',
}

function NotificationsPage({
  actionItems,
  deliveryCenter,
  enabledModules,
  notifications,
  onNavigate,
}: {
  actionItems: NotificationActionItem[]
  deliveryCenter?: ReactNode
  enabledModules?: string[]
  notifications: NotificationRow[]
  onNavigate: (page: Page) => void
}) {
  const issues = moduleScopedNotificationRows(notifications, enabledModules)
  const alerts = groupedNotificationAlerts(actionItems, issues, enabledModules)
  return (
    <div className="space-y-6">
      {deliveryCenter}
      <Card>
        <CardHeader>
          <CardTitle>Urgent HR alerts</CardTitle>
          <CardDescription>Important hiring issues HR should check now. Daily work stays in Candidates, Assessments, Interviews, and Reports.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {alerts.length ? (
            NOTIFICATION_GROUPS.filter((group) => alerts.some((item) => item.group === group.id)).map((group) => (
              <section className="rounded-2xl border border-line bg-panel/70 p-4" key={group.id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold">{group.label}</div>
                    <div className="mt-1 text-sm text-subtle">{group.description}</div>
                  </div>
                  <Badge tone={group.id === 'delivery_issues' ? 'warning' : 'muted'}>
                    {notificationGroupCount(alerts, group.id)} alert{notificationGroupCount(alerts, group.id) === 1 ? '' : 's'}
                  </Badge>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {alerts.filter((item) => item.group === group.id).map((item) => (
                    <div className="rounded-xl border border-line bg-panel-muted/60 p-4" key={item.id}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-semibold">{item.title}</div>
                          <div className="mt-1 text-sm leading-6 text-subtle">{item.detail}</div>
                        </div>
                        <Badge tone={notificationSeverityTone(item.severity)}>{item.count}</Badge>
                      </div>
                      {NOTIFICATION_ACTION_TARGETS[item.actionLabel] ? (
                        <button
                          type="button"
                          onClick={() => onNavigate(NOTIFICATION_ACTION_TARGETS[item.actionLabel])}
                          className="mt-3 inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-[#8a5a16] transition hover:text-[#6f4711]"
                        >
                          {item.actionLabel}
                          <span aria-hidden="true">→</span>
                        </button>
                      ) : (
                        <div className="mt-3 text-xs text-subtle">Suggested next step: {item.actionLabel}</div>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            ))
          ) : (
            <EmptyState text="All clear — no urgent HR alerts." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function RankingCandidateCard({
  candidate,
  index,
  onSelect,
}: {
  candidate: RankingCandidate
  index: number
  onSelect: (candidate: RankingCandidate) => void
}) {
  const evaluation = candidate.gpt_evaluation
  const topStrengths = (evaluation?.strengths || candidate.evidence || candidate.reasons || []).slice(0, 2)
  const mainGap = rankingMissingEvidence(candidate)[0]
  const mainRisk = evaluation?.risks?.[0]
  return (
    <article className="rounded-2xl border border-line bg-panel-muted/60 p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">Rank #{index + 1}</div>
          <h3 className="mt-1 text-lg font-semibold tracking-tight">{candidate.name || candidate.phone}</h3>
          <div className="mt-1 text-sm text-subtle">
            {candidate.position_title || candidate.position_code} / {stageLabel(candidate.status)} / {stageLabel(candidate.confidence || 'limited')} evidence
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{Math.round(candidate.score)} / 100</Badge>
          <Button onClick={() => onSelect(candidate)} size="sm" variant="secondary">
            Open profile
          </Button>
        </div>
      </div>

      <div className="mt-5 rounded-2xl border border-ink/10 bg-panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-3xl">
            <div className="text-xs font-semibold uppercase tracking-wide text-subtle">Fit summary</div>
            <p className="mt-2 text-base font-medium leading-7 text-text">
              {evaluation?.fit_summary || 'No fit summary is stored yet. Open details for available scoring evidence.'}
            </p>
          </div>
          <Badge tone={evaluation?.source === 'gpt_structured' ? 'success' : 'muted'}>
            {evaluation?.source === 'gpt_structured' ? 'AI reviewed' : 'Stored score'}
          </Badge>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <DecisionSnapshot label="Top strengths" values={topStrengths} />
          <DecisionSnapshot label="Main gap or risk" values={[mainGap || mainRisk || 'No major gap captured yet.']} tone="warning" />
          <DecisionSnapshot label="Recommended next step" values={[evaluation?.recommended_next_step || 'Open the profile and review available evidence before deciding.']} tone="strong" />
        </div>
      </div>

      <details className="mt-4 rounded-xl border border-line bg-panel p-4">
        <summary className="cursor-pointer text-sm font-semibold text-text">Show evidence and score breakdown</summary>
        <RankingEvaluation candidate={candidate} />
        <div className="mt-4 rounded-xl border border-line bg-panel-muted/60 p-4">
          <div className="mb-3 text-sm font-semibold">Score breakdown</div>
          <div className="grid gap-2 md:grid-cols-3">
            {scoreBreakdownItems(candidate).map((item) => (
              <ScoreBreakdown key={item.label} label={item.label} max={item.max} value={item.value} />
            ))}
          </div>
        </div>
      </details>
    </article>
  )
}

function DecisionSnapshot({
  label,
  tone = 'default',
  values,
}: {
  label: string
  tone?: 'default' | 'strong' | 'warning'
  values: string[]
}) {
  return (
    <div className="rounded-xl border border-line bg-panel-muted/60 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{label}</div>
      <div className={cn('mt-2 text-sm leading-6', tone === 'strong' ? 'text-text' : 'text-subtle')}>
        {values.filter(Boolean).slice(0, 2).join(' ') || 'Not captured yet.'}
      </div>
    </div>
  )
}

function RankingEvaluation({ candidate }: { candidate: RankingCandidate }) {
  const evaluation = candidate.gpt_evaluation
  const evidenceUsed = rankingEvidenceUsed(candidate)
  const missingEvidence = rankingMissingEvidence(candidate)
  const criteriaNotes = evaluation?.criterion_notes || []
  if (!evaluation) return null
  return (
    <div className="mt-5 rounded-2xl border border-ink/10 bg-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">AI decision support</div>
          <p className="mt-2 text-base font-medium leading-7 text-text">
            {evaluation.fit_summary || 'Structured evaluation is not available yet.'}
          </p>
        </div>
        <Badge tone={evaluation.source === 'gpt_structured' ? 'success' : 'muted'}>
          {evaluation.source === 'gpt_structured' ? 'AI reviewed' : 'Stored score'}
        </Badge>
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-3">
        <EvaluationPanel label="Why this score" tone="strong" values={evaluation.strengths || []} />
        <EvaluationPanel label="Missing evidence / gaps" tone="warning" values={missingEvidence} />
        <EvaluationPanel label="Risks to verify" tone="danger" values={evaluation.risks || []} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EvaluationPanel label="Evidence used" values={evidenceUsed} />
        <EvaluationPanel label="Role-specific criteria notes" values={criteriaNotes} />
      </div>

      {evaluation.recommended_next_step ? (
        <div className="mt-4 rounded-xl border border-ink/10 bg-ink px-4 py-3 text-sm text-white">
          <span className="font-semibold">Recommended next step: </span>
          {evaluation.recommended_next_step}
        </div>
      ) : null}
    </div>
  )
}

function EvaluationPanel({
  label,
  tone = 'default',
  values,
}: {
  label: string
  tone?: 'default' | 'strong' | 'warning' | 'danger'
  values: string[]
}) {
  return (
    <div className="rounded-xl border border-line bg-panel-muted/60 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{label}</div>
        <span
          className={cn(
            'h-2 w-2 rounded-full',
            tone === 'strong' && 'bg-emerald-500',
            tone === 'warning' && 'bg-amber-500',
            tone === 'danger' && 'bg-rose-500',
            tone === 'default' && 'bg-ink/30',
          )}
        />
      </div>
      {values.length ? (
        <ul className="mt-3 space-y-2 text-sm leading-6 text-subtle">
          {values.slice(0, 4).map((value) => (
            <li className="flex gap-2" key={value}>
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-ink/35" />
              <span>{value}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-3 text-sm text-subtle">None captured yet</div>
      )}
    </div>
  )
}

function rankingEvidenceUsed(candidate: RankingCandidate) {
  const values = [...(candidate.evidence || []), ...(candidate.reasons || [])]
  return uniqueStrings(values).slice(0, 5)
}

function uniqueStrings(values: string[]) {
  const seen = new Set<string>()
  const out: string[] = []
  values.forEach((value) => {
    const cleaned = String(value || '').trim()
    const key = cleaned.toLowerCase()
    if (!cleaned || seen.has(key)) return
    seen.add(key)
    out.push(cleaned)
  })
  return out
}

function rankingMissingEvidence(candidate: RankingCandidate) {
  const evaluation = candidate.gpt_evaluation
  const gaps = evaluation?.gaps || []
  const missing = gaps.filter((item) => /\b(missing|not available|not stored|no |without|pending)\b/i.test(item))
  return (missing.length ? missing : gaps).slice(0, 5)
}

function candidateRankingEvidenceUsed(application: ApplicationSummary) {
  return uniqueStrings([...(application.ranking?.evidence || []), ...(application.ranking?.reasons || [])]).slice(0, 5)
}

function candidateRankingMissingEvidence(application: ApplicationSummary) {
  const gaps = application.ranking?.gpt_evaluation?.gaps || []
  const missing = gaps.filter((item) => /\b(missing|not available|not stored|no |without|pending)\b/i.test(item))
  if (missing.length || gaps.length) return (missing.length ? missing : gaps).slice(0, 5)
  const fallback: string[] = []
  if (!application.cv?.received) fallback.push('CV is missing.')
  if (application.screening_status !== 'complete') fallback.push('Screening is not complete.')
  if (!application.assessment?.status) fallback.push('Assessment result is missing.')
  if (!application.interview?.status) fallback.push('Interview feedback is missing.')
  return fallback
}

function ReportsPage({
  assessmentEnabled,
  canExportReports,
  onExportAssessments,
  onExportCandidates,
  onExportFollowUps,
  onExportInterviews,
  onExportRoles,
  reports,
}: {
  assessmentEnabled: boolean
  canExportReports: boolean
  onExportAssessments: () => void
  onExportCandidates: () => void
  onExportFollowUps: () => void
  onExportInterviews: () => void
  onExportRoles: () => void
  reports: PrehireReportsResponse | null
}) {
  const summary = reports?.summary
  const exports = reports?.exports
  const breakdowns = reports?.breakdowns
  const interviewTotal = (summary?.interview_scheduled || 0) + (summary?.interview_completed || 0) + (summary?.interview_no_show || 0)
  const stageRows = (breakdowns?.applications_by_stage || []).map((row) => ({ ...row, label: stageLabel(row.label) }))
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Hiring reports</CardTitle>
          <CardDescription>
            Download hiring analytics and exports for leadership review. Daily work stays in Overview, Jobs, Candidates, Ranking, and Assessments.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <ExportCard
            count={exports?.candidate_rows || 0}
            description="Spreadsheet of candidate applications, CV status, hiring stage, assessment progress, interview progress, and last update."
            label="Candidate report"
            onExport={onExportCandidates}
            disabled={!canExportReports}
          />
          <ExportCard
            count={exports?.role_rows || 0}
            description="Spreadsheet of job openings, application totals, active applications, and review-ready candidates."
            label="Role report"
            onExport={onExportRoles}
            disabled={!canExportReports}
          />
          {assessmentEnabled ? (
            <ExportCard
              count={exports?.assessment_rows || 0}
              description="Spreadsheet of candidate assessment progress, score band, completion date, and last update."
              label="Assessment report"
              onExport={onExportAssessments}
              disabled={!canExportReports}
            />
          ) : null}
          {interviewTotal ? (
            <ExportCard
              count={exports?.interview_rows || 0}
              description="Spreadsheet of candidate interviews, feedback progress, scheduled times, invite status, and last update."
              label="Interview report"
              onExport={onExportInterviews}
              disabled={!canExportReports}
            />
          ) : null}
          <ExportCard
            count={exports?.followup_rows || 0}
            description="Spreadsheet of candidates who need HR follow-up, recommended action, job, phone, and created date."
            label="Follow-up report"
            onExport={onExportFollowUps}
            disabled={!canExportReports}
          />
          {!canExportReports ? (
            <div className="rounded-2xl border border-line bg-panel-muted/60 p-4 text-sm leading-6 text-subtle">
              Downloads are disabled for your current role.
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Current hiring analytics</CardTitle>
          <CardDescription>Summary numbers for the current hiring pipeline.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <Info label="CV status" value={`${summary?.cv_received || 0} received / ${summary?.cv_missing || 0} incomplete starts`} />
          <Info label="Screening complete" value={`${summary?.screening_complete || 0} candidates`} />
          <Info label="Ready for review" value={`${summary?.ready_for_review || 0} candidates`} />
          {assessmentEnabled ? <Info label="Assessment status" value={`${summary?.assessment_pending || 0} pending / ${summary?.assessment_completed || 0} completed`} /> : null}
          {interviewTotal ? <Info label="Interview status" value={`${summary?.interview_scheduled || 0} scheduled / ${summary?.interview_completed || 0} completed / ${summary?.interview_no_show || 0} no-show`} /> : null}
          <Info label="Follow-ups" value={`${summary?.followups || 0} candidates need contact`} />
          {typeof summary?.followup_delivery_events === 'number' && summary.followup_delivery_events !== summary.followups ? (
            <Info label="Failed delivery events" value={`${summary.followup_delivery_events} events`} />
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Breakdowns</CardTitle>
          <CardDescription>Simple counts by hiring stage, role, and HR follow-up need.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 lg:grid-cols-3">
          <ReportBreakdown title="Applications by stage" rows={stageRows} emptyText="No application stages to report." />
          <ReportBreakdown title="Candidates by role" rows={breakdowns?.candidates_by_role || []} emptyText="No role counts to report." />
          <ReportBreakdown title="Follow-ups by type" rows={breakdowns?.followups_by_type || []} emptyText="No follow-ups need reporting right now." />
        </CardContent>
      </Card>
    </div>
  )
}

function ReportBreakdown({
  emptyText,
  rows,
  title,
}: {
  emptyText: string
  rows: Array<{ label: string; count: number }>
  title: string
}) {
  const shown = rows.slice(0, 8)
  const remaining = rows.length - shown.length
  return (
    <div className="rounded-2xl border border-line bg-panel-muted/60 p-4">
      <div className="font-semibold">{title}</div>
      <div className="mt-3 space-y-2">
        {rows.length ? (
          shown.map((row) => (
            <div className="flex items-center justify-between gap-3 text-sm" key={row.label}>
              <span className="text-subtle">{row.label}</span>
              <Badge>{row.count}</Badge>
            </div>
          ))
        ) : (
          <div className="text-sm text-subtle">{emptyText}</div>
        )}
        {remaining > 0 ? <div className="pt-1 text-xs text-subtle/80">+{remaining} more — see the full export for details.</div> : null}
      </div>
    </div>
  )
}

function ExportCard({
  count,
  description,
  disabled,
  label,
  onExport,
}: {
  count: number
  description: string
  disabled?: boolean
  label: string
  onExport: () => void | Promise<void>
}) {
  return (
    <div className="rounded-2xl border border-line bg-panel-muted/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{label}</div>
          <div className="mt-1 text-sm leading-6 text-subtle">{description}</div>
        </div>
        <Badge tone="muted">{count} records</Badge>
      </div>
      <Button className="mt-4 w-full justify-center" disabled={disabled} onClick={onExport} size="sm" variant="secondary">
        <Download size={16} /> Download
      </Button>
    </div>
  )
}

function SettingsPage({
  access,
  busy,
  createdInviteLink,
  inviteEmail,
  inviteName,
  inviteRole,
  linkPhone,
  onInvite,
  onClearInviteLink,
  onCopyInviteLink,
  onLinkWhatsApp,
  onLogout,
  onSave,
  onUpdateUser,
  prehireEnabled,
  setAccess,
  setInviteEmail,
  setInviteName,
  setInviteRole,
  setLinkPhone,
  team,
  userAccess,
}: {
  access: DashboardAccess
  busy: boolean
  createdInviteLink: string
  inviteEmail: string
  inviteName: string
  inviteRole: string
  linkPhone: string
  onInvite: () => void
  onClearInviteLink: () => void
  onCopyInviteLink: (link: string) => void
  onLinkWhatsApp: () => void
  onLogout: () => void
  onSave: () => void
  onUpdateUser: (userId: string, body: { role?: string; status?: string }) => void
  prehireEnabled: boolean
  setAccess: (access: DashboardAccess) => void
  setInviteEmail: (value: string) => void
  setInviteName: (value: string) => void
  setInviteRole: (value: string) => void
  setLinkPhone: (value: string) => void
  team: DashboardTeamResponse | null
  userAccess: DashboardUserAccess | null
}) {
  const canManageUsers = hasDashboardPermission(userAccess, 'users.manage')
  const account = userAccess?.user
  const recoveryAccess = isRecoveryAccess(userAccess)
  const fallbackUser = currentUserTeamRow(userAccess)
  const displayedTeamUsers = team?.users?.length ? team.users : fallbackUser ? [fallbackUser] : []
  const confirm = useConfirm()
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
            <CardDescription>Your signed-in Wathefni workspace identity.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {recoveryAccess ? (
              <div className="rounded-2xl border border-[#e8c47d]/55 bg-[#fff7e6]/80 p-4 text-sm leading-6 text-[#8a5a12]">
                You’re signed in with a backup access code. Create or sign in to a workspace account for everyday use.
              </div>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2">
              <Info label="Name" value={account?.name || 'Not loaded yet'} />
              <Info label="Email" value={account?.email || access.email || 'Not loaded yet'} />
              <Info label="Role" value={(account?.role && ROLE_LABELS_UI[account.role]) || userAccess?.role_label || account?.role_label || 'Not loaded yet'} />
              <Info label="Company / workspace" value={account?.company_code || access.companyCode || 'WATHEFNI'} />
              <Info label="Status" value={account?.status ? stageLabel(account.status) : 'Not loaded yet'} />
              <Info label="Workspace" value="Wathefni HR" />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button disabled={busy} onClick={onLogout} variant="secondary">
                <LogOut size={16} /> Log out
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Workspace Access</CardTitle>
            <CardDescription>Your role, capabilities, and linked WhatsApp identity.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-lg border border-line bg-panel-muted/60 p-3">
              <div className="text-xs uppercase tracking-wide text-subtle">What you can do</div>
              <div className="mt-2 space-y-1 text-sm leading-6 text-text">
                {readableCapabilities(userAccess).length ? (
                  readableCapabilities(userAccess).map((capability) => <div key={capability}>{capability}</div>)
                ) : (
                  <div className="text-subtle">Verify access to load your role capabilities.</div>
                )}
              </div>
            </div>
            <div className="rounded-lg border border-line bg-panel-muted/60 p-3">
              <div className="text-xs uppercase tracking-wide text-subtle">WhatsApp identity</div>
              <div className="mt-3 flex gap-2">
                <Input onChange={(event) => setLinkPhone(event.target.value)} placeholder="WhatsApp phone" value={linkPhone} />
                <Button disabled={busy} onClick={onLinkWhatsApp} variant="secondary">Link</Button>
              </div>
              <p className="mt-2 text-xs leading-5 text-subtle">Dashboard login and WhatsApp conversations stay separate. Linking lets Wathefni map WhatsApp AI actions to this user.</p>
            </div>
            <details className="rounded-lg border border-line bg-panel-muted/45 p-3">
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-subtle">Backup access</summary>
              <div className="mt-3 space-y-3">
                <p className="text-xs leading-5 text-subtle">
                  Use this only to set up or recover workspace access. For everyday use, sign in with a workspace email and password.
                </p>
                <Input
                  onChange={(event) => setAccess({ ...access, token: event.target.value })}
                  placeholder="Backup access code"
                  type="password"
                  value={access.token}
                />
                <div className="grid gap-3 md:grid-cols-2">
                  <Input onChange={(event) => setAccess({ ...access, hrPhone: event.target.value })} placeholder="Registered HR phone" value={access.hrPhone} />
                  <Input
                    onChange={(event) => setAccess({ ...access, companyCode: event.target.value.toUpperCase() })}
                    placeholder="Company code"
                    value={access.companyCode}
                  />
                </div>
                <Button disabled={busy} onClick={onSave} variant="secondary">
                  Use backup access
                </Button>
              </div>
            </details>
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Team Access</CardTitle>
            <CardDescription>Invite team members and assign one of Wathefni’s built-in roles.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {canManageUsers ? (
              <div className="space-y-3 rounded-2xl border border-line bg-panel-muted/50 p-4">
                <div className="grid gap-3 lg:grid-cols-[1fr_1fr_220px_auto]">
                  <Input onChange={(event) => setInviteName(event.target.value)} placeholder="Name optional" value={inviteName} />
                  <Input onChange={(event) => setInviteEmail(event.target.value)} placeholder="Email" type="email" value={inviteEmail} />
                  <Select onChange={(event) => setInviteRole(event.target.value)} value={inviteRole}>
                    {Object.entries(ROLE_LABELS_UI).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </Select>
                  <Button disabled={busy} onClick={onInvite}><Plus size={16} /> Create invite link</Button>
                </div>
                <p className="text-xs leading-5 text-subtle">
                  Wathefni creates a secure invite link for each team member — share it with them directly.
                </p>
                {createdInviteLink ? (
                  <div className="rounded-2xl border border-[#e8c47d]/55 bg-[#fff7e6]/80 p-4">
                    <div className="text-sm font-semibold text-text">Invite link ready</div>
                    <p className="mt-1 text-xs leading-5 text-subtle">Share this invite link with the new team member. It expires automatically.</p>
                    <div className="mt-3 flex flex-col gap-2 md:flex-row">
                      <Input readOnly value={createdInviteLink} />
                      <Button onClick={() => onCopyInviteLink(createdInviteLink)} variant="secondary"><Copy size={16} /> Copy link</Button>
                      <Button onClick={onClearInviteLink} variant="ghost">Dismiss</Button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="rounded-2xl border border-line bg-panel-muted/50 p-4 text-sm text-subtle">Only Owners/Admins can invite users or change team access.</div>
            )}
            {team?.invites?.length ? (
              <div className="rounded-2xl border border-line/55 bg-panel/70 p-4">
                <div className="text-sm font-semibold text-text">Pending invites</div>
                <div className="mt-3 grid gap-2">
                  {team.invites.map((invite) => (
                    <div className="flex flex-col gap-1 rounded-xl bg-white/35 p-3 text-sm md:flex-row md:items-center md:justify-between" key={invite.invite_id}>
                      <div>
                        <div className="font-medium text-text">{invite.email}</div>
                        <div className="text-xs text-subtle">{ROLE_LABELS_UI[invite.role] || invite.role} · Expires {invite.expires_at ? formatDateTime(invite.expires_at) : 'soon'}</div>
                      </div>
                      <Badge tone="warning">Pending</Badge>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="overflow-x-auto rounded-3xl border border-line/55 bg-panel/75">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead className="bg-[#f7f1e7]/72 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                  <tr>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Email</th>
                    <th className="px-4 py-3">Phone</th>
                    <th className="px-4 py-3">WhatsApp</th>
                    <th className="px-4 py-3">Role</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Last active</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/45 bg-panel/42">
                  {displayedTeamUsers.map((user) => (
                    <tr key={user.user_id}>
                      <td className="px-4 py-3 font-medium text-text">{user.name || 'Invited user'}</td>
                      <td className="px-4 py-3 text-subtle">{user.email}</td>
                      <td className="px-4 py-3 text-subtle">{user.phone || 'Not linked'}</td>
                      <td className="px-4 py-3">
                        <Badge tone={user.whatsapp_linked ? 'success' : 'muted'}>{user.whatsapp_linked ? 'WhatsApp linked' : 'Not linked'}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        {canManageUsers ? (
                          <Select
                            onChange={async (event) => {
                              const nextRole = event.target.value
                              if (nextRole === user.role) return
                              if (
                                !(await confirm({
                                  title: 'Change role?',
                                  body: `Change ${user.name || user.email}'s role to ${ROLE_LABELS_UI[nextRole] || nextRole}? This changes what they can see and do in the workspace.`,
                                  confirmLabel: 'Change role',
                                  destructive: true,
                                }))
                              )
                                return
                              onUpdateUser(user.user_id, { role: nextRole })
                            }}
                            value={user.role}
                          >
                            {Object.entries(ROLE_LABELS_UI).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                          </Select>
                        ) : ROLE_LABELS_UI[user.role] || user.role}
                      </td>
                      <td className="px-4 py-3"><Badge tone={user.status === 'active' ? 'success' : user.status === 'disabled' ? 'danger' : 'warning'}>{stageLabel(user.status)}</Badge></td>
                      <td className="px-4 py-3 text-subtle">{user.last_active_at ? formatDateTime(user.last_active_at) : 'No activity yet'}</td>
                      <td className="px-4 py-3">
                        {canManageUsers && user.status !== 'disabled' && team?.users?.length ? (
                          <Button
                            onClick={async () => {
                              if (
                                !(await confirm({
                                  title: 'Deactivate user?',
                                  body: `${user.name || user.email} will immediately lose access to this workspace. You can re-invite them later.`,
                                  confirmLabel: 'Deactivate',
                                  destructive: true,
                                }))
                              )
                                return
                              onUpdateUser(user.user_id, { status: 'disabled' })
                            }}
                            size="sm"
                            variant="secondary"
                          >
                            Deactivate
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                  {!displayedTeamUsers.length ? (
                    <tr><td className="px-4 py-6 text-subtle" colSpan={8}>{team ? 'No team members yet.' : 'Team members are loading...'}</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
        {prehireEnabled && canManageUsers ? <IntegrationsCard access={access} /> : null}
        {prehireEnabled && hasDashboardPermission(userAccess, 'candidate.import') ? <IntakeSettingsCard access={access} /> : null}
    </div>
  )
}

function IntakeSettingsCard({ access }: { access: DashboardAccess }) {
  const [autoAdmit, setAutoAdmit] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const confirm = useConfirm()

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const data = await getImportSettings(access)
        if (active) setAutoAdmit(data.auto_admit_explicit_imports)
      } catch {
        if (active) setAutoAdmit(null)
      }
    })()
    return () => {
      active = false
    }
  }, [access])

  if (autoAdmit === null) return null

  const toggle = async () => {
    const next = !autoAdmit
    if (
      !(await confirm({
        title: next ? 'Turn on auto-add?' : 'Turn off auto-add?',
        body: next
          ? 'Matching imported candidates will be added to your pipeline automatically without Intake review. Continue?'
          : 'All imported candidates will go to Intake review first before entering your pipeline. Continue?',
        confirmLabel: next ? 'Turn on' : 'Turn off',
      }))
    )
      return
    setBusy(true)
    setError('')
    try {
      const data = await updateImportSettings(access, next)
      setAutoAdmit(data.auto_admit_explicit_imports)
    } catch (err) {
      setError(friendlyDashboardError(err, 'We couldn’t update this setting right now. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Candidate intake</CardTitle>
        <CardDescription>How imported and emailed CVs enter your pipeline.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/70 bg-white/55 p-4">
          <div className="min-w-0">
            <div className="text-sm font-medium text-text">Auto-add candidates with a clear role</div>
            <p className="mt-1 text-xs leading-5 text-subtle">
              When a CV arrives with a role that clearly matches an open position (a role-specific inbox, or an exact
              role in your sheet), add the candidate to Candidates automatically. They are labelled, never messaged, and
              never ranked without your review. Turn this off to review every import in Intake first.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={autoAdmit}
            disabled={busy}
            onClick={() => void toggle()}
            className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${autoAdmit ? 'bg-emerald-500' : 'bg-subtle/40'} disabled:opacity-60`}
          >
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${autoAdmit ? 'translate-x-5' : 'translate-x-1'}`} />
          </button>
        </div>
        {error ? <p className="text-xs text-rose-600">{error}</p> : null}
      </CardContent>
    </Card>
  )
}

function IntegrationsCard({ access }: { access: DashboardAccess }) {
  const [feature, setFeature] = useState<MailboxFeatureStatus | null>(null)
  const [connection, setConnection] = useState<MailboxConnection | null>(null)
  const [labels, setLabels] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'warning'; text: string } | null>(null)
  const confirm = useConfirm()

  const reload = useCallback(async () => {
    try {
      const data = await getMailboxConnections(access)
      setFeature(data.feature)
      setConnection(data.connections[0] || null)
    } catch {
      setFeature(null)
    }
  }, [access])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const outcome = params.get('mailbox')
    if (!outcome) return
    if (outcome === 'connected') setNotice({ tone: 'success', text: 'Recruitment inbox connected. Choose a label/folder, then turn on Auto-import.' })
    else if (outcome === 'failed') setNotice({ tone: 'warning', text: 'We could not connect that inbox. Please try again.' })
    else if (outcome === 'unavailable') setNotice({ tone: 'warning', text: 'Email inbox import is not available yet.' })
    params.delete('mailbox')
    const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
    window.history.replaceState({}, '', next)
  }, [])

  const loadLabels = useCallback(async (mailboxId: string) => {
    try {
      const data = await getMailboxLabels(access, mailboxId)
      setLabels(data.labels)
    } catch {
      setLabels([])
      setNotice({ tone: 'warning', text: 'Reconnect the inbox to load folders.' })
      void reload()
    }
  }, [access, reload])

  useEffect(() => {
    if (connection?.status === 'connected' && connection.has_credentials) void loadLabels(connection.mailbox_id)
  }, [connection?.mailbox_id, connection?.status, connection?.has_credentials, loadLabels])

  // Feature ships dark: only render when the server says it is available.
  if (!feature?.enabled) return null

  const connect = async () => {
    setBusy(true)
    setNotice(null)
    try {
      const data = await connectMailbox(access, {})
      window.location.href = data.authorize_url
    } catch (error) {
      setNotice({ tone: 'warning', text: friendlyDashboardError(error, 'We couldn’t start the inbox connection right now. Please try again.') })
      setBusy(false)
    }
  }

  const setLabel = async (label: string) => {
    if (!connection) return
    setBusy(true)
    try {
      const res = await updateMailbox(access, connection.mailbox_id, { label_filter: label || null })
      setConnection(res.connection)
    } finally {
      setBusy(false)
    }
  }

  const toggleAuto = async () => {
    if (!connection) return
    const next = !connection.auto_import
    if (
      !(await confirm({
        title: next ? 'Turn on auto-import?' : 'Turn off auto-import?',
        body: next
          ? 'Wathefni will automatically import new CVs from this inbox folder. Continue?'
          : 'Wathefni will stop importing CVs from this inbox automatically. Continue?',
        confirmLabel: next ? 'Turn on' : 'Turn off',
      }))
    )
      return
    setBusy(true)
    try {
      const res = await updateMailbox(access, connection.mailbox_id, { auto_import: next })
      setConnection(res.connection)
    } finally {
      setBusy(false)
    }
  }

  const checkNow = async () => {
    if (!connection) return
    setBusy(true)
    setNotice(null)
    try {
      const res = await checkMailboxNow(access, connection.mailbox_id)
      setNotice({ tone: 'success', text: res.message })
      void reload()
    } catch (error) {
      setNotice({ tone: 'warning', text: error instanceof DashboardApiError && error.code === 'mailbox_needs_reconnect' ? 'This inbox needs reconnecting.' : 'Could not check the inbox right now.' })
      void reload()
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    if (!connection) return
    if (
      !(await confirm({
        title: 'Disconnect this inbox?',
        body: 'Wathefni will stop importing CVs from this inbox and remove its connection. You can reconnect later, but it will need to be set up again.',
        confirmLabel: 'Disconnect inbox',
        destructive: true,
      }))
    )
      return
    setBusy(true)
    try {
      await disconnectMailbox(access, connection.mailbox_id)
      setConnection(null)
      setLabels([])
      setNotice({ tone: 'success', text: 'Inbox disconnected.' })
    } finally {
      setBusy(false)
    }
  }

  const connected = connection?.status === 'connected' && connection.has_credentials
  const needsReconnect = !!connection && (connection.status === 'needs_reconnect' || connection.status === 'error')

  return (
    <Card className="xl:col-span-2">
      <CardHeader>
        <CardTitle>Integrations</CardTitle>
        <CardDescription>Connect a recruitment inbox so CVs emailed to you land in Import Review automatically.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {notice ? (
          <div className={cn('rounded-2xl border p-3 text-sm leading-6', notice.tone === 'success' ? 'border-emerald-300/60 bg-emerald-50/70 text-emerald-800' : 'border-[#e8c47d]/55 bg-[#fff7e6]/80 text-[#8a5a12]')}>
            {notice.text}
          </div>
        ) : null}

        <div className="rounded-2xl border border-line bg-panel-muted/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/70 text-text"><Inbox size={18} /></span>
              <div>
                <div className="text-sm font-semibold text-text">Recruitment inbox</div>
                <div className="text-xs text-subtle">
                  {connection?.email_address ? connection.email_address : 'Gmail / Google Workspace'}
                </div>
              </div>
            </div>
            <Badge tone={connected ? 'success' : needsReconnect ? 'danger' : 'warning'}>{connection ? connection.status_label : 'Not connected'}</Badge>
          </div>

          {!connection || needsReconnect ? (
            <div className="mt-4">
              <Button disabled={busy} onClick={connect}>
                {busy ? <Loader2 className="animate-spin" size={16} /> : <MessageCircle size={16} />}
                {needsReconnect ? 'Reconnect inbox' : 'Connect recruitment inbox'}
              </Button>
              {!feature.gmail_oauth_ready ? (
                <p className="mt-2 text-xs leading-5 text-subtle">Email connection isn’t available for your workspace yet. Please check back soon.</p>
              ) : null}
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <div className="grid gap-2 md:grid-cols-[1fr_auto] md:items-end">
                <label className="space-y-1">
                  <span className="text-xs uppercase tracking-wide text-subtle">Folder / label to import from</span>
                  <Select disabled={busy} onChange={(event) => void setLabel(event.target.value)} value={connection.label_filter || ''}>
                    <option value="">All mail (not recommended)</option>
                    {connection.label_filter && !labels.includes(connection.label_filter) ? (
                      <option value={connection.label_filter}>{connection.label_filter}</option>
                    ) : null}
                    {labels.map((label) => <option key={label} value={label}>{label}</option>)}
                  </Select>
                </label>
                <Button disabled={busy} onClick={checkNow} variant="secondary">
                  {busy ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />} Check now
                </Button>
              </div>

              <div className="flex items-center justify-between rounded-xl border border-line/55 bg-panel/70 p-3">
                <div>
                  <div className="text-sm font-medium text-text">Auto-import</div>
                  <div className="text-xs text-subtle">{connection.auto_import ? 'New CVs import automatically.' : 'Off — use Check now to import manually.'}</div>
                </div>
                <Button disabled={busy} onClick={toggleAuto} variant={connection.auto_import ? 'secondary' : 'default'}>
                  {connection.auto_import ? 'Turn off' : 'Turn on'}
                </Button>
              </div>

              <p className="text-xs leading-5 text-subtle">Imported CVs go to Import Review / Needs role. Wathefni only reads this inbox — it never sends, deletes, or marks email as read.</p>
              <Button disabled={busy} onClick={disconnect} variant="ghost">Disconnect inbox</Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function AccessVerificationPage({
  access,
  accessIssue,
  acceptName,
  acceptPassword,
  acceptPhone,
  busy,
  inviteToken,
  onVerify,
  setAcceptName,
  setAcceptPassword,
  setAcceptPhone,
  setAccess,
}: {
  access: DashboardAccess
  accessIssue: AccessIssue
  acceptName: string
  acceptPassword: string
  acceptPhone: string
  busy: boolean
  inviteToken: string
  onVerify: () => void
  setAcceptName: (value: string) => void
  setAcceptPassword: (value: string) => void
  setAcceptPhone: (value: string) => void
  setAccess: (access: DashboardAccess) => void
}) {
  if (inviteToken) {
    return (
      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.45fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Complete Your Wathefni Invite</CardTitle>
            <CardDescription>Create your workspace login. Your fixed role is already assigned by the company Owner/Admin.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                if (!busy) onVerify()
              }}
            >
              <Input autoComplete="name" autoFocus name="name" onChange={(event) => setAcceptName(event.target.value)} placeholder="Your name" value={acceptName} />
              <Input autoComplete="new-password" name="new-password" onChange={(event) => setAcceptPassword(event.target.value)} placeholder="Create password" type="password" value={acceptPassword} />
              <Input autoComplete="tel" name="phone" onChange={(event) => setAcceptPhone(event.target.value)} placeholder="WhatsApp phone optional" value={acceptPhone} />
              <Button disabled={busy} type="submit">
                {busy ? <Loader2 className="animate-spin" size={16} /> : <UserCheck size={16} />} Accept invite
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>What Happens Next</CardTitle>
            <CardDescription>Wathefni will sign you into the company workspace and apply your assigned role immediately.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Info label="Workspace" value="Company HR workspace" />
            <Info label="Permissions" value="Fixed by assigned role" />
            <Info label="WhatsApp" value={acceptPhone ? 'Linked after accept' : 'Can be linked later'} />
          </CardContent>
        </Card>
      </div>
    )
  }
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.45fr)]">
      <Card>
        <CardHeader>
          <CardTitle>{accessIssue.title}</CardTitle>
          <CardDescription>{accessIssue.description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (!busy) onVerify()
            }}
          >
            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  autoComplete="username"
                  autoFocus
                  name="email"
                  onChange={(event) => setAccess({ ...access, email: event.target.value })}
                  placeholder="Work email"
                  type="email"
                  value={access.email || ''}
                />
                <Input
                  autoComplete="current-password"
                  name="password"
                  onChange={(event) => setAccess({ ...access, password: event.target.value })}
                  placeholder="Password"
                  type="password"
                  value={access.password || ''}
                />
              </div>
              <Input
                autoComplete="off"
                name="company-code"
                onChange={(event) => setAccess({ ...access, companyCode: event.target.value.toUpperCase() })}
                placeholder="Company code"
                value={access.companyCode}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button disabled={busy} type="submit">
                {busy ? <Loader2 className="animate-spin" size={16} /> : <UserCheck size={16} />} Sign in
              </Button>
              <span className="text-xs text-subtle">Use your invited workspace account.</span>
            </div>
          </form>
          <details className="rounded-2xl border border-line bg-panel-muted/50 p-4">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-subtle">Backup access</summary>
            <div className="mt-3 space-y-3">
              <p className="text-xs leading-5 text-subtle">
                Use a backup access code only if you need to set up or recover the workspace.
              </p>
              <Input
                onChange={(event) => setAccess({ ...access, token: event.target.value })}
                placeholder="Backup access code"
                type="password"
                value={access.token}
              />
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  onChange={(event) => setAccess({ ...access, hrPhone: event.target.value })}
                  placeholder="Registered HR phone"
                  value={access.hrPhone}
                />
                <Input
                  onChange={(event) => setAccess({ ...access, companyCode: event.target.value.toUpperCase() })}
                  placeholder="Company code"
                  value={access.companyCode}
                />
              </div>
            </div>
          </details>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Workspace Access</CardTitle>
          <CardDescription>After sign-in, Wathefni loads your company workspace, modules, and role permissions.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Info label="Company" value={access.companyCode || 'Verified after access check'} />
          <Info label="Your WhatsApp phone" value={access.hrPhone ? 'Ready to link' : 'Can be linked after login'} />
          <Info label="Your role" value="Loaded after access is verified" />
        </CardContent>
      </Card>
    </div>
  )
}

function NeedsSettings({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in required</CardTitle>
        <CardDescription>Sign in to your Wathefni workspace from Settings to load the dashboard.</CardDescription>
      </CardHeader>
      <CardContent>
        <Button onClick={onOpenSettings}>Open Settings</Button>
      </CardContent>
    </Card>
  )
}

function LoadingDashboard({
  busy,
  notice,
  onOpenSettings,
  onRefresh,
}: {
  busy: boolean
  notice: string
  onOpenSettings: () => void
  onRefresh: () => void
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Loading live dashboard data</CardTitle>
        <CardDescription>Wathefni found saved dashboard access and is loading live hiring data before showing metrics.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border border-line bg-panel-muted/60 p-4 text-sm text-subtle">{notice}</div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={onRefresh}>
            {busy ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
            Load now
          </Button>
          <Button disabled={busy} onClick={onOpenSettings} variant="secondary">
            Check Settings
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function AdminAIPage({
  assessmentEnabled,
  enabledModules,
  busy,
  historyOpen,
  input,
  messages,
  newChatConfirmOpen,
  onApplyNavigation,
  onAsk,
  onCloseHistory,
  onCloseNewChatConfirm,
  onConfirm,
  onInputChange,
  onNewChat,
  onOpenCandidate,
  onOpenHistory,
  onOpenSession,
  onPrompt,
  onRequestNewChat,
  sessions,
}: {
  assessmentEnabled: boolean
  enabledModules?: string[]
  busy: boolean
  historyOpen: boolean
  input: string
  messages: ChatMessage[]
  newChatConfirmOpen: boolean
  onApplyNavigation: (item: DashboardChatNavigation) => void
  onAsk: () => void
  onCloseHistory: () => void
  onCloseNewChatConfirm: () => void
  onConfirm: () => void
  onInputChange: (value: string) => void
  onNewChat: () => void
  onOpenCandidate: (appKey?: string) => void
  onOpenHistory: () => void
  onOpenSession: (session: DashboardChatSession) => void
  onPrompt: (prompt: string) => void
  onRequestNewChat: () => void
  sessions: DashboardChatSession[]
}) {
  const chatEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  const groupedSessions = groupDashboardChatSessions(sessions)
  const promptChips = assistantPromptChips(enabledModules, assessmentEnabled)
  const posthireOn = posthireModulesEnabled(enabledModules)
  const emptyPrompt = posthireOn
    ? 'Ask about hiring or your team — candidates, onboarding, attendance, leave, shifts, payroll, or compliance.'
    : assessmentEnabled
      ? 'Ask about candidates, rankings, assessments, interviews, or follow-ups.'
      : 'Ask about candidates, rankings, interviews, or follow-ups.'

  return (
    <section className="h-[calc(100vh-220px)] min-h-[460px]">
      <div className="flex h-full min-h-0 flex-col rounded-[2.25rem] border border-white/70 bg-panel/82 shadow-[var(--shadow-premium)] ring-1 ring-ink/[0.03] backdrop-blur-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-line/55 px-5 py-3 lg:px-8">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-subtle">Wathefni Assistant</div>
          <div className="flex items-center gap-1 text-sm">
            <button className="rounded-full px-3 py-1.5 text-subtle transition hover:bg-white/55 hover:text-text" onClick={onOpenHistory} type="button">
              History
            </button>
            <span className="text-line">|</span>
            <button className="rounded-full px-3 py-1.5 text-subtle transition hover:bg-white/55 hover:text-text" onClick={onRequestNewChat} type="button">
              New chat
            </button>
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-6 lg:px-10">
            {messages.length === 0 ? (
              <div className="flex h-full min-h-[260px] flex-col items-center justify-center text-center">
                <div className="max-w-xl text-lg font-semibold tracking-[-0.02em] text-text">
                  {emptyPrompt}
                </div>
                <div className="mt-5 flex max-w-2xl flex-wrap justify-center gap-2">
                  {promptChips.map((prompt) => (
                    <button
                      className="rounded-full border border-white/70 bg-white/45 px-4 py-2 text-sm font-medium text-subtle shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_20px_rgba(24,20,15,0.035)] transition duration-200 hover:-translate-y-0.5 hover:bg-panel hover:text-text hover:shadow-soft"
                      key={prompt}
                      onClick={() => onPrompt(prompt)}
                      type="button"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {messages.map((message) => (
              <div
                className={message.role === 'user' ? 'ml-auto w-fit max-w-[60%] rounded-[1.35rem] bg-[linear-gradient(180deg,#24211d_0%,#11100e_100%)] px-[18px] py-3 text-white shadow-[0_14px_34px_rgba(24,20,15,0.18)]' : 'flex max-w-5xl items-start gap-3'}
                key={message.id}
              >
                {message.role === 'assistant' ? (
                  <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full border border-white/70 bg-white/55 text-slate shadow-soft">
                    <MessageCircle size={15} />
                  </div>
                ) : null}
                <div className={message.role === 'assistant' ? 'min-w-0 flex-1' : ''}>
                  <div className={`whitespace-pre-wrap text-base ${message.role === 'assistant' ? 'leading-7 text-text' : 'leading-6 text-white'}`}>
                    {message.text || (message.isStreaming ? <span className="inline-flex gap-1 text-mist"><span className="h-2 w-2 animate-pulse rounded-full bg-mist" /><span className="h-2 w-2 animate-pulse rounded-full bg-mist [animation-delay:120ms]" /><span className="h-2 w-2 animate-pulse rounded-full bg-mist [animation-delay:240ms]" /></span> : null)}
                  </div>
                  {message.candidateCards?.length ? (
                    <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                      {message.candidateCards.map((card) => (
                        <button
                          className="group rounded-3xl border border-white/70 bg-white/55 p-5 text-left shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_14px_34px_rgba(24,20,15,0.055)] backdrop-blur transition duration-200 hover:-translate-y-1 hover:bg-panel/90 hover:shadow-[0_18px_46px_rgba(24,20,15,0.09)]"
                          key={card.app_key || card.phone || card.name}
                          onClick={() => onOpenCandidate(card.app_key)}
                          type="button"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="font-semibold">{card.name || card.phone || 'Candidate'}</div>
                              <div className="mt-1 text-sm text-subtle">{card.position || (card.status ? stageLabel(card.status) : '') || card.phone}</div>
                            </div>
                            {card.score != null ? (
                              <div className="rounded-full border border-white/70 bg-white/60 px-2.5 py-1 text-xs font-semibold text-text shadow-[0_1px_0_rgba(255,255,255,0.8)_inset]">
                                {Math.round(Number(card.score))}/100
                              </div>
                            ) : null}
                          </div>
                          {card.reasons?.length ? (
                            <div className="mt-3 text-xs leading-5 text-subtle">{card.reasons[0]}</div>
                          ) : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {message.confirmation ? (
                    <div className="mt-4 max-w-2xl rounded-3xl border border-amber-200/70 bg-[linear-gradient(180deg,rgba(255,251,235,0.92),rgba(254,243,199,0.62))] p-5 shadow-[0_1px_0_rgba(255,255,255,0.85)_inset,0_16px_42px_rgba(146,64,14,0.10)] backdrop-blur">
                      <div className="text-sm font-semibold text-amber-900">
                        {message.confirmation.is_active === false ? 'Confirmation inactive' : 'Confirmation required'}
                      </div>
                      <div className="mt-1 text-sm leading-6 text-amber-800">
                        {message.confirmation.summary || 'This action will only run after explicit approval.'}
                      </div>
                      {message.confirmation.is_active === false ? (
                        <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-amber-700">
                          {message.confirmation.status === 'expired' ? 'Expired' : 'Inactive'}
                        </div>
                      ) : (
                      <Button className="mt-3" onClick={onConfirm} size="sm">
                        {message.confirmation.label || 'Confirm action'}
                      </Button>
                      )}
                    </div>
                  ) : null}
                  {message.navigation?.length ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {message.navigation.map((item) => (
                        <Button key={`${item.page}-${item.label}-${item.position_code || ''}`} onClick={() => onApplyNavigation(item)} size="sm" variant="secondary">
                          {item.label || `Open ${item.page}`}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <form
            className="shrink-0 border-t border-line/55 bg-panel/72 px-5 py-4 backdrop-blur-xl lg:px-8"
            onSubmit={(event) => {
              event.preventDefault()
              onAsk()
            }}
          >
            <div className="flex min-h-[68px] items-center gap-3 rounded-[1.6rem] border border-white/70 bg-white/55 py-2 pl-4 pr-2 shadow-[0_1px_0_rgba(255,255,255,0.85)_inset,0_18px_46px_rgba(24,20,15,0.075)] backdrop-blur">
              <Textarea
                className="max-h-28 min-h-10 flex-1 resize-none border-0 bg-transparent py-2 text-base shadow-none focus:ring-0"
                onChange={(event) => onInputChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    onAsk()
                  }
                }}
                placeholder="Message"
                value={input}
              />
              <button
                aria-label="Send message"
                className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-ink bg-ink text-white transition hover:-translate-y-0.5 hover:shadow-soft disabled:border-line disabled:bg-panel disabled:text-mist"
                disabled={busy || !input.trim()}
                type="submit"
              >
                {busy ? <Loader2 className="animate-spin" size={17} /> : <ArrowUp size={19} />}
              </button>
            </div>
          </form>
        </div>
      </div>
      {historyOpen ? (
        <div className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-[2px]" onClick={onCloseHistory}>
          <aside
            className="ml-auto flex h-full w-full max-w-md flex-col border-l border-white/70 bg-panel/95 p-6 shadow-[0_24px_80px_rgba(24,20,15,0.18)] backdrop-blur-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-line/55 pb-4">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-subtle">Wathefni Assistant</div>
                <h3 className="mt-1 text-xl font-semibold tracking-tight">History</h3>
              </div>
              <Button onClick={onCloseHistory} size="sm" variant="secondary">Close</Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto py-4">
              {groupedSessions.some((group) => group.sessions.length) ? (
                groupedSessions.map((group) => group.sessions.length ? (
                  <section className="mb-5" key={group.label}>
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">{group.label}</div>
                    <div className="space-y-2">
                      {group.sessions.map((session) => (
                        <button
                          className="w-full rounded-2xl border border-line/60 bg-white/36 p-3 text-left transition hover:border-[#c89445]/35 hover:bg-panel/75"
                          key={session.conversation_id}
                          onClick={() => onOpenSession(session)}
                          type="button"
                        >
                          <div className="font-semibold text-text">{session.title || 'Wathefni Assistant chat'}</div>
                          <div className="mt-1 text-xs text-subtle">{chatSessionTimeLabel(session)}</div>
                        </button>
                      ))}
                    </div>
                  </section>
                ) : null)
              ) : (
                <EmptyState text="No Wathefni Assistant sessions yet. Your recent dashboard chats will appear here." />
              )}
            </div>
          </aside>
        </div>
      ) : null}
      {newChatConfirmOpen ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-ink/20 p-4 backdrop-blur-[2px]" onClick={onCloseNewChatConfirm}>
          <div
            className="w-full max-w-md rounded-[1.75rem] border border-white/70 bg-panel/95 p-6 shadow-[0_24px_80px_rgba(24,20,15,0.18)] backdrop-blur-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="text-lg font-semibold tracking-tight">Start a new chat?</div>
            <p className="mt-2 text-sm leading-6 text-subtle">
              This clears the current conversation view, but saved actions and hiring records will remain.
            </p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Button onClick={onCloseNewChatConfirm} variant="secondary">Cancel</Button>
              <Button disabled={busy} onClick={onNewChat}>New chat</Button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

function chatSessionDate(session: DashboardChatSession) {
  const raw = session.last_message_at || session.updated_at || session.created_at
  const date = raw ? new Date(raw) : new Date()
  return Number.isNaN(date.getTime()) ? new Date() : date
}

function groupDashboardChatSessions(sessions: DashboardChatSession[]) {
  const now = new Date()
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startYesterday = startToday - 24 * 60 * 60 * 1000
  const groups = [
    { label: 'Today', sessions: [] as DashboardChatSession[] },
    { label: 'Yesterday', sessions: [] as DashboardChatSession[] },
    { label: 'Earlier', sessions: [] as DashboardChatSession[] },
  ]
  sessions.forEach((session) => {
    const time = chatSessionDate(session).getTime()
    if (time >= startToday) groups[0].sessions.push(session)
    else if (time >= startYesterday) groups[1].sessions.push(session)
    else groups[2].sessions.push(session)
  })
  return groups
}

function chatSessionTimeLabel(session: DashboardChatSession) {
  const date = chatSessionDate(session)
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function ActionCard({
  item,
}: {
  item: {
    label: string
    value: number
    detail: string
    icon: typeof Users
    tone: 'default' | 'success' | 'warning' | 'danger' | 'muted'
    onClick: () => void
    eyebrow?: string
  }
}) {
  const Icon = item.icon
  const dotClass =
    item.tone === 'success'
      ? 'bg-emerald-500 shadow-[0_0_14px_rgba(16,185,129,0.38)]'
      : item.tone === 'danger'
      ? 'bg-rose-500 shadow-[0_0_14px_rgba(244,63,94,0.32)]'
      : item.tone === 'default'
      ? 'bg-slate-400 shadow-[0_0_14px_rgba(100,116,139,0.24)]'
      : item.tone === 'muted'
      ? 'bg-mist'
      : 'bg-[#c89445] shadow-[0_0_14px_rgba(200,148,69,0.46)]'
  return (
    <button
      className="group rounded-[1.35rem] border border-line/60 bg-white/36 p-4 text-start transition duration-200 hover:border-[#c89445]/35 hover:bg-panel/72"
      onClick={item.onClick}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {item.eyebrow ? <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-mist">{item.eyebrow}</div> : null}
          <div className={`text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle ${item.eyebrow ? 'mt-1' : ''}`}>{item.label}</div>
          <div className="mt-2 text-3xl font-semibold tracking-[-0.035em] tabular-nums">{item.value}</div>
        </div>
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl border border-line/60 bg-panel/65 text-slate transition group-hover:border-[#c89445]/30 group-hover:text-ink">
          <Icon size={18} />
        </div>
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <div className="text-sm leading-5 text-subtle">{item.detail}</div>
        <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${item.value ? dotClass : 'bg-emerald-500 shadow-[0_0_14px_rgba(16,185,129,0.34)]'}`} />
      </div>
    </button>
  )
}

function RoleBottleneck({
  assessmentEnabled,
  job,
  locale,
  onOpenCandidates,
}: {
  assessmentEnabled: boolean
  job: PositionSummary
  locale: RecruitingLocale
  onOpenCandidates: () => void
}) {
  return (
    <button
      className="w-full rounded-2xl border border-line/60 bg-white/34 p-3.5 text-start transition duration-200 hover:border-[#c89445]/30 hover:bg-panel/72"
      onClick={onOpenCandidates}
      type="button"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="font-medium">{job.position_title || job.position_code}</div>
        <Badge tone={Number(job.active_count || 0) ? 'warning' : 'muted'}>{roleActiveBadge(Number(job.active_count || 0), locale)}</Badge>
      </div>
      <div className="mt-1 text-sm text-subtle">{roleBottleneckLabel(job, locale, assessmentEnabled)}</div>
    </button>
  )
}

function MetricGrid({ metrics }: { metrics: Array<{ label: string; value: number | string | undefined; icon: typeof Users }> }) {
  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
      {metrics.map((metric) => {
        const Icon = metric.icon
        return (
          <section className="rounded-[1.35rem] border border-line/55 bg-panel/70 p-4 shadow-[0_10px_28px_rgba(24,20,15,0.035)]" key={metric.label}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle">{metric.label}</div>
                <div className="mt-2 text-2xl font-semibold tracking-tight">{compactNumber(metric.value)}</div>
              </div>
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-2xl border border-line/55 bg-white/45 text-slate">
                <Icon size={18} />
              </div>
            </div>
          </section>
        )
      })}
    </section>
  )
}

function CandidateRow({
  application,
  assessmentEnabled,
  locale,
  onPreviewCv,
  onSelect,
}: {
  application: ApplicationSummary
  assessmentEnabled: boolean
  locale: RecruitingLocale
  onPreviewCv: (application: ApplicationSummary) => void
  onSelect: (application: ApplicationSummary) => void
}) {
  const important = isReadyForReview(application)
  return (
    <tr className={`cursor-pointer transition duration-150 hover:bg-white/42 ${important ? 'bg-[#f4e7cf]/28' : ''}`} onClick={() => onSelect(application)}>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          {important ? <span className="h-2 w-2 rounded-full bg-[#c89445]" /> : null}
          <div className="font-semibold">{candidateName(application)}</div>
        </div>
        <div className="text-xs text-subtle">{application.candidate?.email || application.phone}</div>
      </td>
      <td className="px-4 py-3 text-subtle">{application.position?.title || application.position?.code || '—'}</td>
      <td className="px-4 py-3 text-subtle">{intakeSourceLabel(application.intake_source || application.data_source, locale)}</td>
      <td className="px-4 py-3">
        <Badge tone={statusTone(application.canonical_stage || application.status)}>
          {canonicalStageLabel(application.canonical_stage || application.status, locale)}
        </Badge>
      </td>
      <td className="px-4 py-3">
        {application.cv?.received && application.allowed_actions?.includes('preview_cv') ? (
          <Button
            onClick={(event) => {
              event.stopPropagation()
              onPreviewCv(application)
            }}
            size="sm"
            variant="secondary"
          >
            {recruitingActionLabel('preview_cv', locale)}
          </Button>
        ) : application.cv?.received ? (
          <Badge tone="success">{locale === 'ar' ? 'تمت الاستلام' : 'Received'}</Badge>
        ) : (
          <Badge tone="warning">{locale === 'ar' ? 'غير مستلمة' : 'Not received'}</Badge>
        )}
      </td>
      {assessmentEnabled ? <td className="px-4 py-3 text-subtle">{assessmentLabel(application)}</td> : null}
      <td className="px-4 py-3">
        <div className="flex flex-col items-start gap-1">
          <Badge tone={application.communication?.status === 'failed' ? 'danger' : application.communication?.status === 'sent' ? 'success' : 'warning'}>
            {communicationLabel(application.communication?.status, locale)}
          </Badge>
          {application.communication?.stage_changed_without_contact ? (
            <span className="max-w-48 text-xs font-medium text-amber-800">{recruitingCopy(locale, 'notInformed')}</span>
          ) : null}
        </div>
      </td>
      <td className="max-w-56 px-4 py-3 text-subtle">
        {application.waiting_for_hr?.length
          ? workflowItemLabel(application.waiting_for_hr[0], locale)
          : recruitingCopy(locale, 'noPendingHr')}
      </td>
      <td className="px-4 py-3">
        <Button onClick={() => onSelect(application)} size="sm" variant="secondary">
          {locale === 'ar' ? 'مراجعة' : 'Review'}
        </Button>
      </td>
    </tr>
  )
}

function ScoreBreakdown({ label, max, value }: { label: string; max: number; value: number }) {
  const width = Math.max(4, Math.min(100, (Number(value || 0) / max) * 100))
  return (
    <div className="rounded-2xl border border-white/70 bg-white/50 p-3 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_20px_rgba(24,20,15,0.035)]">
      <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-subtle">
        <span>{label}</span>
        <span>
          {Math.round(value)}/{max}
        </span>
      </div>
      <div className="mt-2 h-1.5 rounded-full bg-panel-muted">
        <div className="h-1.5 rounded-full bg-ink" style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

function PipelineRow({ count, label }: { count: number; label: string }) {
  const width = Math.max(8, Math.min(100, Number(count || 0) * 12))
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-subtle">{count}</span>
      </div>
      <div className="h-2 rounded-full bg-panel-muted">
        <div className="h-2 rounded-full bg-ink" style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

function TimelineItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3 rounded-2xl border border-line/55 bg-white/34 p-3 text-sm">
      <div className="mt-1 h-2 w-2 rounded-full bg-[#c89445]" />
      <div>
        <div className="font-medium">{label}</div>
        <div className="text-subtle">{value}</div>
      </div>
    </div>
  )
}

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="rounded-2xl border border-line/55 bg-white/32 p-3.5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle">{label}</div>
      <div className="mt-1.5 break-words text-sm font-medium text-text">{value || '—'}</div>
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[1.5rem] border border-dashed border-line/75 bg-white/28 p-5 text-sm leading-6 text-subtle">
      <div className="flex items-center gap-2 font-medium text-text">
        <span className="h-1.5 w-1.5 rounded-full bg-[#c89445]" />
        <span className="max-w-2xl">{text}</span>
      </div>
    </div>
  )
}

type NotificationGroupId = 'pre_hiring' | 'onboarding' | 'delivery_issues' | 'completions'

type NotificationAlert = {
  id: string
  group: NotificationGroupId
  title: string
  detail: string
  actionLabel: string
  count: number
  severity?: string
}

const NOTIFICATION_GROUPS: Array<{ id: NotificationGroupId; label: string; description: string }> = [
  { id: 'pre_hiring', label: 'Hiring alerts', description: 'Important candidate or assistant actions that need HR attention now.' },
  { id: 'onboarding', label: 'Onboarding exceptions', description: 'Urgent employee issues only when that module is active.' },
  { id: 'delivery_issues', label: 'Delivery alerts', description: 'Assessment or interview messages that did not reach the candidate.' },
  { id: 'completions', label: 'Completions', description: 'Candidate steps completed today that may need quick HR review.' },
]

function groupedNotificationAlerts(actionItems: NotificationActionItem[], issues: NotificationRow[], enabledModules?: string[]): NotificationAlert[] {
  const alerts = actionItems
    .map(notificationAlertFromActionItem)
    .filter((item): item is NotificationAlert => item !== null && notificationGroupEnabled(item.group, enabledModules))
  void issues
  const severityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 }
  return alerts.sort((a, b) => {
    const groupOrder = NOTIFICATION_GROUPS.findIndex((group) => group.id === a.group) - NOTIFICATION_GROUPS.findIndex((group) => group.id === b.group)
    if (groupOrder) return groupOrder
    const severity = (severityOrder[String(a.severity || '')] ?? 9) - (severityOrder[String(b.severity || '')] ?? 9)
    if (severity) return severity
    return b.count - a.count
  })
}

function notificationAlertFromActionItem(item: NotificationActionItem): NotificationAlert | null {
  const count = Number(item.count || 0)
  if (count <= 0) return null
  const group = notificationItemGroup(item)
  const kind = String(item.kind || '')
  const label = String(item.metadata?.label || item.metadata?.document_type || 'required document')
  if (kind === 'missing_onboarding_item') {
    return {
      id: `${kind}:${label}`,
      group: 'onboarding',
      title: 'Missing document',
      detail: `${count} employee${count === 1 ? '' : 's'} still need ${label}.`,
      actionLabel: 'Follow up with employee',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'screening_completed_today') {
    return {
      id: kind,
      group: 'completions',
      title: 'Review completed screening',
      detail: `${count} candidate${count === 1 ? '' : 's'} finished a screening step today.`,
      actionLabel: 'Review completed screening',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'assessment_delivery_failed') {
    return {
      id: kind,
      group: 'delivery_issues',
      title: 'Assessment delivery failed',
      detail: `${count} assessment message${count === 1 ? '' : 's'} did not reach the candidate.`,
      actionLabel: 'Open Assessments queue',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'interview_invite_failed') {
    return {
      id: kind,
      group: 'delivery_issues',
      title: 'Interview invite failed',
      detail: `${count} interview invite${count === 1 ? '' : 's'} did not reach the candidate.`,
      actionLabel: 'Open Interviews queue',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'ai_action_needs_approval') {
    return {
      id: kind,
      group: 'pre_hiring',
      title: 'AI action needs approval',
      detail: `${count} AI action${count === 1 ? '' : 's'} are waiting for HR approval.`,
      actionLabel: 'Review in Wathefni Assistant',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'closed_conversations') {
    return {
      id: kind,
      group: 'delivery_issues',
      title: 'Send approved message',
      detail: `${count} person${count === 1 ? '' : 's'} need an approved message before contact can continue.`,
      actionLabel: 'Send approved message',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'stale_conversations' || kind === 'failed_onboarding_reminders') {
    return {
      id: kind,
      group: kind === 'failed_onboarding_reminders' ? 'onboarding' : 'delivery_issues',
      title: kind === 'failed_onboarding_reminders' ? 'Follow up with employee' : 'Needs HR attention',
      detail: kind === 'failed_onboarding_reminders'
        ? `${count} employee${count === 1 ? '' : 's'} need HR follow-up for onboarding.`
        : `${count} person${count === 1 ? '' : 's'} need HR to choose the best contact method.`,
      actionLabel: kind === 'failed_onboarding_reminders' ? 'Follow up with employee' : 'Needs HR attention',
      count,
      severity: item.severity,
    }
  }
  if (kind.startsWith('compliance_')) {
    return {
      id: kind,
      group: 'onboarding',
      title: 'Missing document',
      detail: `${count} employee document${count === 1 ? '' : 's'} need HR review.`,
      actionLabel: 'Follow up with employee',
      count,
      severity: item.severity,
    }
  }
  return {
    id: `${kind}:${item.title}`,
    group,
    title: hrNotificationText(item.title || 'Needs HR attention'),
    detail: hrNotificationText(item.action || 'Needs HR attention'),
    actionLabel: hrNotificationActionLabel(group),
    count,
    severity: item.severity,
  }
}

function notificationItemGroup(item: NotificationActionItem): NotificationGroupId {
  const configured = String(item.metadata?.module_group || '')
  if (configured === 'pre_hiring' || configured === 'onboarding' || configured === 'delivery_issues' || configured === 'completions') return configured
  const kind = String(item.kind || '')
  if (kind.includes('screening_completed') || kind.includes('completed')) return 'completions'
  if (kind.includes('onboarding') || kind.includes('compliance') || item.page === 'onboarding') return 'onboarding'
  if (kind.includes('conversation') || kind.includes('delivery') || kind.includes('failed')) return 'delivery_issues'
  return 'pre_hiring'
}

function notificationGroupCount(alerts: NotificationAlert[], groupId: NotificationGroupId) {
  return alerts.filter((item) => item.group === groupId).length
}

function notificationGroupEnabled(groupId: NotificationGroupId, enabledModules?: string[]) {
  if (!enabledModules?.length) return true
  if (groupId === 'onboarding') return enabledModules.includes('onboarding')
  if (groupId === 'pre_hiring' || groupId === 'completions') return enabledModules.includes('pre_hiring')
  return true
}

function notificationSeverityTone(severity: string | undefined): 'success' | 'warning' | 'danger' | 'muted' {
  if (severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  if (severity === 'low') return 'success'
  return 'muted'
}

function hrNotificationActionLabel(group: NotificationGroupId) {
  if (group === 'pre_hiring') return 'Open Candidates queue'
  if (group === 'onboarding') return 'Open Onboarding queue'
  if (group === 'completions') return 'Review completed work'
  return 'Needs HR attention'
}

function hrNotificationText(value: string) {
  return value
    .replace(/invalid_grant/gi, 'Email needs reconnecting')
    .replace(/no_usable_conversation_id/gi, 'WhatsApp conversation is not active')
    .replace(new RegExp(['stale', 'conversations?'].join(' '), 'gi'), 'people needing attention')
    .replace(new RegExp(['fallback', 'channel'].join(' '), 'gi'), 'best contact method')
    .replace(new RegExp(['reminders?', 'failed'].join(' '), 'gi'), 'people need HR follow-up')
    .replace(new RegExp(['conversation', 'closed'].join(' '), 'gi'), 'approved message needed')
    .replace(new RegExp(['delivery', 'exception'].join(' '), 'gi'), 'needs HR attention')
}

function notificationIssueRows(notifications: NotificationRow[]) {
  // "delivered" here is a Postmark delivery-confirmation event (the email
  // reached the candidate) — a success, not something HR needs to follow up
  // on. Treat it the same as sent/completed/recovered.
  return notifications.filter((item) => !['sent', 'completed', 'recovered', 'delivered'].includes(normalizedDeliveryStatus(item)))
}

function moduleScopedNotificationRows(notifications: NotificationRow[], enabledModules?: string[]) {
  const rows = notificationIssueRows(notifications)
  if (!enabledModules?.length) return rows
  return enabledModules.includes('pre_hiring') ? rows : []
}

function jobNotificationLabel(item: { status?: string; last_error?: string; created_at?: string }) {
  const normalized = String(item.status || '').toLowerCase()
  const lastError = String(item.last_error || '').toLowerCase()
  if (normalized === 'sent') return `Candidate contacted ${formatDateTime(item.created_at)}`
  if (lastError) return safeDeliveryErrorLabel(lastError)
  if (normalized === 'failed') return 'Candidate was not reached. Try another contact method.'
  return formatDateTime(item.created_at)
}

function normalizedDeliveryStatus(item: NotificationRow) {
  const raw = String(item.dashboard_status || item.status || 'unknown').toLowerCase()
  if (raw === 'blocked_closed_conversation') return 'blocked_by_closed_conversation'
  if (raw === 'stale_conversation') return 'stale'
  return raw || 'unknown'
}

function candidateName(application: ApplicationSummary) {
  return application.candidate?.name || application.phone || 'Unknown candidate'
}

const STAGE_LABELS: Record<string, string> = {
  awaiting_cv: 'Waiting for CV',
  cv_processing: 'Processing CV',
  cv_received: 'Processing CV',
  screening: 'Processing CV',
  ready_for_review: 'Ready for review',
  screening_complete: 'Ready for review',
  review_pending: 'Ready for review',
  shortlisted: 'Shortlisted',
  interview: 'Interview',
  scheduled: 'Scheduled',
  completed: 'Completed',
  no_show: 'No-show',
  rescheduled: 'Rescheduled',
  cancelled: 'Cancelled',
  notes_pending: 'Notes pending',
  feedback_complete: 'Feedback complete',
  hired: 'Hired',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  in_progress: 'In progress',
  in_review: 'In review',
  needs_review: 'Needs review',
  pending_review: 'Pending review',
  not_started: 'Not started',
  phone_screen: 'Phone screen',
  // Offer labels kept as read aliases only — formal offer lifecycle is out of scope.
  offered: 'Shortlisted',
  offer_sent: 'Shortlisted',
  link_sent: 'Sent',
  opened: 'Opened',
  consented: 'Opened',
  submitted: 'Submitted',
  processing: 'Processing',
  transcription_failed: 'Needs retry',
  summary_pending: 'Preparing summary',
  synthetic_until_client_benchmark: 'Collecting company results',
  internal_synthetic_until_client_benchmark: 'Collecting company results',
  // Video review readiness — namespaced away from application stage.
  video_ready_for_review: 'Ready for review',
}

function stageLabel(value: string | null | undefined) {
  const normalized = String(value || 'unknown').toLowerCase()
  if (STAGE_LABELS[normalized]) return STAGE_LABELS[normalized]
  // Humanize any remaining snake_case key into sentence case so raw status keys
  // (e.g. "phone_screen") never reach users as-is.
  const spaced = normalized.replaceAll('_', ' ').trim()
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : spaced
}

function friendlyDashboardError(error: unknown, fallback: string, locale: RecruitingLocale = 'en') {
  const staleMessage = locale === 'ar'
    ? 'تغيّر هذا الطلب. حدّث الصفحة وراجع المرحلة الحالية قبل المحاولة مجدداً.'
    : 'This application changed. Refresh it and review the current stage before trying again.'
  const permissionMessage = locale === 'ar'
    ? 'ليست لديك صلاحية لتنفيذ هذا الإجراء.'
    : 'You do not have permission to do this action.'
  if (error instanceof DashboardApiError) {
    if (['stale_state', 'stale_decision', 'stage_mismatch', 'application_state_changed'].includes(error.code)) {
      return staleMessage
    }
    if (['permission_denied', 'action_forbidden', 'forbidden_transition'].includes(error.code)) {
      return permissionMessage
    }
    if (error.code === 'account_inactive') {
      return 'Your account is not active.'
    }
    if (error.code === 'module_disabled') {
      return 'This feature is not enabled for this company.'
    }
    const accessIssue = accessIssueFromError(error)
    if (accessIssue) return accessIssue.description
    if (/invalid_grant|gmail_auth|token has been expired/i.test(error.message)) return 'Email needs reconnecting.'
    if (/no_usable_conversation_id|conversation_closed|conversation_inactive/i.test(error.message)) return 'WhatsApp conversation is not active.'
    if (error.message && !/backend|traceback|exception|error"|detail|module_disabled|auth_failed|not_found|permission_denied/i.test(error.message)) return error.message
  }
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  if (!message) return fallback
  if (/stale_state|stale_decision|stage_mismatch|state changed/i.test(message)) {
    return staleMessage
  }
  if (/action_forbidden|permission_denied|forbidden_transition/i.test(message)) {
    return permissionMessage
  }
  if (/invalid_grant|gmail_auth|token has been expired/i.test(message)) return 'Email needs reconnecting.'
  if (/no_usable_conversation_id|conversation_closed|conversation_inactive/i.test(message)) return 'WhatsApp conversation is not active.'
  if (/conversation_|no_usable_|backend|traceback|exception|error"|detail|module_disabled|auth_failed|not_found/i.test(message)) {
    return fallback
  }
  return message
}

function isReadyForReview(application: ApplicationSummary) {
  const status = String(application.status || '').toLowerCase()
  return ['ready_for_review', 'screening_complete', 'review_pending'].includes(status)
}

function assessmentStatusCount(statusCounts: Array<{ status: string; count: number }>, status: string) {
  return statusCounts.find((item) => item.status === status)?.count || 0
}

function interviewStatusCount(statusCounts: Array<{ status: string; count: number }>, status: string) {
  return statusCounts.find((item) => item.status === status)?.count || 0
}

function interviewFeedbackCount(feedbackCounts: Array<{ feedback_status: string; count: number }>, status: string) {
  return feedbackCounts.find((item) => item.feedback_status === status)?.count || 0
}

function assessmentAverageLabel(value: number | null | undefined) {
  if (value == null || Number.isNaN(Number(value))) return 'No completed attempts yet'
  return `${value}%`
}

function setupCalibrationLabel(value: string | null | undefined) {
  const normalized = String(value || '').toLowerCase()
  if (!normalized || normalized.includes('synthetic') || normalized.includes('benchmark')) return 'Collecting company results'
  if (normalized.includes('empirical') || normalized.includes('ready')) return 'Ready'
  return stageLabel(normalized)
}

function assessmentQueue(applications: ApplicationSummary[]) {
  return applications.filter((application) => {
    const status = String(application.assessment?.status || '').toLowerCase()
    const stage = String(application.status || '').toLowerCase()
    return (!status || status === 'pending') && application.cv?.received && ['screening_complete', 'review_pending', 'ready_for_review', 'shortlisted'].includes(stage)
  })
}

function assessmentModuleEnabled(state: DashboardModuleState, summary?: SummaryResponse | null) {
  if (Array.isArray(state?.enabled_modules)) return state.enabled_modules.includes('assessments')
  if (typeof summary?.features?.assessments_enabled === 'boolean') return summary.features.assessments_enabled
  return false
}

function disabledAssessmentsResponse(companyCode: string): AssessmentsResponse {
  return {
    company_code: companyCode,
    ok: false,
    enabled: false,
    module_disabled: true,
    required_module: 'assessments',
    total: 0,
    status_counts: [],
    average_percent: null,
    attempts: [],
  }
}

function isModuleDisabledError(error: unknown, module: string) {
  if (!(error instanceof Error)) return false
  return error.message.includes('module_disabled') && error.message.includes(module)
}

function assessmentBandTone(band: string | null | undefined): 'default' | 'success' | 'warning' | 'danger' | 'muted' {
  const normalized = String(band || '').toLowerCase()
  if (['strong', 'qualified'].includes(normalized)) return 'success'
  if (normalized === 'needs_review') return 'warning'
  if (normalized === 'low') return 'danger'
  return 'muted'
}

function basicScreeningLabel(application: ApplicationSummary) {
  if (application.screening_status === 'complete') return 'Basic screening complete'
  if (application.screening_status === 'in_progress') return 'Basic screening in progress'
  return application.cv?.received ? 'CV received' : 'CV missing'
}

function assessmentLabel(application: ApplicationSummary) {
  const assessment = application.assessment
  if (assessment?.status === 'completed') {
    return assessment.percent == null ? 'Assessment complete' : `Assessment complete (${assessment.percent}%)`
  }
  if (assessment?.status) return `Assessment ${stageLabel(assessment.status)}`
  if (application.screening_status === 'complete') return 'Screening complete'
  if (application.screening_status === 'in_progress') return 'Screening in progress'
  return 'Not started'
}

function interviewLabel(application: ApplicationSummary) {
  const interview = application.interview
  if (!interview?.status) return 'Not scheduled'
  if (interview.interview_type === 'async_video') return asyncVideoDisplayStatus(interview).label
  const status = stageLabel(interview.status)
  const time = interview.scheduled_start ? formatDateTime(interview.scheduled_start) : ''
  const feedback = interview.feedback_status ? ` / ${stageLabel(interview.feedback_status)}` : ''
  return [status, time].filter(Boolean).join(' / ') + feedback
}

function interviewInviteLine(interview: InterviewTruth) {
  if (interview.interview_type === 'async_video') {
    return asyncVideoDisplayStatus(interview).description
  }
  const invite = interview.candidate_notified || interview.candidate_invited || interview.calendar_invite_sent
    ? `Invite sent${interview.notification_channel ? ` by ${notificationChannelLabel(interview.notification_channel).toLowerCase()}` : ''}`
    : 'Invite not confirmed yet'
  const meet = interview.meet_link ? 'Meet link available' : 'Meet link not recorded'
  return `${invite} · ${meet}`
}

function interviewStateLine(interview: InterviewTruth) {
  if (interview.interview_type === 'async_video') {
    const status = asyncVideoDisplayStatus(interview)
    return `${status.label} · ${interview.feedback_status === 'feedback_complete' ? 'Reviewed' : 'Review pending'}`
  }
  const status = stageLabel(interview.status)
  const feedback = interview.feedback_status === 'feedback_complete' ? 'Feedback complete' : 'Feedback pending'
  return `${status} · ${feedback}`
}

function summaryValue(summary: CandidateInterview['ai_summary'] | undefined, keys: string[]) {
  const data = summary as Record<string, unknown> | undefined
  for (const key of keys) {
    const value = data?.[key]
    if (typeof value === 'string' && value.trim()) return value
    if (typeof value === 'number') return String(value)
  }
  return ''
}

function normalizeOverallImpression(value: string) {
  const normalized = value.trim()
  if (!normalized) return ''
  if (/^evidence ready$/i.test(normalized) || /^review needed$/i.test(normalized)) return 'Needs more evidence'
  return normalized
}

function normalizeEvidenceConfidence(value: string) {
  const normalized = value.trim()
  if (!normalized) return ''
  if (/^decision support$/i.test(normalized) || /^unknown$/i.test(normalized)) return 'Limited'
  return normalized
}

function asyncVideoDisplayStatus(interview: InterviewTruth): { label: string; description: string; tone: 'default' | 'success' | 'warning' | 'danger' | 'muted' } {
  const review = interview.video_review_status
  const state = String(review?.state || '').toLowerCase()
  const asyncStatus = String(interview.async_status || '').toLowerCase()
  const hasResponse = Boolean(review?.response_count || ('video_answers' in interview && interview.video_answers?.length))
  const summaryReady = Boolean(review?.summary_ready || interview.ai_summary?.summary || interview.ai_summary?.overall_summary)
  if (String(interview.status || '').toLowerCase() === 'cancelled') {
    return { label: 'Cancelled', description: 'This video interview is no longer active.', tone: 'muted' }
  }
  if (interview.feedback_status === 'feedback_complete') {
    return { label: 'Reviewed', description: 'HR review notes are saved for this video interview.', tone: 'success' }
  }
  if (state === 'ready_for_review' || summaryReady) {
    return { label: 'Ready for review', description: 'The video answer and AI summary are ready for HR review.', tone: 'success' }
  }
  if (state === 'processing' || state === 'summary_pending' || state === 'transcription_failed' || Boolean(review?.pending_count || review?.failed_count)) {
    return { label: 'Processing', description: 'The candidate submitted the video. The written summary is being prepared.', tone: review?.failed_count ? 'danger' : 'warning' }
  }
  if (state === 'submitted' || hasResponse || asyncStatus === 'completed' || String(interview.status || '').toLowerCase() === 'completed') {
    return { label: 'Submitted', description: 'The candidate submitted the video response.', tone: 'warning' }
  }
  if (state === 'started' || ['opened', 'consented', 'in_progress'].includes(asyncStatus)) {
    return { label: 'Opened', description: 'The candidate opened the link and started the video interview flow.', tone: 'default' }
  }
  return { label: 'Sent', description: 'The video interview link has been sent. Waiting for the candidate response.', tone: 'default' }
}

function asyncVideoActivityLabel(interview: InterviewTruth) {
  const answers = 'video_answers' in interview ? interview.video_answers || [] : []
  const submittedAt = answers[0]?.submitted_at || interview.completed_at
  if (submittedAt) return formatDateTime(submittedAt)
  if (interview.consent_accepted_at) return `Opened ${formatDateTime(interview.consent_accepted_at)}`
  if (interview.invite_sent_at) return `Sent ${formatDateTime(interview.invite_sent_at)}`
  return asyncVideoDisplayStatus(interview).label
}

function videoInterviewProcessingLine(interview: CandidateInterview) {
  if (interview.interview_type === 'async_video') return asyncVideoDisplayStatus(interview).description
  const answers = interview.video_answers || []
  if (!answers.length) return 'Waiting for the candidate to submit a video answer.'
  const failed = answers.filter((answer) => answer.transcript_status === 'failed').length
  if (failed) return `${failed} answer${failed === 1 ? '' : 's'} need summary retry. Original video remains available.`
  const pending = answers.filter((answer) => answer.transcript_status !== 'completed').length
  if (pending) return 'Video response is submitted. The written summary is being prepared.'
  if (interview.ai_summary?.summary || interview.ai_summary?.overall_summary) return 'Video answer and Wathefni analysis are ready for HR review.'
  return 'Video answer is ready. AI summary is being prepared.'
}

function booleanTruthLabel(value: boolean | null | undefined) {
  if (value === true) return 'Yes'
  if (value === false) return 'No'
  return 'Not recorded'
}

function calendarEventLabel(interview: InterviewTruth) {
  if (interview.calendar_event_id) return 'Calendar event created'
  return 'Not recorded'
}

function candidateNotifiedLabel(interview: InterviewTruth) {
  if (interview.candidate_notified) return 'Yes'
  if (interview.candidate_invited) return 'Invited by calendar'
  if (interview.calendar_invite_sent) return 'Calendar invite sent'
  return booleanTruthLabel(interview.candidate_notified)
}

function notificationChannelLabel(channel: string | null | undefined) {
  const normalized = String(channel || '').toLowerCase()
  if (!normalized) return 'Not recorded'
  if (normalized === 'whatsapp') return 'WhatsApp'
  if (normalized === 'email') return 'Email'
  if (normalized === 'both' || normalized === 'whatsapp_email') return 'WhatsApp + email'
  if (normalized === 'calendar' || normalized === 'calendar_email') return 'Google Calendar email'
  return stageLabel(normalized)
}

function inviteTruthLabel(interview: InterviewTruth) {
  if (interview.candidate_notified) return `Sent${interview.notification_channel ? ` via ${notificationChannelLabel(interview.notification_channel)}` : ''}`
  if (interview.calendar_invite_sent) return 'Calendar invite sent'
  if (interview.candidate_invited) return 'Candidate invited'
  return 'Not recorded'
}

function notesStateLabel(interview: InterviewTruth) {
  if ('notes' in interview && interview.notes?.trim()) return 'HR notes saved'
  if ('transcript' in interview && interview.transcript?.trim()) return 'Transcript saved'
  return 'Notes pending'
}

function candidateSummary(application: ApplicationSummary) {
  const raw = application.raw_json || {}
  const interviewSummary = application.interview ? interviewSummaryText(application.interview) : ''
  if (interviewSummary) return interviewSummary
  const summary = raw.ai_summary || raw.summary || raw.notes
  if (typeof summary === 'string' && summary.trim()) return summary
  return `${candidateName(application)} is currently at ${stageLabel(application.status)} for ${
    application.position?.title || application.position?.code || 'this role'
  }. Use Ranking for scored comparison against other candidates.`
}

function recommendedCandidateAction(application: ApplicationSummary) {
  const status = String(application.status || '').toLowerCase()
  if (!application.cv?.received) return 'Ask the candidate to send their CV before HR review.'
  if (application.screening_status !== 'complete') return 'Finish missing screening answers before comparing this candidate.'
  if (!application.assessment?.status && ['screening_complete', 'review_pending', 'ready_for_review', 'shortlisted'].includes(status)) {
    return 'Send the assessment or review whether assessment evidence is required for this role.'
  }
  if (!application.interview?.status && ['shortlisted', 'review_pending', 'ready_for_review', 'screening_complete'].includes(status)) {
    return 'Review the profile, then schedule an interview if the fit still looks strong.'
  }
  if (application.interview?.feedback_status !== 'feedback_complete' && application.interview?.status === 'completed') {
    return 'Save interview feedback and prepare the Wathefni analysis.'
  }
  if (status === 'hired') return 'Candidate is already hired. Continue onboarding/post-hire follow-up.'
  return 'Review the candidate’s details and choose the next step.'
}

function interviewSummaryText(interview: InterviewTruth) {
  if ('summary' in interview && typeof interview.summary === 'string' && interview.summary.trim()) return interview.summary
  if (interview.ai_summary?.summary?.trim()) return interview.ai_summary.summary
  return ''
}

function normalizedJobStatus(job: PositionSummary) {
  const raw = String(job.status || '').toLowerCase()
  if (['open', 'active', 'published'].includes(raw)) return 'open'
  if (['closed', 'paused', 'inactive', 'draft'].includes(raw)) return raw
  return Number(job.active_count || 0) > 0 ? 'open' : 'closed'
}

function formatRequirements(requirements: unknown) {
  if (Array.isArray(requirements) && requirements.length) {
    return requirements.map((item) => `- ${String(item)}`).join('\n')
  }
  if (requirements && typeof requirements === 'object') {
    return Object.entries(requirements as Record<string, unknown>)
      .map(([key, value]) => `${stageLabel(key)}: ${Array.isArray(value) ? value.join(', ') : String(value)}`)
      .join('\n')
  }
  if (typeof requirements === 'string' && requirements.trim()) return requirements
  return 'No structured requirements are stored for this opening yet.'
}

function downloadQr(dataUrl: string, job: PositionSummary) {
  if (!dataUrl) return
  const anchor = document.createElement('a')
  anchor.href = dataUrl
  anchor.download = `${job.position_code || 'job'}-qr.png`
  anchor.click()
}

function rankingCandidateApplication(candidate: RankingCandidate): ApplicationSummary {
  const ranking = {
    score: candidate.score,
    score_breakdown: candidate.score_breakdown,
    confidence: candidate.confidence,
    evidence: candidate.evidence,
    reasons: candidate.reasons,
    role_profile: candidate.role_profile,
    gpt_evaluation: candidate.gpt_evaluation,
    evidence_digest: candidate.evidence_digest,
    evaluation_audit: candidate.evaluation_audit,
  }
  if (candidate.application) {
    return { ...candidate.application, ranking }
  }
  return {
    app_key: candidate.app_key,
    company_code: '',
    phone: candidate.phone,
    candidate: { name: candidate.name },
    position: {
      code: candidate.position_code,
      title: candidate.position_title || candidate.position_code,
    },
    status: candidate.status,
    screening_status: candidate.screening_status,
    ranking,
  }
}

function scoreBreakdownItems(candidate: RankingCandidate) {
  const breakdown = candidate.score_breakdown || {}
  return [
    { label: 'Role match', value: Number(breakdown.role_fit || 0), max: 20 },
    { label: 'Skill match', value: Number(breakdown.skill_match || 0), max: 20 },
    { label: 'Experience', value: Number(breakdown.experience || 0), max: 15 },
    { label: 'CV evidence', value: Number(breakdown.cv_evidence ?? breakdown.accomplishments ?? 0), max: 10 },
    { label: 'Screening', value: Number(breakdown.screening || 0), max: 10 },
    { label: 'Assessment', value: Number(breakdown.assessment || 0), max: 10 },
    { label: 'Interview', value: Number(breakdown.interview || 0), max: 8 },
    { label: 'Readiness', value: Number(breakdown.readiness || 0), max: 5 },
    { label: 'Confidence', value: Number(breakdown.confidence || 0), max: 2 },
  ]
}

function fallbackStatusCounts() {
  return [
    { status: 'screening', count: 0 },
    { status: 'review_pending', count: 0 },
    { status: 'shortlisted', count: 0 },
    { status: 'hired', count: 0 },
  ]
}

export default App
