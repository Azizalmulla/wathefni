import { useQueryClient } from '@tanstack/react-query'
import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  BriefcaseBusiness,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  Loader2,
  MapPin,
  Phone,
  Plus,
  UsersRound,
  Video,
  X,
} from 'lucide-react'

import { PeoplePicker } from '@/components/PeoplePicker'
import { Button } from '@/components/ui/button'
import { useBodyScrollLock, useOverlayFocus } from '@/hooks/useOverlayA11y'
import {
  cancelCalendarEvent,
  createCalendarEvent,
  DashboardApiError,
  getCalendarTeamScopes,
  inviteCalendarGuest,
  previewCalendarConflicts,
  resolveCalendarRescheduleRequest,
  rsvpCalendarEvent,
  updateCalendarEvent,
  type CalendarConflict,
  type CalendarEvent,
} from '@/lib/api'
import {
  useCalendarEventQuery,
  useCalendarEventSyncQuery,
  useCalendarEventsQuery,
  useCalendarRescheduleQuery,
  useCalendarTeamScopesQuery,
} from '@/lib/query/hooks'
import { invalidate } from '@/lib/query/invalidation'
import { qk } from '@/lib/query/keys'
import { fetchCalendarEvents } from '@/lib/query/fetchers'
import type { DashboardAccess } from '@/types'

type Scope = 'mine' | 'team' | 'company'
type ViewMode = 'day' | 'week' | 'month'

type Props = {
  access: DashboardAccess
  canManage: boolean
  canCompany: boolean
  canOverride?: boolean
  locale?: 'en' | 'ar'
  onNotice?: (text: string, kind?: 'success' | 'error') => void
  onOpenInterview?: (interviewId: string) => void
  onOpenProjectionOwner?: (link: CalendarProjectionDeepLink) => void
}

type Draft = {
  event_id?: string
  expected_version?: number
  event_type: string
  title: string
  visibility: string
  start_local: string
  end_local: string
  timezone: string
  all_day: boolean
  location: string
  meeting_url: string
  attendee_user_id: string
  guest_email: string
  override_conflicts: boolean
  override_reason: string
}

const HOURS = Array.from({ length: 14 }, (_, i) => i + 7) // 07–20
export const CALENDAR_DAY_START_HOUR = 7
export const CALENDAR_DAY_END_HOUR = 21 // exclusive (last painted hour is 20:00)
export const CALENDAR_HOUR_PX = 64
/** Readable floor for timed cards (title + time). */
export const CALENDAR_MIN_EVENT_HEIGHT_PX = 40

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function startOfDay(d: Date) {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

function addDays(d: Date, n: number) {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

function startOfWeek(d: Date) {
  // Sunday-start (Kuwait-friendly)
  const x = startOfDay(d)
  x.setDate(x.getDate() - x.getDay())
  return x
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function toLocalInput(iso?: string) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromLocalInput(value: string) {
  const d = new Date(value)
  return d.toISOString()
}

function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function stripPreviewLabel(title: string) {
  return String(title || '')
    .replace(/^(Preview|معاينة)\s*[·•\-–—]\s*/i, '')
    .replace(/^(Preview|معاينة)\s+/i, '')
    .trim()
}

function eventTitle(event: CalendarEvent, isAr: boolean) {
  // Only privacy-redacted busy_only rows hide the title — not every OOO/busy flag.
  if (event.detail_level === 'busy_only') return isAr ? 'مشغول' : 'Busy'
  const raw = isAr && event.title_ar ? event.title_ar : event.title || (isAr ? 'حدث' : 'Event')
  return stripPreviewLabel(raw)
}

/** Human-readable primary line: type · subject/person (time rendered separately). */
export function eventPrimaryLabel(event: CalendarEvent, isAr: boolean) {
  const title = eventTitle(event, isAr)
  if (event.detail_level === 'busy_only' || event.busy) return title
  if (/[·•]/.test(title)) return title
  const type = eventTypeLabel(event.event_type, isAr)
  const cat = previewCategoryLabel(String(event.metadata?.preview_category || ''), isAr)
  const lead = cat || type
  if (!lead) return title
  if (title.toLowerCase().startsWith(lead.toLowerCase())) return title
  return `${lead} · ${title}`
}

function statusChip(status?: string, isAr?: boolean) {
  const s = (status || 'confirmed').toLowerCase()
  if (s === 'cancelled') return isAr ? 'ملغى' : 'Cancelled'
  if (s === 'completed') return isAr ? 'مكتمل' : 'Completed'
  if (s === 'tentative') return isAr ? 'مبدئي' : 'Tentative'
  return isAr ? 'مؤكد' : 'Confirmed'
}

/** Category fill uses shared Wathefni tokens. Soft edge — never transparent-only. */
export function eventSurfaceClass(event: CalendarEvent) {
  const type = String(event.event_type || event.authority || '').toLowerCase()
  const status = String(event.status || '').toLowerCase()
  const previewCategory = String(event.metadata?.preview_category || '').toLowerCase()
  if (status === 'cancelled') {
    return 'border-line/45 bg-wf-accent-paused-soft text-wf-accent-paused-ink'
  }
  if (
    type.includes('interview')
    || previewCategory === 'interview'
    || previewCategory === 'video_interview'
    || event.interview_managed
    || event.authority === 'interview'
  ) {
    return 'border-line/45 bg-wf-accent-follow-soft text-wf-accent-follow-ink'
  }
  if (
    type.includes('deadline')
    || type.includes('assessment')
    || previewCategory === 'candidate_followup'
    || previewCategory === 'compliance_expiry'
    || previewCategory === 'onboarding_deadline'
    || previewCategory === 'payroll_cutoff'
  ) {
    return 'border-line/45 bg-wf-accent-review-soft text-wf-accent-review-ink'
  }
  if (previewCategory === 'employee_start' || previewCategory === 'training_company') {
    return 'border-line/45 bg-wf-accent-priority-soft text-wf-accent-priority-ink'
  }
  if (
    type.includes('out_of_office')
    || type.includes('personal')
    || previewCategory === 'approved_leave'
    || event.busy
    || event.detail_level === 'busy_only'
  ) {
    return 'border-line/45 bg-wf-accent-paused-soft text-wf-accent-paused-ink'
  }
  if (status === 'tentative') {
    return 'border-line/45 bg-wf-accent-assess-soft text-wf-accent-assess-ink'
  }
  // Default meeting — warm raised cream, distinct from both grid and coloured categories.
  return 'border-line/50 bg-panel-muted/95 text-wf-ink'
}

export function eventRailClass(event: CalendarEvent) {
  const surface = eventSurfaceClass(event)
  if (surface.includes('follow')) return 'bg-wf-accent-follow'
  if (surface.includes('review')) return 'bg-wf-accent-review'
  if (surface.includes('paused')) return 'bg-wf-accent-paused'
  if (surface.includes('assess')) return 'bg-wf-accent-assess'
  if (surface.includes('priority')) return 'bg-wf-accent-priority'
  return 'bg-wf-ink/40'
}

function eventDrawerAccentClass(event: CalendarEvent) {
  return eventRailClass(event)
}

/** Shared hover / focus / selected chrome for all card variants. */
export function eventCardInteractiveClass(selected: boolean) {
  return [
    'transition-[box-shadow,filter,ring-color] duration-150',
    'hover:z-30 hover:brightness-[0.97] hover:shadow-md',
    'active:brightness-[0.95]',
    'focus-visible:z-30 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wf-ink/40',
    selected ? 'z-30 ring-2 ring-wf-ink/25 shadow-md' : 'shadow-sm',
  ].join(' ')
}

export type CalendarCardVariant = 'solo-short' | 'solo-medium' | 'solo-long' | 'cascade' | 'all-day' | 'month'

export function calendarCardVariant(
  event: CalendarEvent,
  options?: { placement?: 'solo' | 'side' | 'cascade'; agenda?: boolean; month?: boolean; allDay?: boolean },
): CalendarCardVariant {
  if (options?.month) return 'month'
  if (options?.allDay || isCalendarAllDayEvent(event)) return 'all-day'
  if (options?.placement === 'cascade') return 'cascade'
  const density = calendarEventDensity(event)
  if (density === 'long') return 'solo-long'
  if (density === 'medium') return 'solo-medium'
  return 'solo-short'
}

export function isCalendarPreviewEvent(event: CalendarEvent | null | undefined): boolean {
  if (!event) return false
  if (event.preview_only) return true
  if (event.metadata?.preview_only) return true
  return String(event.event_id || '').startsWith('calprev-')
}

export function isCalendarProjectionEvent(event: CalendarEvent | null | undefined): boolean {
  if (!event) return false
  if (event.projection_managed) return true
  if (event.metadata?.projection) return true
  return String(event.event_id || '').startsWith('calproj-')
}

export type CalendarProjectionDeepLink = {
  page?: string
  employee?: string
  leave?: string
  item?: string
  document_type?: string
}

export function calendarProjectionDeepLink(event: CalendarEvent | null | undefined): CalendarProjectionDeepLink | null {
  if (!isCalendarProjectionEvent(event)) return null
  const raw = event?.metadata?.deep_link
  if (!raw || typeof raw !== 'object') return null
  return raw as CalendarProjectionDeepLink
}

function eventTypeLabel(type?: string, isAr?: boolean) {
  const t = (type || 'other').toLowerCase()
  const en: Record<string, string> = {
    meeting: 'Meeting',
    personal_block: 'Personal time',
    deadline: 'Deadline',
    out_of_office: 'Out of office',
    interview: 'Interview',
    hold: 'Hold',
    other: 'Other',
  }
  const ar: Record<string, string> = {
    meeting: 'اجتماع',
    personal_block: 'وقت شخصي',
    deadline: 'موعد نهائي',
    out_of_office: 'خارج المكتب',
    interview: 'مقابلة',
    hold: 'حجز',
    other: 'أخرى',
  }
  return (isAr ? ar : en)[t] || (type || (isAr ? 'أخرى' : 'Other'))
}

function previewCategoryLabel(category?: string, isAr?: boolean) {
  const c = String(category || '').toLowerCase()
  const en: Record<string, string> = {
    interview: 'Interview',
    video_interview: 'Video interview',
    candidate_followup: 'Follow-up',
    employee_start: 'Employee start',
    approved_leave: 'Approved leave',
    onboarding_deadline: 'Onboarding',
    payroll_cutoff: 'Payroll',
    compliance_expiry: 'Compliance',
    training_company: 'Training',
    meeting: 'Meeting',
  }
  const ar: Record<string, string> = {
    interview: 'مقابلة',
    video_interview: 'مقابلة مرئية',
    candidate_followup: 'متابعة',
    employee_start: 'بدء موظف',
    approved_leave: 'إجازة معتمدة',
    onboarding_deadline: 'إنهاء التعيين',
    payroll_cutoff: 'رواتب',
    compliance_expiry: 'امتثال',
    training_company: 'تدريب',
    meeting: 'اجتماع',
  }
  return (isAr ? ar : en)[c] || ''
}

function allDayEventCardLabels(event: CalendarEvent, isAr: boolean) {
  const primary = eventPrimaryLabel(event, isAr)
  const category = String(event.metadata?.preview_category || '').toLowerCase()
  const parts = primary.split(/[·•]/).map((part) => part.trim()).filter(Boolean)
  const subject = parts.length > 1 ? parts.slice(1).join(' · ') : primary
  if (category === 'employee_start') {
    return {
      eyebrow: isAr ? 'بدء موظف' : 'Employee start',
      title: isAr ? `${subject} يبدأ اليوم` : `${subject} starts today`,
    }
  }
  if (category === 'approved_leave') {
    return {
      eyebrow: isAr ? 'إجازة معتمدة' : 'Approved leave',
      title: isAr ? `${subject} · خارج المكتب اليوم` : `${subject} · Away all day`,
    }
  }
  return {
    eyebrow: previewCategoryLabel(category, isAr) || eventTypeLabel(event.event_type, isAr),
    title: primary,
  }
}

export function calendarEventDurationMinutes(event: CalendarEvent) {
  const start = new Date(event.start_at || '')
  const end = new Date(event.end_at || '')
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 0
  return Math.max(0, (end.getTime() - start.getTime()) / 60000)
}

export function isCalendarAllDayEvent(event: CalendarEvent) {
  return Boolean(event.all_day)
}

export function splitCalendarDayEvents(events: CalendarEvent[]) {
  const allDay: CalendarEvent[] = []
  const timed: CalendarEvent[] = []
  for (const event of events) {
    if (isCalendarAllDayEvent(event)) allDay.push(event)
    else timed.push(event)
  }
  return { allDay, timed }
}

/** Position a timed event inside the 07–20 board; clamp out-of-range safely (never silent drop). */
export function timedEventGeometry(event: CalendarEvent) {
  const start = new Date(event.start_at || '')
  const end = new Date(event.end_at || '')
  const gridPx = HOURS.length * CALENDAR_HOUR_PX
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return {
      top: 0,
      height: CALENDAR_MIN_EVENT_HEIGHT_PX,
      clippedStart: false,
      clippedEnd: false,
      completelyOutside: true,
    }
  }
  const startHour = start.getHours() + start.getMinutes() / 60 + start.getSeconds() / 3600
  const endHour = end.getHours() + end.getMinutes() / 60 + end.getSeconds() / 3600
  const completelyBefore = endHour <= CALENDAR_DAY_START_HOUR
  const completelyAfter = startHour >= CALENDAR_DAY_END_HOUR
  if (completelyBefore) {
    return {
      top: 0,
      height: CALENDAR_MIN_EVENT_HEIGHT_PX,
      clippedStart: true,
      clippedEnd: false,
      completelyOutside: true,
    }
  }
  if (completelyAfter) {
    return {
      top: Math.max(0, gridPx - CALENDAR_MIN_EVENT_HEIGHT_PX),
      height: CALENDAR_MIN_EVENT_HEIGHT_PX,
      clippedStart: false,
      clippedEnd: true,
      completelyOutside: true,
    }
  }
  const clippedStart = startHour < CALENDAR_DAY_START_HOUR
  const clippedEnd = endHour > CALENDAR_DAY_END_HOUR
  const top = Math.max(0, (Math.max(startHour, CALENDAR_DAY_START_HOUR) - CALENDAR_DAY_START_HOUR) * CALENDAR_HOUR_PX)
  const bottom = Math.min(gridPx, (Math.min(endHour, CALENDAR_DAY_END_HOUR) - CALENDAR_DAY_START_HOUR) * CALENDAR_HOUR_PX)
  const height = Math.max(CALENDAR_MIN_EVENT_HEIGHT_PX, bottom - top)
  return { top, height: Math.min(height, gridPx - top), clippedStart, clippedEnd, completelyOutside: false }
}

export type CalendarEventDensity = 'short' | 'medium' | 'long'

export function calendarEventDensity(event: CalendarEvent): CalendarEventDensity {
  const minutes = calendarEventDurationMinutes(event)
  if (minutes < 75) return 'short'
  if (minutes < 120) return 'medium'
  return 'long'
}

type TimedEventLayout = {
  event: CalendarEvent
  lane: number
  laneCount: number
  /** side-by-side only when each card stays readable; otherwise cascade. */
  placement: 'solo' | 'side' | 'cascade'
  cascadeIndex: number
  cascadeDepth: number
  overflowCount: number
  /** Overflow slot — still reachable via +N affordance (never silently dropped). */
  hidden: boolean
  overflowEvents: CalendarEvent[]
}

/** Max concurrent side-by-side cards. Week columns are narrow — prefer cascade. */
export const CALENDAR_MAX_SIDE_BY_SIDE = 1
/** Visible cascaded cards before +N overflow. */
export const CALENDAR_MAX_CASCADE_VISIBLE = 3
/** Horizontal cascade step (px). */
export const CALENDAR_CASCADE_OFFSET_PX = 12

/**
 * Overlap layout: never compress below a readable width.
 * When concurrent events would force narrow columns, cascade (offset stack)
 * and overflow extras into +N on the topmost visible card.
 */
export function layoutTimedCalendarEvents(
  events: CalendarEvent[],
  options?: { maxSideBySide?: number; maxCascadeVisible?: number },
): TimedEventLayout[] {
  const maxSideBySide = options?.maxSideBySide ?? CALENDAR_MAX_SIDE_BY_SIDE
  const maxCascadeVisible = options?.maxCascadeVisible ?? CALENDAR_MAX_CASCADE_VISIBLE
  const sorted = events
    .filter((event) => {
      const start = new Date(event.start_at || '').getTime()
      const end = new Date(event.end_at || '').getTime()
      return Number.isFinite(start) && Number.isFinite(end) && end > start
    })
    .sort((a, b) => {
      const startDelta = new Date(a.start_at || '').getTime() - new Date(b.start_at || '').getTime()
      if (startDelta !== 0) return startDelta
      return new Date(b.end_at || '').getTime() - new Date(a.end_at || '').getTime()
    })

  const result: TimedEventLayout[] = []
  let index = 0
  while (index < sorted.length) {
    const group: CalendarEvent[] = [sorted[index]]
    let groupEnd = new Date(sorted[index].end_at || '').getTime()
    let cursor = index + 1
    while (cursor < sorted.length) {
      const start = new Date(sorted[cursor].start_at || '').getTime()
      if (start >= groupEnd) break
      group.push(sorted[cursor])
      groupEnd = Math.max(groupEnd, new Date(sorted[cursor].end_at || '').getTime())
      cursor += 1
    }

    const laneEnds: number[] = []
    const laneAssigned = group.map((event) => {
      const start = new Date(event.start_at || '').getTime()
      const end = new Date(event.end_at || '').getTime()
      let lane = laneEnds.findIndex((laneEnd) => laneEnd <= start)
      if (lane < 0) {
        lane = laneEnds.length
        laneEnds.push(end)
      } else {
        laneEnds[lane] = end
      }
      return { event, lane }
    })
    const laneCount = Math.max(1, laneEnds.length)

    if (laneCount === 1) {
      result.push({
        event: group[0],
        lane: 0,
        laneCount: 1,
        placement: 'solo',
        cascadeIndex: 0,
        cascadeDepth: 1,
        overflowCount: 0,
        hidden: false,
        overflowEvents: [],
      })
    } else if (laneCount <= maxSideBySide) {
      for (const item of laneAssigned) {
        result.push({
          event: item.event,
          lane: item.lane,
          laneCount,
          placement: 'side',
          cascadeIndex: item.lane,
          cascadeDepth: laneCount,
          overflowCount: 0,
          hidden: false,
          overflowEvents: [],
        })
      }
    } else {
      // Cascade by start order (stable within group). Longest-first already applied via sort ties.
      const depth = group.length
      const overflowEvents = group.slice(maxCascadeVisible)
      const overflowCount = overflowEvents.length
      group.forEach((event, cascadeIndex) => {
        const hidden = cascadeIndex >= maxCascadeVisible
        const isOverflowAnchor = !hidden && cascadeIndex === Math.min(maxCascadeVisible, depth) - 1
        result.push({
          event,
          lane: cascadeIndex,
          laneCount: depth,
          placement: 'cascade',
          cascadeIndex,
          cascadeDepth: depth,
          overflowCount: isOverflowAnchor ? overflowCount : 0,
          hidden,
          overflowEvents: isOverflowAnchor ? overflowEvents : [],
        })
      })
    }
    index = cursor
  }
  return result
}

function eventTimeRange(event: CalendarEvent, isAr: boolean) {
  if (event.all_day) return isAr ? 'طوال اليوم' : 'All day'
  const start = new Date(event.start_at || '')
  const end = new Date(event.end_at || '')
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return ''
  const locale = isAr ? 'ar' : 'en'
  const timeZone = event.timezone || undefined
  const time = new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  })
  const day = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone,
  })
  const crossesDay = day.format(start) !== day.format(end)
  return `${time.format(start)} – ${time.format(end)}${crossesDay ? (isAr ? ' (+يوم)' : ' (+1d)') : ''}`
}

