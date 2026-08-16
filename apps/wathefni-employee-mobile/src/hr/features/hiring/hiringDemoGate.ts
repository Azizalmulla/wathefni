/**
 * Hiring demo gate — presentation-only. Never writes to recruiting APIs.
 *
 * Demo is OFF unless EXPO_PUBLIC_HR_HIRING_DEMO=1 (or baked extra).
 * Demo ids are prefixed `__demo__` and must never be sent to decision endpoints.
 */
import Constants from 'expo-constants'

import { readDemoFlag } from '@hr/features/demoProductionGuard'

export const HIRING_DEMO_SOURCE = 'hr_hiring_demo_v1' as const
export const HIRING_DEMO_ID_PREFIX = '__demo__'

export function hiringDemoEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_HIRING_DEMO || '').trim()
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { hiringDemo?: string } } | undefined)?.unifiedApp
      ?.hiringDemo || '',
  ).trim()
  return readDemoFlag(fromEnv, fromExtra)
}

export function isHiringDemoId(id: string | null | undefined): boolean {
  return String(id || '').startsWith(HIRING_DEMO_ID_PREFIX)
}
