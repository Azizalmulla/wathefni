/**
 * Wave 4 — pre-hiring fetch authority.
 *
 * `/dashboard/bootstrap.enabled_modules` is the canonical module list.
 * Missing bootstrap must not invent pre_hiring. Summary is only a fallback
 * list when bootstrap is dark (404), never a "data exists ⇒ enabled" signal.
 */

export type PrehireAuthorityInput = {
  bootstrapSettled: boolean
  bootstrapError: boolean
  bootstrapMissing: boolean
  bootstrapEnabledModules?: string[] | null
  summaryEnabledModules?: string[] | null
}

export type PrehireAuthority = {
  hasPrehire: boolean
  fetchSummary: boolean
  fetchPrehireCore: boolean
}

function includesPrehire(modules: string[] | null | undefined): boolean {
  return Array.isArray(modules) && modules.includes('pre_hiring')
}

export function resolvePrehireAuthority(input: PrehireAuthorityInput): PrehireAuthority {
  if (!input.bootstrapSettled || input.bootstrapError) {
    return { hasPrehire: false, fetchSummary: false, fetchPrehireCore: false }
  }

  if (Array.isArray(input.bootstrapEnabledModules)) {
    const hasPrehire = includesPrehire(input.bootstrapEnabledModules)
    return { hasPrehire, fetchSummary: hasPrehire, fetchPrehireCore: hasPrehire }
  }

  if (input.bootstrapMissing) {
    const hasPrehire = includesPrehire(input.summaryEnabledModules)
    return { hasPrehire, fetchSummary: true, fetchPrehireCore: hasPrehire }
  }

  return { hasPrehire: false, fetchSummary: false, fetchPrehireCore: false }
}
