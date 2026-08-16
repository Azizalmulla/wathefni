import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  CALENDAR_HOUR_PX,
  CALENDAR_MIN_EVENT_HEIGHT_PX,
  calendarCardVariant,
  eventCardInteractiveClass,
  eventRailClass,
  eventSurfaceClass,
} from '@/components/CalendarShell'

describe('Calendar Visual System', () => {
  const src = readFileSync(resolve(__dirname, 'CalendarShell.tsx'), 'utf8')

  it('uses token surfaces, category rail, and selected interactive chrome', () => {
    expect(src).toContain('data-calendar-category-rail')
    expect(src).toContain('data-calendar-card-variant')
    expect(src).toContain('data-calendar-selected')
    expect(src).toContain('eventCardInteractiveClass')
    expect(src).toContain('ring-2 ring-wf-ink/25')
    expect(src).toContain('bg-wf-surface-raised')
    expect(src).toContain('w-[3px]')
    expect(src).not.toMatch(/border-transparent bg-wf-accent/)
    expect(src).not.toMatch(/#[0-9a-fA-F]{6}/)
    expect(src).not.toContain('outline-[#8f6a32]')
    expect(src).not.toContain('bg-[#22211f]')
    expect(CALENDAR_HOUR_PX).toBe(64)
    expect(CALENDAR_MIN_EVENT_HEIGHT_PX).toBe(40)
  })

  it('classifies approved card variants', () => {
    expect(calendarCardVariant({ event_id: '1', all_day: true } as any)).toBe('all-day')
    expect(calendarCardVariant({ event_id: '1', start_at: '2026-08-05T09:00:00+03:00', end_at: '2026-08-05T09:30:00+03:00' } as any)).toBe('solo-short')
    expect(calendarCardVariant({ event_id: '1', start_at: '2026-08-05T09:00:00+03:00', end_at: '2026-08-05T10:30:00+03:00' } as any)).toBe('solo-medium')
    expect(calendarCardVariant({ event_id: '1', start_at: '2026-08-05T09:00:00+03:00', end_at: '2026-08-05T11:00:00+03:00' } as any)).toBe('solo-long')
    expect(calendarCardVariant({ event_id: '1', start_at: '2026-08-05T09:00:00+03:00', end_at: '2026-08-05T10:00:00+03:00' } as any, { placement: 'cascade' })).toBe('cascade')
    expect(calendarCardVariant({ event_id: '1' } as any, { month: true })).toBe('month')
  })

  it('keeps warm meeting surface and accent rails on categories', () => {
    const meeting = eventSurfaceClass({ event_id: 'm', event_type: 'meeting' } as any)
    const training = { event_id: 't', metadata: { preview_category: 'training_company' } } as any
    expect(meeting).toContain('bg-panel-muted/95')
    expect(meeting).toContain('border-line/50')
    expect(eventRailClass({ event_id: 'i', event_type: 'interview' } as any)).toContain('bg-wf-accent-follow')
    expect(eventSurfaceClass(training)).toContain('bg-wf-accent-priority-soft')
    expect(eventRailClass(training)).toContain('bg-wf-accent-priority')
    expect(eventCardInteractiveClass(true)).toContain('ring-2 ring-wf-ink/25')
    expect(eventCardInteractiveClass(false)).not.toContain('ring-2')
  })

  it('uses explicit all-day semantics and non-clipping short-card padding', () => {
    expect(src).toContain('starts today')
    expect(src).toContain('Away all day')
    expect(src).toContain("'px-2 py-1'")
    expect(src).toContain('anchorLongCard')
    expect(src).not.toContain('border-dashed border-line/15')
  })
})
