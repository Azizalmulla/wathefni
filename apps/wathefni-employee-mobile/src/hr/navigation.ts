/** HR workspace lives under /hr/* so it never collides with Employee routes. */

export const HR_BASE = '/hr'

export function toHrPath(destination: string | null | undefined): string {
  const raw = String(destination || '').trim()
  if (!raw || raw === '/') return HR_BASE
  if (raw.startsWith(HR_BASE + '/') || raw === HR_BASE) return raw
  if (raw.startsWith('/')) return `${HR_BASE}${raw}`
  return `${HR_BASE}/${raw}`
}

export function fromHrPath(path: string): string {
  if (path === HR_BASE) return '/'
  if (path.startsWith(HR_BASE + '/')) return path.slice(HR_BASE.length) || '/'
  return path
}

/** Strip query/hash and normalize to an HR absolute path. */
export function normalizeHrPath(path: string | null | undefined): string {
  const raw = String(path || '').trim().split('?')[0].split('#')[0]
  if (!raw) return HR_BASE
  return toHrPath(raw.startsWith('/') ? raw : `/${raw}`)
}

/**
 * Canonical cold-start / empty-history parent for an HR route.
 * Detail → owning list (or Home when no list). Module list → More or Hiring.
 * Never returns the same route.
 */
export function hrCanonicalParent(path: string | null | undefined): string {
  const full = normalizeHrPath(path)
  const p = fromHrPath(full)

  if (p === '/change-pin') return toHrPath('/settings')
  if (p === '/settings') return toHrPath('/more')

  if (p.startsWith('/leave/')) return HR_BASE
  if (p.startsWith('/candidates/')) return toHrPath('/candidates')
  if (p === '/candidates') return toHrPath('/hiring')
  if (p === '/jobs') return toHrPath('/hiring')
  if (p.startsWith('/interviews/')) return toHrPath('/interviews')
  if (p === '/interviews') return toHrPath('/hiring')

  if (p.startsWith('/employees/')) return toHrPath('/people')
  if (p === '/employees') return toHrPath('/more')

  if (p.startsWith('/tasks/')) return toHrPath('/tasks')
  if (p === '/tasks' || p.startsWith('/tasks')) return toHrPath('/more')

  if (p.startsWith('/onboarding/')) return toHrPath('/onboarding')
  if (p === '/onboarding') return toHrPath('/more')
  if (p.startsWith('/preboarding/')) return toHrPath('/preboarding')
  if (p === '/preboarding') return toHrPath('/more')
  if (p.startsWith('/probation/')) return toHrPath('/probation')
  if (p === '/probation') return toHrPath('/more')
  if (p.startsWith('/performance/')) return toHrPath('/performance')
  if (p === '/performance') return toHrPath('/more')

  if (p.startsWith('/documents/')) return toHrPath('/documents')
  if (p === '/documents') return toHrPath('/more')

  if (p.startsWith('/attendance/')) return toHrPath('/attendance')
  if (p === '/attendance') return toHrPath('/more')

  if (p.startsWith('/shift-swaps/')) return toHrPath('/shifts')
  if (p === '/shifts') return toHrPath('/more')

  if (p === '/delivery-alerts') return toHrPath('/more')
  if (p === '/assistant') return toHrPath('/more')

  // Tab roots and unknown → Home
  return HR_BASE
}

export type HrSafeBackDecision =
  | { action: 'back' }
  | { action: 'replace'; href: string }

/** Pure decision for tests — never depends on Expo history existing. */
export function decideHrSafeBack(
  canGoBack: boolean,
  currentPath: string,
  parentOverride?: string | null,
): HrSafeBackDecision {
  if (canGoBack) return { action: 'back' }
  const href = parentOverride
    ? normalizeHrPath(parentOverride)
    : hrCanonicalParent(currentPath)
  return { action: 'replace', href }
}

export type HrRouterLike = {
  canGoBack: () => boolean
  back: () => void
  replace: (href: never) => void
}

export function performHrSafeBack(
  router: HrRouterLike,
  currentPath: string,
  parentOverride?: string | null,
): void {
  const decision = decideHrSafeBack(router.canGoBack(), currentPath, parentOverride)
  if (decision.action === 'back') {
    router.back()
    return
  }
  router.replace(decision.href as never)
}
