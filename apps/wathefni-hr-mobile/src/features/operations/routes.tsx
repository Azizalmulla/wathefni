import { useMemo, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
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
import { formatDate, formatDateRange, formatDateTime, formatTimeRange } from '@/i18n/date'
import {
  facetStatusLabel,
  intakeLabel,
  lifecycleCommunicationLabel,
  lifecycleStageLabel,
  workflowLabel,
} from '@/features/recruiting/lifecycle'
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
  const client = useQueryClient()
  const permitted = routeAvailable(shell.me, 'tasks')
  const query = useQuery({
    queryKey: ['hr-tasks'],
    queryFn: ({ signal }) => mobileApi.tasks(shell.request, signal),
    enabled: permitted,
  })
  const [pending, setPending] = useState<OperationalItem | null>(null)
  const resolve = useMutation({
    mutationFn: (item: OperationalItem) =>
      mobileApi.taskResolve(shell.request, item.id, {
        status: 'done',
        expected_status: item.status || 'open',
      }),
    onSuccess: async () => {
      setPending(null)
      await client.invalidateQueries({ queryKey: ['hr-tasks'] })
    },
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
    <>
      <OperationalListView
        company={shell.company}
        eyebrow={shell.t('tasks.eyebrow')}
        title={shell.t('tasks.title')}
        items={items}
        state={
          permitted
            ? resourceState({
                loading: query.isLoading,
                error: query.error || resolve.error,
                stale: query.data?.stale,
                empty: query.data?.items.length === 0,
                success: resolve.isSuccess,
              })
            : 'permission'
        }
        actionsForItem={(item) =>
          item.allowedActions?.includes('resolve')
            ? [{ key: 'resolve', label: shell.t('tasks.complete') }]
            : []
        }
        onAction={(item) => setPending(item)}
        onRetry={() => void query.refetch()}
        onLocale={shell.toggleLocale}
      />
      <ConfirmationSheet
        visible={Boolean(pending)}
        value={
          pending
            ? {
                target: pending.title,
                action: shell.t('tasks.complete'),
                consequence: shell.t('tasks.completeConsequence'),
                currentState: pending.status || 'open',
              }
            : null
        }
        loading={resolve.isPending}
        onCancel={() => setPending(null)}
        onConfirm={() => pending && resolve.mutate(pending)}
      />
    </>
  )
}

export function LeaveQueueRoute() {
  const shell = useShell()
  const router = useRouter()
  const permitted = routeAvailable(shell.me, 'leave')
  const query = useQuery({
    queryKey: ['hr-leave'],
    queryFn: ({ signal }) => mobileApi.leave(shell.request, 'requested', signal),
    enabled: permitted,
  })
  const items = (query.data?.items || []).map<OperationalItem>((item) => ({
    id: item.leave_id,
    title: item.employee.name,
    subtitle: item.leave_type,
    meta: formatDateRange(item.start_date, item.end_date, shell.locale),
    status: item.status,
    tone: toneForStatus(item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('leave.queueEyebrow')}
      title={shell.t('leave.queueTitle')}
      items={items}
      state={queryState(query, permitted)}
      onOpen={(item) => router.push(`/leave/${encodeURIComponent(item.id)}` as never)}
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
      canOpen={(selected) => {
        const document = query.data?.items.find((item) => item.document_id === selected.id)
        return Boolean(
          document?.source === 'compliance' && document.employee?.employee_key && document.document_type,
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
      canOpen={(item) => item.id.startsWith('swap:')}
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
      canOpen={(selected) => {
        const destination = query.data?.items.find((item) => item.alert_id === selected.id)?.destination
        return Boolean(destination?.startsWith('/'))
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
  const [stageFilter, setStageFilter] = useState('')
  const query = useQuery({
    queryKey: ['candidates'],
    queryFn: ({ signal }) => mobileApi.candidates(shell.request, signal),
    enabled: permitted,
  })
  const stages = useMemo(() => {
    const values = new Set<string>()
    for (const item of query.data?.items || []) {
      const stage = item.canonical_stage || item.status
      if (stage) values.add(stage)
    }
    return [...values]
  }, [query.data?.items])
  const sorted = useMemo(
    () =>
      [...(query.data?.items || [])]
        .filter((item) => !stageFilter || (item.canonical_stage || item.status) === stageFilter)
        .sort((a, b) => (b.score ?? -1) - (a.score ?? -1)),
    [query.data?.items, stageFilter],
  )
  const items = sorted.map<OperationalItem>((item) => ({
    id: item.app_key,
    title: item.candidate.name,
    subtitle: item.position?.title || item.position?.code,
    meta: [
      item.score != null ? `${item.score}` : null,
      intakeLabel(item.intake_source, shell.locale),
      lifecycleCommunicationLabel(item.communication_status, shell.locale),
      item.next_human_action ? workflowLabel(item.next_human_action, shell.locale) : null,
    ].filter(Boolean).join(' · '),
    status: lifecycleStageLabel(item.canonical_stage || item.status, shell.locale),
    tone: toneForStatus(item.canonical_stage || item.status),
    allowedActions: item.allowed_actions,
  }))
  return (
    <OperationalListView
      company={shell.company}
      eyebrow={shell.t('candidates.eyebrow')}
      title={shell.t('candidates.title')}
      items={items}
      state={queryState(query, permitted)}
      header={
        <View style={candidateStyles.header}>
          <Text style={candidateStyles.note}>{shell.t('candidates.rankingNote')}</Text>
          <View style={candidateStyles.filters}>
            <Pressable
              accessibilityRole="button"
              onPress={() => setStageFilter('')}
              style={[candidateStyles.chip, !stageFilter && candidateStyles.chipActive]}
            >
              <Text style={candidateStyles.chipText}>{shell.t('candidates.filterAll')}</Text>
            </Pressable>
            {stages.map((stage) => (
              <Pressable
                key={stage}
                accessibilityRole="button"
                onPress={() => setStageFilter(stage)}
                style={[candidateStyles.chip, stageFilter === stage && candidateStyles.chipActive]}
              >
                <Text style={candidateStyles.chipText}>{lifecycleStageLabel(stage, shell.locale)}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      }
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
    meta: [
      facetStatusLabel(item.status, shell.locale),
      item.scheduled_at ? formatDateTime(item.scheduled_at, shell.locale) : null,
      item.next_human_action ? workflowLabel(item.next_human_action, shell.locale) : null,
    ].filter(Boolean).join(' · '),
    status: lifecycleStageLabel(item.application_stage, shell.locale),
    tone: toneForStatus(item.application_stage || item.status),
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
  const analysis = String(item?.ai_summary?.overall_summary || item?.ai_summary?.summary || '')
  return (
    <OperationalDetailView
      company={shell.company}
      eyebrow={shell.t('interviews.detailEyebrow')}
      title={item?.candidate.name || shell.t('interviews.detailTitle')}
      status={lifecycleStageLabel(item?.application_stage, shell.locale)}
      state={!permitted ? 'permission' : resourceState({ loading: query.isLoading, error: query.error || notes.error, stale: query.data?.stale })}
      facts={[
        { label: shell.t('common.position'), value: item?.position?.title || item?.position?.code },
        { label: shell.t('interviews.applicationStage'), value: lifecycleStageLabel(item?.application_stage, shell.locale) },
        { label: shell.t('interviews.status'), value: facetStatusLabel(item?.status, shell.locale) },
        { label: shell.t('interviews.scheduled'), value: item?.scheduled_at ? formatDateTime(item.scheduled_at, shell.locale) : null },
        { label: shell.t('interviews.channelLocation'), value: item?.meeting?.join_url || item?.meeting?.type },
        { label: shell.t('interviews.invitationStatus'), value: lifecycleCommunicationLabel(item?.invitation_status || item?.communication_status, shell.locale) },
        { label: shell.t('interviews.candidateConfirmation'), value: facetStatusLabel(item?.candidate_confirmation, shell.locale) },
        { label: shell.t('interviews.notesStatus'), value: facetStatusLabel(item?.notes_status, shell.locale) },
        { label: shell.t('interviews.nextHumanAction'), value: workflowLabel(item?.next_human_action, shell.locale) },
        { label: shell.t('interviews.advisorySummary'), value: analysis || null },
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

const candidateStyles = StyleSheet.create({
  header: { gap: 10 },
  note: { color: '#5C4A3A', fontSize: 13, fontWeight: '700', lineHeight: 18 },
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#E4D6C8',
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: '#FFF8F1',
  },
  chipActive: { backgroundColor: '#F3E4D4', borderColor: '#C9A98A' },
  chipText: { color: '#2A2118', fontSize: 13, fontWeight: '800' },
})

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
