/**
 * HR Tasks demo — presentation-only. Never POSTs resolve.
 */
import Constants from 'expo-constants'

import { readDemoFlag } from '@hr/features/demoProductionGuard'

export const TASKS_DEMO_SOURCE = 'hr_tasks_demo_v1' as const
export const TASKS_DEMO_ID_PREFIX = '__demo_task__'

export function tasksDemoEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_TASKS_DEMO || '').trim()
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { tasksDemo?: string } } | undefined)?.unifiedApp
      ?.tasksDemo || '',
  ).trim()
  return readDemoFlag(fromEnv, fromExtra)
}

export function isTasksDemoId(taskId: string | null | undefined): boolean {
  return String(taskId || '').startsWith(TASKS_DEMO_ID_PREFIX)
}
