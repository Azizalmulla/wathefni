import { StyleSheet, Text, View } from 'react-native'

import { StatusChip } from '@/components/ui'
import { statusTone } from '@/lib/format'
import { ambient, colors, font, radius, scheduleComposition, spacing, typeScaling } from '@/theme'

/**
 * Schedule attendance uses Home brand fills (not semantic outline chips):
 * Present → green, Late → yellow, Absent → pink. The label always carries the word.
 */
export type AttendanceKind = 'present' | 'late' | 'absent'

export function attendanceKind(status: string | null | undefined): AttendanceKind | null {
  const s = String(status || '').toLowerCase()
  if (s === 'present') return 'present'
  if (s === 'late') return 'late'
  if (s === 'absent') return 'absent'
  return null
}

export function attendanceFill(kind: AttendanceKind): string {
  if (kind === 'present') return ambient.leave.fill
  if (kind === 'late') return ambient.payslips.fill
  return ambient.schedule.fill
}

/** Planned / scheduled chip — powder blue family, not a semantic outline. */
export function ScheduledStatusMark({ label }: { label: string }) {
  return (
    <View style={[styles.pill, { backgroundColor: scheduleComposition.planned.fill }]}>
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.pillText}>
        {label}
      </Text>
    </View>
  )
}

export function AttendanceStatusMark({
  status,
  label,
}: {
  status: string | null | undefined
  label: string
}) {
  const kind = attendanceKind(status)
  if (!kind) return <StatusChip label={label} tone={statusTone(status)} />
  return (
    <View style={[styles.pill, { backgroundColor: attendanceFill(kind) }]}>
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.pillText}>
        {label}
      </Text>
    </View>
  )
}

export function AttendanceCountPill({
  kind,
  value,
  label,
}: {
  kind: AttendanceKind
  value: string
  label: string
}) {
  return (
    <View
      style={[styles.countPill, { backgroundColor: attendanceFill(kind) }]}
      accessibilityLabel={`${value} ${label}`}
    >
      <Text maxFontSizeMultiplier={typeScaling.body} style={styles.countValue}>
        {value}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.countLabel}>
        {label}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical: 5,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
    flexShrink: 1,
  },
  pillText: { color: colors.ink, fontSize: font.tiny, fontWeight: '800' },
  countPill: {
    flexGrow: 1,
    flexBasis: 0,
    minWidth: 96,
    gap: 2,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.xl,
  },
  countValue: { color: colors.ink, fontSize: font.h3, fontWeight: '800' },
  countLabel: { color: colors.ink, fontSize: font.tiny, fontWeight: '700', opacity: 0.78 },
})
