import { useMemo, useState } from 'react'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { mobileApi } from '@/api/mobile'
import { openAuthenticatedFile } from '@/api/files'
import { resourceState, type ResourceState } from '@/api/state'
import type { MobileCollection } from '@/api/types'
import { useServerConfirmation } from '@/api/useServerConfirmation'
import { useAuth } from '@/auth/AuthProvider'
import { hasCapability, routeAvailable } from '@/capabilities'
import {
  Card,
  ActionableCard,
  ConfirmationSheet,
  type ConfirmationView,
} from '@/components/primitives'
import { useLocale } from '@/i18n'
import { formatDate, formatDateTime, formatTimeRange } from '@/i18n/date'
import {
  NotesEditor,
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
    company: me?.principal.company_code || 'WATHEFNI',
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
  const shell = useShell()
  const permitted = routeAvailable(shell.me, 'tasks')
  const query = useQuery({
    queryKey: ['hr-tasks'],
    queryFn: ({ signal }) => mobileApi.tasks(shell.request, signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.task_id,
    title: item.title,
    subtitle: item.summary,
    meta: item.due_at ? `${shell.t('common.due')} ${formatDateTime(item.due_at, shell.locale)}` : null,
    status: item.status,
    tone: toneForStatus(item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('tasks.eyebrow')}
      title={shell.t('tasks.title')}
      items={items}
      state={queryState(query, permitted)}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function OnboardingRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'onboarding')
  const query = useQuery({
    queryKey: ['onboarding'],
    queryFn: ({ signal }) => mobileApi.onboarding(shell.request, signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.employee_key,
    title: item.employee.name,
    subtitle: item.current_step || item.employee.position_title,
    meta: item.start_date ? formatDate(item.start_date, shell.locale) : item.employee.department,
    status: item.status,
    tone: toneForStatus(item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('onboarding.eyebrow')}
      title={shell.t('onboarding.title')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(item) => router.push(`/onboarding/${encodeURIComponent(item.id)}` as never)}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function OnboardingDetailRoute() {
  const { employeeKey = '' } = useLocalSearchParams<{ employeeKey: string }>()
  const shell = useShell()
  const client = useQueryClient()
  const permitted = routeAvailable(shell.me, 'onboarding')
  const query = useQuery({
    queryKey: ['onboarding', employeeKey],
    queryFn: ({ signal }) => mobileApi.onboardingDetail(shell.request, employeeKey, signal),
    enabled: permitted && Boolean(employeeKey),
  })
  const confirmation = useServerConfirmation<{ itemId: string; outcome: 'received' | 'waived' }>({
    keyPrefix: 'onboarding-review',
    execute: (input, fields) =>
      mobileApi.onboardingReview(shell.request, employeeKey, {
        item_id: input.itemId,
        outcome: input.outcome,
        ...fields,
      }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['onboarding', employeeKey] }),
        client.invalidateQueries({ queryKey: ['onboarding'] }),
        client.invalidateQueries({ queryKey: ['documents'] }),
      ])
    },
  })
  const item = query.data?.item
  const state = !permitted
    ? 'permission'
    : resourceState({
        loading: query.isLoading,
        error: query.error || confirmation.error,
        stale: query.data?.stale,
        success: confirmation.succeeded,
      })
  return (
    <OperationalDetailView
      company={shell.company}
      eyebrow={shell.t('onboarding.detailEyebrow')}
      title={item?.employee.name || shell.t('onboarding.detailTitle')}
      status={item?.status}
      state={state}
      facts={[
        { label: shell.t('common.position'), value: item?.employee.position_title },
        { label: shell.t('common.department'), value: item?.employee.department },
        { label: shell.t('onboarding.currentStep'), value: item?.current_step },
        { label: shell.t('common.startDate'), value: item?.start_date ? formatDate(item.start_date, shell.locale) : null },
      ]}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    >
      {(item?.items || []).map((checklistItem) => (
        <Card key={checklistItem.item_id} tone="sky">
          <ActionableCard
            title={checklistItem.label}
            subtitle={checklistItem.required ? shell.t('onboarding.required') : shell.t('onboarding.optional')}
            status={checklistItem.status}
          />
          {checklistItem.allowed_actions.includes('review') ? (
            <ActionableCard
              title={shell.t('common.review')}
              subtitle={shell.t('onboarding.documentAction')}
              onPress={() =>
                void confirmation
                  .prepare({ itemId: checklistItem.item_id, outcome: 'received' })
                  .catch(() => undefined)
              }
            />
          ) : null}
        </Card>
      ))}
      <ConfirmationSheet
        visible={confirmation.visible}
        value={confirmation.view}
        loading={confirmation.loading}
        onCancel={confirmation.cancel}
        onConfirm={() => void confirmation.confirm().catch(() => undefined)}
      />
    </OperationalDetailView>
  )
}

export function AttendanceRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'attendance')
  const query = useQuery({
    queryKey: ['attendance'],
    queryFn: ({ signal }) => mobileApi.attendance(shell.request, signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.exception_id,
    title: item.employee.name,
    subtitle: item.exception_type,
    meta: item.occurred_at ? formatDateTime(item.occurred_at, shell.locale) : item.note,
    status: item.status,
    tone: toneForStatus(item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('attendance.eyebrow')}
      title={shell.t('attendance.title')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(item) => router.push(`/attendance/${encodeURIComponent(item.id)}` as never)}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function DocumentsRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'documents')
  const query = useQuery({
    queryKey: ['documents'],
    queryFn: ({ signal }) => mobileApi.documents(shell.request, signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.document_id,
    title: item.employee?.name || item.name,
    subtitle: item.employee?.name ? item.name : item.document_type,
    meta: item.submitted_at ? formatDateTime(item.submitted_at, shell.locale) : item.document_type,
    status: item.status,
    tone: toneForStatus(item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('documents.eyebrow')}
      title={shell.t('documents.title')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(selected) => {
        const document = query.data?.items.find((item) => item.document_id === selected.id)
        const employeeKey = document?.employee?.employee_key
        if (!employeeKey || !document.document_type || document.source !== 'compliance') return
        router.push(
          `/documents/${encodeURIComponent(employeeKey)}/${encodeURIComponent(document.document_type)}` as never,
        )
      }}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function DocumentDetailRoute() {
  const { employeeKey = '', documentType = '' } = useLocalSearchParams<{
    employeeKey: string
    documentType: string
  }>()
  const shell = useShell()
  const client = useQueryClient()
  const permitted = hasCapability(shell.me, 'hr', 'document_review')
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)
  const query = useQuery({
    queryKey: ['document', employeeKey, documentType],
    queryFn: ({ signal }) =>
      mobileApi.documentDetail(shell.request, employeeKey, documentType, signal),
    enabled: permitted && Boolean(employeeKey && documentType),
  })
  const review = useMutation({
    mutationFn: () =>
      mobileApi.documentReview(shell.request, employeeKey, documentType, {
        expected_status: query.data?.item.status || 'needs_review',
      }),
    onSuccess: async () => {
      setConfirmation(null)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['document', employeeKey, documentType] }),
        client.invalidateQueries({ queryKey: ['documents'] }),
      ])
    },
  })
  const item = query.data?.item
  const canReview = item?.allowed_actions.includes('review') === true
  const openFile = (download: boolean) => {
    const path = download ? item?.download_path : item?.preview_path
    if (!path) return
    void openAuthenticatedFile({
      request: shell.request,
      path,
      filename: item?.name,
      download,
    }).catch(() => undefined)
  }
  return (
    <OperationalDetailView
      company={shell.company}
      eyebrow={shell.t('documents.detailEyebrow')}
      title={item?.name || shell.t('documents.detailTitle')}
      status={item?.status}
      state={
        !permitted
          ? 'permission'
          : resourceState({
              loading: query.isLoading,
              error: query.error || review.error,
              stale: query.data?.stale,
              success: review.isSuccess,
            })
      }
      facts={[
        { label: shell.t('common.department'), value: item?.employee?.department },
        { label: shell.t('common.date'), value: item?.submitted_at ? formatDate(item.submitted_at, shell.locale) : null },
      ]}
      actions={canReview ? [{ key: 'review', label: shell.t('common.review') }] : []}
      onAction={() =>
        setConfirmation({
          target: `${item?.employee?.name || shell.t('documents.detailTitle')} · ${item?.name || documentType}`,
          action: shell.t('common.review'),
          consequence: shell.t('documents.reviewConsequence'),
          currentState: item?.status || 'needs_review',
        })
      }
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    >
      {item?.preview_path ? (
        <ActionableCard
          title={shell.t('common.view')}
          subtitle={item.name}
          onPress={() => openFile(false)}
        />
      ) : null}
      {item?.download_path ? (
        <ActionableCard
          title={shell.t('candidate.downloadCV')}
          subtitle={item.name}
          onPress={() => openFile(true)}
        />
      ) : null}
      <ConfirmationSheet
        visible={Boolean(confirmation)}
        value={confirmation}
        loading={review.isPending}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => review.mutate()}
      />
    </OperationalDetailView>
  )
}