function eventContext(event: CalendarEvent) {
  if (event.detail_level === 'busy_only') return ''
  const metadata = event.metadata || {}
  const candidate =
    String(metadata.candidate_name || metadata.display_name || (event.guests || [])[0]?.display_name || '').trim()
  const job = String(metadata.job_title || metadata.position_title || metadata.role_title || '').trim()
  if (candidate && job) return `${candidate} · ${job}`
  return candidate || job || String(event.description || '').trim()
}

function eventChannel(event: CalendarEvent, isAr: boolean) {
  const url = String(event.meeting_url || '').toLowerCase()
  if (url) {
    if (url.includes('teams.microsoft') || url.includes('teams.live')) return { label: 'Teams', icon: Video }
    if (url.includes('meet.google')) return { label: 'Meet', icon: Video }
    if (url.includes('zoom.')) return { label: 'Zoom', icon: Video }
    return { label: isAr ? 'اجتماع عبر الإنترنت' : 'Online meeting', icon: Video }
  }
  const location = String(event.location || '').trim()
  if (!location) return null
  if (/phone|call|هاتف|اتصال/i.test(location)) return { label: isAr ? 'هاتف' : 'Phone', icon: Phone }
  return { label: location, icon: MapPin }
}

function participantInitial(value: unknown) {
  const text = String(value || '').trim()
  return text ? text.slice(0, 1).toUpperCase() : '?'
}

function eventTypeVisual(event: CalendarEvent) {
  const type = String(event.event_type || event.authority || '').toLowerCase()
  const previewCategory = String(event.metadata?.preview_category || '').toLowerCase()
  if (type.includes('interview') || previewCategory.includes('interview')) return { icon: Video, badge: 'bg-wf-accent-follow-soft text-wf-accent-follow-ink' }
  if (previewCategory === 'training_company' || previewCategory === 'employee_start') return { icon: UsersRound, badge: 'bg-wf-accent-priority-soft text-wf-accent-priority-ink' }
  if (
    type.includes('deadline')
    || type.includes('assessment')
    || ['candidate_followup', 'compliance_expiry', 'onboarding_deadline', 'payroll_cutoff'].includes(previewCategory)
  ) return { icon: Clock3, badge: 'bg-wf-accent-review-soft text-wf-accent-review-ink' }
  if (type.includes('out_of_office') || type.includes('personal') || previewCategory === 'approved_leave') return { icon: MapPin, badge: 'bg-wf-accent-paused-soft text-wf-accent-paused-ink' }
  return { icon: CalendarRange, badge: 'bg-wf-frame text-wf-ink' }
}

