/**
 * Attendance demo gate — presentation-only. Never POSTs to resolve.
 */
import Constants from 'expo-constants'

import { readDemoFlag } from '@hr/features/demoProductionGuard'

export const ATTENDANCE_DEMO_SOURCE = 'hr_attendance_demo_v1' as const
export const ATTENDANCE_DEMO_ID_PREFIX = '__demo_att__'

export function attendanceDemoEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_ATTENDANCE_DEMO || '').trim()
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { attendanceDemo?: string } } | undefined)
      ?.unifiedApp?.attendanceDemo || '',
  ).trim()
  return readDemoFlag(fromEnv, fromExtra)
}

export function isAttendanceDemoId(id: string | null | undefined): boolean {
  return String(id || '').startsWith(ATTENDANCE_DEMO_ID_PREFIX)
}
