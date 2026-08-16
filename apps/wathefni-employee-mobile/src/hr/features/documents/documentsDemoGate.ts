/**
 * Document Reviews demo — presentation-only. Never POSTs review.
 */
import Constants from 'expo-constants'

import { readDemoFlag } from '@hr/features/demoProductionGuard'

export const DOCUMENTS_DEMO_SOURCE = 'hr_documents_demo_v1' as const
export const DOCUMENTS_DEMO_EMP_PREFIX = '__demo_doc_emp__'
export const DOCUMENTS_DEMO_TYPE_PREFIX = '__demo_doc_type__'

export function documentsDemoEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_DOCUMENTS_DEMO || '').trim()
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { documentsDemo?: string } } | undefined)
      ?.unifiedApp?.documentsDemo || '',
  ).trim()
  return readDemoFlag(fromEnv, fromExtra)
}

export function isDocumentsDemoEmployee(key: string | null | undefined): boolean {
  return String(key || '').startsWith(DOCUMENTS_DEMO_EMP_PREFIX)
}
