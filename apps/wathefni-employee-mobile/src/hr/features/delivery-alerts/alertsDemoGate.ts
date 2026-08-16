/**
 * Delivery Alerts demo — presentation-only. Never mutates outbound or tasks.
 */
import Constants from 'expo-constants'

import { readDemoFlag } from '@hr/features/demoProductionGuard'

export const ALERTS_DEMO_SOURCE = 'hr_delivery_alerts_demo_v1' as const
export const ALERTS_DEMO_ID_PREFIX = '__demo_alert__'

export function alertsDemoEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_DELIVERY_ALERTS_DEMO || '').trim()
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { deliveryAlertsDemo?: string } } | undefined)
      ?.unifiedApp?.deliveryAlertsDemo || '',
  ).trim()
  return readDemoFlag(fromEnv, fromExtra)
}

export function isAlertsDemoId(id: string | null | undefined): boolean {
  return String(id || '').startsWith(ALERTS_DEMO_ID_PREFIX)
}
