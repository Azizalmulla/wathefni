/** Operator principal key for HR local-lock material (never employee_key). */

import type { MobileMe } from '@hr/api/types'

export function operatorPrincipalKey(
  me: MobileMe | null | undefined,
  companyCodeFallback?: string | null,
): string {
  const company = String(
    me?.principal.company_code || companyCodeFallback || '',
  )
    .trim()
    .toUpperCase()
  const userId = String(me?.principal.user_id || '').trim()
  if (!company || !userId) return ''
  return `${company}:${userId}`
}
