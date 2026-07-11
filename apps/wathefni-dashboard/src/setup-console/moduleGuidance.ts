import type { AvailableModule, ModuleBundle, ModuleAppSurface } from './types'

export function moduleByKey(modules: AvailableModule[]): Record<string, AvailableModule> {
  return Object.fromEntries(modules.map((module) => [module.key, module]))
}

export function expandHardDependencies(
  selected: string[],
  modules: AvailableModule[],
): { selected: string[]; notices: string[] } {
  const byKey = moduleByKey(modules)
  const next = new Set(selected.filter((key) => key in byKey))
  const notices: string[] = []
  let changed = true
  while (changed) {
    changed = false
    for (const key of [...next]) {
      for (const dependency of byKey[key]?.depends_on || []) {
        if (!next.has(dependency) && dependency in byKey) {
          next.add(dependency)
          const moduleLabel = byKey[key]?.label || key
          const dependencyLabel = byKey[dependency]?.label || dependency
          notices.push(`${moduleLabel} requires ${dependencyLabel}, so ${dependencyLabel} was included.`)
          changed = true
        }
      }
    }
  }
  return { selected: [...next].sort(), notices }
}

export function removeModuleWithDependents(
  selected: string[],
  modules: AvailableModule[],
  removeKey: string,
): { selected: string[]; notices: string[] } {
  const byKey = moduleByKey(modules)
  const next = new Set(selected.filter((key) => key in byKey))
  const notices: string[] = []
  const remove = new Set<string>([removeKey])
  let changed = true
  while (changed) {
    changed = false
    for (const key of [...next]) {
      const deps = byKey[key]?.depends_on || []
      if (deps.some((dependency) => remove.has(dependency))) {
        if (!remove.has(key)) {
          remove.add(key)
          const moduleLabel = byKey[key]?.label || key
          const dependencyLabel = byKey[removeKey]?.label || removeKey
          notices.push(`${moduleLabel} requires ${dependencyLabel}, so ${moduleLabel} was removed.`)
          changed = true
        }
      }
    }
  }
  for (const key of remove) next.delete(key)
  return { selected: [...next].sort(), notices }
}

export function applyBundleModules(
  selected: string[],
  modules: AvailableModule[],
  bundle: ModuleBundle,
): { selected: string[]; notices: string[] } {
  const merged = [...new Set([...selected, ...bundle.modules])]
  return expandHardDependencies(merged, modules)
}

export function softRecommendations(
  selected: string[],
  modules: AvailableModule[],
): Array<{ from: string; fromLabel: string; key: string; label: string; copy: string }> {
  const byKey = moduleByKey(modules)
  const selectedSet = new Set(selected)
  const items: Array<{ from: string; fromLabel: string; key: string; label: string; copy: string }> = []
  const seen = new Set<string>()
  for (const key of selected) {
    const module = byKey[key]
    if (!module) continue
    for (const recommended of module.recommended_with || []) {
      if (selectedSet.has(recommended) || !(recommended in byKey)) continue
      const dedupe = `${key}:${recommended}`
      if (seen.has(dedupe)) continue
      seen.add(dedupe)
      items.push({
        from: key,
        fromLabel: module.label,
        key: recommended,
        label: byKey[recommended]?.label || recommended,
        copy: module.recommendation_copy || '',
      })
    }
  }
  return items
}

export function deriveAppSurfaces(
  selected: string[],
  modules: AvailableModule[],
): ModuleAppSurface[] {
  const byKey = moduleByKey(modules)
  if (!selected.includes('employee_app')) return []
  const surfaces: ModuleAppSurface[] = []
  for (const key of selected) {
    const module = byKey[key]
    if (!module?.app_surface_key) continue
    surfaces.push({
      module_key: module.key,
      surface_key: module.app_surface_key,
      label: module.app_surface_label || module.label,
      available_when_app_live: true,
    })
  }
  return surfaces
}
