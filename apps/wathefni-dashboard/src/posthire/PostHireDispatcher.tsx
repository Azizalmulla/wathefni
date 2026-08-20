import { lazy, Suspense, type ReactNode } from 'react'

import { PageSkeleton } from '@/pages/PageSkeleton'
import { markPageChunkLoaded, pageChunkLoaded, rememberChunkLoader } from '@/lib/hrWebNavPrefetch'
import type { PostHireModulePage } from '@/posthire/PostHire'
import type { AccessIssue } from '@/lib/access'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type PostHireDispatcherProps = {
  page: PostHireModulePage
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
  onOpenNotifications?: () => void
  onNavigate?: (page: string, opts?: { employee?: string }) => void
}

function loadAndMark<T>(page: string, loader: () => Promise<{ default: T }>) {
  return rememberChunkLoader(page, () =>
    loader().then((mod) => {
      markPageChunkLoaded(page)
      return mod
    }),
  ) as Promise<{ default: T }>
}

const LazyEmployees = lazy(() =>
  loadAndMark('employees', () => import('@/posthire/PostHire').then((module) => ({ default: module.EmployeesPage }))),
)
const LazyOnboarding = lazy(() =>
  loadAndMark('onboarding', () => import('@/posthire/PostHire').then((module) => ({ default: module.OnboardingPage }))),
)
const LazyAttendance = lazy(() =>
  loadAndMark('attendance', () => import('@/posthire/PostHire').then((module) => ({ default: module.AttendancePage }))),
)
const LazyPayroll = lazy(() =>
  loadAndMark('payroll', () => import('@/posthire/PostHire').then((module) => ({ default: module.PayrollPage }))),
)
const LazyInbox = lazy(() =>
  loadAndMark('inbox', () => import('@/posthire/PostHire').then((module) => ({ default: module.ActionInboxPage }))),
)
const LazyAnalyticsFallback = lazy(() =>
  loadAndMark('analytics-core', () => import('@/posthire/PostHire').then((module) => ({ default: module.AnalyticsPage }))),
)
const LazyCompliance = lazy(() =>
  loadAndMark('compliance', () => import('@/posthire/PostHire').then((module) => ({ default: module.CompliancePage }))),
)
const LazyWorkforce = lazy(() =>
  loadAndMark('workforce', () =>
    import('@/posthire/employees360/WorkforcePage').then((module) => ({ default: module.WorkforcePage })),
  ),
)
const LazyPreboarding = lazy(() =>
  loadAndMark('preboarding', () =>
    import('@/posthire/PreboardingWorkspace').then((module) => ({ default: module.PreboardingWorkspace })),
  ),
)
const LazyProbation = lazy(() =>
  loadAndMark('probation', () =>
    import('@/posthire/ProbationWorkspace').then((module) => ({ default: module.ProbationWorkspace })),
  ),
)
const LazyLeave = lazy(() =>
  loadAndMark('leave', () => import('@/posthire/LeaveWorkspace').then((module) => ({ default: module.LeaveWorkspace }))),
)
const LazyPerformance = lazy(() =>
  loadAndMark('performance', () =>
    import('@/posthire/PerformanceWorkspace').then((module) => ({ default: module.PerformanceWorkspace })),
  ),
)
const LazyTalent = lazy(() =>
  loadAndMark('talent', () => import('@/posthire/TalentWorkspace').then((module) => ({ default: module.TalentWorkspace }))),
)
const LazyLearning = lazy(() =>
  loadAndMark('learning', () =>
    import('@/posthire/LearningWorkspace').then((module) => ({ default: module.LearningWorkspace })),
  ),
)
const LazyBenefits = lazy(() =>
  loadAndMark('benefits', () =>
    import('@/posthire/BenefitsWorkspace').then((module) => ({ default: module.BenefitsWorkspace })),
  ),
)
const LazyEmployeeRelations = lazy(() =>
  loadAndMark('employee-relations', () =>
    import('@/posthire/EmployeeRelationsWorkspace').then((module) => ({ default: module.EmployeeRelationsWorkspace })),
  ),
)
const LazyEngagement = lazy(() =>
  loadAndMark('engagement', () =>
    import('@/posthire/EngagementWorkspace').then((module) => ({ default: module.EngagementWorkspace })),
  ),
)
const LazyCompensation = lazy(() =>
  loadAndMark('compensation-planning', () =>
    import('@/posthire/CompensationPlanningWorkspace').then((module) => ({
      default: module.CompensationPlanningWorkspace,
    })),
  ),
)
const LazyWorkforcePlanning = lazy(() =>
  loadAndMark('workforce-planning', () =>
    import('@/posthire/WorkforcePlanningWorkspace').then((module) => ({ default: module.WorkforcePlanningWorkspace })),
  ),
)
const LazyJobArchitecture = lazy(() =>
  loadAndMark('job-architecture', () =>
    import('@/posthire/JobArchitectureWorkspace').then((module) => ({ default: module.JobArchitectureWorkspace })),
  ),
)
const LazyShifts = lazy(() =>
  loadAndMark('shifts', () => import('@/posthire/ShiftsWorkspace').then((module) => ({ default: module.ShiftsWorkspace }))),
)
const LazyIntelligence = lazy(() =>
  loadAndMark('analytics', () =>
    import('@/posthire/intelligence/IntelligenceWorkspace').then((module) => ({ default: module.IntelligenceWorkspace })),
  ),
)

