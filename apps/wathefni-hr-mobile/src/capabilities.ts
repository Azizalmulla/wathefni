import type { FeatureCapability, MobileMe, WorkspaceKey } from '@/api/types'

export function enabledWorkspaces(me: MobileMe | null): WorkspaceKey[] {
  if (!me) return []
  return (['hr', 'recruiting', 'owner'] as WorkspaceKey[]).filter(
    (workspace) => me.workspaces[workspace]?.enabled,
  )
}

export function capability(
  me: MobileMe | null,
  workspace: WorkspaceKey,
  feature: string,
): FeatureCapability | null {
  return me?.workspaces[workspace]?.features?.[feature] || null
}

export function hasCapability(
  me: MobileMe | null,
  workspace: WorkspaceKey,
  feature: string,
): boolean {
  return capability(me, workspace, feature)?.enabled === true
}

export function can(
  me: MobileMe | null,
  workspace: WorkspaceKey,
  feature: string,
  action: string,
): boolean {
  const value = capability(me, workspace, feature)
  return value?.enabled === true && value.actions.includes(action)
}