function TimedEventCardContent({
  event,
  isAr,
  laneCount = 1,
  agenda = false,
  compact = false,
  multilineTitle = false,
  variant,
}: {
  event: CalendarEvent
  isAr: boolean
  laneCount?: number
  agenda?: boolean
  compact?: boolean
  multilineTitle?: boolean
  variant?: CalendarCardVariant
}) {
  const resolvedVariant =
    variant
    || calendarCardVariant(event, {
      placement: compact ? 'cascade' : 'solo',
      agenda,
    })
  const density = calendarEventDensity(event)
  const narrow = !agenda && laneCount > 1
  const isCascade = resolvedVariant === 'cascade' || compact
  const isLong = resolvedVariant === 'solo-long'
  const isMedium = resolvedVariant === 'solo-medium' || (agenda && density === 'medium')
  const showMedium = !isCascade && (isMedium || isLong || (density !== 'short' && (!narrow || laneCount <= 2)))
  const showRich = !isCascade && isLong && (agenda || laneCount === 1)
  const rawContext = eventContext(event)
  const titleText = eventPrimaryLabel(event, isAr).toLowerCase()
  const contextParts = rawContext
    .split('·')
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)
  const context = contextParts.length > 0 && contextParts.every((part) => titleText.includes(part)) ? '' : rawContext
  const channel = eventChannel(event, isAr)
  const ChannelIcon = channel?.icon
  const typeVisual = eventTypeVisual(event)
  const TypeIcon = typeVisual.icon
  const attendees = event.detail_level === 'busy_only' ? [] : event.attendees || []
  const guests = event.detail_level === 'busy_only' ? [] : event.guests || []
  const participantCount = attendees.length + guests.length
  const participantLabels = [
    ...guests.map((guest) => guest.display_name || guest.email || guest.phone),
    ...attendees.map((attendee) => attendee.display_name || attendee.user_id),
  ]
  const canJoin = Boolean(event.meeting_url && event.detail_level === 'full')
  const hasRichDetails = Boolean(context || channel || participantCount > 0 || canJoin)
  const categoryLabel =
    previewCategoryLabel(String(event.metadata?.preview_category || ''), isAr)
    || eventTypeLabel(event.event_type, isAr)
  const anchorLongCard = isLong && !hasRichDetails
  const preview = isCalendarPreviewEvent(event)
  const titleClamp = multilineTitle || resolvedVariant === 'solo-short' || resolvedVariant === 'solo-long'
    ? 'line-clamp-2 break-words'
    : 'truncate'
  const titleSize = isLong
    ? 'text-[13px] leading-snug'
    : isCascade
      ? 'text-[11px] leading-[1.25]'
      : 'text-[12px] leading-snug'

  return (
    <div
      className={`flex h-full min-h-0 flex-col items-start justify-start overflow-hidden ${preview ? 'ps-0.5' : ''}`}
      data-preview-only={preview ? 'true' : undefined}
      data-calendar-card-variant={resolvedVariant}
    >
      <div className="flex w-full min-w-0 items-start gap-1.5">
        {preview ? (
          <span
            className="mt-0.5 h-3 w-0.5 shrink-0 rounded-full bg-wf-accent-review-ink/55"
            title={isAr ? 'معاينة' : 'Preview'}
            aria-hidden
          />
        ) : null}
        {!isCascade && (isMedium || isLong) ? (
          <span className={`grid h-4 w-4 shrink-0 place-items-center rounded-full ${typeVisual.badge}`}>
            <TypeIcon className="h-2.5 w-2.5" />
          </span>
        ) : null}
        <div className="min-w-0 flex-1 overflow-hidden">
          <p
            className={`${titleClamp} font-semibold text-wf-ink ${titleSize}`}
            title={eventPrimaryLabel(event, isAr)}
          >
            {eventPrimaryLabel(event, isAr)}
          </p>
          <p
            className={`mt-0.5 flex min-w-0 items-center gap-1 truncate font-medium text-wf-ink-muted ${isCascade ? 'text-[9px] leading-[11px]' : 'text-[10px] leading-[12px]'}`}
            title={eventTimeRange(event, isAr)}
          >
            <Clock3 className="h-2.5 w-2.5 shrink-0" />
            <span className="min-w-0 truncate">{eventTimeRange(event, isAr)}</span>
          </p>
        </div>
      </div>

      {showMedium && !anchorLongCard && !/[·•]/.test(eventPrimaryLabel(event, isAr)) ? (
        <div className="mt-1.5 flex w-full min-w-0 items-center gap-1 overflow-hidden text-[10px] font-medium">
          <span className="truncate rounded-full bg-wf-surface-raised/80 px-1.5 py-0.5 text-wf-ink-muted">{eventTypeLabel(event.event_type, isAr)}</span>
          <span className="truncate rounded-full bg-wf-surface-raised/65 px-1.5 py-0.5 text-wf-ink-muted">{statusChip(event.status, isAr)}</span>
        </div>
      ) : showMedium && !anchorLongCard ? (
        <div className="mt-1.5 flex w-full min-w-0 items-center gap-1 overflow-hidden text-[10px] font-medium text-wf-ink-muted">
          <span className="truncate rounded-full bg-wf-surface-raised/65 px-1.5 py-0.5">{statusChip(event.status, isAr)}</span>
        </div>
      ) : null}

      {showRich && context ? (
        <p className="mt-1.5 flex w-full items-start gap-1 text-[10px] leading-tight text-wf-ink-muted">
          <BriefcaseBusiness className="mt-px h-3 w-3 shrink-0" />
          <span className="truncate">{context}</span>
        </p>
      ) : null}

      {showRich && channel && ChannelIcon ? (
        <p className="mt-1 flex w-full min-w-0 items-center gap-1 text-[10px] font-medium text-wf-ink-muted">
          <ChannelIcon className="h-3 w-3 shrink-0" />
          <span className="truncate">{channel.label}</span>
        </p>
      ) : null}

      {showRich && participantCount > 0 ? (
        <div className="mt-1.5 flex w-full items-center justify-between gap-1">
          <div className="flex min-w-0 items-center">
            <div className="flex -space-x-1 rtl:space-x-reverse" aria-label={isAr ? `${participantCount} مشاركين` : `${participantCount} participants`}>
              {participantLabels.slice(0, 3).map((label, index) => (
                <span
                  key={`${String(label)}-${index}`}
                  className="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-wf-surface-raised bg-wf-ink text-[8px] font-semibold text-white"
                >
                  {participantInitial(label)}
                </span>
              ))}
            </div>
            {participantCount > 3 ? <span className="ms-1 text-[9px] font-semibold text-wf-ink-muted">+{participantCount - 3}</span> : null}
          </div>
          <UsersRound className="h-3 w-3 shrink-0 text-wf-ink-muted" />
        </div>
      ) : null}

      {showRich && canJoin ? (
        <button
          type="button"
          className="mt-1.5 inline-flex w-full items-center justify-center gap-1 rounded-full bg-wf-ink px-2.5 py-1 text-[9px] font-semibold text-white shadow-sm hover:bg-wf-sidebar"
          onClick={(eventClick) => {
            eventClick.stopPropagation()
            window.open(event.meeting_url, '_blank', 'noopener,noreferrer')
          }}
        >
          <ExternalLink className="h-3 w-3" />
          {isAr ? 'انضمام' : 'Join'}
        </button>
      ) : null}

      {anchorLongCard ? (
        <div className="mt-auto flex w-full min-w-0 items-center gap-1 border-t border-wf-ink/10 pt-2 text-[10px] font-medium text-wf-ink-muted">
          <span className="truncate rounded-full bg-wf-surface-raised/80 px-1.5 py-0.5">{categoryLabel}</span>
          <span className="truncate rounded-full bg-wf-surface-raised/65 px-1.5 py-0.5">{statusChip(event.status, isAr)}</span>
        </div>
      ) : null}
    </div>
  )
}

function emptyDraft(anchor: Date): Draft {
  const start = new Date(anchor)
  start.setMinutes(0, 0, 0)
  if (start.getHours() < 9) start.setHours(9)
  const end = new Date(start.getTime() + 60 * 60 * 1000)
  return {
    event_type: 'meeting',
    title: '',
    visibility: 'attendees_only',
    start_local: toLocalInput(start.toISOString()),
    end_local: toLocalInput(end.toISOString()),
    timezone: 'Asia/Kuwait',
    all_day: false,
    location: '',
    meeting_url: '',
    attendee_user_id: '',
    guest_email: '',
    override_conflicts: false,
    override_reason: '',
  }
}

