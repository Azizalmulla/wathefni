import type { DashboardTeamUser, DashboardUserAccess } from '@/types'

export function hasActorPermission(permissions: readonly string[] | null | undefined, permission: string) {
  const requested = String(permission || '').trim()
  if (!requested || !Array.isArray(permissions) || permissions.length === 0) return false
  if (permissions.includes('*:*')) return true
  return permissions.includes(requested)
}

export function hasDashboardPermission(access: DashboardUserAccess | null | undefined, permission: string) {
  return hasActorPermission(access?.permissions, permission)
}

/**
 * Jobs UI visibility. Bootstrap emits explicit `jobs.*` via the backend expander
 * in `prehire_jobs.expand_effective_jobs_permissions`. The client does not
 * re-derive Jobs access from settings.manage or prehire.read.
 */
export function hasJobsPermission(access: DashboardUserAccess | null | undefined, permission: string) {
  return hasDashboardPermission(access, permission)
}

const PERMISSION_CAPABILITY_LABELS: Record<string, string> = {
  'prehire.read': 'View hiring dashboards, candidates, and reports',
  'jobs.read': 'View Jobs inventory and openings',
  'jobs.create': 'Create job openings',
  'jobs.edit': 'Edit job openings',
  'jobs.publish': 'Publish, resume, and reopen jobs',
  'jobs.close': 'Pause and close jobs',
  'candidate.manage': 'Manage candidate profiles and application details',
  'candidate.import': 'Bulk import candidate CVs',
  'candidate.decide': 'Make final candidate decisions',
  'interview.manage': 'Schedule interviews and manage video interview reviews',
  'assessment.manage': 'Send assessments and review candidate results',
  'report.export': 'Download hiring reports and exports',
  'settings.manage': 'Manage company hiring settings',
  'users.manage': 'Manage team access',
  'employees.read': 'View the employee directory, profiles, and organization structure',
  'employees.manage': 'Create, edit, and import employees; manage organization administration',
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

export const ROLE_LABELS_UI: Record<string, string> = {
  owner: 'Company Admin',
  hr_admin: 'HR Admin',
  hr_manager: 'HR Manager',
  recruiter: 'Recruiter',
  hiring_manager: 'Hiring Manager',
  interviewer: 'Interviewer',
  payroll_operator: 'Payroll Operator',
  manager: 'Team Manager',
  viewer: 'Viewer',
}

function humanizePermission(permission: string) {
  return permission
    .split('.')
    .map((part) => part.replace(/_/g, ' '))
    .join(' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export function readableCapabilities(access: DashboardUserAccess | null | undefined) {
  return (access?.permissions || [])
    .map((permission) => PERMISSION_CAPABILITY_LABELS[permission] || humanizePermission(permission))
    .filter(Boolean)
}

export function isRecoveryAccess(access: DashboardUserAccess | null | undefined) {
  const email = access?.user?.email || ''
  return Boolean(access?.is_recovery_access || access?.user?.is_recovery_access || email.endsWith('.wathefni.local'))
}

export function currentUserTeamRow(access: DashboardUserAccess | null | undefined): DashboardTeamUser | null {
  const user = access?.user
  if (!user?.user_id || !user.email) return null
  return {
    user_id: user.user_id,
    company_code: user.company_code || '',
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
