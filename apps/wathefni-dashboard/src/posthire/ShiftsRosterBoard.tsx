import { CalendarClock, Plus } from 'lucide-react'
import { useMemo } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { shiftStatusLabel, shiftsCopy, type ShiftsLocale } from '@/posthire/shiftsUx'
import {
  shiftStateRailClass,
  shiftStateSurfaceClass,
  shiftStateTextClass,
} from '@/posthire/visualBaseline'
import type { PosthireShiftRow } from '@/types'

export type ShiftBoardItem = PosthireShiftRow & { spanMarker?: boolean }

type RosterRow = {
  key: string
  label: string
  site?: string
  team?: string
  weeklyMinutes: number
}

type Props = {
  shifts: PosthireShiftRow[]
  days: Date[]
  anchor: Date
  locale: ShiftsLocale
  isMobile: boolean
  coldLoading: boolean
  canManage: boolean
  selectedId: string | null
  onSelect: (shift: PosthireShiftRow) => void
  onCreate: (day?: Date, employeeName?: string) => void
  onSelectDay: (day: Date) => void
}

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function addDays(d: Date, n: number) {
  const next = new Date(d)
  next.setDate(next.getDate() + n)
  return next
}

function startOfWeek(d: Date) {
  const next = startOfDay(d)
  return addDays(next, -next.getDay())
}

function isoDate(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function parseDate(raw?: string | null) {
  const value = String(raw || '').slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function timeMinutes(raw?: string | null) {
  const [hour, minute] = String(raw || '00:00').slice(0, 5).split(':').map(Number)
  return hour * 60 + minute
}

export function shiftDuration(shift: PosthireShiftRow) {
  const start = timeMinutes(shift.start_time)
  let end = timeMinutes(shift.end_time)
  if (shift.ends_next_day || shift.is_overnight || end <= start) end += 24 * 60
  return Math.max(0, end - start)
}

function overlaps(a: ShiftBoardItem, b: ShiftBoardItem) {
  if (a.spanMarker || b.spanMarker) return false
  const aStart = timeMinutes(a.start_time)
  const bStart = timeMinutes(b.start_time)
  let aEnd = timeMinutes(a.end_time)
  let bEnd = timeMinutes(b.end_time)
  if (a.ends_next_day || a.is_overnight || aEnd <= aStart) aEnd += 24 * 60
  if (b.ends_next_day || b.is_overnight || bEnd <= bStart) bEnd += 24 * 60
  return aStart < bEnd && bStart < aEnd
}

export function cellHasOverlap(items: ShiftBoardItem[]) {
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      if (overlaps(items[i], items[j])) return true
    }
  }
  return false
}

