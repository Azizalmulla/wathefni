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
    <section className="rounded-[1.55rem] bg-[#fffaf0] p-5" dir={isAr ? 'rtl' : 'ltr'} data-testid="overview-my-calendar">
      <div className="flex items-center justify-between gap-3 px-1 pb-3">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-[#716a5e]" />
          <h3 className="text-[15px] font-semibold tracking-[-0.025em] text-[#23211d]">
            {isAr ? 'تقويمي' : 'My calendar'}
          </h3>
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-[#716a5e]" aria-label={isAr ? 'جاري التحديث' : 'Refreshing'} />
          ) : null}
        </div>
        <button className="text-xs font-semibold text-[#716a5e] underline-offset-4 hover:underline" onClick={onOpenCalendar} type="button">
          {isAr ? 'عرض التقويم الكامل' : 'View full calendar'}
        </button>
      </div>

      {coldLoading ? (
        <div className="flex items-center gap-2 py-6 text-sm text-[#716a5e]">
          <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading…'}
        </div>
      ) : (
        <>
          <div className="rounded-[1.1rem] bg-white/70 p-3" data-rendering-soft-keep data-rendering-updating={refreshing ? 'true' : undefined}>
            <div className="mb-2 text-center text-xs font-semibold text-[#716a5e]">
              {first.toLocaleDateString(isAr ? 'ar' : 'en', { month: 'long', year: 'numeric' })}
            </div>
            <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-[#8a8274]">
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
                    className={`relative grid h-8 place-items-center rounded-full text-[11px] ${
                      isSelected ? 'bg-[#23211d] text-white' : isToday ? 'bg-[#eee5d4] text-[#23211d]' : 'text-[#23211d] hover:bg-[#f3ebe0]'
                    }`}
                  >
                    {cell.day}
                    {hasBusy ? <span className={`absolute bottom-1 h-1 w-1 rounded-full ${isSelected ? 'bg-white' : 'bg-[#c89445]'}`} /> : null}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="mt-3 space-y-2">
            <div className="flex items-center justify-between px-1">
              <h4 className="text-xs font-semibold text-[#716a5e]">
                {selectedDay || data?.today
                  ? (isAr ? 'أحداث اليوم' : 'Day events')
                  : (isAr ? 'القادمة' : 'Upcoming')}
              </h4>
              {onAddEvent ? (
                <button type="button" className="inline-flex items-center gap-1 text-xs font-semibold text-[#716a5e]" onClick={onAddEvent}>
                  <Plus className="h-3.5 w-3.5" /> {isAr ? 'إضافة' : 'Add'}
                </button>
              ) : null}
            </div>
            {(dayItems.length ? dayItems : upcoming).length === 0 ? (
              <p className="px-1 text-sm text-[#8a8274]">{isAr ? 'لا أحداث' : 'No events'}</p>
            ) : (
              (dayItems.length ? dayItems : upcoming).map((event) => (
                <button
                  key={event.event_id}
                  type="button"
                  onClick={onOpenCalendar}
                  className="flex w-full items-center justify-between rounded-[1rem] border border-[#e8dfd0] bg-[#f8f3e9] px-3 py-2 text-left"
                >
                  <span className="truncate text-sm font-semibold text-[#23211d]">{eventLabel(event, isAr)}</span>
                  <span className="shrink-0 text-[11px] text-[#8a8274]">
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