export function AttendanceDetailRoute() {
  const { attendanceId = '' } = useLocalSearchParams<{ attendanceId: string }>()
  const shell = useShell()
  const client = useQueryClient()
  const permitted = hasCapability(shell.me, 'hr', 'attendance_exceptions')
  const query = useQuery({
    queryKey: ['attendance', attendanceId],
    queryFn: ({ signal }) => mobileApi.attendanceDetail(shell.request, attendanceId, signal),
    enabled: permitted && Boolean(attendanceId),
  })
  const confirmation = useServerConfirmation<{ status: 'present' | 'late' | 'absent' | 'completed' }>({
    keyPrefix: 'attendance-resolve',
    execute: (input, fields) =>
      mobileApi.resolveAttendance(shell.request, attendanceId, {
        status: input.status,
        ...fields,
      }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['attendance', attendanceId] }),
        client.invalidateQueries({ queryKey: ['attendance'] }),
      ])
    },
  })
  const item = query.data?.item
  const canResolve = item?.allowed_actions.includes('resolve') === true
  return (
    <OperationalDetailView
      company={shell.company}
      eyebrow={shell.t('attendance.detailEyebrow')}
      title={item?.employee.name || shell.t('attendance.detailTitle')}
      status={item?.status}
      state={
        !permitted
          ? 'permission'
          : resourceState({
              loading: query.isLoading,
              error: query.error || confirmation.error,
              stale: query.data?.stale,
              success: confirmation.succeeded,
            })
      }
      facts={[
        { label: shell.t('common.date'), value: item?.occurred_at ? formatDate(item.occurred_at, shell.locale) : null },
        { label: shell.t('attendance.exception'), value: item?.exception_type },
        { label: shell.t('common.note'), value: item?.note },
      ]}
      actions={
        canResolve
          ? (['present', 'late', 'absent', 'completed'] as const).map((status) => ({
              key: status,
              label: shell.t(`attendance.${status}`),
              tone: status === 'absent' ? 'danger' as const : 'secondary' as const,
            }))
          : []
      }
      onAction={(status) =>
        void confirmation
          .prepare({ status: status as 'present' | 'late' | 'absent' | 'completed' })
          .catch(() => undefined)
      }
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    >
      <ConfirmationSheet
        visible={confirmation.visible}
        value={confirmation.view}
        loading={confirmation.loading}
        onCancel={confirmation.cancel}
        onConfirm={() => void confirmation.confirm().catch(() => undefined)}
      />
    </OperationalDetailView>
  )
}

