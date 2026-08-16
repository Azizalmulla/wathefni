/**
 * HTTPS App Link / Universal Link mapping.
 * Installed-app intercept lands here; unknown slugs fail closed (null).
 * Custom scheme `wathefni://` remains valid and is handled by Expo Router.
 */
const HOSTS = new Set(['api.octo-hr.com', 'api.wathefni.ai'])
const PREFIX = '/l/'

const EMPLOYEE: Record<string, string> = {
  '': '/',
  home: '/',
  inbox: '/notifications',
  notifications: '/notifications',
  profile: '/profile',
  settings: '/settings',
  leave: '/leave',
  'leave/request': '/leave/request',
  'leave/history': '/leave/history',
  schedule: '/schedule',
  shifts: '/schedule',
  attendance: '/schedule',
  documents: '/documents',
  onboarding: '/onboarding',
  preboarding: '/preboarding',
  probation: '/probation',
  payslips: '/payslips',
  bank: '/bank',
  performance: '/performance',
  talent: '/talent',
  learning: '/learning',
  benefits: '/benefits',
  engagement: '/engagement',
}

const HR: Record<string, string> = {
  '': '/hr',
  inbox: '/hr/inbox',
  people: '/hr/people',
  employees: '/hr/people',
  leave: '/hr',
  hiring: '/hr/hiring',
  candidates: '/hr/candidates',
  interviews: '/hr/interviews',
  jobs: '/hr/jobs',
  onboarding: '/hr/onboarding',
  attendance: '/hr/attendance',
  shifts: '/hr/shifts',
  documents: '/hr/documents',
  performance: '/hr/performance',
  settings: '/hr/settings',
}

export function hrefFromHttpsAppLink(url: string | null | undefined): string | null {
  const raw = String(url || '').trim()
  if (!raw) return null
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    return null
  }
  if (parsed.protocol === 'wathefni:') {
    const path = `${parsed.host}${parsed.pathname}`.replace(/\/+/g, '/')
    return path.startsWith('/') ? path : `/${path}`
  }
  if (parsed.protocol !== 'https:' || !HOSTS.has(parsed.hostname)) return null
  const pathname = parsed.pathname.replace(/\/+$/, '') || '/'
  if (pathname !== '/l' && !pathname.startsWith(PREFIX)) return null
  const rest = pathname === '/l' ? '' : pathname.slice(PREFIX.length)
  if (rest.startsWith('hr')) {
    const slug = rest === 'hr' ? '' : rest.slice(3)
    return HR[slug] ?? null
  }
  return EMPLOYEE[rest] ?? null
}
