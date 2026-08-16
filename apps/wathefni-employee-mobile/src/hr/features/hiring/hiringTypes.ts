import type { StatusTone } from '@/components/ui'

export type HiringStatusTone = Extract<StatusTone, 'yellow' | 'blue' | 'pink' | 'green'>

export type HiringSummary = {
  activeJobs: number
  activeCandidates: number
  interviewsSoon: number
}

export type HiringPriority = {
  id: string
  kind: 'candidate_review' | 'assessment' | 'follow_up' | 'role' | 'generic'
  title: string
  body: string
  titleKey?: string
  bodyKey?: string
  positionCode?: string | null
  statusTone: HiringStatusTone
  destination: string
  demo?: boolean
}

export type HiringUpcomingKind = 'interview' | 'feedback' | 'offer' | 'candidate'

export type HiringUpcomingItem = {
  id: string
  kind: HiringUpcomingKind
  title: string
  subtitle: string
  statusTone: HiringStatusTone
  statusLabelKey: string
  destination: string
  at: string | null
  demo?: boolean
}

export type HiringBrowseKey = 'jobs' | 'candidates' | 'interviews' | 'ranking' | 'assessments' | 'requisitions'

export type HiringHomeModel = {
  source: 'live' | 'hr_hiring_demo_v1'
  demo: boolean
  summary: HiringSummary
  priority: HiringPriority | null
  upcoming: HiringUpcomingItem[]
  browse: HiringBrowseKey[]
}
