export type EmployeeHomeAuthStatus =
  | 'loading'
  | 'signedOut'
  | 'signedIn'
  | 'blocked'
  | 'locked'
  | 'needsPinSetup'
  | 'needsBiometricOptIn'

/** Protected Home data becomes request-capable only after Employee auth is open. */
export function canFetchEmployeeHome(status: EmployeeHomeAuthStatus): boolean {
  return status === 'signedIn'
}
