import { memo, useCallback, useEffect, useMemo, useRef, useState, startTransition } from 'react'
import {
  Dimensions,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native'

import { useI18n } from '@/i18n'
import { localizeNumerals } from '@/lib/format'
import { useReducedMotion } from '@/motion'
import { selectionFeedback, weekSnapFeedback } from '@/native/haptics'
import { colors, font, layout, spacing, typeScaling } from '@/theme'

import {
  addDaysISO,
  buildWeekDays,
  buildWeekStarts,
  firstWeekdayForLocale,
  startOfWeekISO,
  weekdayUTC,
} from './scheduleDayModel'

/**
 * Vertical stadium drawn *inside* the selected day cell.
 * An absolute overlay + translateX was clipped by the horizontal ScrollView on the
 * first/last day (left edge flat, text shoved right). In-cell fill cannot clip.
 */
const CAPSULE_WIDTH = 38
const CAPSULE_HEIGHT = 56
const CAPSULE_RADIUS = CAPSULE_WIDTH / 2
const STRIP_HEIGHT = 68

type Props = {
  today: string
  selectedDate: string
  windowDays: number
  /** Precomputed presence set — must be referentially stable while payload is unchanged. */
  presence: Set<string>
  onSelectDate: (date: string) => void
}

/**
 * Week strip hot path:
 * - Local visual selection updates immediately (latest tap wins).
 * - Selected fill lives in the day cell — perfect stadium, no edge clipping.
 * - Parent only receives the date for the day panel; strip does not wait on it to move.
 */
export const ScheduleWeekStrip = memo(function ScheduleWeekStrip({
  today,
  selectedDate,
  windowDays,
  presence,
  onSelectDate,
}: Props) {
  const { locale, isRTL, t } = useI18n()
  const reducedMotion = useReducedMotion()
  const screenW = Dimensions.get('window').width
  const firstDay = firstWeekdayForLocale(locale)

  const weekStarts = useMemo(
    () => buildWeekStarts(today, windowDays, windowDays, firstDay),
    [today, windowDays, firstDay],
  )

  const weekdayLabels = useMemo(() => {
    const tag = locale === 'ar' ? 'ar-KW' : 'en-GB'
    return Array.from({ length: 7 }, (_, dow) => {
      const probe = addDaysISO('2024-01-07', dow)
      const [y, m, d] = probe.split('-').map(Number)
      const label = new Intl.DateTimeFormat(tag, {
        weekday: 'short',
        timeZone: 'UTC',
      }).format(new Date(Date.UTC(y, m - 1, d)))
      return locale === 'ar' ? label : label.replace(/\./g, '').slice(0, 3).toUpperCase()
    })
  }, [locale])

  const [visualDate, setVisualDate] = useState(selectedDate)
  const visualDateRef = useRef(selectedDate)
  const lastEmittedRef = useRef(selectedDate)
  const weekIndexRef = useRef(0)
  const scrollRef = useRef<ScrollView>(null)
  const ignoreScrollSync = useRef(false)
  const onSelectDateRef = useRef(onSelectDate)
  onSelectDateRef.current = onSelectDate

  const dayIndexInWeek = useCallback(
    (date: string) => {
      const days = buildWeekDays(startOfWeekISO(date, firstDay))
      return Math.max(0, days.indexOf(date))
    },
    [firstDay],
  )

  const scrollToWeekIfNeeded = useCallback(
    (date: string, animated: boolean) => {
      const weekStart = startOfWeekISO(date, firstDay)
      const idx = Math.max(0, weekStarts.indexOf(weekStart))
      if (idx === weekIndexRef.current) return
      weekIndexRef.current = idx
      ignoreScrollSync.current = true
      scrollRef.current?.scrollTo({
        x: idx * screenW,
        animated: animated && !reducedMotion,
      })
      setTimeout(() => {
        ignoreScrollSync.current = false
      }, animated && !reducedMotion ? 280 : 0)
    },
    [firstDay, reducedMotion, screenW, weekStarts],
  )

  const applySelection = useCallback(
    (date: string, source: 'tap' | 'external' | 'swipe') => {
      if (date === visualDateRef.current && source === 'tap') return
      visualDateRef.current = date
      setVisualDate(date)
      scrollToWeekIfNeeded(date, source === 'tap' || source === 'external')
      // Tap = day tick. Swipe settle = stronger week snap. Never while dragging.
      // Feedback is throttled centrally — rapid taps stay smooth.
      if (source === 'tap') selectionFeedback()
      else if (source === 'swipe') weekSnapFeedback()
      if (date !== lastEmittedRef.current) {
        lastEmittedRef.current = date
        startTransition(() => {
          onSelectDateRef.current(date)
        })
      }
    },
    [scrollToWeekIfNeeded],
  )

  const onTap = useCallback((date: string) => applySelection(date, 'tap'), [applySelection])

  useEffect(() => {
    if (selectedDate === lastEmittedRef.current) return
    lastEmittedRef.current = selectedDate
    applySelection(selectedDate, 'external')
  }, [selectedDate, applySelection])

  useEffect(() => {
    weekIndexRef.current = Math.max(
      0,
      weekStarts.indexOf(startOfWeekISO(visualDateRef.current, firstDay)),
    )
  }, [firstDay, weekStarts])

  const onMomentumEnd = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      if (ignoreScrollSync.current) return
      const idx = Math.round(e.nativeEvent.contentOffset.x / Math.max(screenW, 1))
      const clamped = Math.max(0, Math.min(weekStarts.length - 1, idx))
      weekIndexRef.current = clamped
      const start = weekStarts[clamped]
      if (!start) return
      const slot = dayIndexInWeek(visualDateRef.current)
      const next = buildWeekDays(start)[slot] || start
      applySelection(next, 'swipe')
    },
    [applySelection, dayIndexInWeek, screenW, weekStarts],
  )

  const selectedWeekStart = startOfWeekISO(visualDate, firstDay)
  const initialWeekIndex = Math.max(0, weekStarts.indexOf(startOfWeekISO(selectedDate, firstDay)))

  return (
    <View
      style={[styles.bleed, { marginHorizontal: -layout.pageMargin }]}
      accessibilityLabel={t('schedule.weekStripLabel')}
    >
      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        decelerationRate="fast"
        showsHorizontalScrollIndicator={false}
        directionalLockEnabled
        disableIntervalMomentum
        nestedScrollEnabled
        keyboardShouldPersistTaps="handled"
        onMomentumScrollEnd={onMomentumEnd}
        style={styles.ltr}
        contentOffset={{ x: initialWeekIndex * screenW, y: 0 }}
      >
        {weekStarts.map((weekStart) => (
          <WeekPage
            key={weekStart}
            weekStart={weekStart}
            width={screenW}
            today={today}
            selectedDate={weekStart === selectedWeekStart ? visualDate : null}
            isRTL={isRTL}
            locale={locale}
            weekdayLabels={weekdayLabels}
            presence={presence}
            todayLabel={t('schedule.today')}
            onSelectDate={onTap}
          />
        ))}
      </ScrollView>
    </View>
  )
})

