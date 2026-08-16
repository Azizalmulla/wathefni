import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'

import { AttendanceHistoryView } from '@/features/schedule/AttendanceHistoryView'
import { kuwaitToday } from '@/lib/format'

/**
 * Dedicated attendance history — beyond the Schedule root ~30-day window.
 * Uses `/app/schedule/history` keyset pages; does not redesign Schedule root.
 */
export default function ScheduleHistoryScreen() {
  const onBack = useEmployeeSafeBack()

  return (
    <AttendanceHistoryView
      today={kuwaitToday()}
      onBack={onBack}
    />
  )
}