export function CalendarShell({
  access,
  canManage,
  canCompany,
  canOverride = false,
  locale = 'en',
  onNotice,
  onOpenInterview,
  onOpenProjectionOwner,
}: Props) {
  const queryClient = useQueryClient()
  const isAr = locale === 'ar'
  const [scope, setScope] = useState<Scope>(() => {
    try {
      const stored = localStorage.getItem('wathefni_calendar_scope')
      if (stored === 'company' || stored === 'mine') return stored
    } catch {
      /* ignore */
    }
    return 'mine'
  })
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(max-width: 900px)').matches : false,
  )
  const [view, setView] = useState<ViewMode>(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches ? 'day' : 'week',
  )
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()))
  const [orgScopeId, setOrgScopeId] = useState<string>('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [mineOnly, setMineOnly] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedSnapshot, setSelectedSnapshot] = useState<CalendarEvent | null>(null)
  const [composerOpen, setComposerOpen] = useState(false)
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(new Date()))
  const [conflicts, setConflicts] = useState<CalendarConflict[]>([])
  const [saving, setSaving] = useState(false)
  const [rsvpBusy, setRsvpBusy] = useState(false)
  const boardScrollRef = useRef<HTMLDivElement | null>(null)
  const savedScrollRef = useRef<{ windowY: number; boardTop: number; view: ViewMode } | null>(null)
  const pendingScrollRestoreRef = useRef(false)
  const detailPanelRef = useRef<HTMLElement | null>(null)
  const composerPanelRef = useRef<HTMLElement | null>(null)
  const selectedIdRef = useRef<string | null>(null)
  selectedIdRef.current = selectedId
  const [overlapMenu, setOverlapMenu] = useState<{
    dayKey: string
    anchorTop: number
    events: CalendarEvent[]
  } | null>(null)

  const closeSelected = useCallback(() => {
    const closingId = selectedIdRef.current
    setSelectedId(null)
    setSelectedSnapshot(null)
    setOverlapMenu(null)
    if (closingId) {
      queryClient.removeQueries({ queryKey: qk.calendarEvent(access, closingId) })
      queryClient.removeQueries({ queryKey: qk.calendarEventSync(access, closingId) })
      queryClient.removeQueries({ queryKey: qk.calendarReschedule(access, closingId) })
    }
  }, [access, queryClient])
  const selectEvent = useCallback((event: CalendarEvent) => {
    setOverlapMenu(null)
    setSelectedId(event.event_id)
    setSelectedSnapshot(event)
  }, [])
  const closeComposer = useCallback(() => {
    setComposerOpen(false)
  }, [])

  useBodyScrollLock(Boolean(isMobile && (selectedId || composerOpen)))
  useOverlayFocus(composerOpen, closeComposer, composerPanelRef)

  useEffect(() => {
    if (!selectedId || composerOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      closeSelected()
    }
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null
      if (!target) return
      if (detailPanelRef.current?.contains(target)) return
      if (target.closest('[data-calendar-event]')) return
      if (target.closest('[data-calendar-overlap-menu]')) return
      if (target.closest('[data-calendar-composer-overlay]')) return
      closeSelected()
      setOverlapMenu(null)
    }
    window.addEventListener('keydown', onKey, true)
    document.addEventListener('mousedown', onPointerDown, true)
    return () => {
      window.removeEventListener('keydown', onKey, true)
      document.removeEventListener('mousedown', onPointerDown, true)
    }
  }, [selectedId, composerOpen, closeSelected])

  const captureScroll = useCallback(() => {
    savedScrollRef.current = {
      windowY: window.scrollY || document.documentElement.scrollTop || 0,
      boardTop: boardScrollRef.current?.scrollTop || 0,
      view,
    }
    pendingScrollRestoreRef.current = true
  }, [view])

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)')
    const apply = () => {
      const mobile = mq.matches
      setIsMobile(mobile)
      if (mobile) setView((current) => (current === 'day' ? current : 'day'))
    }
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem('wathefni_calendar_scope', scope)
    } catch {
      /* ignore */
    }
  }, [scope])

  const range = useMemo(() => {
    if (view === 'day') {
      const start = startOfDay(anchor)
      const end = addDays(start, 1)
      return { start, end, days: [start] }
    }
    if (view === 'month') {
      const monthStart = startOfMonth(anchor)
      const gridStart = startOfWeek(monthStart)
      const end = addDays(gridStart, 42)
      const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
      return { start: gridStart, end, days }
    }
    const weekStart = startOfWeek(anchor)
    const end = addDays(weekStart, 7)
    const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
    return { start: weekStart, end, days }
  }, [anchor, view])

  const effectiveScope = scope === 'company' && !canCompany ? 'mine' : scope
  const eventsParams = useMemo(
    () => ({
      start: range.start.toISOString(),
      end: range.end.toISOString(),
      scope: effectiveScope,
      orgScopeId: effectiveScope === 'team' && orgScopeId ? orgScopeId : undefined,
      typeFilter: typeFilter || undefined,
      statusFilter: statusFilter || undefined,
      mineOnly: effectiveScope === 'mine' ? undefined : mineOnly || undefined,
    }),
    [effectiveScope, mineOnly, orgScopeId, range.end, range.start, statusFilter, typeFilter],
  )

  const eventsQuery = useCalendarEventsQuery(access, eventsParams)
  const teamScopesQuery = useCalendarTeamScopesQuery(access)
  const eventDetailQuery = useCalendarEventQuery(access, selectedId || '', Boolean(selectedId))
  const eventSyncQuery = useCalendarEventSyncQuery(access, selectedId || '', Boolean(selectedId))
  const rescheduleQuery = useCalendarRescheduleQuery(access, selectedId || '', Boolean(selectedId))

  // One request identity for view + range + filters. Board paints the last committed
  // identity only — chrome may lead; never double-paint cache-then-refetch.
  const requestKey = useMemo(
    () =>
      [
        view,
        range.start.toISOString(),
        range.end.toISOString(),
        eventsParams.scope,
        eventsParams.orgScopeId || '',
        eventsParams.typeFilter || '',
        eventsParams.statusFilter || '',
        eventsParams.mineOnly ? '1' : '0',
      ].join('|'),
    [eventsParams, range.end, range.start, view],
  )

  const events = eventsQuery.data?.events || []
  const coldLoading = eventsQuery.isPending && !eventsQuery.data
  type PaintedPreviewMeta = NonNullable<typeof eventsQuery.data>['populated_preview'] | null | undefined
  const [paintedCalendar, setPaintedCalendar] = useState(() => ({
    requestKey,
    view,
    anchor,
    range,
    events: [] as CalendarEvent[],
    previewMeta: null as PaintedPreviewMeta,
    signature: '',
  }))
  useEffect(() => {
    if (!eventsQuery.data || eventsQuery.isPlaceholderData) return
    const nextEvents = eventsQuery.data.events || []
    const signature = `${eventsQuery.dataUpdatedAt}:${nextEvents.map((event) => event.event_id).join(',')}`
    // While a new scope/filter/view is still fetching, keep the prior complete board.
    // Cached hits that also revalidate would otherwise paint twice (stale → fresh).
    setPaintedCalendar((prev) => {
      if (prev.requestKey !== requestKey && eventsQuery.isFetching) return prev
      if (prev.requestKey === requestKey && prev.signature === signature) return prev
      return {
        requestKey,
        view,
        anchor,
        range,
        events: nextEvents,
        previewMeta: eventsQuery.data?.populated_preview ?? null,
        signature,
      }
    })
  }, [
    anchor,
    eventsQuery.data,
    eventsQuery.dataUpdatedAt,
    eventsQuery.isFetching,
    eventsQuery.isPlaceholderData,
    range,
    requestKey,
    view,
  ])
  const boardView = paintedCalendar.view
  const boardAnchor = paintedCalendar.anchor
  const boardRange = paintedCalendar.range
  const boardEvents = paintedCalendar.events
  const boardPending = paintedCalendar.requestKey !== requestKey && paintedCalendar.signature !== ''
  const previewMeta = paintedCalendar.previewMeta ?? eventsQuery.data?.populated_preview
  const previewMode = Boolean(previewMeta?.enabled)
  const refreshing = boardPending || (eventsQuery.isFetching && Boolean(eventsQuery.data))
  const selectedFromList = selectedId ? events.find((e) => e.event_id === selectedId) || null : null
  // selectedId is the sole mount authority — never reuse prior detail query payload after close.
  const selected = !selectedId
    ? null
    : (
      (eventDetailQuery.data?.event && eventDetailQuery.data.event.event_id === selectedId
        ? eventDetailQuery.data.event
        : null)
      || selectedFromList
      || (selectedSnapshot && selectedSnapshot.event_id === selectedId ? selectedSnapshot : null)
    )
  const quietCustomerStatus = eventSyncQuery.data?.customer_status
  const quietSynced = quietCustomerStatus === 'synced'
  const quietNotSynced = quietCustomerStatus === 'pending' || quietCustomerStatus === 'unavailable'
  const rescheduleRequests = rescheduleQuery.data?.requests || []

  useEffect(() => {
    if (!selectedId) return
    if (selectedFromList) setSelectedSnapshot(selectedFromList)
    else if (eventDetailQuery.data?.event && eventDetailQuery.data.event.event_id === selectedId) {
      setSelectedSnapshot(eventDetailQuery.data.event)
    }
  }, [selectedId, selectedFromList, eventDetailQuery.data?.event])

  useEffect(() => {
    if (!selectedId) {
      setSelectedSnapshot(null)
      return
    }
    // Keep drawer open across range refresh / soft-keep — never clear solely because
    // the id left the painted list while a fetch is in flight.
    if (refreshing || eventsQuery.isFetching) return
    // Keep selection even when the event is outside the current range (snapshot).
  }, [selectedId, refreshing, eventsQuery.isFetching])

  useEffect(() => {
    if (!pendingScrollRestoreRef.current) return
    if (eventsQuery.isFetching) return
    const saved = savedScrollRef.current
    pendingScrollRestoreRef.current = false
    if (!saved) return
    window.requestAnimationFrame(() => {
      window.scrollTo(0, saved.windowY)
      if (boardScrollRef.current) {
        boardScrollRef.current.scrollTop = saved.view === view ? saved.boardTop : 0
      }
    })
  }, [eventsQuery.isFetching, eventsQuery.dataUpdatedAt, view, anchor])

  const teamMeta = useMemo(() => {
    const fromScopes = teamScopesQuery.data || null
    const fromEvents = eventsQuery.data?.team || null
    if (!fromScopes && !fromEvents) return null
    // Prefer dedicated team-scopes payload; event meta must not wipe scopes.
    return {
      ...(fromEvents || {}),
      ...(fromScopes || { ok: true }),
      ok: true,
      scopes: fromScopes?.scopes ?? fromEvents?.scopes ?? [],
      has_team_scope:
        fromScopes?.has_team_scope
        ?? fromEvents?.has_team_scope
        ?? Boolean((fromScopes?.scopes || fromEvents?.scopes || []).length),
      show_team_switch:
        fromScopes?.show_team_switch
        ?? fromEvents?.show_team_switch
        ?? Boolean((fromScopes?.scopes || fromEvents?.scopes || []).length),
    } as Awaited<ReturnType<typeof getCalendarTeamScopes>>
  }, [eventsQuery.data?.team, teamScopesQuery.data])

  useEffect(() => {
    const primary = teamScopesQuery.data?.primary_org_scope_id
    if (primary && !orgScopeId) setOrgScopeId(primary)
  }, [orgScopeId, teamScopesQuery.data?.primary_org_scope_id])

  useEffect(() => {
    if (!eventsQuery.error) return
    const err = eventsQuery.error
    onNotice?.(err instanceof Error ? err.message : isAr ? 'تعذر تحميل التقويم' : 'Failed to load calendar', 'error')
  }, [eventsQuery.error, isAr, onNotice])

  // Restrained adjacent-range prefetch (prev/next period, same scope/filters).
  useEffect(() => {
    if (!eventsQuery.data) return
    const step = view === 'day' ? 1 : view === 'week' ? 7 : 0
    const neighbors: Date[] = []
    if (view === 'month') {
      neighbors.push(new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1))
      neighbors.push(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1))
    } else {
      neighbors.push(addDays(anchor, -step))
      neighbors.push(addDays(anchor, step))
    }
    const handle = window.setTimeout(() => {
      for (const neighbor of neighbors) {
        let start: Date
        let end: Date
        if (view === 'day') {
          start = startOfDay(neighbor)
          end = addDays(start, 1)
        } else if (view === 'month') {
          const monthStart = startOfMonth(neighbor)
          start = startOfWeek(monthStart)
          end = addDays(start, 42)
        } else {
          start = startOfWeek(neighbor)
          end = addDays(start, 7)
        }
        const params = {
          ...eventsParams,
          start: start.toISOString(),
          end: end.toISOString(),
        }
        void queryClient.prefetchQuery({
          queryKey: qk.calendarEvents(access, params),
          queryFn: ({ signal }) =>
            fetchCalendarEvents(
              access,
              {
                start: params.start,
                end: params.end,
                scope: params.scope,
                org_scope_id: params.orgScopeId,
                event_type: params.typeFilter,
                status: params.statusFilter,
                mine_only: params.mineOnly,
              },
              signal,
            ),
        })
      }
    }, 450)
    return () => window.clearTimeout(handle)
  }, [access, anchor, eventsParams, eventsQuery.data, queryClient, view])

  // Prefetch the opposite calendar scope for the same range/filters so Mine↔Company
  // can settle without a blank or double-paint flash.
  useEffect(() => {
    if (!eventsQuery.data || !canCompany) return
    if (effectiveScope !== 'mine' && effectiveScope !== 'company') return
    const opposite = effectiveScope === 'mine' ? 'company' : 'mine'
    const handle = window.setTimeout(() => {
      const params = {
        ...eventsParams,
        scope: opposite,
        orgScopeId: undefined,
        mineOnly: opposite === 'mine' ? undefined : eventsParams.mineOnly,
      }
      void queryClient.prefetchQuery({
        queryKey: qk.calendarEvents(access, params),
        queryFn: ({ signal }) =>
          fetchCalendarEvents(
            access,
            {
              start: params.start,
              end: params.end,
              scope: params.scope,
              org_scope_id: params.orgScopeId,
              event_type: params.typeFilter,
              status: params.statusFilter,
              mine_only: params.mineOnly,
            },
            signal,
          ),
      })
    }, 500)
    return () => window.clearTimeout(handle)
  }, [access, canCompany, effectiveScope, eventsParams, eventsQuery.data, queryClient])

  const refreshCalendar = useCallback(async () => {
    await invalidate.calendarAll(queryClient, access)
  }, [access, queryClient])

  const showTeam = Boolean(teamMeta?.has_team_scope) || (teamMeta?.scopes || []).length > 0
  const noTeamGuidance = Boolean(teamMeta?.no_team_guidance)

  useEffect(() => {
    if (scope === 'company' && !canCompany) setScope('mine')
    if (scope === 'team' && !showTeam) setScope('mine')
  }, [canCompany, scope, showTeam])

  const navigate = (dir: -1 | 1) => {
    captureScroll()
    closeSelected()
    startTransition(() => {
      if (view === 'day') setAnchor((a) => addDays(a, dir))
      else if (view === 'week') setAnchor((a) => addDays(a, dir * 7))
      else setAnchor((a) => new Date(a.getFullYear(), a.getMonth() + dir, 1))
    })
  }

  const changeView = (mode: ViewMode) => {
    if (mode === view) return
    captureScroll()
    closeSelected()
    startTransition(() => setView(mode))
  }

  const openCreate = (day?: Date) => {
    if (!canManage) return
    closeSelected()
    setDraft(emptyDraft(day || anchor))
    setConflicts([])
    setComposerOpen(true)
  }

  const openEdit = (event: CalendarEvent) => {
    if (isCalendarPreviewEvent(event)) {
      onNotice?.(
        isAr
          ? 'أحداث المعاينة وهمية للمراجعة فقط — لا يمكن تعديلها.'
          : 'Preview events are synthetic for review only — they cannot be edited.',
        'error',
      )
      return
    }
    if (isCalendarProjectionEvent(event)) {
      const link = calendarProjectionDeepLink(event)
      if (link && onOpenProjectionOwner) onOpenProjectionOwner(link)
      else onNotice?.(isAr ? 'يُدار هذا الحدث عبر الوحدة المالكة' : 'This event is managed in its owning module', 'error')
      return
    }
    if (event.interview_managed || event.authority === 'interview') {
      if (event.interview_id && onOpenInterview) onOpenInterview(event.interview_id)
      else onNotice?.(isAr ? 'يُدار هذا الحدث عبر المقابلات' : 'This event is managed through Interviews', 'error')
      return
    }
    if (event.detail_level === 'busy_only') return
    setDraft({
      event_id: event.event_id,
      expected_version: event.version,
      event_type: event.event_type || 'meeting',
      title: event.title || '',
      visibility: event.visibility || 'attendees_only',
      start_local: toLocalInput(event.start_at),
      end_local: toLocalInput(event.end_at),
      timezone: event.timezone || 'Asia/Kuwait',
      all_day: Boolean(event.all_day),
      location: event.location || '',
      meeting_url: event.meeting_url || '',
      attendee_user_id: String((event.attendees || []).find((a) => !a.is_organizer)?.user_id || ''),
      guest_email: String((event.guests || [])[0]?.email || ''),
      override_conflicts: false,
      override_reason: '',
    })
    setConflicts([])
    setComposerOpen(true)
  }

  const runPreview = async () => {
    try {
      const attendees = draft.attendee_user_id ? [{ user_id: draft.attendee_user_id, role: 'required' }] : []
      const res = await previewCalendarConflicts(access, {
        start_at: fromLocalInput(draft.start_local),
        end_at: fromLocalInput(draft.end_local),
        timezone: draft.timezone,
        all_day: draft.all_day,
        attendees,
        exclude_event_id: draft.event_id,
      })
      setConflicts(res.conflicts || [])
    } catch (err) {
      onNotice?.(err instanceof Error ? err.message : 'Conflict preview failed', 'error')
    }
  }

  const saveDraft = async () => {
    if (!canManage) return
    setSaving(true)
    try {
      const attendees = draft.attendee_user_id ? [{ user_id: draft.attendee_user_id, role: 'required' }] : []
      const guests = draft.guest_email.trim() ? [{ email: draft.guest_email.trim(), guest_kind: 'external' }] : []
      const body: Record<string, unknown> = {
        event_type: draft.event_type,
        title: draft.title.trim(),
        visibility: draft.visibility,
        start_at: fromLocalInput(draft.start_local),
        end_at: fromLocalInput(draft.end_local),
        timezone: draft.timezone,
        all_day: draft.all_day,
        location: draft.location || undefined,
        meeting_url: draft.meeting_url || undefined,
        attendees,
        guests,
        override_conflicts: draft.override_conflicts,
        override_reason: draft.override_reason || undefined,
      }
      if (draft.event_id && draft.expected_version) {
        await updateCalendarEvent(access, draft.event_id, {
          ...body,
          expected_version: draft.expected_version,
        })
      } else {
        await createCalendarEvent(access, body)
      }
      onNotice?.(isAr ? 'تم حفظ الحدث' : 'Event saved', 'success')
      setComposerOpen(false)
      setConflicts([])
      if (draft.event_id) await invalidate.calendarEvent(queryClient, access, draft.event_id)
      else await refreshCalendar()
    } catch (err: unknown) {
      const detail =
        err instanceof DashboardApiError && typeof err.detail === 'object' && err.detail
          ? (err.detail as Record<string, unknown>)
          : null
      const conflictsList = (detail?.conflicts || (detail?.details as any)?.conflicts) as CalendarConflict[] | undefined
      if (Array.isArray(conflictsList) && conflictsList.length) {
        setConflicts(conflictsList)
        onNotice?.(isAr ? 'تعارض في الجدولة — المسودة محفوظة' : 'Scheduling conflict — draft preserved', 'error')
      } else if (detail?.error === 'stale_version' || (err instanceof DashboardApiError && err.status === 409)) {
        onNotice?.(isAr ? 'تم تعديل الحدث من مكان آخر. حدّث ثم أعد المحاولة.' : 'Event changed elsewhere. Refresh and retry.', 'error')
      } else {
        onNotice?.(err instanceof Error ? err.message : isAr ? 'تعذر الحفظ' : 'Save failed', 'error')
      }
    } finally {
      setSaving(false)
    }
  }

  const cancelSelected = async () => {
    if (!selected || !canManage || !selected.version) return
    if (selected.interview_managed) {
      onNotice?.(isAr ? 'ألغِ عبر المقابلات' : 'Cancel via Interviews', 'error')
      return
    }
    try {
      await cancelCalendarEvent(access, selected.event_id, { expected_version: selected.version })
      onNotice?.(isAr ? 'تم إلغاء الحدث' : 'Event cancelled', 'success')
      closeSelected()
      await invalidate.calendarAll(queryClient, access)
    } catch (err) {
      onNotice?.(err instanceof Error ? err.message : 'Cancel failed', 'error')
    }
  }

  const submitRsvp = async (status: string) => {
    if (!selected) return
    setRsvpBusy(true)
    try {
      const result = await rsvpCalendarEvent(access, selected.event_id, {
        rsvp_status: status,
      })
      queryClient.setQueryData(qk.calendarEvent(access, selected.event_id), { event: result.event })
      onNotice?.(isAr ? 'تم تحديث الحضور' : 'RSVP updated', 'success')
      await invalidate.calendarEvent(queryClient, access, selected.event_id)
    } catch (err) {
      onNotice?.(err instanceof Error ? err.message : 'RSVP failed', 'error')
    } finally {
      setRsvpBusy(false)
    }
  }

  const resolveRequest = async (requestId: string, decision: string) => {
    try {
      const res = await resolveCalendarRescheduleRequest(access, requestId, { decision })
      onNotice?.(res.message || (isAr ? 'تم تحديث الطلب' : 'Request updated'), 'success')
      if (selectedId) await invalidate.calendarEvent(queryClient, access, selectedId)
    } catch (err) {
      onNotice?.(err instanceof Error ? err.message : 'Resolve failed', 'error')
    }
  }

  const eventsForDay = (day: Date) =>
    boardEvents.filter((e) => {
      if (!e.start_at) return false
      return sameDay(new Date(e.start_at), day)
    })

  const rangeLabel = useMemo(() => {
    const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }
    const loc = isAr ? 'ar' : 'en'
    if (view === 'day') return anchor.toLocaleDateString(loc, opts)
    if (view === 'week') {
      return `${range.days[0].toLocaleDateString(loc, opts)} – ${range.days[6].toLocaleDateString(loc, opts)}`
    }
    return anchor.toLocaleDateString(loc, { month: 'long', year: 'numeric' })
  }, [anchor, isAr, range.days, view])

  const agendaDays =
    boardView === 'month'
      ? boardRange.days.filter((d) => d.getMonth() === boardAnchor.getMonth())
      : boardRange.days

  return (
    <section className="relative space-y-2" dir={isAr ? 'rtl' : 'ltr'} data-calendar-wave1c data-calendar-composition>
      <div
        className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-line/70 bg-wf-frame/80 px-2 py-1.5"
        data-calendar-controls
      >
        <div className="inline-flex rounded-full bg-panel-muted p-0.5">
          {(['day', 'week', 'month'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`rounded-full px-2.5 py-1 text-[13px] transition ${view === mode ? 'bg-wf-ink text-white' : 'text-muted hover:text-ink'} ${isMobile && mode !== 'day' ? 'hidden sm:inline' : ''}`}
              onClick={() => changeView(mode)}
            >
              {mode === 'day' ? (isAr ? 'يوم' : 'Day') : mode === 'week' ? (isAr ? 'أسبوع' : 'Week') : isAr ? 'شهر' : 'Month'}
            </button>
          ))}
        </div>

        <div className="inline-flex items-center gap-0.5">
          <button type="button" className="rounded-lg p-1.5 text-muted transition hover:bg-panel-muted hover:text-ink active:bg-line" onClick={() => navigate(-1)} aria-label="prev">
            {isAr ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-[13px] font-medium text-ink transition hover:bg-panel-muted active:bg-line"
            onClick={() => {
              captureScroll()
              closeSelected()
              setAnchor(startOfDay(new Date()))
            }}
          >
            {isAr ? 'اليوم' : 'Today'}
          </button>
          <button type="button" className="rounded-lg p-1.5 text-muted transition hover:bg-panel-muted hover:text-ink active:bg-line" onClick={() => navigate(1)} aria-label="next">
            {isAr ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </div>
        <span className="px-1 text-[13px] font-semibold text-ink">{rangeLabel}</span>

        <div className="ms-auto inline-flex items-center gap-1.5">
          <div className="inline-flex rounded-full bg-panel-muted p-0.5" role="group" aria-label={isAr ? 'نطاق التقويم' : 'Calendar scope'}>
            <button
              type="button"
              className={`rounded-full px-2.5 py-1 text-[12px] transition ${scope === 'mine' ? 'bg-wf-ink text-white' : 'text-muted hover:text-ink'}`}
              title={isAr ? 'أحداثك التي تملكها أو تنظّمها أو تحضرها' : 'Events you own, organize, or attend'}
              aria-pressed={scope === 'mine'}
              data-testid="calendar-scope-mine"
              onClick={() => {
                if (scope === 'mine') return
                closeSelected()
                startTransition(() => {
                  setScope('mine')
                  setMineOnly(false)
                })
              }}
            >
              {isAr ? 'تقويمي' : 'Mine'}
            </button>
            {showTeam ? (
              <button
                type="button"
                className={`rounded-full px-2.5 py-1 text-[12px] transition ${scope === 'team' ? 'bg-wf-ink text-white' : 'text-muted hover:text-ink'}`}
                title={isAr ? 'أحداث نطاق فريق التوظيف المرتبط بحسابك' : 'Events shared with your hiring team scope'}
                aria-pressed={scope === 'team'}
                data-testid="calendar-scope-team"
                onClick={() => {
                  if (scope === 'team') return
                  closeSelected()
                  startTransition(() => setScope('team'))
                }}
              >
                {isAr ? 'الفريق' : 'Team'}
              </button>
            ) : null}
            {canCompany ? (
              <button
                type="button"
                className={`rounded-full px-2.5 py-1 text-[12px] transition ${scope === 'company' ? 'bg-wf-ink text-white' : 'text-muted hover:text-ink'}`}
                title={isAr ? 'أحداث الشركة التي يُسمح لك برؤيتها' : 'Company-wide events you are allowed to see'}
                aria-pressed={scope === 'company'}
                data-testid="calendar-scope-company"
                onClick={() => {
                  if (scope === 'company') return
                  closeSelected()
                  startTransition(() => setScope('company'))
                }}
              >
                {isAr ? 'الشركة' : 'Company'}
              </button>
            ) : null}
          </div>

          <select
            className="h-8 rounded-lg border border-line/55 bg-wf-surface-raised/90 px-2 text-[12px] text-ink"
            value={typeFilter}
            onChange={(e) => {
              closeSelected()
              const next = e.target.value
              startTransition(() => setTypeFilter(next))
            }}
            aria-label={isAr ? 'النوع' : 'Type'}
          >
            <option value="">{isAr ? 'كل الأنواع' : 'All types'}</option>
            {['meeting', 'personal_block', 'deadline', 'out_of_office', 'interview', 'other'].map((t) => (
              <option key={t} value={t}>{eventTypeLabel(t, isAr)}</option>
            ))}
          </select>
          <select
            className="h-8 rounded-lg border border-line/55 bg-wf-surface-raised/90 px-2 text-[12px] text-ink"
            value={statusFilter}
            onChange={(e) => {
              closeSelected()
              const next = e.target.value
              startTransition(() => setStatusFilter(next))
            }}
            aria-label={isAr ? 'الحالة' : 'Status'}
          >
            <option value="">{isAr ? 'كل الحالات' : 'All statuses'}</option>
            {['confirmed', 'tentative', 'cancelled', 'completed'].map((s) => (
              <option key={s} value={s}>{statusChip(s, isAr)}</option>
            ))}
          </select>
          {canCompany || showTeam ? (
            <label
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg border border-line/55 bg-wf-surface-raised/90 px-2 text-[12px] text-ink ${
                effectiveScope === 'mine' ? 'invisible' : ''
              }`}
              aria-hidden={effectiveScope === 'mine' || undefined}
            >
              <input
                type="checkbox"
                checked={mineOnly}
                disabled={effectiveScope === 'mine'}
                onChange={(e) => {
                  closeSelected()
                  const next = e.target.checked
                  startTransition(() => setMineOnly(next))
                }}
              />
              {isAr ? 'خاص بي' : 'Mine only'}
            </label>
          ) : null}

          {previewMode ? (
            <span
              className="inline-flex max-w-[14rem] items-center gap-1.5 truncate rounded-full bg-wf-accent-review-soft/70 px-2 py-1 text-[10px] font-medium text-wf-accent-review-ink"
              data-calendar-populated-preview-banner
              title={isAr ? 'معاينة كاناري WATHEFNI' : 'WATHEFNI canary preview'}
            >
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-wf-accent-review-ink/70" aria-hidden />
              {isAr ? 'معاينة' : 'Preview'}
              {typeof previewMeta?.injected === 'number' ? ` · ${previewMeta.injected}` : ''}
            </span>
          ) : null}

          {canManage ? (
            <Button className="h-8 px-2.5 text-[12px]" onClick={() => openCreate()} size="sm">
              <Plus className="h-3.5 w-3.5" />
              {isAr ? 'إضافة' : 'Add'}
            </Button>
          ) : null}
        </div>
      </div>

      {scope === 'team' && noTeamGuidance && !(teamMeta?.scopes || []).length ? (
        <div className="rounded-xl border border-dashed border-line/60 bg-wf-surface/80 px-3 py-2 text-[13px] text-muted">
          {isAr
            ? 'لا يوجد نطاق فريق توظيف مرتبط بحسابك. استخدم تقويم الشركة للإشراف إن كان متاحاً.'
            : 'No hiring team scope is bound to your account. Use Company calendar for oversight when available.'}
        </div>
      ) : null}

      {scope === 'team' && (teamMeta?.scopes || []).length > 1 ? (
        <select
          className="h-8 rounded-lg border border-line/55 bg-wf-surface-raised/90 px-2 text-[12px]"
          value={orgScopeId}
          onChange={(e) => {
            closeSelected()
            const next = e.target.value
            startTransition(() => setOrgScopeId(next))
          }}
        >
          {(teamMeta?.scopes || []).map((s) => (
            <option key={s.org_scope_id} value={s.org_scope_id}>
              {s.label || s.org_scope_id}
            </option>
          ))}
        </select>
      ) : null}

      <div className="relative">
        <div
          ref={boardScrollRef}
          className="relative overflow-auto rounded-2xl border border-line/70 bg-wf-surface"
          data-rendering-soft-keep
          data-calendar-board
          data-testid="calendar-board"
          data-rendering-updating={refreshing && !coldLoading ? 'true' : undefined}
          data-calendar-painted-view={boardView}
          data-calendar-board-pending={boardPending ? 'true' : undefined}
          aria-busy={refreshing || coldLoading || undefined}
        >
          {refreshing && !coldLoading ? (
            <div
              className="pointer-events-none absolute end-2 top-2 z-50 flex h-6 items-center gap-1.5 rounded-full border border-line/55 bg-wf-surface-raised/95 px-2.5 text-[10px] text-muted shadow-sm"
              data-rendering-updating-rail
            >
              <Loader2 className="h-3 w-3 animate-spin opacity-70" aria-hidden />
              <span className="sr-only">{isAr ? 'جاري التحديث' : 'Updating'}</span>
            </div>
          ) : null}
          {coldLoading && boardEvents.length === 0 ? (
            <div className="flex items-center gap-2 p-6 text-sm text-muted">
              <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading…'}
            </div>
          ) : isMobile || boardView === 'day' ? (
            <div className="divide-y divide-line/55">
              {agendaDays.map((day) => {
                const dayEvents = eventsForDay(day)
                return (
                  <div key={day.toISOString()} className="px-3 py-2.5">
                    <div className="mb-1.5 flex items-center justify-between">
                      <h3 className="text-[13px] font-semibold text-ink">
                        {day.toLocaleDateString(isAr ? 'ar' : 'en', { weekday: 'long', month: 'short', day: 'numeric' })}
                      </h3>
                      {canManage ? (
                        <button type="button" className="text-[11px] font-semibold text-muted underline" onClick={() => openCreate(day)}>
                          {isAr ? 'إضافة' : 'Add'}
                        </button>
                      ) : null}
                    </div>
                    {dayEvents.length === 0 ? (
                      <p className="py-1 text-[12px] text-muted">{isAr ? 'لا أحداث' : 'No events'}</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {dayEvents.map((event) => (
                          <li key={event.event_id}>
                            <div
                              role="button"
                              tabIndex={0}
                              data-calendar-event
                              data-calendar-selected={selectedId === event.event_id ? 'true' : undefined}
                              aria-selected={selectedId === event.event_id}
                              className={`flex w-full cursor-pointer overflow-hidden rounded-xl border text-start ${eventSurfaceClass(event)} ${eventCardInteractiveClass(selectedId === event.event_id)}`}
                              data-preview-only={isCalendarPreviewEvent(event) ? 'true' : undefined}
                              onClick={() => selectEvent(event)}
                              onKeyDown={(keyEvent) => {
                                if (keyEvent.key === 'Enter' || keyEvent.key === ' ') selectEvent(event)
                              }}
                            >
                              <span className={`w-[3px] shrink-0 self-stretch ${eventRailClass(event)}`} data-calendar-category-rail aria-hidden />
                              <div className="min-w-0 flex-1 px-2.5 py-2">
                                <TimedEventCardContent event={event} isAr={isAr} agenda variant={calendarCardVariant(event, { agenda: true })} />
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )
              })}
            </div>
          ) : boardView === 'week' ? (
            <div className="overflow-x-auto" data-calendar-week>
              <div className="grid min-w-[1120px] grid-cols-[64px_repeat(7,minmax(0,1fr))] border-b border-line/40 bg-wf-frame" data-calendar-week-header>
                <div className="border-e border-line/40" />
                {boardRange.days.map((day) => (
                  <div
                    key={day.toISOString()}
                    className={`border-s border-line/40 px-2 py-3 text-center text-xs font-semibold ${
                      sameDay(day, new Date()) ? 'bg-accent-soft text-wf-accent-review-ink' : 'text-muted'
                    }`}
                  >
                    <span className="uppercase tracking-[0.08em]">{day.toLocaleDateString(isAr ? 'ar' : 'en', { weekday: 'short' })}</span>
                    <div className={`mx-auto mt-1 grid h-7 w-7 place-items-center rounded-full text-sm ${sameDay(day, new Date()) ? 'bg-accent text-white' : 'text-ink'}`}>
                      {day.getDate()}
                    </div>
                  </div>
                ))}
              </div>
              <div
                className="grid min-w-[1120px] grid-cols-[64px_repeat(7,minmax(0,1fr))] border-b border-line/40 bg-wf-frame/70"
                data-calendar-all-day-row
              >
                <div className="flex items-start justify-center border-e border-line/40 px-1 py-2.5 text-[9px] font-semibold uppercase tracking-[0.04em] text-wf-ink-muted">
                  {isAr ? 'اليوم' : 'All-day'}
                </div>
                {boardRange.days.map((day) => {
                  const { allDay } = splitCalendarDayEvents(eventsForDay(day))
                  return (
                    <div
                      key={`allday-${day.toISOString()}`}
                      className={`min-h-[48px] space-y-1 border-s border-line/40 p-1.5 ${sameDay(day, new Date()) ? 'bg-accent-soft/20' : ''}`}
                    >
                      {allDay.map((event) => {
                        const labels = allDayEventCardLabels(event, isAr)
                        return (
                          <button
                            key={event.event_id}
                            type="button"
                            data-calendar-event
                            data-calendar-all-day-event
                            data-calendar-card-variant="all-day"
                            data-calendar-selected={selectedId === event.event_id ? 'true' : undefined}
                            data-testid={`calendar-allday-event-${event.event_id}`}
                            className={`flex w-full overflow-hidden rounded-xl border text-start leading-snug ${eventSurfaceClass(event)} ${eventCardInteractiveClass(selectedId === event.event_id)}`}
                            data-preview-only={isCalendarPreviewEvent(event) ? 'true' : undefined}
                            onClick={() => selectEvent(event)}
                          >
                            <span className={`w-[3px] shrink-0 self-stretch ${eventRailClass(event)}`} data-calendar-category-rail aria-hidden />
                            <span className="min-w-0 flex-1 px-2 py-1.5">
                              <span className="block truncate text-[9px] font-semibold uppercase tracking-[0.07em] text-wf-ink-muted">
                                {labels.eyebrow}
                              </span>
                              <span className="mt-0.5 block line-clamp-2 text-[11px] font-semibold text-wf-ink">
                                {labels.title}
                              </span>
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  )
                })}
              </div>
              <div
                className="relative grid min-w-[1120px] grid-cols-[64px_repeat(7,minmax(0,1fr))]"
                style={{ height: HOURS.length * CALENDAR_HOUR_PX }}
                data-calendar-week-grid
              >
                <div className="relative border-e border-line/40 bg-wf-frame/55">
                  {HOURS.map((h) => (
                    <div
                      key={h}
                      className="absolute start-0 end-0 border-t border-line/35 px-2 pt-1.5 text-[11px] font-medium tabular-nums text-wf-ink-muted"
                      style={{ top: (h - CALENDAR_DAY_START_HOUR) * CALENDAR_HOUR_PX }}
                    >
                      {new Intl.DateTimeFormat(isAr ? 'ar' : 'en', { hour: 'numeric', minute: '2-digit' }).format(new Date(2026, 0, 1, h))}
                    </div>
                  ))}
                </div>
                {boardRange.days.map((day) => {
                  const dayKey = day.toISOString()
                  const { timed } = splitCalendarDayEvents(eventsForDay(day))
                  const layouts = layoutTimedCalendarEvents(timed, { maxSideBySide: 1 })
                  return (
                    <div
                      key={dayKey}
                      className={`relative border-s border-line/35 ${sameDay(day, new Date()) ? 'bg-accent-soft/20' : 'bg-wf-surface/45'}`}
                    >
                      {HOURS.map((h) => (
                        <div
                          key={h}
                          className="absolute inset-x-0 border-t border-line/25"
                          style={{ top: (h - CALENDAR_DAY_START_HOUR) * CALENDAR_HOUR_PX, height: CALENDAR_HOUR_PX }}
                        />
                      ))}
                      {layouts.map((layout) => {
                        if (layout.hidden) return null
                        const { event, placement, cascadeIndex, overflowCount, overflowEvents, laneCount } = layout
                        const geometry = timedEventGeometry(event)
                        const density = calendarEventDensity(event)
                        const offsetPx = placement === 'cascade' ? cascadeIndex * CALENDAR_CASCADE_OFFSET_PX : 0
                        const width =
                          placement === 'side'
                            ? `calc(${100 / laneCount}% - 6px)`
                            : `calc(100% - ${10 + offsetPx}px)`
                        const insetInlineStart =
                          placement === 'side'
                            ? `calc(${(layout.lane * 100) / laneCount}% + 3px)`
                            : `${4 + offsetPx}px`
                        const cardVariant = calendarCardVariant(event, { placement })
                        const isSelected = selectedId === event.event_id
                        return (
                          <div
                            key={event.event_id}
                            role="button"
                            tabIndex={0}
                            data-calendar-event
                            data-calendar-card-variant={cardVariant}
                            data-calendar-selected={isSelected ? 'true' : undefined}
                            aria-selected={isSelected}
                            data-testid={`calendar-timed-event-${event.event_id}`}
                            data-density={density}
                            data-placement={placement}
                            data-lane={`${layout.lane + 1}/${laneCount}`}
                            data-cascade-index={cascadeIndex}
                            data-calendar-clipped={
                              geometry.clippedStart || geometry.clippedEnd
                                ? `${geometry.clippedStart ? 'start' : ''}${geometry.clippedStart && geometry.clippedEnd ? ',' : ''}${geometry.clippedEnd ? 'end' : ''}`
                                : undefined
                            }
                            title={eventPrimaryLabel(event, isAr)}
                            className={`absolute flex cursor-pointer overflow-hidden rounded-xl border text-start ${eventSurfaceClass(event)} ${eventCardInteractiveClass(isSelected)} ${
                              placement === 'cascade' ? 'ring-1 ring-wf-surface-raised/80 shadow-md' : ''
                            } ${cardVariant === 'solo-long' ? 'border-line/70 shadow-md' : ''}`}
                            style={{
                              top: geometry.top,
                              height: geometry.height,
                              minHeight: CALENDAR_MIN_EVENT_HEIGHT_PX,
                              insetInlineStart,
                              width,
                              zIndex: (isSelected ? 28 : 12) + cascadeIndex,
                              minWidth: placement === 'cascade' || placement === 'solo' ? 88 : undefined,
                            }}
                            onClick={() => selectEvent(event)}
                            onKeyDown={(keyEvent) => {
                              if (keyEvent.key === 'Enter' || keyEvent.key === ' ') selectEvent(event)
                            }}
                          >
                            <span className={`w-[3px] shrink-0 self-stretch ${eventRailClass(event)}`} data-calendar-category-rail aria-hidden />
                            <div className={`min-w-0 flex-1 ${
                              placement === 'cascade'
                                ? 'p-1.5'
                                : cardVariant === 'solo-short'
                                  ? 'px-2 py-1'
                                  : 'p-2'
                            }`}>
                              <TimedEventCardContent
                                event={event}
                                isAr={isAr}
                                laneCount={1}
                                compact={placement === 'cascade'}
                                multilineTitle={placement === 'solo' && geometry.height >= 56}
                                variant={cardVariant}
                              />
                            </div>
                            {overflowCount > 0 ? (
                              <button
                                type="button"
                                className="absolute bottom-1 end-1 rounded-full bg-wf-ink/90 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                                data-calendar-overlap-more
                                aria-label={isAr ? `+${overflowCount} المزيد` : `+${overflowCount} more`}
                                onClick={(clickEvent) => {
                                  clickEvent.preventDefault()
                                  clickEvent.stopPropagation()
                                  setOverlapMenu({
                                    dayKey,
                                    anchorTop: geometry.top + geometry.height,
                                    events: overflowEvents,
                                  })
                                }}
                              >
                                +{overflowCount}
                              </button>
                            ) : null}
                          </div>
                        )
                      })}
                      {overlapMenu?.dayKey === dayKey ? (
                        <div
                          className="absolute start-1 end-1 z-40 max-h-40 overflow-auto rounded-xl border border-line/70 bg-wf-surface-raised p-1.5 shadow-soft"
                          style={{ top: Math.min(overlapMenu.anchorTop, HOURS.length * CALENDAR_HOUR_PX - 120) }}
                          data-calendar-overlap-menu
                          role="listbox"
                        >
                          <p className="px-1.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                            {isAr ? 'المزيد' : 'More'}
                          </p>
                          {overlapMenu.events.map((event) => (
                            <button
                              key={event.event_id}
                              type="button"
                              role="option"
                              data-calendar-event
                              className={`mb-1 flex w-full items-start rounded-md px-1.5 py-1 text-start text-[11px] font-medium leading-snug last:mb-0 ${eventSurfaceClass(event)}`}
                              onClick={() => selectEvent(event)}
                            >
                              <span className="line-clamp-2 min-w-0">{eventPrimaryLabel(event, isAr)}</span>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-7 gap-px bg-line/60">
              {boardRange.days.map((day) => {
                const inMonth = day.getMonth() === boardAnchor.getMonth()
                const dayEvents = eventsForDay(day)
                return (
                  <button
                    key={day.toISOString()}
                    type="button"
                    className={`min-h-[96px] bg-wf-surface p-2 text-start ${inMonth ? '' : 'opacity-40'}`}
                    onClick={() => {
                      captureScroll()
                      closeSelected()
                      setAnchor(startOfDay(day))
                      setView('day')
                    }}
                  >
                    <div
                      className={
                        sameDay(day, new Date())
                          ? 'inline-flex h-7 w-7 items-center justify-center rounded-full bg-wf-ink text-xs font-semibold text-white'
                          : 'text-xs font-semibold text-ink'
                      }
                    >
                      {day.getDate()}
                    </div>
                    <div className="mt-1 space-y-1">
                      {dayEvents.slice(0, 4).map((event) => (
                        <div
                          key={event.event_id}
                          data-calendar-event
                          data-calendar-card-variant="month"
                          data-calendar-selected={selectedId === event.event_id ? 'true' : undefined}
                          className={`flex overflow-hidden rounded-lg border text-[10px] font-semibold leading-snug ${eventSurfaceClass(event)} ${eventCardInteractiveClass(selectedId === event.event_id)}`}
                          data-preview-only={isCalendarPreviewEvent(event) ? 'true' : undefined}
                          onClick={(e) => {
                            e.stopPropagation()
                            selectEvent(event)
                          }}
                        >
                          <span className={`w-[3px] shrink-0 self-stretch ${eventRailClass(event)}`} data-calendar-category-rail aria-hidden />
                          <span className="flex min-w-0 flex-1 items-start gap-1 px-1.5 py-1">
                            {isCalendarPreviewEvent(event) ? (
                              <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-wf-accent-review-ink/60" aria-hidden />
                            ) : null}
                            <span className="line-clamp-2 min-w-0 text-wf-ink">{eventPrimaryLabel(event, isAr)}</span>
                          </span>
                        </div>
                      ))}
                      {dayEvents.length > 4 ? <div className="text-[10px] text-muted">+{dayEvents.length - 4}</div> : null}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {selectedId && selected && !composerOpen
          ? createPortal(
            <aside
            ref={detailPanelRef}
            role="dialog"
            aria-modal="false"
            data-calendar-detail-drawer
            data-calendar-detail-mode={isMobile ? 'sheet' : 'side'}
            data-calendar-selected-id={selectedId}
            className={
              isMobile
                ? 'fixed inset-x-0 bottom-0 z-[80] max-h-[72vh] overflow-hidden rounded-t-2xl border border-line/70 bg-wf-surface shadow-soft'
                : 'fixed end-3 top-[4.75rem] z-[80] flex w-[min(100%,300px)] max-h-[calc(100vh-5.5rem)] flex-col overflow-hidden rounded-2xl border border-line/70 bg-wf-surface shadow-soft rtl:end-auto rtl:start-3'
            }
          >
            <div className={`h-1 w-full shrink-0 ${eventDrawerAccentClass(selected!)}`} data-calendar-detail-accent aria-hidden />
            <div className="flex items-start justify-between gap-2 border-b border-line/50 px-3.5 pb-2.5 pt-3">
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted" data-calendar-category>
                  {eventTypeLabel(selected!.event_type, isAr)}
                </p>
                <h2 className="mt-0.5 text-[1.05rem] font-semibold leading-snug text-ink">{eventPrimaryLabel(selected!, isAr)}</h2>
                {isCalendarPreviewEvent(selected!) ? (
                  <p className="mt-1 text-[11px] font-medium text-wf-accent-review-ink" data-calendar-preview-only>
                    {isAr
                      ? 'معاينة فقط — ليست سجلاً حقيقياً في أي وحدة.'
                      : 'Preview only — not a real record in any module.'}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-panel-muted hover:text-ink active:bg-line focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wf-ink/40"
                aria-label={isAr ? 'إغلاق' : 'Close'}
                data-calendar-detail-close
                onClick={(event) => {
                  event.preventDefault()
                  event.stopPropagation()
                  closeSelected()
                }}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="overflow-y-auto px-3.5 py-3">
              <dl className="space-y-0 divide-y divide-line/50 text-[13px]">
                <div className="flex gap-3 py-2 first:pt-0">
                  <dt className="w-16 shrink-0 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'الوقت' : 'When'}</dt>
                  <dd className="min-w-0 leading-snug text-ink">
                    {selected.all_day
                      ? (isAr ? 'طوال اليوم' : 'All day')
                      : (
                        <>
                          {selected.start_at
                            ? new Date(selected.start_at).toLocaleString(isAr ? 'ar' : 'en', {
                                month: 'short',
                                day: 'numeric',
                                hour: 'numeric',
                                minute: '2-digit',
                              })
                            : '—'}
                          {selected.end_at
                            ? ` – ${new Date(selected.end_at).toLocaleTimeString(isAr ? 'ar' : 'en', {
                                hour: 'numeric',
                                minute: '2-digit',
                              })}`
                            : ''}
                        </>
                      )}
                    <div className="mt-0.5 text-[11px] text-muted">{selected.timezone || 'Asia/Kuwait'}</div>
                  </dd>
                </div>
                <div className="flex gap-3 py-2">
                  <dt className="w-16 shrink-0 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'الحالة' : 'Status'}</dt>
                  <dd data-calendar-status className="font-medium text-ink">{statusChip(selected.status, isAr)}</dd>
                </div>
                {selected.location && selected.detail_level !== 'busy_only' ? (
                  <div className="flex gap-3 py-2">
                    <dt className="w-16 shrink-0 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'الموقع' : 'Location'}</dt>
                    <dd className="min-w-0 text-ink">{selected.location}</dd>
                  </div>
                ) : null}
                {selected.meeting_url && selected.detail_level === 'full' ? (
                  <div className="flex gap-3 py-2">
                    <dt className="w-16 shrink-0 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'الرابط' : 'Link'}</dt>
                    <dd className="min-w-0 break-all text-wf-accent-review-ink">{selected.meeting_url}</dd>
                  </div>
                ) : null}
                {quietSynced || quietNotSynced ? (
                  <div className="flex gap-3 py-2">
                    <dt className="w-16 shrink-0 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'المزامنة' : 'Sync'}</dt>
                    <dd className="text-muted">{quietSynced ? (isAr ? 'تمت المزامنة' : 'Synced') : (isAr ? 'غير متزامن' : 'Not synced')}</dd>
                  </div>
                ) : null}
              </dl>

              {selected.interview_managed ? (
                <div className="mt-3 rounded-xl border border-line/70 bg-accent-soft px-3 py-2 text-[12px] leading-snug text-wf-accent-review-ink">
                  {isAr ? 'يُدار عبر المقابلات — التعديل من واجهة المقابلات فقط.' : 'Managed through Interviews — edit via Interview authority only.'}
                </div>
              ) : null}
              {isCalendarProjectionEvent(selected) ? (
                <div className="mt-3 rounded-xl border border-line/70 bg-accent-soft px-3 py-2 text-[12px] leading-snug text-wf-accent-review-ink">
                  {isAr
                    ? 'عرض زمني فقط — التعديل من الوحدة المالكة.'
                    : 'Read-only time view — make changes in the owning module.'}
                </div>
              ) : null}

              {selected.detail_level === 'full' && (selected.attendees || []).length ? (
                <div className="mt-3">
                  <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'الحضور' : 'Attendees'}</p>
                  <ul className="mt-1.5 space-y-1">
                    {(selected.attendees || []).map((a, i) => (
                      <li key={String(a.user_id || i)} className="rounded-lg bg-panel-muted/90 px-2 py-1 text-[12px] text-ink">
                        {String(a.user_id)} · {String(a.role || 'required')} · {String(a.rsvp_status || 'needs_action')}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {selected.detail_level === 'full' && (selected.guests || []).length ? (
                <div className="mt-3">
                  <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'الضيوف' : 'Guests'}</p>
                  <ul className="mt-1.5 space-y-1">
                    {(selected.guests || []).map((g, i) => (
                      <li key={String(g.guest_id || i)} className="flex items-center justify-between gap-2 rounded-lg bg-panel-muted/90 px-2 py-1 text-[12px] text-ink">
                        <span>
                          {String(g.display_name || g.email || g.phone || 'guest')} · {String(g.rsvp_status || 'needs_action')}
                          {g.invite_status ? ` · ${String(g.invite_status)}` : ''}
                        </span>
                        {canManage && g.guest_id ? (
                          <button
                            type="button"
                            className="underline"
                            onClick={() => {
                              void inviteCalendarGuest(access, selected.event_id, String(g.guest_id))
                                .then(() => onNotice?.(isAr ? 'تم وضع الدعوة في قائمة الإرسال' : 'Invite queued', 'success'))
                                .catch((err) => onNotice?.(err instanceof Error ? err.message : 'Invite failed', 'error'))
                            }}
                          >
                            {isAr ? 'دعوة' : 'Invite'}
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {rescheduleRequests.length ? (
                <div className="mt-3 rounded-xl border border-accent/35 bg-accent-soft p-2.5">
                  <p className="text-[11px] font-semibold text-wf-accent-review-ink">{isAr ? 'طلبات إعادة الجدولة' : 'Reschedule requests'}</p>
                  {rescheduleRequests.map((req) => (
                    <div key={String(req.request_id)} className="mt-2 text-[12px] text-wf-ink-muted">
                      <div>{String(req.note || (isAr ? 'بدون ملاحظة' : 'No note'))}</div>
                      {canManage ? (
                        <div className="mt-1 flex gap-2">
                          <button type="button" className="underline" onClick={() => void resolveRequest(String(req.request_id), 'accepted')}>
                            {isAr ? 'قبول الطلب' : 'Accept request'}
                          </button>
                          <button type="button" className="underline" onClick={() => void resolveRequest(String(req.request_id), 'declined')}>
                            {isAr ? 'رفض' : 'Decline'}
                          </button>
                        </div>
                      ) : null}
                      {req.interview_id ? (
                        <p className="mt-1 text-[10px] text-wf-ink-muted">
                          {isAr ? 'مرتبط بمقابلة — أكّد الوقت عبر المقابلات.' : 'Interview-linked — confirm time via Interviews.'}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}

              {selected.detail_level === 'full' && selected.status !== 'cancelled' && !isCalendarPreviewEvent(selected) && !isCalendarProjectionEvent(selected) ? (
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line/50 pt-3">
                  <span className="w-full text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{isAr ? 'ردّي' : 'My RSVP'}</span>
                  {(['accepted', 'declined', 'tentative'] as const).map((status) => (
                    <Button key={status} variant="secondary" disabled={rsvpBusy} onClick={() => void submitRsvp(status)} size="sm" className="h-8 text-[12px]">
                      {status === 'accepted' ? (isAr ? 'قبول' : 'Accept') : status === 'declined' ? (isAr ? 'رفض' : 'Decline') : isAr ? 'مبدئي' : 'Tentative'}
                    </Button>
                  ))}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {canManage && selected.detail_level === 'full' && !selected.interview_managed && !isCalendarPreviewEvent(selected) && !isCalendarProjectionEvent(selected) ? (
                  <>
                    <Button variant="secondary" size="sm" className="h-8 text-[12px]" onClick={() => openEdit(selected)}>{isAr ? 'تعديل' : 'Edit'}</Button>
                    <Button variant="secondary" size="sm" className="h-8 text-[12px]" onClick={() => void cancelSelected()}>{isAr ? 'إلغاء' : 'Cancel'}</Button>
                  </>
                ) : null}
                {selected.interview_managed && selected.interview_id && onOpenInterview ? (
                  <Button size="sm" className="h-8 text-[12px]" onClick={() => onOpenInterview(selected.interview_id!)}>{isAr ? 'فتح المقابلة' : 'Open interview'}</Button>
                ) : null}
                {isCalendarProjectionEvent(selected) && onOpenProjectionOwner && calendarProjectionDeepLink(selected) ? (
                  <Button
                    size="sm"
                    className="h-8 text-[12px]"
                    onClick={() => onOpenProjectionOwner(calendarProjectionDeepLink(selected)!)}
                  >
                    {isAr ? 'فتح السجل' : 'Open record'}
                  </Button>
                ) : null}
              </div>
            </div>
          </aside>,
            document.body,
          )
         : null}

        {composerOpen ? (
          <div className="fixed inset-0 z-[70]" data-calendar-composer-overlay>
            <button
              type="button"
              className="absolute inset-0 bg-ink/25"
              aria-label={isAr ? 'إغلاق' : 'Close'}
              data-calendar-composer-backdrop
              onClick={closeComposer}
            />
            <aside
              ref={composerPanelRef}
              role="dialog"
              aria-modal="true"
              data-calendar-composer-drawer
              data-calendar-detail-mode={isMobile ? 'sheet' : 'side'}
              className={
                isMobile
                  ? 'absolute inset-x-0 bottom-0 z-10 max-h-[92vh] overflow-y-auto rounded-t-[1.55rem] border border-line/55 bg-wf-surface-raised p-4 shadow-soft'
                  : 'absolute inset-y-0 end-0 z-10 flex w-full max-w-[400px] flex-col overflow-y-auto border-s border-line/55 bg-wf-surface-raised p-4 shadow-soft'
              }
              onClick={(event) => event.stopPropagation()}
            >
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-ink">{draft.event_id ? (isAr ? 'تعديل حدث' : 'Edit event') : isAr ? 'حدث جديد' : 'New event'}</h2>
              <button
                type="button"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-line/50 text-muted transition hover:bg-panel-muted hover:text-ink active:bg-line"
                aria-label={isAr ? 'إغلاق' : 'Close'}
                data-calendar-composer-close
                onClick={(event) => {
                  event.preventDefault()
                  event.stopPropagation()
                  closeComposer()
                }}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-sm">
              <label className="block space-y-1">
                <span className="text-xs text-muted">{isAr ? 'النوع' : 'Type'}</span>
                <select className="w-full rounded-xl border border-line/60 px-3 py-2" value={draft.event_type} onChange={(e) => setDraft({ ...draft, event_type: e.target.value })}>
                  {['meeting', 'personal_block', 'deadline', 'out_of_office', 'other'].map((t) => (
                    <option key={t} value={t}>{eventTypeLabel(t, isAr)}</option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-xs text-muted">{isAr ? 'العنوان' : 'Title'}</span>
                <input className="w-full rounded-xl border border-line/60 px-3 py-2" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="block space-y-1">
                  <span className="text-xs text-muted">{isAr ? 'البداية' : 'Start'}</span>
                  <input type="datetime-local" className="w-full rounded-xl border border-line/60 px-2 py-2" value={draft.start_local} onChange={(e) => setDraft({ ...draft, start_local: e.target.value })} />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs text-muted">{isAr ? 'النهاية' : 'End'}</span>
                  <input type="datetime-local" className="w-full rounded-xl border border-line/60 px-2 py-2" value={draft.end_local} onChange={(e) => setDraft({ ...draft, end_local: e.target.value })} />
                </label>
              </div>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={draft.all_day} onChange={(e) => setDraft({ ...draft, all_day: e.target.checked })} />
                {isAr ? 'طوال اليوم' : 'All day'}
              </label>
              <label className="block space-y-1">
                <span className="text-xs text-muted">{isAr ? 'الظهور' : 'Visibility'}</span>
                <select className="w-full rounded-xl border border-line/60 px-3 py-2" value={draft.visibility} onChange={(e) => setDraft({ ...draft, visibility: e.target.value })}>
                  <option value="private">{isAr ? 'خاص' : 'Private'}</option>
                  <option value="attendees_only">{isAr ? 'الحضور فقط' : 'Attendees only'}</option>
                  <option value="team">{isAr ? 'فريق التوظيف' : 'Hiring team'}</option>
                  {canCompany ? <option value="company">{isAr ? 'تقويم الشركة' : 'Company calendar'}</option> : null}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-xs text-muted">{isAr ? 'الموقع' : 'Location'}</span>
                <input className="w-full rounded-xl border border-line/60 px-3 py-2" value={draft.location} onChange={(e) => setDraft({ ...draft, location: e.target.value })} />
              </label>
              <label className="block space-y-1">
                <span className="text-xs text-muted">{isAr ? 'رابط الاجتماع' : 'Meeting URL'}</span>
                <input className="w-full rounded-xl border border-line/60 px-3 py-2" value={draft.meeting_url} onChange={(e) => setDraft({ ...draft, meeting_url: e.target.value })} />
              </label>
              <div className="space-y-1">
                <span className="text-xs text-muted">{isAr ? 'مدعو داخلي' : 'Internal attendee'}</span>
                <PeoplePicker
                  access={access}
                  purpose="directory"
                  locale={locale}
                  value={draft.attendee_user_id}
                  onChange={(userId) => setDraft({ ...draft, attendee_user_id: userId })}
                />
              </div>
              <label className="block space-y-1">
                <span className="text-xs text-muted">{isAr ? 'ضيف خارجي (بريد)' : 'External guest email'}</span>
                <input className="w-full rounded-xl border border-line/60 px-3 py-2" value={draft.guest_email} onChange={(e) => setDraft({ ...draft, guest_email: e.target.value })} />
              </label>

              {conflicts.length ? (
                <div className="space-y-2 rounded-xl border border-accent/40 bg-accent-soft p-3">
                  <p className="text-xs font-semibold text-wf-accent-review-ink">{isAr ? 'تعارضات' : 'Conflicts'}</p>
                  {conflicts.map((c, i) => (
                    <div key={`${c.type}-${i}`} className="text-xs text-wf-ink-muted">
                      <span className="font-semibold">{c.blocking ? (isAr ? 'مانع' : 'Blocking') : isAr ? 'تنبيه' : 'Warning'}</span>
                      {' · '}
                      {isAr && c.message_ar ? c.message_ar : c.message}
                    </div>
                  ))}
                  {canOverride && conflicts.some((c) => c.blocking) ? (
                    <div className="space-y-2 pt-1">
                      <label className="inline-flex items-center gap-2 text-xs">
                        <input
                          type="checkbox"
                          checked={draft.override_conflicts}
                          onChange={(e) => setDraft({ ...draft, override_conflicts: e.target.checked })}
                        />
                        {isAr ? 'تجاوز التعارضات' : 'Override conflicts'}
                      </label>
                      {draft.override_conflicts ? (
                        <input
                          className="w-full rounded-xl border border-line/60 px-3 py-2 text-xs"
                          placeholder={isAr ? 'سبب التجاوز' : 'Override reason'}
                          value={draft.override_reason}
                          onChange={(e) => setDraft({ ...draft, override_reason: e.target.value })}
                        />
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2 pt-1">
                <Button variant="secondary" onClick={() => void runPreview()}>{isAr ? 'معاينة التعارض' : 'Preview conflicts'}</Button>
                <Button disabled={saving || !draft.title.trim()} onClick={() => void saveDraft()}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {isAr ? 'حفظ' : 'Save'}
                </Button>
              </div>
            </div>
          </aside>
          </div>
        ) : null}
      </div>
    </section>
  )
}
