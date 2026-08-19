import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '..')
const calendarSrc = readFileSync(resolve(root, 'components/CalendarShell.tsx'), 'utf8')
const appSrc = readFileSync(resolve(root, 'App.tsx'), 'utf8')

describe('Calendar Wave 1c final visual closure', () => {
  it('uses one shell title path without Wathefni Calendar hierarchy', () => {
    expect(calendarSrc).not.toContain('Wathefni Calendar')
    expect(calendarSrc).not.toContain('WATHEFNI canary')
    expect(calendarSrc).toContain('data-calendar-wave1c')
    expect(calendarSrc).toContain('data-calendar-populated-preview-banner')
    expect(appSrc).toContain("pagePersonality === 'spatial' ? 'h-8 w-8 px-0")
  })

  it('uses overlay detail drawer / mobile sheet without grid push', () => {
    expect(calendarSrc).toContain('data-calendar-detail-drawer')
    expect(calendarSrc).toContain("data-calendar-detail-mode={isMobile ? 'sheet' : 'side'}")
    expect(calendarSrc).not.toContain('xl:grid-cols-[minmax(0,1fr)_360px]')
    expect(calendarSrc).toContain('useBodyScrollLock')
  })

  it('keeps preview disclosure without repeating Preview in every title', () => {
    expect(calendarSrc).toContain('stripPreviewLabel')
    expect(calendarSrc).toContain('eventPrimaryLabel')
    expect(calendarSrc).toContain('data-preview-only')
    expect(calendarSrc).toContain('Preview only — not a real record')
    expect(calendarSrc).not.toMatch(/uppercase tracking-wide[\s\S]{0,40}Preview/)
  })

  it('preserves Wave 1b contracts', () => {
    expect(calendarSrc).toContain('selectedSnapshot')
    expect(calendarSrc).toContain('captureScroll')
    expect(calendarSrc).toContain('bg-wf-accent-follow-soft')
    expect(calendarSrc).toContain('interview_managed')
    expect(calendarSrc).toContain('Managed through Interviews')
  })

  it('uses cascade overlap layout with readable titles and portal detail', () => {
    expect(calendarSrc).toContain('CALENDAR_CASCADE_OFFSET_PX')
    expect(calendarSrc).toContain("placement: 'cascade'")
    expect(calendarSrc).toContain('data-calendar-overlap-more')
    expect(calendarSrc).toContain('data-calendar-overlap-menu')
    expect(calendarSrc).toContain('line-clamp-2')
    expect(calendarSrc).toContain('createPortal')
    expect(calendarSrc).toContain('data-calendar-all-day-row')
    expect(calendarSrc).toContain('data-calendar-detail-close')
    expect(calendarSrc).toContain('min-w-[1120px]')
    expect(calendarSrc).toContain('data-calendar-category-rail')
    expect(calendarSrc).not.toContain('hover:-translate-y-px')
    expect(calendarSrc).not.toContain('whitespace-nowrap')
  })

  it('uses one compact composition with reliable detail close paths', () => {
    expect(calendarSrc).toContain('data-calendar-composition')
    expect(calendarSrc).toContain('data-calendar-controls')
    expect(calendarSrc).toContain('data-calendar-detail-accent')
    expect(calendarSrc).toContain('data-calendar-event')
    expect(calendarSrc).toContain('closeSelected()')
    expect(calendarSrc).toContain("event.key !== 'Escape'")
    expect(calendarSrc).toContain("closest('[data-calendar-event]')")
    expect(calendarSrc).toContain('removeQueries')
    expect(calendarSrc).toContain('selectedId && selected && !composerOpen')
  })
})
