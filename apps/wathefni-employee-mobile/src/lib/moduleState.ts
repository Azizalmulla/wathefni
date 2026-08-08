/**
 * Per-module read truth for aggregate surfaces (Home).
 *
 * Home combines several independent module reads. A read that is still loading or
 * that failed must never be rendered as a business fact ("No shift scheduled
 * today"), so every module carries its own state and the surface states
 * unavailability explicitly instead of falling back to an empty business value.
 *
 * The states are produced by the server's `/app/home` projection — the owning module
 * decides whether its own read succeeded. This module is the shared vocabulary and the
 * single predicate the UI uses before stating anything as fact.
 */
export type ModuleDataState = 'disabled' | 'loading' | 'error' | 'ready'

export const MODULE_DATA_STATES: readonly ModuleDataState[] = ['disabled', 'loading', 'error', 'ready']

/** Narrow an untrusted server value, failing closed to `error` rather than `ready`. */
export function asModuleDataState(value: unknown): ModuleDataState {
  return MODULE_DATA_STATES.includes(value as ModuleDataState) ? (value as ModuleDataState) : 'error'
}

/** True only when the module's own data is present and may be stated as fact. */
export function isModuleFactual(state: ModuleDataState): boolean {
  return state === 'ready'
}
