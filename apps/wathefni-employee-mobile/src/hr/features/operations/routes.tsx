import { useMemo } from 'react'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import { resourceState, type ResourceState } from '@hr/api/state'
import type { MobileCollection } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { resolveCompanyBrand } from '@/branding/CompanyBrand'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { useLocale } from '@hr/i18n'
import { formatDate, formatDateTime } from '@hr/i18n/date'
import {
  facetStatusLabel,
  intakeLabel,
  lifecycleCommunicationLabel,
  lifecycleStageLabel,
  workflowLabel,
} from '@hr/features/recruiting/lifecycle'
import { CandidatesQueueView } from '@hr/features/recruiting/CandidatesQueueView'
import { InterviewsQueueView } from '@hr/features/recruiting/InterviewsQueueView'
import { InterviewDetailView } from '@hr/features/recruiting/InterviewDetailView'
import { HRPeopleDirectoryView } from '@hr/features/people/HRPeopleDirectoryView'
import { HRAttendanceQueueView } from '@hr/features/attendance/HRAttendanceQueueView'
import { HRAttendanceDetailView } from '@hr/features/attendance/HRAttendanceDetailView'
import { HRShiftsHomeView } from '@hr/features/shifts/HRShiftsHomeView'
import { HRShiftSwapDetailView } from '@hr/features/shifts/HRShiftSwapDetailView'
import { HROnboardingQueueView } from '@hr/features/onboarding/HROnboardingQueueView'
import { HROnboardingDetailView } from '@hr/features/onboarding/HROnboardingDetailView'
import { HRDocumentReviewsQueueView } from '@hr/features/documents/HRDocumentReviewsQueueView'
import { HRDocumentReviewDetailView } from '@hr/features/documents/HRDocumentReviewDetailView'
import { HRTasksQueueView } from '@hr/features/tasks/HRTasksQueueView'
import { HRTaskDetailView } from '@hr/features/tasks/HRTaskDetailView'
import {
  OperationalDetailView,
  OperationalListView,
  toneForStatus,
  type OperationalItem,
} from './OperationalViews'

function useShell() {
  const { me, request, refreshMe } = useAuth()
  const { locale, setLocale, t } = useLocale()
  return {
    me,
    request,
    locale,
    t,
    company: resolveCompanyBrand(me?.company_identity, locale).name,
    refreshMe,
    toggleLocale: () => void setLocale(locale === 'ar' ? 'en' : 'ar'),
  }
}

function queryState<T>(
  query: { isLoading: boolean; error: unknown; data?: MobileCollection<T> },
  permitted: boolean,
): ResourceState {
  if (!permitted) return 'permission'
  return resourceState({
    loading: query.isLoading,
    error: query.error,
    stale: query.data?.stale,
    empty: query.data?.items.length === 0,
  })
}

export function TasksRoute() {
  return <HRTasksQueueView />
}

export function TaskDetailRoute() {
  return <HRTaskDetailView />
}

export function OnboardingRoute() {
  return <HROnboardingQueueView />
}

export function OnboardingDetailRoute() {
  return <HROnboardingDetailView />
}

export function AttendanceRoute() {
  return <HRAttendanceQueueView />
}

export function AttendanceDetailRoute() {
  return <HRAttendanceDetailView />
}

export function DocumentsRoute() {
  return <HRDocumentReviewsQueueView />
}

export function DocumentDetailRoute() {
  return <HRDocumentReviewDetailView />
}

export function ShiftsRoute() {
  return <HRShiftsHomeView />
}

export function ShiftSwapDetailRoute() {
  return <HRShiftSwapDetailView />
}

export function EmployeesRoute() {
  return <HRPeopleDirectoryView showBack />
}

/** Thin re-export — Delivery Alerts lives under features/delivery-alerts (cream/black). */
export { HRDeliveryAlertsMonitorView as DeliveryAlertsRoute } from '@hr/features/delivery-alerts/HRDeliveryAlertsMonitorView'

export function CandidatesRoute() {
  return <CandidatesQueueView />
}

export function InterviewsRoute() {
  return <InterviewsQueueView />
}

export function InterviewDetailRoute() {
  return <InterviewDetailView />
}

type Translator = ReturnType<typeof useLocale>['t']

function actionLabel(action: string, t: Translator): string {
  const labels: Record<string, string> = {
    approve: t('common.approve'),
    reject: t('common.reject'),
    review: t('common.review'),
    complete: t('common.complete'),
    resolve: t('common.resolve'),
  }
  return labels[action] || action.replaceAll('_', ' ')
}
