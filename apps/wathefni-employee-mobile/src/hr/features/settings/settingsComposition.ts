import type { MobileMe, WorkspaceKey } from '@hr/api/types'

/** Human-readable role — prefer backend role_label; never expose raw capability keys. */
export function operatorRoleLabel(me: MobileMe): string {
  const labeled = String(me.principal.role_label || '').trim()
  if (labeled) return labeled
  const role = String(me.principal.role || '').trim().toLowerCase()
  switch (role) {
    case 'admin':
    case 'owner':
      return 'Admin'
    case 'hr':
    case 'hr_manager':
      return 'HR'
    case 'manager':
      return 'Manager'
    case 'viewer':
      return 'Viewer'
    default:
      return labeled || role || 'Operator'
  }
}

export function operatorRoleLabelKey(me: MobileMe): string {
  const role = String(me.principal.role || '').trim().toLowerCase()
  switch (role) {
    case 'admin':
    case 'owner':
      return 'hrSettings.roleAdmin'
    case 'hr':
    case 'hr_manager':
      return 'hrSettings.roleHr'
    case 'manager':
      return 'hrSettings.roleManager'
    case 'viewer':
      return 'hrSettings.roleViewer'
    default:
      return me.principal.role_label ? '' : 'hrSettings.roleOperator'
  }
}

/** Company-wide vs team — no scope binding / configuration_error. */
export function scopeAccessLabelKey(me: MobileMe): string {
  return me.scope.restricted ? 'hrSettings.scopeTeam' : 'hrSettings.scopeCompany'
}

export type WorkspaceAccessRow = {
  key: WorkspaceKey
  labelKey: string
}

/** Relevant enabled workspaces only — human labels, not feature keys. */
export function workspaceAccessRows(me: MobileMe): WorkspaceAccessRow[] {
  const rows: WorkspaceAccessRow[] = []
  if (me.workspaces.hr?.enabled) {
    rows.push({ key: 'hr', labelKey: 'hrSettings.accessHr' })
  }
  if (me.workspaces.recruiting?.enabled) {
    rows.push({ key: 'recruiting', labelKey: 'hrSettings.accessHiring' })
  }
  if (me.workspaces.owner?.enabled) {
    rows.push({ key: 'owner', labelKey: 'hrSettings.accessOwner' })
  }
  return rows
}
