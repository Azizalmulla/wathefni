import type { Shift, ShiftSwap } from '@hr/api/types'
import type { StatusTone } from '@/components/ui'
import {
  SHIFTS_DEMO_ID_PREFIX,
  SHIFTS_DEMO_SHIFT_PREFIX,
  SHIFTS_DEMO_SOURCE,
} from './shiftsDemoGate'

export type ShiftsHomeTab = 'needs_attention' | 'today'

/** Extensible attention kinds — v1 ships swaps only. */
export type ShiftsAttentionKind = 'shift_swap'

export type ShiftsAttentionItem = {
  kind: ShiftsAttentionKind
  id: string
  swap: ShiftSwap
}

export function swapStatusLabelKey(status: string | null | undefined): string {
  switch ((status || '').trim().toLowerCase()) {
    case 'requested':
      return 'hrShifts.statusRequested'
    case 'approved':
      return 'hrShifts.statusApproved'
    case 'rejected':
      return 'hrShifts.statusRejected'
    case 'cancelled':
      return 'hrShifts.statusCancelled'
    default:
      return 'hrShifts.statusRequested'
  }
}

export function swapStatusTone(status: string | null | undefined): StatusTone {
  switch ((status || '').trim().toLowerCase()) {
    case 'requested':
      return 'yellow'
    case 'approved':
      return 'green'
    case 'rejected':
      return 'pink'
    case 'cancelled':
      return 'neutral'
    default:
      return 'yellow'
  }
}

export function shiftStatusLabelKey(status: string | null | undefined): string {
  switch ((status || '').trim().toLowerCase()) {
    case 'scheduled':
      return 'hrShifts.shiftScheduled'
    case 'cancelled':
      return 'hrShifts.shiftCancelled'
    case 'conflicted':
    case 'reconciliation_required':
      return 'hrShifts.shiftConflicted'
    default:
      return 'hrShifts.shiftScheduled'
  }
}

export function composeNeedsAttention(swaps: ShiftSwap[]): ShiftsAttentionItem[] {
  return swaps
    .filter((swap) => (swap.status || '').toLowerCase() === 'requested')
    .map((swap) => ({
      kind: 'shift_swap' as const,
      id: swap.swap_id,
      swap,
    }))
}

export function swapListSubtitle(
  swap: ShiftSwap,
  t: (k: string, p?: Record<string, string | number>) => string,
): string {
  const target = swap.replacement?.name
  const parts = [target ? t('hrShifts.withTarget', { name: target }) : null, swap.reason].filter(
    Boolean,
  )
  return parts.join(' · ')
}

export function formatShiftLine(
  shift: Shift | null | undefined,
  locale: string,
  formatDate: (iso: string, locale: string) => string,
  formatRange: (start: string | null, end: string | null, locale?: string) => string,
): string {
  if (!shift) return '—'
  const date = shift.shift_date || (shift.starts_at ? shift.starts_at.slice(0, 10) : null)
  const dateLabel = date ? formatDate(date, locale) : null
  const time = formatRange(shift.starts_at || null, shift.ends_at || null, locale)
  return [dateLabel, time, shift.location, shift.role].filter(Boolean).join(' · ')
}

