/** Alerts & Delivery page + action authority (UX gate only; backend stays authoritative). */

export const ALERTS_DELIVERY_MANAGE_PERMISSIONS = [
  'users.manage',
  'leave.manage',
  'onboarding.manage',
  'compliance.manage',
  'attendance.manage',
  'shifts.manage',
  'payroll.manage',
] as const

export function canManageAlertsAndDelivery(permissions: string[] | null | undefined): boolean {
  const perms = permissions || []
  return ALERTS_DELIVERY_MANAGE_PERMISSIONS.some((permission) => perms.includes(permission))
}
