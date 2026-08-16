import type {
  InterviewSummary,
  PrehirePositionSummary,
  PriorityItem,
  PrioritySection,
} from '@hr/api/types'
import { HIRING_SECTION_TYPES } from '@hr/shell/ia'
import { hiringDemoEnabled } from './hiringDemoGate'
import { demoAllowedInThisBuild } from '@hr/features/demoProductionGuard'
import { buildHiringDemoModel } from './hiringDemoData'
import type {
  HiringBrowseKey,
  HiringHomeModel,
  HiringPriority,
  HiringSummary,
  HiringUpcomingItem,
} from './hiringTypes'

export type {
  HiringBrowseKey,
  HiringHomeModel,
  HiringPriority,
  HiringStatusTone,
  HiringSummary,
  HiringUpcomingItem,
  HiringUpcomingKind,
} from './hiringTypes'

const SOON_MS = 48 * 3600_000

function isSoon(iso: string | null | undefined, now: number): boolean {
  if (!iso) return false
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return false
  return t >= now - 2 * 3600_000 && t <= now + SOON_MS
}

function feedbackDue(row: InterviewSummary): boolean {
  const s = String(row.feedback_status || row.notes_status || '').toLowerCase()
  return s.includes('pending') || s.includes('due') || s === 'requested' || s === 'needed'
}

function priorityTitleKey(kind: HiringPriority['kind']): string {
  switch (kind) {
    case 'assessment':
      return 'hrHiring.priorityAssessmentTitle'
    case 'follow_up':
      return 'hrHiring.priorityFollowUpTitle'
    case 'role':
      return 'hrHiring.priorityRoleTitle'
    case 'candidate_review':
      return 'hrHiring.priorityReviewTitle'
    default:
      return 'hrHiring.priorityGenericTitle'
  }
}

function priorityBodyKey(kind: HiringPriority['kind']): string {
  switch (kind) {
    case 'assessment':
      return 'hrHiring.priorityAssessmentBody'
    case 'follow_up':
      return 'hrHiring.priorityFollowUpBody'
    case 'role':
      return 'hrHiring.priorityRoleBody'
    case 'candidate_review':
      return 'hrHiring.priorityReviewBody'
    default:
      return 'hrHiring.priorityGenericBody'
  }
}

function priorityFromSections(sections: PrioritySection[]): HiringPriority | null {
  const hiring = sections.filter((s) => HIRING_SECTION_TYPES.has(s.type))
  const items: { section: PrioritySection; item: PriorityItem }[] = []
  for (const section of hiring) {
    for (const item of section.items) {
      if (item.destination) items.push({ section, item })
    }
  }
  if (!items.length) return null
  const preferred =
    items.find((e) => e.item.type.includes('ready') || e.item.status === 'ready_for_review') ||
    items.find((e) => e.section.type === 'candidate_decisions') ||
    items[0]
  const { item } = preferred
  const kind: HiringPriority['kind'] = item.type.includes('assessment')
    ? 'assessment'
    : item.type.includes('follow')
      ? 'follow_up'
      : item.type.includes('role')
        ? 'role'
        : item.type.includes('candidate')
          ? 'candidate_review'
          : 'generic'
  const dest = String(item.destination || '')
  const positionMatch = dest.match(/[?&]position=([^&]+)/i)
  const positionCode = positionMatch ? decodeURIComponent(positionMatch[1]) : null
  return {
    id: `${item.type}:${item.target_id}`,
    kind,
    titleKey: priorityTitleKey(kind),
    bodyKey: priorityBodyKey(kind),
    title: item.summary,
    body: String(item.status || '').replace(/_/g, ' '),
    statusTone: 'yellow',
    destination: dest,
    positionCode,
  }
}

function upcomingFromLive(interviews: InterviewSummary[], now: number): HiringUpcomingItem[] {
  const rows: HiringUpcomingItem[] = []

  for (const row of interviews) {
    if (isSoon(row.scheduled_at, now)) {
      rows.push({
        id: `interview:${row.interview_id}`,
        kind: 'interview',
        title: row.candidate.name,
        subtitle: row.position?.title || row.position?.code || '',
        statusTone: 'blue',
        statusLabelKey: 'hrHiring.statusInterview',
        destination: `/hr/interviews/${encodeURIComponent(row.interview_id)}`,
        at: row.scheduled_at || null,
      })
    } else if (feedbackDue(row)) {
      rows.push({
        id: `feedback:${row.interview_id}`,
        kind: 'feedback',
        title: row.candidate.name,
        subtitle: row.position?.title || row.position?.code || '',
        statusTone: 'yellow',
        statusLabelKey: 'hrHiring.statusFeedbackDue',
        destination: `/hr/interviews/${encodeURIComponent(row.interview_id)}`,
        at: row.scheduled_at || row.scheduled_end || null,
      })
    }
  }

  rows.sort((a, b) => {
    const ta = a.at ? new Date(a.at).getTime() : 0
    const tb = b.at ? new Date(b.at).getTime() : 0
    return ta - tb
  })
  return rows.slice(0, 8)
}

export function browseKeysForCapabilities(opts: {
  canCandidates: boolean
  canInterviews: boolean
  canRequisitions?: boolean
}): HiringBrowseKey[] {
  const keys: HiringBrowseKey[] = []
  if (opts.canRequisitions) keys.push('requisitions')
  if (opts.canCandidates) keys.push('jobs', 'candidates', 'ranking')
  if (opts.canInterviews) keys.push('interviews')
  // Assessments: no real mobile surface — omit (do not fake / web-handoff).
  return keys
}

/** Browse destinations — Ranking/Candidates require position context via Jobs first. */
export function browseDestination(key: HiringBrowseKey): string {
  switch (key) {
    case 'requisitions':
      return '/hr/requisitions'
    case 'jobs':
    case 'candidates':
    case 'ranking':
      return '/hr/jobs'
    case 'interviews':
      return '/hr/interviews'
    case 'assessments':
      return '/hr/jobs'
  }
}

export function composeHiringHome(input: {
  sections: PrioritySection[]
  positions: PrehirePositionSummary[]
  interviews: InterviewSummary[]
  browse: HiringBrowseKey[]
  forceDemo?: boolean
  now?: Date
}): HiringHomeModel {
  if (demoAllowedInThisBuild() && (input.forceDemo ?? hiringDemoEnabled())) {
    const demo = buildHiringDemoModel(input.now)
    return { ...demo, browse: input.browse.length ? input.browse : demo.browse }
  }

  const now = (input.now || new Date()).getTime()
  const readyCandidates = input.positions.reduce(
    (sum, row) => sum + (typeof row.ready_for_review === 'number' ? row.ready_for_review : 0),
    0,
  )
  const summary: HiringSummary = {
    activeJobs: input.positions.length,
    activeCandidates: readyCandidates,
    interviewsSoon: input.interviews.filter((row) => isSoon(row.scheduled_at, now)).length,
  }

  return {
    source: 'live',
    demo: false,
    summary,
    priority: priorityFromSections(input.sections),
    upcoming: upcomingFromLive(input.interviews, now),
    browse: input.browse,
  }
}
