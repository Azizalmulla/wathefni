/**
 * Inbox row → in-app destination.
 *
 * Mirrors push follow-through: explicit deep_link first, then flow defaults,
 * then null (caller may still mark-read with no navigation).
 */
import type { MeResponse, NotificationItem } from '@/api/types'
import { openableHref } from '@/composition/employeeAppComposition'
import { FLOW_DEFAULT_PATHS } from '@/push/resolvePushDestination'

export function candidatePathFromNotification(item: NotificationItem): string | null {
  const payslipId = String(item.deep_link?.payslip_id || '')
  const path = String(item.deep_link?.path || '').trim()
  if (path) {
    if (payslipId && path.startsWith('/payslips') && !path.includes('?')) {
      return `${path}?payslip_id=${encodeURIComponent(payslipId)}`
    }
    return path
  }
  const flow = String(item.flow || '')
    .trim()
    .toLowerCase()
  return FLOW_DEFAULT_PATHS[flow] ?? null
}

export function inboxOpenableHref(me: MeResponse | null, item: NotificationItem): string | null {
  const candidate = candidatePathFromNotification(item)
  if (!candidate) return null
  return openableHref(me, candidate)
}