const POSTHIRE_CHUNK_LOADERS: Record<PostHireModulePage, () => Promise<unknown>> = {
  employees: () => import('@/posthire/PostHire'),
  workforce: () => import('@/posthire/employees360/WorkforcePage'),
  inbox: () => import('@/posthire/PostHire'),
  preboarding: () => import('@/posthire/PreboardingWorkspace'),
  onboarding: () => import('@/posthire/PostHire'),
  probation: () => import('@/posthire/ProbationWorkspace'),
  attendance: () => import('@/posthire/PostHire'),
  leave: () => import('@/posthire/LeaveWorkspace'),
  performance: () => import('@/posthire/PerformanceWorkspace'),
  talent: () => import('@/posthire/TalentWorkspace'),
  learning: () => import('@/posthire/LearningWorkspace'),
  benefits: () => import('@/posthire/BenefitsWorkspace'),
  'employee-relations': () => import('@/posthire/EmployeeRelationsWorkspace'),
  engagement: () => import('@/posthire/EngagementWorkspace'),
  'compensation-planning': () => import('@/posthire/CompensationPlanningWorkspace'),
  'workforce-planning': () => import('@/posthire/WorkforcePlanningWorkspace'),
  'job-architecture': () => import('@/posthire/JobArchitectureWorkspace'),
  shifts: () => import('@/posthire/ShiftsWorkspace'),
  payroll: () => import('@/posthire/PostHire'),
  analytics: () => import('@/posthire/intelligence/IntelligenceWorkspace'),
  compliance: () => import('@/posthire/PostHire'),
}

export function prefetchPostHirePage(page: string) {
  const loader = POSTHIRE_CHUNK_LOADERS[page as PostHireModulePage]
  if (!loader) return
  void loader().then(() => markPageChunkLoaded(page))
}

function PaintFallback({ page }: { page: string }) {
  if (pageChunkLoaded(page)) return null
  return <PageSkeleton />
}

function wrap(page: string, node: ReactNode) {
  return <Suspense fallback={<PaintFallback page={page} />}>{node}</Suspense>
}

export function PostHirePage({
  page,
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
  onOpenNotifications,
  onNavigate,
}: PostHireDispatcherProps) {
  // Alerts & Delivery owns communication failures — no duplicate DeliveryStatusStrip on specialist modules.
  void onOpenNotifications
  const common = { access, permissions, role, onNotice, onAccessIssue }
  switch (page) {
    case 'employees':
      return wrap(page, <LazyEmployees {...common} onNavigate={onNavigate} />)
    case 'workforce':
      return wrap(page, <LazyWorkforce {...common} onNavigate={onNavigate} />)
    case 'inbox':
      return wrap(page, <LazyInbox access={access} onAccessIssue={onAccessIssue} onNavigate={onNavigate} />)
    case 'preboarding':
      return wrap(page, <LazyPreboarding {...common} />)
    case 'probation':
      return wrap(page, <LazyProbation {...common} />)
    case 'onboarding':
      return wrap(page, <LazyOnboarding {...common} onNavigate={onNavigate} />)
    case 'attendance':
      return wrap(page, <LazyAttendance {...common} />)
    case 'leave':
      return wrap(page, <LazyLeave {...common} />)
    case 'performance':
      return wrap(page, <LazyPerformance {...common} />)
    case 'talent':
      return wrap(page, <LazyTalent {...common} />)
    case 'learning':
      return wrap(page, <LazyLearning {...common} />)
    case 'benefits':
      return wrap(page, <LazyBenefits {...common} />)
    case 'employee-relations':
      return wrap(page, <LazyEmployeeRelations {...common} />)
    case 'engagement':
      return wrap(page, <LazyEngagement {...common} />)
    case 'compensation-planning':
      return wrap(page, <LazyCompensation {...common} />)
    case 'workforce-planning':
      return wrap(page, <LazyWorkforcePlanning {...common} />)
    case 'job-architecture':
      return wrap(page, <LazyJobArchitecture {...common} />)
    case 'shifts':
      return wrap(page, <LazyShifts {...common} />)
    case 'payroll':
      return wrap(page, <LazyPayroll {...common} />)
    case 'analytics':
      return wrap(
        page,
        <LazyIntelligence
          {...common}
          onNavigate={onNavigate}
          fallback={
            <Suspense fallback={null}>
              <LazyAnalyticsFallback access={access} onAccessIssue={onAccessIssue} onNavigate={onNavigate} />
            </Suspense>
          }
        />,
      )
    case 'compliance':
      return wrap(page, <LazyCompliance {...common} onNavigate={onNavigate} />)
    default:
      return null
  }
}
