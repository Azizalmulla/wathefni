/**
 * Map canonical `/app/me` features[x].reason values to customer-facing i18n keys.
 * Never invents entitlement — only presents the server-stamped reason calmly.
 * Unknown/raw backend codes fall back to the generic unavailable message.
 */
export type FeatureUnavailableReasonKind =
  | 'module_disabled'
  | 'no_access'
  | 'temporarily_unavailable'
  | 'generic'

const MODULE_DISABLED = new Set(['module_disabled'])

const NO_ACCESS = new Set([
  'bank_ess_not_allowlisted',
  'employee_not_eligible',
  'not_allowlisted',
  'not_entitled',
])

const TEMPORARILY_UNAVAILABLE = new Set([
  'feature_not_available',
  'bank_ess_disabled',
  'ess_v5_disabled',
  'bank_ess_pending_eligibility',
  'temporarily_unavailable',
  'maintenance',
])

export function featureUnavailableReasonKind(
  reason: string | null | undefined,
): FeatureUnavailableReasonKind {
  const code = String(reason || '')
    .trim()
    .toLowerCase()
  if (!code) return 'generic'
  if (MODULE_DISABLED.has(code)) return 'module_disabled'
  if (NO_ACCESS.has(code)) return 'no_access'
  if (TEMPORARILY_UNAVAILABLE.has(code)) return 'temporarily_unavailable'
  // Unknown codes stay generic — never echo the raw enum to the employee.
  return 'generic'
}

export function featureUnavailableMessageKey(
  reason: string | null | undefined,
):
  | 'feature.unavailable.message'
  | 'feature.unavailable.moduleDisabled'
  | 'feature.unavailable.noAccess'
  | 'feature.unavailable.temporarilyUnavailable' {
  switch (featureUnavailableReasonKind(reason)) {
    case 'module_disabled':
      return 'feature.unavailable.moduleDisabled'
    case 'no_access':
      return 'feature.unavailable.noAccess'
    case 'temporarily_unavailable':
      return 'feature.unavailable.temporarilyUnavailable'
    default:
      return 'feature.unavailable.message'
  }
}

export function featureUnavailableTitleKey(
  reason: string | null | undefined,
): 'feature.unavailable.title' | 'feature.unavailable.temporarilyUnavailableTitle' {
  return featureUnavailableReasonKind(reason) === 'temporarily_unavailable'
    ? 'feature.unavailable.temporarilyUnavailableTitle'
    : 'feature.unavailable.title'
}
