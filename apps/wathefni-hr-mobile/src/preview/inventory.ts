export const previewViews = [
  'sign-in',
  'home',
  'tasks',
  'onboarding',
  'documents',
  'attendance',
  'shifts',
  'shift-swap',
  'employees',
  'employee-profile',
  'delivery-alerts',
  'candidates',
  'candidate',
  'interviews',
  'interview',
  'settings',
  'leave',
] as const

export const previewOperators = [
  'hr-only',
  'recruiter-only',
  'restricted-manager',
  'multi-workspace',
] as const

export const previewScenarios = [
  'ready',
  'loading',
  'empty',
  'error',
  'offline',
  'permission',
  'revoked',
  'company-disabled',
  'company-archived',
  'session-expired',
  'stale',
  'success',
] as const

export function previewUrl(
  base: string,
  view: (typeof previewViews)[number],
  locale: 'en' | 'ar',
  operator: (typeof previewOperators)[number],
  scenario: (typeof previewScenarios)[number],
): string {
  const query = new URLSearchParams({ view, locale, operator, scenario, controls: '0' })
  return `${base}?${query}`
}
