/**
 * Auth Wave 2 Phase 3 — single-flight auto-lock coordinator.
 * Only the resume path may seal. Background work only records intent in refs.
 */

import type { AutoLockDecisionReason, AutoLockTimeoutMs } from './autoLockPolicy'
import { decideAutoLockOnResume } from './autoLockPolicy'

export type AutoLockPendingIntent = 'timeout' | 'confirmed_device_lock' | null

export type AutoLockResumeSnapshot = {
  awayStartedAt: number | null
  resumeAt: number
  elapsedMs: number | null
  timeoutMs: AutoLockTimeoutMs
  enteredBackground: boolean
  deviceWasLocked: boolean
  pendingIntent: AutoLockPendingIntent
  reason: AutoLockDecisionReason
}

/**
 * Pure resume decision. Prefer explicit pendingIntent from a settled background
 * observation; otherwise fall back to elapsed timeout after a true background.
 */
export function coordinateResumeDecision(input: {
  awayStartedAt: number | null
  resumeAt: number
  timeoutMs: AutoLockTimeoutMs
  enteredBackground: boolean
  deviceWasLocked: boolean
  pendingIntent: AutoLockPendingIntent
}): AutoLockResumeSnapshot {
  const elapsedMs = input.awayStartedAt != null ? input.resumeAt - input.awayStartedAt : null
  let reason: AutoLockDecisionReason = 'none'

  if (!input.enteredBackground) {
    reason = 'none'
  } else if (input.pendingIntent === 'confirmed_device_lock' || input.deviceWasLocked) {
    reason = 'confirmed_device_lock'
  } else if (input.pendingIntent === 'timeout') {
    reason = 'timeout'
  } else {
    reason = decideAutoLockOnResume({
      elapsedMs: elapsedMs ?? 0,
      timeoutMs: input.timeoutMs,
      deviceWasLocked: false,
      enteredBackground: true,
    })
  }

  return {
    awayStartedAt: input.awayStartedAt,
    resumeAt: input.resumeAt,
    elapsedMs,
    timeoutMs: input.timeoutMs,
    enteredBackground: input.enteredBackground,
    deviceWasLocked: input.deviceWasLocked,
    pendingIntent: input.pendingIntent,
    reason,
  }
}