export function ShiftsRoute() {
  const shell = useShell()
  const router = useRouter()
  const canShifts = hasCapability(shell.me, 'hr', 'today_shifts')
  const canSwaps = hasCapability(shell.me, 'hr', 'shift_swap_decisions')
  const date = new Date().toISOString().slice(0, 10)
  const shifts = useQuery({
    queryKey: ['shifts', date],
    queryFn: ({ signal }) => mobileApi.shifts(shell.request, date, signal),
    enabled: canShifts,
  })
  const swaps = useQuery({
    queryKey: ['shift-swaps'],
    queryFn: ({ signal }) => mobileApi.swaps(shell.request, signal),
    enabled: canSwaps,
  })
  const items = [
    ...(shifts.data?.items || []).map<OperationalItem>((item) => ({
      id: `shift:${item.shift_id}`,
      title: item.employee.name,
      subtitle: item.location,
      meta: formatTimeRange(item.starts_at, item.ends_at, shell.locale),
      status: item.status,
      tone: toneForStatus(item.status),
    })),
    ...(swaps.data?.items || []).map<OperationalItem>((item) => ({
      id: `swap:${item.swap_id}`,
      title: `${shell.t('shifts.swap')} · ${item.requester.name}`,
      subtitle: item.reason,
      meta: formatTimeRange(item.starts_at, item.ends_at, shell.locale),
      status: item.status,
      tone: toneForStatus(item.status),
    })),
  ]
  const loading = (canShifts && shifts.isLoading) || (canSwaps && swaps.isLoading)
  const error = shifts.error || swaps.error
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('shifts.eyebrow')}
      title={shell.t('shifts.title')}
      items={items}
      state={resourceState({ loading, error, empty: !items.length })}
      onOpen={(item) => {
        if (item.id.startsWith('swap:')) router.push(`/shift-swaps/${item.id.slice(5)}` as never)
      }}
      onRetry={() => {
        if (canShifts) void shifts.refetch()
        if (canSwaps) void swaps.refetch()
      }}
      onLocale={shell.toggleLocale}
    />
  )
}