/** Demo builders live beside composition for import locality in views. */
export function buildShiftsDemoModel(todayIso: string): {
  source: typeof SHIFTS_DEMO_SOURCE
  attention: ShiftsAttentionItem[]
  today: Shift[]
} {
  const tomorrow = shiftDay(todayIso, 1)
  const swapId = (s: string) => `${SHIFTS_DEMO_ID_PREFIX}${s}`
  const shiftId = (s: string) => `${SHIFTS_DEMO_SHIFT_PREFIX}${s}`

  const reqShiftA: Shift = {
    shift_id: shiftId('req-a'),
    employee: {
      name: 'Sara Al-Mutairi',
      employee_key: 'demo-sara',
      position_title: 'Store Manager',
      department: 'Retail',
    },
    status: 'scheduled',
    shift_date: tomorrow,
    starts_at: `${tomorrow}T09:00:00+03:00`,
    ends_at: `${tomorrow}T17:00:00+03:00`,
    location: 'Salmiya Branch',
    role: 'operations',
    allowed_actions: ['read'],
  }
  const tgtShiftA: Shift = {
    shift_id: shiftId('tgt-a'),
    employee: {
      name: 'Noura Hassan',
      employee_key: 'demo-noura',
      position_title: 'Sales Associate',
      department: 'Sales',
    },
    status: 'scheduled',
    shift_date: tomorrow,
    starts_at: `${tomorrow}T12:00:00+03:00`,
    ends_at: `${tomorrow}T20:00:00+03:00`,
    location: 'Salmiya Branch',
    role: 'guest',
    allowed_actions: ['read'],
  }

  const reqShiftB: Shift = {
    shift_id: shiftId('req-b'),
    employee: {
      name: 'Ahmed Darwish',
      employee_key: 'demo-ahmed',
      position_title: 'Customer Care',
      department: 'Support',
    },
    status: 'scheduled',
    shift_date: todayIso,
    starts_at: `${todayIso}T14:00:00+03:00`,
    ends_at: `${todayIso}T22:00:00+03:00`,
    location: 'HQ Support Floor',
    role: 'night',
    allowed_actions: ['read'],
  }
  const tgtShiftB: Shift = {
    shift_id: shiftId('tgt-b'),
    employee: {
      name: 'Layla Farid',
      employee_key: 'demo-layla',
      position_title: 'Sales Associate',
      department: 'Sales',
    },
    status: 'scheduled',
    shift_date: todayIso,
    starts_at: `${todayIso}T08:00:00+03:00`,
    ends_at: `${todayIso}T16:00:00+03:00`,
    location: 'HQ Support Floor',
    role: 'general',
    allowed_actions: ['read'],
  }

  const swaps: ShiftSwap[] = [
    {
      swap_id: swapId('1'),
      requester: reqShiftA.employee,
      replacement: tgtShiftA.employee,
      status: 'requested',
      shift_date: tomorrow,
      starts_at: reqShiftA.starts_at,
      ends_at: reqShiftA.ends_at,
      reason: 'Family appointment — covering each other’s mid-shift',
      requester_shift_id: reqShiftA.shift_id,
      target_shift_id: tgtShiftA.shift_id,
      requester_shift: reqShiftA,
      target_shift: tgtShiftA,
      requested_at: `${todayIso}T08:15:00+03:00`,
      allowed_actions: ['approve', 'reject'],
      destination: `/shift-swaps/${swapId('1')}`,
    },
    {
      swap_id: swapId('2'),
      requester: reqShiftB.employee,
      replacement: tgtShiftB.employee,
      status: 'requested',
      shift_date: todayIso,
      starts_at: reqShiftB.starts_at,
      ends_at: reqShiftB.ends_at,
      reason: 'Swap evening coverage for morning preference',
      requester_shift_id: reqShiftB.shift_id,
      target_shift_id: tgtShiftB.shift_id,
      requester_shift: reqShiftB,
      target_shift: tgtShiftB,
      requested_at: `${todayIso}T07:40:00+03:00`,
      allowed_actions: ['approve', 'reject'],
      destination: `/shift-swaps/${swapId('2')}`,
    },
  ]

  const today: Shift[] = [
    {
      shift_id: shiftId('today-1'),
      employee: {
        name: 'Bilal Chowdhury',
        employee_key: 'demo-bilal',
        position_title: 'Warehouse Operative',
        department: 'Warehouse',
      },
      status: 'scheduled',
      shift_date: todayIso,
      starts_at: `${todayIso}T08:00:00+03:00`,
      ends_at: `${todayIso}T16:00:00+03:00`,
      location: 'Shuwaikh Warehouse',
      role: 'operations',
      allowed_actions: ['read'],
    },
    {
      shift_id: shiftId('today-2'),
      employee: {
        name: 'Omar Al-Sabah',
        employee_key: 'demo-omar',
        position_title: 'Shift Lead',
        department: 'Retail',
      },
      status: 'scheduled',
      shift_date: todayIso,
      starts_at: `${todayIso}T10:00:00+03:00`,
      ends_at: `${todayIso}T18:00:00+03:00`,
      location: 'Avenues Store',
      role: 'guest',
      allowed_actions: ['read'],
    },
    {
      ...reqShiftB,
      shift_id: shiftId('today-3'),
    },
    {
      ...tgtShiftB,
      shift_id: shiftId('today-4'),
    },
  ]

  return {
    source: SHIFTS_DEMO_SOURCE,
    attention: composeNeedsAttention(swaps),
    today,
  }
}

function shiftDay(iso: string, delta: number): string {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + delta)
  return d.toISOString().slice(0, 10)
}
