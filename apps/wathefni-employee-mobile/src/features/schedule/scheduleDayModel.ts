/**
 * Schedule day navigation over the existing `/app/workday` payload.
 *
 * Contract honesty (do not invent beyond this):
 * - `today.entries` — expected+recorded paired for Kuwait today only
 * - `upcoming` — shifts from tomorrow through today+window (no attendance)
 * - `recent` — attendance in the last `window.days`, excluding today (no shift roster)
 * - Outside that window the payload has no facts; the UI must say so
 */

import type { WorkdayEntry, WorkdayRecorded, WorkdayResponse, WorkdayScheduled } from '@/api/types'

export type DayRelation = 'today' | 'past' | 'future'

export type SelectedDayModel = {
  date: string
  isToday: boolean
  relation: DayRelation
  /** True when the date is inside the workday fetch window we can speak about. */
  inWindow: boolean
  /** Paired or single-sided entries for the selected-day panel. */
  entries: WorkdayEntry[]
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/** Add whole calendar days to a `YYYY-MM-DD` string without device-zone drift. */
export function addDaysISO(iso: string, delta: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + delta))
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`
}

export function weekdayUTC(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay()
}

/**
 * First day of the week for the employee locale.
 * English: Sunday. Arabic (Kuwait): Saturday.
 */
export function firstWeekdayForLocale(locale: string): number {
  return locale === 'ar' ? 6 : 0
}

export function startOfWeekISO(iso: string, firstDay: number): string {
  const dow = weekdayUTC(iso)
  const delta = (dow - firstDay + 7) % 7
  return addDaysISO(iso, -delta)
}

export function buildWeekDays(weekStart: string): string[] {
  return Array.from({ length: 7 }, (_, i) => addDaysISO(weekStart, i))
}

/** Weeks covering [today - pastDays, today + futureDays], aligned to locale week starts. */
export function buildWeekStarts(today: string, pastDays: number, futureDays: number, firstDay: number): string[] {
  const from = startOfWeekISO(addDaysISO(today, -pastDays), firstDay)
  const to = startOfWeekISO(addDaysISO(today, futureDays), firstDay)
  const weeks: string[] = []
  let cursor = from
  // Hard cap avoids runaway loops on bad input.
  for (let i = 0; i < 24; i += 1) {
    weeks.push(cursor)
    if (cursor === to) break
    cursor = addDaysISO(cursor, 7)
  }
  return weeks
}

/** Dates that carry a real shift or attendance fact in the current payload. */
export function presenceDates(data: WorkdayResponse): Set<string> {
  const set = new Set<string>()
  if (data.today.entries.length) set.add(data.date)
  for (const entry of data.today.entries) {
    if (entry.scheduled?.date) set.add(String(entry.scheduled.date).slice(0, 10))
    if (entry.recorded?.date) set.add(String(entry.recorded.date).slice(0, 10))
  }
  for (const shift of data.upcoming ?? []) {
    if (shift.date) set.add(String(shift.date).slice(0, 10))
  }
  for (const record of data.recent ?? []) {
    if (record.date) set.add(String(record.date).slice(0, 10))
  }
  return set
}

function windowBounds(data: WorkdayResponse): { past: string; future: string; days: number } {
  const days = Math.max(1, Number(data.window?.days ?? 30))
  return {
    days,
    past: addDaysISO(data.date, -days),
    future: addDaysISO(data.date, days),
  }
}

/** Normalize attendance scheduled_* (ISO or HH:MM) into HH:MM for formatTimeRange. */
export function kuwaitWallClockHm(value: string | null | undefined): string | null {
  if (!value) return null
  const raw = String(value).trim()
  if (/^\d{1,2}:\d{2}/.test(raw)) return raw.slice(0, 5).padStart(5, '0')
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return null
  const parts = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kuwait',
  }).formatToParts(d)
  const hour = parts.find((p) => p.type === 'hour')?.value
  const minute = parts.find((p) => p.type === 'minute')?.value
  if (!hour || !minute) return null
  return `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
}

function pastEntryFromRecord(record: WorkdayRecorded): WorkdayEntry {
  const start = kuwaitWallClockHm(record.scheduled_start)
  const end = kuwaitWallClockHm(record.scheduled_end)
  const hasExpected = Boolean(start || end)
  const scheduled: WorkdayScheduled | null = hasExpected
    ? {
        shift_id: record.shift_id,
        date: record.date,
        start_time: start,
        end_time: end,
        status: record.status,
        role: null,
        location: null,
        timezone: 'Asia/Kuwait',
        notes: null,
      }
    : null
  return {
    kind: scheduled ? 'scheduled' : 'recorded_only',
    scheduled,
    recorded: record,
  }
}

function futureEntryFromShift(shift: WorkdayScheduled): WorkdayEntry {
  return {
    kind: 'scheduled',
    scheduled: shift,
    recorded: null,
  }
}

/**
 * Resolve what the selected-day panel may honestly show from one `/app/workday` response.
 */
export function resolveSelectedDay(data: WorkdayResponse, selectedDate: string): SelectedDayModel {
  const date = String(selectedDate || '').slice(0, 10)
  const today = data.date
  const { past, future } = windowBounds(data)
  const isToday = date === today
  const relation: DayRelation = isToday ? 'today' : date < today ? 'past' : 'future'
  const inWindow = isToday || (date >= past && date <= future)

  if (!inWindow) {
    return { date, isToday, relation, inWindow: false, entries: [] }
  }

  if (isToday) {
    return { date, isToday: true, relation: 'today', inWindow: true, entries: data.today.entries }
  }

  if (relation === 'future') {
    const shifts = (data.upcoming ?? []).filter((s) => String(s.date).slice(0, 10) === date)
    return {
      date,
      isToday: false,
      relation: 'future',
      inWindow: true,
      entries: shifts.map(futureEntryFromShift),
    }
  }

  const records = (data.recent ?? []).filter((r) => String(r.date).slice(0, 10) === date)
  return {
    date,
    isToday: false,
    relation: 'past',
    inWindow: true,
    entries: records.map(pastEntryFromRecord),
  }
}