function initials(label: string) {
  return label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

function roleLine(shift: PosthireShiftRow) {
  const raw = String(shift.role || '').trim()
  if (!raw || raw === '—' || raw === '-') return ''
  return raw
}

function locationLine(shift: PosthireShiftRow, rowSite?: string) {
  const location = String(shift.location || '').trim()
  const site = String(shift.site_key || '').trim()
  const row = String(rowSite || '').trim().toLowerCase()
  if (location && location.toLowerCase() !== row) return location
  if (site && site.toLowerCase() !== row) return site
  return ''
}

function isExceptional(shift: PosthireShiftRow) {
  const state = String(shift.ui_state || shift.status || '').toLowerCase()
  return state === 'conflicted' || state === 'reconciliation_required' || state === 'cancelled'
}

export function buildShiftDayMap(shifts: PosthireShiftRow[]) {
  const map = new Map<string, ShiftBoardItem[]>()
  for (const shift of shifts) {
    const employee = String(shift.employee_key || shift.employee_name || '')
    const date = String(shift.shift_date || '').slice(0, 10)
    const key = `${employee}|${date}`
    map.set(key, [...(map.get(key) || []), shift])
    if (shift.ends_next_day || shift.is_overnight) {
      const parsed = parseDate(date)
      if (!parsed) continue
      const nextKey = `${employee}|${isoDate(addDays(parsed, 1))}`
      const continuation = map.get(nextKey) || []
      if (!continuation.some((item) => item.shift_id === shift.shift_id && item.spanMarker)) {
        map.set(nextKey, [...continuation, { ...shift, spanMarker: true }])
      }
    }
  }
  for (const [key, items] of map) {
    map.set(
      key,
      [...items].sort((a, b) => timeMinutes(a.start_time) - timeMinutes(b.start_time)),
    )
  }
  return map
}

function WeekShiftTile({
  shift,
  locale,
  selected,
  overlap,
  rowSite,
  onSelect,
}: {
  shift: ShiftBoardItem
  locale: ShiftsLocale
  selected: boolean
  overlap: boolean
  rowSite?: string
  onSelect: () => void
}) {
  const c = shiftsCopy(locale)
  const start = String(shift.start_time || '').slice(0, 5)
  const end = String(shift.end_time || '').slice(0, 5)
  const state = shift.ui_state || shift.status || 'scheduled'
  const overnight = Boolean(shift.ends_next_day || shift.is_overnight)
  const continuation = Boolean(shift.spanMarker)
  const exceptional = isExceptional(shift)
  const status = exceptional ? shiftStatusLabel(state, locale) : ''
  const timeLabel = continuation
    ? `${start}–${end}`
    : overnight
      ? `${start}–${end}`
      : `${start}–${end}`
  const place = continuation ? '' : locationLine(shift, rowSite)

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'relative min-w-0 overflow-hidden rounded-[0.62rem] border-0 px-2.5 py-2 text-start transition hover:-translate-y-px hover:brightness-[0.99]',
        shiftStateSurfaceClass(shift),
        continuation && 'rounded-s-[0.2rem]',
        overnight && !continuation && 'rounded-e-[0.2rem]',
        selected && 'ring-2 ring-wf-ink/30',
        overlap && 'px-2 py-1.5',
      )}
      data-testid="shift-block"
      data-shifts-week-tile
      data-shift-state={String(state).toLowerCase()}
      data-shift-assignment-type={String(shift.assignment_type || 'general').toLowerCase()}
      data-shift-continuation={continuation ? 'true' : 'false'}
    >
      <span
        className={cn(
          'absolute inset-y-1.5 start-1 w-[3px] rounded-full',
          shiftStateRailClass(shift),
          continuation && 'inset-y-0 start-0 w-1 rounded-none',
        )}
        aria-hidden
      />
      <span className="flex min-w-0 flex-wrap items-baseline justify-between gap-1">
        <span
          className={cn(
            'text-[11px] font-bold leading-none tracking-[-0.02em] [font-variant-numeric:tabular-nums]',
            overlap && 'text-[10px]',
          )}
        >
          {timeLabel}
        </span>
        {status ? (
          <span
            className={cn(
              'shrink-0 truncate text-[8px] font-bold uppercase tracking-[0.05em]',
              shiftStateTextClass(shift),
              overlap && 'max-w-[3.5rem] text-[7px]',
            )}
          >
            {status}
          </span>
        ) : overnight && !continuation ? (
          <span className={cn('shrink-0 text-[8px] font-semibold opacity-75', overlap && 'text-[7px]')}>{c.nextDay}</span>
        ) : null}
      </span>
      {continuation ? (
        <span className={cn('mt-1 block truncate text-[10px] font-semibold leading-tight', overlap && 'text-[9px]')}>
          {c.nextDay}
        </span>
      ) : roleLine(shift) ? (
        <span className={cn('mt-1 block truncate text-[10px] font-semibold leading-tight', overlap && 'text-[9px]')}>
          {roleLine(shift)}
        </span>
      ) : null}
      {!overlap && place ? (
        <span className="mt-0.5 block truncate text-[8px] leading-tight opacity-65">{place}</span>
      ) : null}
    </button>
  )
}

