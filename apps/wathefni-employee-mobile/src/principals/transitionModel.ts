export type TransitionPrincipal = 'employee' | 'hr'

export type TransitionAvailability = {
  employeeSession: boolean
  hrSession: boolean
}

export type TransitionShell = TransitionPrincipal | 'unsigned'

export function shellWithPendingTarget(
  availability: TransitionAvailability,
  preference: TransitionPrincipal | null,
  pendingTarget: TransitionPrincipal | null,
): TransitionShell {
  if (pendingTarget) return pendingTarget
  if (availability.employeeSession && !availability.hrSession) return 'employee'
  if (!availability.employeeSession && availability.hrSession) return 'hr'
  if (!availability.employeeSession && !availability.hrSession) return 'unsigned'
  return preference === 'employee' || preference === 'hr' ? preference : 'employee'
}

export function canonicalRouteForTarget(
  target: TransitionPrincipal,
  availability: TransitionAvailability,
): '/(tabs)' | '/(auth)/activate' | '/hr' | '/hr/sign-in' {
  if (target === 'hr') return availability.hrSession ? '/hr' : '/hr/sign-in'
  return availability.employeeSession ? '/(tabs)' : '/(auth)/activate'
}

export function routePrincipal(segments: readonly string[]): TransitionShell {
  if (segments[0] === 'hr') return 'hr'
  if (segments.length === 0 || !segments[0] || segments[0] === 'index') return 'unsigned'
  return 'employee'
}

export function targetRouteIsMounted(
  target: TransitionPrincipal,
  availability: TransitionAvailability,
  segments: readonly string[],
): boolean {
  if (target === 'hr') {
    if (segments[0] !== 'hr') return false
    return availability.hrSession || segments[1] === 'sign-in'
  }
  if (
    segments[0] === 'hr' ||
    segments.length === 0 ||
    !segments[0] ||
    segments[0] === 'index'
  ) return false
  return availability.employeeSession || segments[0] === '(auth)'
}
