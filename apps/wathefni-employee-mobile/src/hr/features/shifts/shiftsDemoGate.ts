/**
 * Shifts demo gate — presentation-only. Never POSTs swap decisions.
 */
import Constants from 'expo-constants'

import { readDemoFlag } from '@hr/features/demoProductionGuard'

export const SHIFTS_DEMO_SOURCE = 'hr_shifts_demo_v1' as const
export const SHIFTS_DEMO_ID_PREFIX = '__demo_swap__'
export const SHIFTS_DEMO_SHIFT_PREFIX = '__demo_shift__'

export function shiftsDemoEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_SHIFTS_DEMO || '').trim()
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { shiftsDemo?: string } } | undefined)?.unifiedApp
      ?.shiftsDemo || '',
  ).trim()
  return readDemoFlag(fromEnv, fromExtra)
}

export function isShiftsDemoSwapId(id: string | null | undefined): boolean {
  return String(id || '').startsWith(SHIFTS_DEMO_ID_PREFIX)
}
