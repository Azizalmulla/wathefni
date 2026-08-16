/**
 * Map Assistant navigation artifacts → HR mobile destinations.
 * Only routes that pass destinationAvailable are returned.
 */

import type { MobileMe } from '@hr/api/types'
import { destinationAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'

export type AssistantNavItem = {
  type?: string
  page?: string
  label?: string
  prompt?: string
  position_code?: string
  app_key?: string
  interview_id?: string
  destination?: string
}

export type AssistantDeepLink = {
  label: string
  href: string
  kind: 'route' | 'prompt'
  prompt?: string
}

const PAGE_TO_HR: Record<string, string> = {
  leave: '/hr',
  attendance: '/hr/attendance',
  shifts: '/hr/shifts',
  onboarding: '/hr/onboarding',
  preboarding: '/hr/preboarding',
  probation: '/hr/probation',
  requisitions: '/hr/requisitions',
  employees: '/hr/people',
  candidates: '/hr/candidates',
  interviews: '/hr/interviews',
  // Ranking is position-scoped on mobile — base remaps to Jobs picker when no position.
  ranking: '/hr/jobs',
  jobs: '/hr/jobs',
  inbox: '/hr/inbox',
  tasks: '/hr/tasks',
  documents: '/hr/documents',
}

/** Pages that must never become mobile deep links (web-only). */
const WEB_ONLY_PAGES = new Set(['reports', 'ai', 'settings', 'overview', 'assessments', 'calendar'])

export function mapAssistantNavigation(
  me: MobileMe | null,
  items: AssistantNavItem[] | null | undefined,
  locale: 'en' | 'ar' = 'en',
): AssistantDeepLink[] {
  const out: AssistantDeepLink[] = []
  const seen = new Set<string>()
  for (const item of items || []) {
    if (!item || typeof item !== 'object') continue
    if (item.type === 'assistant_prompt' && item.prompt) {
      const label = String(item.label || (locale === 'ar' ? 'متابعة' : 'Continue')).trim()
      const key = `prompt:${item.prompt}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push({ label, href: '', kind: 'prompt', prompt: String(item.prompt) })
      continue
    }
    const page = String(item.page || '').trim().toLowerCase()
    if (!page || WEB_ONLY_PAGES.has(page)) continue
    let href = PAGE_TO_HR[page]
    if (!href) continue
    const appKey = String(item.app_key || '').trim()
    const interviewId = String(item.interview_id || '').trim()
    const positionCode = String(item.position_code || '').trim()

    if (page === 'candidates' && appKey) {
      href = `/hr/candidates/${encodeURIComponent(appKey)}`
    } else if ((page === 'candidates' || page === 'ranking') && positionCode) {
      href = `/hr/candidates?position=${encodeURIComponent(positionCode)}`
    } else if (page === 'candidates' && !appKey && !positionCode) {
      href = '/hr/jobs'
    } else if (page === 'interviews') {
      // Never treat app_key as interview_id — UUID failure.
      if (interviewId) {
        href = `/hr/interviews/${encodeURIComponent(interviewId)}`
      } else {
        href = '/hr/interviews'
      }
    }

    const dest = toHrPath(href)
    if (!destinationAvailable(me, dest)) continue
    const label =
      String(item.label || '').trim() ||
      (locale === 'ar' ? 'فتح' : 'Open')
    const key = `route:${dest}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ label, href: dest, kind: 'route' })
  }
  return out.slice(0, 6)
}

export function mapCandidateCardLink(
  me: MobileMe | null,
  appKey: string | null | undefined,
  label: string,
): AssistantDeepLink | null {
  const key = String(appKey || '').trim()
  if (!key) return null
  const href = toHrPath(`/candidates/${encodeURIComponent(key)}`)
  if (!destinationAvailable(me, href)) return null
  return { label, href, kind: 'route' }
}