export function ShiftSwapDetailRoute() {
  const { swapId = '' } = useLocalSearchParams<{ swapId: string }>()
  const shell = useShell()
  const client = useQueryClient()
  const permitted = hasCapability(shell.me, 'hr', 'shift_swap_decisions')
  const query = useQuery({
    queryKey: ['shift-swap', swapId],
    queryFn: ({ signal }) => mobileApi.swapDetail(shell.request, swapId, signal),
    enabled: permitted && Boolean(swapId),
  })
  const confirmation = useServerConfirmation<{ action: 'approve' | 'reject' }>({
    keyPrefix: 'shift-swap',
    execute: (input, fields) =>
      mobileApi.swapDecision(shell.request, swapId, { action: input.action, ...fields }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['shift-swap', swapId] }),
        client.invalidateQueries({ queryKey: ['shift-swaps'] }),
      ])
    },
  })
  const item = query.data?.item
  return (
    <OperationalDetailView
      company={shell.company}
      eyebrow={shell.t('shifts.swapEyebrow')}
      title={item?.requester.name || shell.t('shifts.swapTitle')}
      status={item?.status}
      state={!permitted ? 'permission' : resourceState({ loading: query.isLoading, error: query.error || confirmation.error, stale: query.data?.stale, success: confirmation.succeeded })}
      facts={[
        { label: shell.t('shifts.replacement'), value: item?.replacement?.name },
        { label: shell.t('common.date'), value: item?.starts_at ? formatDate(item.starts_at, shell.locale) : null },
        { label: shell.t('common.time'), value: formatTimeRange(item?.starts_at, item?.ends_at, shell.locale) },
        { label: shell.t('common.reason'), value: item?.reason },
      ]}
      actions={(item?.allowed_actions || []).filter((action) => ['approve', 'reject'].includes(action)).map((action) => ({
        key: action,
        label: actionLabel(action, shell.t),
        tone: action === 'reject' ? 'danger' as const : 'primary' as const,
      }))}
      onAction={(action) =>
        void confirmation
          .prepare({ action: action as 'approve' | 'reject' })
          .catch(() => undefined)
      }
      onRetry={() => {
        void query.refetch()
      }}
      onLocale={shell.toggleLocale}
    >
      <ConfirmationSheet
        visible={confirmation.visible}
        value={confirmation.view}
        loading={confirmation.loading}
        onCancel={confirmation.cancel}
        onConfirm={() => void confirmation.confirm().catch(() => undefined)}
      />
    </OperationalDetailView>
  )
}

