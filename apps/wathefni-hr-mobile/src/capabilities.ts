import type { FeatureCapability, MobileMe, WorkspaceKey } from '@/api/types'

export function enabledWorkspaces(me: MobileMe | null): WorkspaceKey[] {
  if (!me) return []
  return (['hr', 'recruiting', 'owner'] as WorkspaceKey[]).filter(
    (workspace) => me.workspaces[workspace]?.enabled,
  )
}

export function capability(
  me: MobileMe | null,
  workspace: WorkspaceKey,
  feature: string,
): FeatureCapability | null {
  return me?.workspaces[workspace]?.features?.[feature] || null
}

export function hasCapability(
  me: MobileMe | null,
  workspace: WorkspaceKey,
  feature: string,
): boolean {
  return capability(me, workspace, feature)?.enabled === true
}

export function can(
  me: MobileMe | null,
  workspace: WorkspaceKey,
  feature: string,
  action: string,
): boolean {
  const value = capability(me, workspace, feature)
  return value?.enabled === true && value.actions.includes(action)
}

export type WorkspaceRoute = {
  key: string
  path: string
  workspace: WorkspaceKey
  features: string[]
}

const routeDefinitions: WorkspaceRoute[] = [
  { key: 'tasks', path: '/tasks', workspace: 'hr', features: ['hr_tasks'] },
  { key: 'leave', path: '/leave', workspace: 'hr', features: ['leave_approvals'] },
  {
    key: 'onboarding',
    path: '/onboarding',
    workspace: 'hr',
    features: ['onboarding_review'],
  },
  {
    key: 'documents',
    path: '/documents',
    workspace: 'hr',
    features: ['document_review'],
  },
  {
    key: 'attendance',
    path: '/attendance',
    workspace: 'hr',
    features: ['attendance_exceptions'],
  },
  {
    key: 'shifts',
    path: '/shifts',
    workspace: 'hr',
    features: ['today_shifts', 'shift_swap_decisions'],
  },
  {
    key: 'employees',
    path: '/employees',
    workspace: 'hr',
    features: ['employee_search', 'employee_quick_profile'],
  },
  {
    key: 'deliveryAlerts',
    path: '/delivery-alerts',
    workspace: 'hr',
    features: ['delivery_alerts'],
  },
  {
    key: 'candidates',
    path: '/candidates',
    workspace: 'recruiting',
    features: ['candidate_rankings', 'candidate_summary', 'candidate_evidence'],
  },
  {
    key: 'interviews',
    path: '/interviews',
    workspace: 'recruiting',
    features: ['interview_status', 'interview_notes'],
  },
]

export function hasAnyCapability(
  me: MobileMe | null,
  workspace: WorkspaceKey,
  features: string[],
): boolean {
  return features.some((feature) => hasCapability(me, workspace, feature))
}

export function workspaceRoutes(me: MobileMe | null): WorkspaceRoute[] {
  return routeDefinitions.filter(
    (route) =>
      me?.workspaces[route.workspace]?.enabled === true &&
      hasAnyCapability(me, route.workspace, route.features),
  )
}

export function routeAvailable(me: MobileMe | null, key: string): boolean {
  return workspaceRoutes(me).some((route) => route.key === key)
}

export function destinationAvailable(me: MobileMe | null, destination: string): boolean {
  const path = destination.split('?')[0]
  if (path === '/' || path === '/settings') return Boolean(me)
  if (path === '/leave' || path.startsWith('/leave/')) return hasCapability(me, 'hr', 'leave_approvals')
  if (path.startsWith('/candidates/')) return routeAvailable(me, 'candidates')
  if (path === '/onboarding' || path.startsWith('/onboarding/')) return routeAvailable(me, 'onboarding')
  if (path === '/documents' || path.startsWith('/documents/')) return routeAvailable(me, 'documents')
  if (path === '/attendance' || path.startsWith('/attendance/')) return routeAvailable(me, 'attendance')
  if (path.startsWith('/employees/')) return routeAvailable(me, 'employees')
  if (path.startsWith('/shift-swaps/')) {
    return hasCapability(me, 'hr', 'shift_swap_decisions')
  }
  if (path.startsWith('/interviews/')) return routeAvailable(me, 'interviews')
  return workspaceRoutes(me).some((route) => route.path === path)
}
