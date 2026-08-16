import type { MobileMe } from '@hr/api/types'

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
