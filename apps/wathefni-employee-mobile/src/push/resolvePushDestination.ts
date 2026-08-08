/**
 * Push-tap destination resolution.
 *
 * Push payloads may carry a registered deep link (path / deep_link / payslip_id)
 * or only a flow name. Follow-through always goes through the Phase 1 route
 * registry + current entitlements; unknown / unentitled / malformed paths fall
 * back calmly to Inbox, then Home. Never invents authority or bypasses unlock —
 * callers navigate only while signed in; LocalUnlockShell still covers the UI.
 */
import type { MeResponse } from '@/api/types'
import { HOME_ROUTE, INBOX_ROUTE, openableHref } from '@/composition/employeeAppComposition'

/** Default in-app paths for known outbound flows when push data omits an explicit path. */
export const FLOW_DEFAULT_PATHS: Record<string, string> = {
  payroll: '/payslips',
  leave: '/(tabs)/leave',
  shift: '/(tabs)/schedule',
  shifts: '/(tabs)/schedule',
  attendance: '/(tabs)/schedule',
  onboarding: '/onboarding',
  compliance: '/documents',
  documents: '/documents',
  bank: '/bank',
}

const INBOX_PATH = INBOX_ROUTE

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function stringField(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

/**
 * Build a candidate in-app path from Expo notification `content.data`.
 * Returns null when there is nothing actionable (caller falls back to Inbox).
 */
export function candidatePathFromPushData(data: unknown): string | null {
  const root = asRecord(data)
  if (!root) return null

  const deep = asRecord(root.deep_link)
  const pathFromDeep = stringField(deep?.path)
  const pathFlat = stringField(root.path) || stringField(root.url)
  const path = pathFromDeep || pathFlat
  const payslipId =
    stringField(deep?.payslip_id) || stringField(root.payslip_id) || stringField(root.payslipId)

  if (path) {
    if (payslipId && path.startsWith('/payslips') && !path.includes('?')) {
      return `${path}?payslip_id=${encodeURIComponent(payslipId)}`
    }
    return path
  }

  if (payslipId) {
    return `/payslips?payslip_id=${encodeURIComponent(payslipId)}`
  }

  const flow = stringField(root.flow).toLowerCase()
  return FLOW_DEFAULT_PATHS[flow] ?? null
}

/**
 * Resolve the href a signed-in push tap should open.
 * Entitled registered destination → that href; otherwise Inbox; otherwise Home.
 */
export function pushFollowThroughHref(me: MeResponse | null, data: unknown): string {
  const candidate = candidatePathFromPushData(data)
  if (candidate) {
    const href = openableHref(me, candidate)
    if (href) return href
  }
  return openableHref(me, INBOX_PATH) ?? HOME_ROUTE
}
