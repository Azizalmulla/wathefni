/**
 * Employee safe-back contract — mirrors HR `decideHrSafeBack` / `hrCanonicalParent`.
 * History exists → back(); otherwise → replace(canonical parent).
 * Never depends on “hopefully Expo Router has history.”
 */

import { HOME_ROUTE, INBOX_ROUTE } from '@/composition/employeeAppComposition'

export function normalizeEmployeePath(path: string | null | undefined): string {
  const raw = String(path || '').trim().split('?')[0].split('#')[0]
  if (!raw || raw === '/') return HOME_ROUTE
  if (raw === '/(tabs)/index' || raw === '/(tabs)/') return HOME_ROUTE
  if (!raw.startsWith('/')) return `/${raw}`
  return raw
}

/**
 * Canonical cold-start / empty-history parent for an Employee route.
 * Detail/subroute → owning tab or parent push; never returns the same route.
 */
export function employeeCanonicalParent(path: string | null | undefined): string {
  const p = normalizeEmployeePath(path)

  if (p === '/change-pin') return '/settings'
  if (p === '/privacy-support') return '/settings'
  if (p === '/settings') return '/(tabs)/profile'
  if (p === '/bank') return '/(tabs)/profile'

  if (p === INBOX_ROUTE || p === '/(tabs)/notifications') return HOME_ROUTE

  if (p === '/leave/history' || p === '/leave/request') return '/(tabs)/leave'
  if (p === '/schedule/history') return '/(tabs)/schedule'

  if (p === '/documents' || p === '/onboarding') return HOME_ROUTE
  if (p.startsWith('/performance/')) return '/performance'
  if (p === '/performance') return HOME_ROUTE
  if (p.startsWith('/talent/')) return '/talent'
  if (p === '/talent') return HOME_ROUTE
  if (p.startsWith('/learning/')) return '/learning'
  if (p === '/learning') return HOME_ROUTE
  if (p.startsWith('/benefits/')) return '/benefits'
  if (p === '/benefits') return HOME_ROUTE
  if (p.startsWith('/engagement/')) return '/engagement'
  if (p === '/engagement') return HOME_ROUTE

  if (p === '/payslips' || p.startsWith('/(tabs)/payslips')) return HOME_ROUTE

  // Tab roots and unknown → Home
  return HOME_ROUTE
}

export type EmployeeSafeBackDecision =
  | { action: 'back' }
  | { action: 'replace'; href: string }

export function decideEmployeeSafeBack(
  canGoBack: boolean,
  currentPath: string,
  parentOverride?: string | null,
): EmployeeSafeBackDecision {
  if (canGoBack) return { action: 'back' }
  const href = parentOverride
    ? normalizeEmployeePath(parentOverride)
    : employeeCanonicalParent(currentPath)
  return { action: 'replace', href }
}

export type EmployeeRouterLike = {
  canGoBack: () => boolean
  back: () => void
  replace: (href: never) => void
}

export function performEmployeeSafeBack(
  router: EmployeeRouterLike,
  currentPath: string,
  parentOverride?: string | null,
): void {
  const decision = decideEmployeeSafeBack(router.canGoBack(), currentPath, parentOverride)
  if (decision.action === 'back') {
    router.back()
    return
  }
  router.replace(decision.href as never)
}
