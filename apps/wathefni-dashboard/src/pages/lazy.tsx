import { lazy } from 'react'

export const LazyCandidatesPage = lazy(() => import('./CandidatesPage').then((module) => ({ default: module.CandidatesPage })))
export const LazyJobsPage = lazy(() => import('./JobsPage').then((module) => ({ default: module.JobsPage })))
export const LazyRequisitionsWorkspace = lazy(() =>
  import('@/prehire/RequisitionsWorkspace').then((module) => ({ default: module.RequisitionsWorkspace })),
)
export const LazyInterviewsPage = lazy(() => import('./InterviewsPage').then((module) => ({ default: module.InterviewsPage })))
export const LazyAssessmentsPage = lazy(() => import('./AssessmentsPage').then((module) => ({ default: module.AssessmentsPage })))
export const LazyRankingPage = lazy(() => import('./RankingPage').then((module) => ({ default: module.RankingPage })))
export const LazyReportsPage = lazy(() => import('./ReportsPage').then((module) => ({ default: module.ReportsPage })))
export const LazySettingsPage = lazy(() => import('./SettingsPage').then((module) => ({ default: module.SettingsPage })))
export const LazyAdminAIPage = lazy(() => import('./AdminAIPage').then((module) => ({ default: module.AdminAIPage })))
export const LazyNotificationsPage = lazy(() => import('./NotificationsPage').then((module) => ({ default: module.NotificationsPage })))

export const LazyCalendarShell = lazy(() => import('@/components/CalendarShell').then((module) => ({ default: module.CalendarShell })))
export const LazyPostHirePage = lazy(() => import('@/posthire/PostHire').then((module) => ({ default: module.PostHirePage })))
export const LazyCandidateProfilePage = lazy(() =>
  import('@/components/candidates/CandidateProfilePage').then((module) => ({ default: module.CandidateProfilePage })),
)
export const LazyJobWorkspace = lazy(() => import('@/components/JobWorkspace').then((module) => ({ default: module.JobWorkspace })))
