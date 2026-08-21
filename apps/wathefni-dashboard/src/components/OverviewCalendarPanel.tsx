import { memo, useEffect, useState } from 'react'
import { CalendarDays, Loader2, Plus } from 'lucide-react'

import type { CalendarEvent, CalendarOverviewResponse } from '@/lib/api'
import { useCalendarOverviewQuery } from '@/lib/query/hooks'
import type { DashboardAccess } from '@/types'

type Props = {
  access: DashboardAccess
  locale?: 'en' | 'ar'
  calendarEnabled?: boolean
  onOpenCalendar: () => void
  onAddEvent?: () => void
}

function eventLabel(event: CalendarEvent, isAr: boolean) {
  if (event.detail_level === 'busy_only' || event.busy) return isAr ? 'مشغول' : 'Busy'
  if (isAr && event.title_ar) return event.title_ar
  return event.title || (isAr ? 'حدث' : 'Event')
}

/** Overview personal summary widget — always signed-in user scope (not a second Calendar UI). */
export const OverviewCalendarPanel = memo(function OverviewCalendarPanel({
  access,
  locale = 'en',
  calendarEnabled = true,
  onOpenCalendar,
  onAddEvent,
}: Props) {
  const isAr = locale === 'ar'
  const [selectedDay, setSelectedDay] = useState<string>('')
  const query = useCalendarOverviewQuery(access, 'mine', calendarEnabled)
  const data = (query.data || null) as CalendarOverviewResponse | null
  const refreshing = query.isFetching && Boolean(data)
  const coldLoading = query.isPending && !data

  useEffect(() => {
    if (data?.today && !selectedDay) setSelectedDay(data.today)
  }, [data, selectedDay])

  if (!calendarEnabled) return null

  const year = data?.month.year || new Date().getFullYear()
  const month = (data?.month.month || new Date().getMonth() + 1) - 1
  const first = new Date(year, month, 1)
  const startPad = first.getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const busyDays = new Set(data?.month.busy_days || [])
  const cells: Array<{ day: number | null; iso?: string }> = [
    ...Array.from({ length: startPad }, () => ({ day: null })),
    ...Array.from({ length: daysInMonth }, (_, i) => {
      const day = i + 1
      const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
      return { day, iso }
    }),
  ]

  const upcoming = (data?.upcoming || []).slice(0, 5)
  const dayItems = upcoming.filter((e) => String(e.start_at || '').startsWith(selectedDay || data?.today || ''))

  return (
    <section className="rounded-[1.55rem] bg-semantic-surface p-5" dir={isAr ? 'rtl' : 'ltr'} data-testid="overview-my-calendar">
      <div className="flex items-center justify-between gap-3 px-1 pb-3">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-semantic-subtle" />
          <h3 className="text-[15px] font-semibold tracking-[-0.025em] text-semantic-ink">
            {isAr ? 'تقويمي' : 'My calendar'}
          </h3>
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-semantic-subtle" aria-label={isAr ? 'جاري التحديث' : 'Refreshing'} />
          ) : null}
        </div>
        <button className="text-xs font-semibold text-semantic-subtle underline-offset-4 hover:underline" onClick={onOpenCalendar} type="button">
          {isAr ? 'عرض التقويم الكامل' : 'View full calendar'}
        </button>
      </div>

      {coldLoading ? (
        <div className="flex items-center gap-2 py-6 text-sm text-[#716a5e]">
          <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading…'}
        </div>
      ) : (
        <>
          <div className="rounded-[1.1rem] bg-semantic-surface-raised p-3" data-rendering-soft-keep data-rendering-updating={refreshing ? 'true' : undefined}>
            <div className="mb-2 text-center text-xs font-semibold text-semantic-subtle">
              {first.toLocaleDateString(isAr ? 'ar' : 'en', { month: 'long', year: 'numeric' })}
            </div>
            <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-semantic-mist">
              {(isAr ? ['ح', 'ن', 'ث', 'ر', 'خ', 'ج', 'س'] : ['S', 'M', 'T', 'W', 'T', 'F', 'S']).map((d, i) => (
                <div key={`${d}-${i}`}>{d}</div>
              ))}
            </div>
            <div className="mt-1 grid grid-cols-7 gap-1">
              {cells.map((cell, idx) => {
                if (!cell.day) return <div key={`pad-${idx}`} />
                const isToday = cell.iso === data?.today
                const isSelected = cell.iso === selectedDay
                const hasBusy = busyDays.has(cell.iso || '')
                return (
                  <button
                    key={cell.iso}
                    type="button"
                    onClick={() => setSelectedDay(cell.iso || '')}
                    className={`relative grid h-8 place-items-center rounded-full text-[11px] transition-colors duration-150 ${
                      isSelected ? 'bg-semantic-ink text-white' : isToday ? 'bg-semantic-accent-soft text-semantic-ink' : 'text-semantic-ink hover:bg-semantic-accent-soft'
                    }`}
                  >
                    {cell.day}
                    {hasBusy ? <span className={`absolute bottom-1 h-1 w-1 rounded-full ${isSelected ? 'bg-white' : 'bg-semantic-accent'}`} /> : null}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="mt-3 space-y-2">
            <div className="flex items-center justify-between px-1">
              <h4 className="text-xs font-semibold text-semantic-subtle">
                {selectedDay || data?.today
                  ? (isAr ? 'أحداث اليوم' : 'Day events')
                  : (isAr ? 'القادمة' : 'Upcoming')}
              </h4>
              {onAddEvent ? (
                <button type="button" className="inline-flex items-center gap-1 text-xs font-semibold text-semantic-subtle" onClick={onAddEvent}>
                  <Plus className="h-3.5 w-3.5" /> {isAr ? 'إضافة' : 'Add'}
                </button>
              ) : null}
            </div>
            {(dayItems.length ? dayItems : upcoming).length === 0 ? (
              <p className="px-1 text-sm text-semantic-mist">{isAr ? 'لا أحداث' : 'No events'}</p>
            ) : (
              (dayItems.length ? dayItems : upcoming).map((event) => (
                <button
                  key={event.event_id}
                  type="button"
                  onClick={onOpenCalendar}
                  className="flex w-full items-center justify-between rounded-[1rem] border border-semantic-line bg-semantic-surface-raised px-3 py-2 text-start"
                >
                  <span className="truncate text-sm font-semibold text-semantic-ink">{eventLabel(event, isAr)}</span>
                  <span className="shrink-0 text-[11px] text-semantic-mist">
                    {event.start_at ? new Date(event.start_at).toLocaleTimeString(isAr ? 'ar' : 'en', { hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </button>
              ))
            )}
          </div>
        </>
      )}
    </section>
  )
})
