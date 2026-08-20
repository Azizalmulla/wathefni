import type { AvailableModule } from './types'

export function findModule(modules: AvailableModule[], key: string) {
  return modules.find((item) => item.key === key)
}

export function isModuleEntitled(module: AvailableModule | undefined) {
  if (!module) return false
  return Boolean(module.configured || module.stored_enabled || module.usable || module.effective)
}

export function isModuleDeployed(module: AvailableModule | undefined) {
  if (!module) return false
  const state = String(module.effective_state?.effective_state || '')
  const reason = String(module.effective_state?.deployment?.reason_code || '')
  if (state === 'unavailable_deployment' || state === 'not_released') return false
  if (reason === 'not_deployed' || reason === 'pilot_allowlist' || reason === 'unavailable_deployment') return false
  return true
}

/** Wave 4–6 policy editors mount only when the company is entitled and the runtime is actually deployed. */
export function isPolicySurfaceReady(module: AvailableModule | undefined) {
  return isModuleEntitled(module) && isModuleDeployed(module)
}