type WeekPageProps = {
  weekStart: string
  width: number
  today: string
  selectedDate: string | null
  isRTL: boolean
  locale: string
  weekdayLabels: string[]
  presence: Set<string>
  todayLabel: string
  onSelectDate: (date: string) => void
}

const WeekPage = memo(function WeekPage({
  weekStart,
  width,
  today,
  selectedDate,
  isRTL,
  locale,
  weekdayLabels,
  presence,
  todayLabel,
  onSelectDate,
}: WeekPageProps) {
  const days = useMemo(() => buildWeekDays(weekStart), [weekStart])
  return (
    <View style={[styles.weekPage, { width }]}>
      <View style={[styles.weekRow, isRTL && styles.weekRowRtl]}>
        {days.map((date) => (
          <DayCell
            key={date}
            date={date}
            selected={selectedDate === date}
            isToday={date === today}
            hasPresence={presence.has(date)}
            weekday={weekdayLabels[weekdayUTC(date)] || ''}
            dayNum={localizeNumerals(Number(date.slice(8, 10)), locale)}
            todayLabel={todayLabel}
            onSelectDate={onSelectDate}
          />
        ))}
      </View>
    </View>
  )
})

type DayCellProps = {
  date: string
  selected: boolean
  isToday: boolean
  hasPresence: boolean
  weekday: string
  dayNum: string
  todayLabel: string
  onSelectDate: (date: string) => void
}

const DayCell = memo(function DayCell({
  date,
  selected,
  isToday,
  hasPresence,
  weekday,
  dayNum,
  todayLabel,
  onSelectDate,
}: DayCellProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={`${weekday} ${dayNum}${isToday ? `, ${todayLabel}` : ''}`}
      hitSlop={4}
      onPress={() => onSelectDate(date)}
      style={styles.dayCell}
    >
      {/* Capsule is a child of the cell — centered, never clipped by the week ScrollView. */}
      {selected ? <View style={styles.capsule} pointerEvents="none" /> : null}
      <View style={styles.dayStack} accessible={false}>
        <Text
          maxFontSizeMultiplier={typeScaling.chip}
          style={[styles.weekday, selected && styles.weekdaySelected]}
        >
          {weekday}
        </Text>
        <Text
          maxFontSizeMultiplier={typeScaling.body}
          style={[styles.dayNum, selected && styles.dayNumSelected]}
        >
          {dayNum}
        </Text>
      </View>
      {!selected && isToday ? <View style={styles.todayMark} /> : null}
      {!selected && !isToday && hasPresence ? <View style={styles.presenceDot} /> : null}
    </Pressable>
  )
})

const styles = StyleSheet.create({
  bleed: {
    height: STRIP_HEIGHT + spacing.sm,
  },
  ltr: {
    direction: 'ltr',
  },
  weekPage: {
    paddingHorizontal: layout.pageMargin,
    justifyContent: 'center',
  },
  weekRow: {
    height: STRIP_HEIGHT,
    flexDirection: 'row',
    alignItems: 'center',
  },
  weekRowRtl: {
    flexDirection: 'row-reverse',
  },
  dayCell: {
    flex: 1,
    height: STRIP_HEIGHT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  capsule: {
    position: 'absolute',
    width: CAPSULE_WIDTH,
    height: CAPSULE_HEIGHT,
    borderRadius: CAPSULE_RADIUS,
    backgroundColor: colors.ink,
  },
  dayStack: {
    height: CAPSULE_HEIGHT,
    width: CAPSULE_WIDTH,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 1,
    zIndex: 1,
  },
  weekday: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.6,
    textAlign: 'center',
    includeFontPadding: false,
  },
  weekdaySelected: {
    color: colors.primaryText,
  },
  dayNum: {
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '700',
    textAlign: 'center',
    includeFontPadding: false,
  },
  dayNumSelected: {
    color: colors.primaryText,
  },
  todayMark: {
    position: 'absolute',
    bottom: 5,
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.ink,
  },
  presenceDot: {
    position: 'absolute',
    bottom: 6,
    width: 3,
    height: 3,
    borderRadius: 1.5,
    backgroundColor: colors.subtle,
    opacity: 0.7,
  },
})
