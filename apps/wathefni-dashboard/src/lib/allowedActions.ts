/**
 * Wave 4 — action visibility.
 *
 * Backend `allowed_actions` is canonical. A presentation overlay may replace
 * that list when the backend sent one; the client never unions extra actions.
 * Missing authority fails closed (no actions).
 */
export function resolveAllowedActions(
  canonical: string[] | null | undefined,
  presentation?: string[] | null,
): string[] {
  if (Array.isArray(presentation)) return [...presentation]
  if (Array.isArray(canonical)) return [...canonical]
  return []
}
