export function visibleActions<T extends string>(
  allowedActions: readonly string[] | null | undefined,
  supportedActions: readonly T[],
): T[] {
  const allowed = new Set(allowedActions || [])
  return supportedActions.filter((action) => allowed.has(action))
}

export function hasAnyAllowedAction(
  allowedActions: readonly string[] | null | undefined,
  aliases: readonly string[],
): boolean {
  return aliases.some((action) => allowedActions?.includes(action))
}
