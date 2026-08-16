import type { FeatureCapability, MobileMe, WorkspaceKey } from '@hr/api/types'
import { fromHrPath } from '@hr/navigation'

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
  { key: 'tasks', path: '/hr/tasks', workspace: 'hr', features: ['hr_tasks'] },
  {
    key: 'onboarding',
    path: '/hr/onboarding',
    workspace: 'hr',
    features: ['onboarding_review'],
  },
  {
    key: 'preboarding',
    path: '/hr/preboarding',
    workspace: 'hr',
    features: ['preboarding_review'],
  },
  {
    key: 'probation',
    path: '/hr/probation',
    workspace: 'hr',
    features: ['probation_review'],
  },
  {
    key: 'performance',
    path: '/hr/performance',
    workspace: 'hr',
    features: ['performance_reviews'],
  },
  {
    key: 'employee-relations',
    path: '/hr/employee-relations',
    workspace: 'hr',
    features: ['employee_relations_actions'],
  },
  {
    key: 'requisitions',
    path: '/hr/requisitions',
    workspace: 'recruiting',
    features: ['requisitions_review'],
  },
  {
    key: 'documents',
    path: '/hr/documents',
    workspace: 'hr',
    features: ['document_review'],
  },
  {
    key: 'attendance',
    path: '/hr/attendance',
    workspace: 'hr',
    features: ['attendance_exceptions'],
  },
  {
    key: 'shifts',
    path: '/hr/shifts',
    workspace: 'hr',
    features: ['today_shifts', 'shift_swap_decisions'],
  },
  {
    key: 'employees',
    path: '/hr/employees',
    workspace: 'hr',
    features: ['employee_search', 'employee_quick_profile'],
  },
  {
    key: 'deliveryAlerts',
    path: '/hr/delivery-alerts',
    workspace: 'hr',
    features: ['delivery_alerts'],
  },
  {
    key: 'assistant',
    path: '/hr/assistant',
    workspace: 'hr',
    features: ['assistant'],
  },
  {
    key: 'candidates',
    path: '/hr/candidates',
    workspace: 'recruiting',
    features: ['candidate_rankings', 'candidate_summary', 'candidate_evidence'],
  },
  {
    key: 'interviews',
    path: '/hr/interviews',
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
  const path = fromHrPath(destination.split('?')[0])
  if (path === '/' || path === '/settings' || path === '/inbox' || path === '/hiring' || path === '/more') {
    return Boolean(me)
  }
  if (path === '/assistant') return hasCapability(me, 'hr', 'assistant')
  if (path === '/people' || path === '/employees') return routeAvailable(me, 'employees')
  if (path === '/jobs') return routeAvailable(me, 'candidates')
  if (path.startsWith('/leave/')) return hasCapability(me, 'hr', 'leave_approvals')
  if (path.startsWith('/candidates/') || path === '/candidates') return routeAvailable(me, 'candidates')
  if (path.startsWith('/onboarding/')) return routeAvailable(me, 'onboarding')
  if (path.startsWith('/preboarding/') || path === '/preboarding') return routeAvailable(me, 'preboarding')
  if (path.startsWith('/probation/') || path === '/probation') return routeAvailable(me, 'probation')
  if (path.startsWith('/requisitions/') || path === '/requisitions') return routeAvailable(me, 'requisitions')
  if (path.startsWith('/employees/')) return routeAvailable(me, 'employees')
  if (path.startsWith('/shift-swaps/')) {
    return hasCapability(me, 'hr', 'shift_swap_decisions')
  }
  if (path.startsWith('/interviews/') || path === '/interviews') return routeAvailable(me, 'interviews')
  if (path.startsWith('/tasks/')) return routeAvailable(me, 'tasks')
  if (path.startsWith('/documents/')) return routeAvailable(me, 'documents')
  if (path.startsWith('/attendance/')) return routeAvailable(me, 'attendance')
  if (path.startsWith('/performance/') || path === '/performance') return routeAvailable(me, 'performance')
  if (path.startsWith('/employee-relations/') || path === '/employee-relations') return routeAvailable(me, 'employee-relations')
  if (path.startsWith('/talent/') || path === '/talent') return routeAvailable(me, 'talent')
  if (path.startsWith('/learning/') || path === '/learning') return routeAvailable(me, 'learning')
  if (path.startsWith('/benefits/') || path === '/benefits') return routeAvailable(me, 'benefits')
  return workspaceRoutes(me).some((route) => fromHrPath(route.path) === path)
}
