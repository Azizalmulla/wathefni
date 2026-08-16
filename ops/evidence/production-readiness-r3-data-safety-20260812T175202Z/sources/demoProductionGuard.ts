/**
 * R3 production-build guard for HR demo queues.
 *
 * A production release must never substitute fabricated Hiring / Attendance /
 * Shifts / Onboarding / Documents / Tasks / Delivery Alert queues, even if an
 * EAS env value or OTA publish accidentally sets EXPO_PUBLIC_HR_*_DEMO=1.
 * Development and design-preview builds can still opt in explicitly.
 */
import Constants from 'expo-constants'
import * as Updates from 'expo-updates'

export function isProductionReleaseBuild(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_WATHEFNI_PRODUCTION_RELEASE || '').trim()
  if (fromEnv === '1') return true
  const extra = Constants.expoConfig?.extra as { dataSafety?: { productionRelease?: string } } | undefined
  if (String(extra?.dataSafety?.productionRelease || '').trim() === '1') return true
  const channel = String(Updates.channel || '').trim().toLowerCase()
  return channel === 'production' || channel === 'canary'
}

export function demoAllowedInThisBuild(): boolean {
  return !isProductionReleaseBuild()
}

export function readDemoFlag(fromEnv: string, fromExtra: string): boolean {
  if (!demoAllowedInThisBuild()) return false
  const env = String(fromEnv || '').trim()
  if (env === '1') return true
  if (env === '0') return false
  return String(fromExtra || '').trim() === '1'
}