function RosterIdentity({ row, compact = false }: { row: RosterRow; compact?: boolean }) {
  const palette = [
    'bg-wf-accent-priority-soft text-wf-accent-priority-ink',
    'bg-wf-accent-follow-soft text-wf-accent-follow-ink',
    'bg-wf-accent-assess-soft text-wf-accent-assess-ink',
  ]
  const tone = palette[Math.abs(row.key.length) % palette.length]
  const hours = (row.weeklyMinutes / 60).toFixed(row.weeklyMinutes % 60 ? 1 : 0)
  return (
    <div
      className={cn(
        'grid min-w-0 items-center gap-2.5',
        compact ? 'grid-cols-[2rem_minmax(0,1fr)]' : 'grid-cols-[2.25rem_minmax(0,1fr)]',
      )}
      data-shifts-identity
    >
      <span className={cn('grid h-8 w-8 place-items-center rounded-[0.75rem] text-[10px] font-bold', tone)}>
        {initials(row.label)}
      </span>
      <span className="min-w-0">
        <span className="flex items-center justify-between gap-1">
          <span className="truncate text-[13px] font-semibold tracking-[-0.015em] text-ink">{row.label}</span>
          {!compact ? (
            <span className="shrink-0 rounded-md bg-wf-ink/[0.05] px-1.5 py-0.5 text-[9px] font-semibold text-muted [font-variant-numeric:tabular-nums]">
              {hours}h
            </span>
          ) : null}
        </span>
        {row.site || row.team ? (
          <span className="mt-0.5 block truncate text-[10px] text-muted">
            {[row.team, row.site].filter(Boolean).join(' · ')}
          </span>
        ) : null}
      </span>
    </div>
  )
}

function DayAgendaShift({
  shift,
  locale,
  selected,
  rowSite,
  onSelect,
}: {
  shift: ShiftBoardItem
  locale: ShiftsLocale
  selected: boolean
  rowSite?: string
  onSelect: () => void
}) {
  return (
    <WeekShiftTile
      shift={shift}
      locale={locale}
      selected={selected}
      overlap={false}
      rowSite={rowSite}
      onSelect={onSelect}
    />
  )
}