export function EmployeesRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'employees')
  const query = useQuery({
    queryKey: ['employees'],
    queryFn: ({ signal }) => mobileApi.employees(shell.request, signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.employee_key,
    title: item.employee.name,
    subtitle: item.employee.position_title,
    meta: item.employee.department,
    status: item.employee.employment_status,
    tone: toneForStatus(item.employee.employment_status || ''),
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('employees.eyebrow')}
      title={shell.t('employees.title')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(item) => router.push(`/employees/${encodeURIComponent(item.id)}` as never)}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function EmployeeDetailRoute() {
  const { employeeKey = '' } = useLocalSearchParams<{ employeeKey: string }>()
  const shell = useShell()
  const permitted = routeAvailable(shell.me, 'employees')
  const query = useQuery({
    queryKey: ['employee', employeeKey],
    queryFn: ({ signal }) => mobileApi.employeeDetail(shell.request, employeeKey, signal),
    enabled: permitted && Boolean(employeeKey),
  })
  const item = query.data?.item
  return (
    <OperationalDetailView
      company={shell.company}
      eyebrow={shell.t('employees.detailEyebrow')}
      title={item?.employee.name || shell.t('employees.detailTitle')}
      status={item?.employee.employment_status}
      state={!permitted ? 'permission' : resourceState({ loading: query.isLoading, error: query.error, stale: query.data?.stale })}
      facts={[
        { label: shell.t('common.position'), value: item?.employee.position_title },
        { label: shell.t('common.department'), value: item?.employee.department },
        { label: shell.t('common.email'), value: item?.email },
        { label: shell.t('common.phone'), value: item?.phone },
        { label: shell.t('employees.manager'), value: item?.manager_name },
        { label: shell.t('common.startDate'), value: item?.started_on ? formatDate(item.started_on, shell.locale) : null },
      ]}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function DeliveryAlertsRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'deliveryAlerts')
  const query = useQuery({
    queryKey: ['delivery-alerts'],
    queryFn: ({ signal }) => mobileApi.alerts(shell.request, signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.alert_id,
    title: item.title,
    subtitle: item.summary,
    meta: [item.channel, item.occurred_at ? formatDateTime(item.occurred_at, shell.locale) : null].filter(Boolean).join(' · '),
    status: item.status,
    tone: toneForStatus(item.status),
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('alerts.eyebrow')}
      title={shell.t('alerts.title')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(selected) => {
        const destination = query.data?.items.find((item) => item.alert_id === selected.id)?.destination
        if (destination?.startsWith('/')) router.push(destination as never)
      }}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function CandidatesRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'candidates')
  const query = useQuery({
    queryKey: ['candidates'],
    queryFn: ({ signal }) => mobileApi.candidates(shell.request, signal),
    enabled: permitted,
  })
  const sorted = useMemo(
    () => [...(query.data?.items || [])].sort((a, b) => (b.score ?? -1) - (a.score ?? -1)),
    [query.data?.items],
  )
  const items = sorted.map<OperationalItem>((item) => ({
    id: item.app_key,
    title: item.candidate.name,
    subtitle: item.position?.title || item.position?.code,
    meta: item.score == null ? shell.t('candidate.scoreUnavailable') : `${shell.t('candidate.score')} ${item.score}/100`,
    status: item.status,
    tone: toneForStatus(item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('candidates.eyebrow')}
      title={shell.t('candidates.title')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(item) => router.push(`/candidates/${encodeURIComponent(item.id)}` as never)}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function InterviewsRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'interviews')
  const query = useQuery({
    queryKey: ['interviews'],
    queryFn: ({ signal }) => mobileApi.interviews(shell.request, signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.interview_id,
    title: item.candidate.name,
    subtitle: item.position?.title || item.position?.code,
    meta: item.scheduled_at ? formatDateTime(item.scheduled_at, shell.locale) : item.communication_status,
    status: item.status,
    tone: toneForStatus(item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('interviews.eyebrow')}
      title={shell.t('interviews.title')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(item) => router.push(`/interviews/${encodeURIComponent(item.id)}` as never)}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    />
  )
}

export function InterviewDetailRoute() {
  const { interviewId = '' } = useLocalSearchParams<{ interviewId: string }>()
  const shell = useShell()
  const client = useQueryClient()
  const permitted = routeAvailable(shell.me, 'interviews')
  const query = useQuery({
    queryKey: ['interview', interviewId],
    queryFn: ({ signal }) => mobileApi.interviewDetail(shell.request, interviewId, signal),
    enabled: permitted && Boolean(interviewId),
  })
  const notes = useMutation({
    mutationFn: (value: string) => mobileApi.interviewNotes(shell.request, interviewId, { notes: value }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['interview', interviewId] }),
  })
  const item = query.data?.item
  const canWriteNotes = item?.allowed_actions.includes('write_notes') || item?.allowed_actions.includes('write')
  return (
    <OperationalDetailView
      company={shell.company}
      eyebrow={shell.t('interviews.detailEyebrow')}
      title={item?.candidate.name || shell.t('interviews.detailTitle')}
      status={item?.status}
      state={!permitted ? 'permission' : resourceState({ loading: query.isLoading, error: query.error || notes.error, stale: query.data?.stale })}
      facts={[
        { label: shell.t('common.position'), value: item?.position?.title || item?.position?.code },
        { label: shell.t('interviews.scheduled'), value: item?.scheduled_at ? formatDateTime(item.scheduled_at, shell.locale) : null },
        { label: shell.t('interviews.delivery'), value: item?.communication_status },
        { label: shell.t('interviews.notes'), value: canWriteNotes ? null : item?.notes },
      ]}
      onRetry={() => void query.refetch()}
      onLocale={shell.toggleLocale}
    >
      {canWriteNotes ? <NotesEditor initialValue={item?.notes} onSave={(value) => notes.mutate(value)} /> : null}
    </OperationalDetailView>
  )
}

type Translator = ReturnType<typeof useLocale>['t']

function actionLabel(action: string, t: Translator): string {
  const labels: Record<string, string> = {
    approve: t('common.approve'),
    reject: t('common.reject'),
    review: t('common.review'),
    complete: t('common.complete'),
    resolve: t('common.resolve'),
    excuse: t('attendance.excuse'),
  }
  return labels[action] || action.replaceAll('_', ' ')
}
