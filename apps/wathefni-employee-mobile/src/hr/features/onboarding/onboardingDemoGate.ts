/**
 * Onboarding demo gate — presentation-only. Never POSTs review.
 */
import Constants from 'expo-constants'

import { readDemoFlag } from '@hr/features/demoProductionGuard'

export const ONBOARDING_DEMO_SOURCE = 'hr_onboarding_demo_v1' as const
export const ONBOARDING_DEMO_ID_PREFIX = '__demo_ob__'

export function onboardingDemoEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_ONBOARDING_DEMO || '').trim()
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { onboardingDemo?: string } } | undefined)
      ?.unifiedApp?.onboardingDemo || '',
  ).trim()
  return readDemoFlag(fromEnv, fromExtra)
}

export function isOnboardingDemoKey(key: string | null | undefined): boolean {
  return String(key || '').startsWith(ONBOARDING_DEMO_ID_PREFIX)
}