function LoadingRoster({ locale }: { locale: ShiftsLocale }) {
  const c = shiftsCopy(locale)
  return (
    <div className="min-w-[1080px]" data-shifts-roster-loading aria-label={c.loading}>
      {Array.from({ length: 4 }, (_, row) => (
        <div
          key={row}
          className="grid grid-cols-[240px_repeat(7,minmax(124px,1fr))] gap-[3px] border-t border-wf-ink/[0.05] px-3"
        >
          <div className="flex min-h-24 items-center gap-2 bg-wf-surface-raised py-3 pe-3">
            <span className="h-8 w-8 animate-pulse rounded-[0.7rem] bg-wf-canvas" />
            <span className="h-3 w-24 animate-pulse rounded bg-wf-canvas" />
          </div>
          {Array.from({ length: 7 }, (_, day) => (
            <div key={day} className={cn('min-h-24 p-2', day === 2 ? 'bg-wf-ink/[0.04]' : 'bg-wf-frame/35')}>
              {(row + day) % 3 === 0 ? <span className="block h-10 animate-pulse rounded-lg bg-wf-canvas/70" /> : null}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export function ShiftsRosterBoard({
  shifts,
  days,
  anchor,
  locale,
  isMobile,
  coldLoading,
  canManage,
  selectedId,
  onSelect,
  onCreate,
  onSelectDay,
}: Props) {
  const c = shiftsCopy(locale)
  const isAr = locale === 'ar'
  const weekDays = useMemo(() => {
    const start = startOfWeek(anchor)
    return Array.from({ length: 7 }, (_, index) => addDays(start, index))
  }, [anchor])

  const rosterRows = useMemo(() => {
    const rows = new Map<string, RosterRow>()
    for (const shift of shifts) {
      const key = String(shift.employee_key || shift.employee_name || shift.shift_id || '')
      if (!key) continue
      const current = rows.get(key)
      const nextMinutes = current?.weeklyMinutes || 0
      rows.set(key, {
        key,
        label: String(shift.employee_name || shift.employee_key || '—'),
        site: shift.site_key || current?.site,
        team: shift.team_key || current?.team,
        weeklyMinutes: nextMinutes + shiftDuration(shift),
      })
    }
    return [...rows.values()].sort((a, b) => a.label.localeCompare(b.label))
  }, [shifts])

  const shiftsByEmployeeDay = useMemo(() => {
    return buildShiftDayMap(shifts)
  }, [shifts])

  const selectedDay = days[0] || anchor
  const selectedDayKey = isoDate(selectedDay)

  if (isMobile) {
    return (
      <div data-shifts-mobile-agenda>
        <div className="mb-3 grid grid-cols-7 gap-1" data-shifts-day-strip>
          {weekDays.map((day) => {
            const active = isoDate(day) === selectedDayKey
            return (
              <button
                key={isoDate(day)}
                type="button"
                onClick={() => onSelectDay(day)}
                className={cn(
                  'rounded-[0.7rem] px-1 py-2 text-center text-[9px] font-semibold',
                  active ? 'bg-wf-ink text-white' : 'bg-wf-ink/[0.045] text-muted',
                )}
              >
                <span className="block text-[8px] uppercase tracking-[0.05em]">
                  {day.toLocaleDateString(isAr ? 'ar' : 'en', { weekday: 'short' })}
                </span>
                <span className="mt-1 block text-[11px]">{day.getDate()}</span>
              </button>
            )
          })}
        </div>
        <div className="overflow-hidden rounded-[1.1rem] bg-wf-surface-raised">
          <div className="flex items-center justify-between px-4 py-3">
            <h3 className="text-[15px] font-semibold tracking-[-0.02em] text-ink">
              {selectedDay.toLocaleDateString(isAr ? 'ar' : 'en', {
                weekday: 'long',
                month: 'long',
                day: 'numeric',
              })}
            </h3>
            {canManage ? (
              <button type="button" className="text-[11px] font-semibold text-muted" onClick={() => onCreate(selectedDay)}>
                {isAr ? 'إضافة' : 'Add'}
              </button>
            ) : null}
          </div>
          {coldLoading ? (
            <div className="space-y-3 border-t border-wf-ink/[0.06] p-4">
              {Array.from({ length: 3 }, (_, index) => (
                <div key={index} className="h-16 animate-pulse rounded-xl bg-wf-canvas/60" />
              ))}
            </div>
          ) : rosterRows.length === 0 ? (
            <div className="border-t border-wf-ink/[0.06] p-5" data-shifts-empty>
              <p className="text-[14px] font-semibold text-ink">{c.emptyBoardTitle}</p>
              <p className="mt-1 text-[11px] text-muted">{c.emptyBoardHint}</p>
              {canManage ? (
                <Button className="mt-3" size="sm" onClick={() => onCreate(selectedDay)}>
                  <Plus className="h-4 w-4" /> {c.schedule}
                </Button>
              ) : null}
            </div>
          ) : (
            rosterRows.map((row) => {
              const items = shiftsByEmployeeDay.get(`${row.key}|${selectedDayKey}`) || []
              if (items.length === 0) return null
              const overlap = cellHasOverlap(items)
              return (
                <div
                  key={row.key}
                  className="grid grid-cols-[3.1rem_minmax(0,1fr)] gap-2.5 border-t border-wf-ink/[0.06] px-4 py-3"
                >
                  <div className="pt-0.5">
                    <RosterIdentity row={row} compact />
                  </div>
                  <div className={cn('grid gap-1.5', overlap && 'grid-cols-2')}>
                    {items.map((shift, index) => (
                      <DayAgendaShift
                        key={`${shift.shift_id || index}-${shift.spanMarker ? 'continuation' : 'shift'}`}
                        shift={shift}
                        locale={locale}
                        selected={selectedId === shift.shift_id}
                        rowSite={row.site}
                        onSelect={() => onSelect(shift)}
                      />
                    ))}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto" data-shifts-roster-grid>
      <div className="min-w-[1080px]">
        <div className="sticky top-0 z-[4] grid grid-cols-[240px_repeat(7,minmax(124px,1fr))] gap-[3px] bg-wf-surface-raised/95 px-3 pb-2 pt-3 backdrop-blur-sm">
          <div className="sticky start-3 z-[6] self-center bg-wf-surface-raised/95 ps-1 text-[9px] font-semibold uppercase tracking-[0.1em] text-muted">
            {c.employee}
          </div>
          {days.map((day) => {
            const today = isoDate(startOfDay(new Date())) === isoDate(day)
            return (
              <div key={isoDate(day)} className="flex min-h-11 items-center justify-center">
                <div
                  className={cn(
                    'min-w-[3rem] rounded-[0.75rem] px-2 py-1.5 text-center',
                    today ? 'bg-wf-ink text-white' : 'text-ink',
                  )}
                >
                  <span className="block text-[9px] font-bold uppercase tracking-[0.07em]">
                    {day.toLocaleDateString(isAr ? 'ar' : 'en', { weekday: 'short' })}
                  </span>
                  <span className={cn('mt-0.5 block text-[11px] font-semibold', today ? 'text-white/75' : 'text-muted')}>
                    {day.getDate()}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        {coldLoading ? (
          <LoadingRoster locale={locale} />
        ) : rosterRows.length === 0 ? (
          <div
            className="grid grid-cols-[240px_repeat(7,minmax(124px,1fr))] gap-[3px] border-t border-wf-ink/[0.05] px-3"
            data-shifts-empty
          >
            <div className="sticky start-3 z-[2] flex min-h-28 items-center gap-2.5 bg-wf-surface-raised py-3 pe-3">
              <span className="grid h-8 w-8 place-items-center rounded-[0.7rem] bg-wf-canvas text-muted">
                <CalendarClock className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-[12px] font-semibold text-ink">{c.emptyBoardTitle}</span>
                <span className="mt-0.5 block text-[9px] text-muted">{c.emptyBoardHint}</span>
              </span>
            </div>
            {days.map((day) => (
              <div
                key={isoDate(day)}
                className="flex min-h-28 items-center justify-center bg-wf-frame/25 px-1.5 py-2"
                data-shifts-day-lane
              >
                {canManage ? (
                  <button
                    type="button"
                    className="flex h-7 items-center gap-1 rounded-lg border border-dashed border-wf-ink/20 px-2.5 text-[10px] font-medium text-muted hover:border-wf-ink/40 hover:bg-wf-surface hover:text-ink transition"
                    onClick={() => onCreate(day)}
                  >
                    <Plus className="h-3 w-3" />
                    {isAr ? 'جدولة' : 'Schedule'}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          rosterRows.map((row) => (
            <div
              key={row.key}
              className="grid grid-cols-[240px_repeat(7,minmax(124px,1fr))] gap-[3px] border-t border-wf-ink/[0.05] px-3"
              data-shifts-roster-row
            >
              <div className="sticky start-3 z-[3] flex min-h-24 items-center bg-wf-surface-raised/95 py-3 pe-3 backdrop-blur-sm">
                <RosterIdentity row={row} />
              </div>
              {days.map((day) => {
                const date = isoDate(day)
                const items = shiftsByEmployeeDay.get(`${row.key}|${date}`) || []
                const today = isoDate(startOfDay(new Date())) === date
                const overlap = cellHasOverlap(items)
                return (
                  <div
                    key={date}
                    className={cn(
                      'min-h-24 bg-wf-frame/25 px-1.5 py-2',
                      today && 'bg-wf-ink/[0.045]',
                    )}
                    data-shifts-day-lane
                  >
                    <div className={cn('grid gap-1.5', overlap && 'grid-cols-2')} data-shifts-overlap={overlap ? 'true' : 'false'}>
                      {items.map((shift, index) => (
                        <WeekShiftTile
                          key={`${shift.shift_id || index}-${shift.spanMarker ? 'continuation' : 'shift'}`}
                          shift={shift}
                          locale={locale}
                          selected={selectedId === shift.shift_id}
                          overlap={overlap}
                          rowSite={row.site}
                          onSelect={() => onSelect(shift)}
                        />
                      ))}
                      {canManage && items.length === 0 ? (
                        <button
                          type="button"
                          className="flex min-h-7 items-center justify-center gap-1 rounded-lg border border-dashed border-wf-ink/15 text-[9px] font-medium text-muted opacity-0 transition hover:border-wf-ink/30 hover:bg-wf-surface hover:opacity-100 hover:text-ink focus:opacity-100"
                          onClick={() => onCreate(day, row.label)}
                        >
                          <Plus className="h-3 w-3" />
                          {isAr ? 'إضافة' : 'Add'}
                        </button>
                      ) : null}
                    </div>
                  </div>
                )
              })}
            </div>
          ))
        )}

        <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-[9px] text-muted" data-shifts-legend>
          {[
            ['bg-wf-accent-review', c.assignmentGuest],
            ['bg-wf-accent-priority', c.assignmentOperations],
            ['bg-wf-accent-assess', c.assignmentEvent],
            ['bg-wf-accent-follow', c.assignmentNight],
            ['bg-wf-ink/35', c.assignmentGeneral],
            ['bg-wf-accent-review-ink', c.statusConflictShort],
          ].map(([tone, label]) => (
            <span key={label} className="inline-flex items-center gap-1">
              <span className={cn('h-[3px] w-3 rounded-full', tone)} /> {label}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

