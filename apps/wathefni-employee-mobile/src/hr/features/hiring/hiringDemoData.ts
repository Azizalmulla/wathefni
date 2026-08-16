/**
 * Isolated Hiring demo dataset for mobile UX review.
 * Does not call APIs. Does not share ids with production recruiting truth.
 */
import { HIRING_DEMO_ID_PREFIX, HIRING_DEMO_SOURCE } from './hiringDemoGate'
import type {
  HiringBrowseKey,
  HiringHomeModel,
  HiringPriority,
  HiringSummary,
  HiringUpcomingItem,
} from './hiringTypes'

const demo = (suffix: string) => `${HIRING_DEMO_ID_PREFIX}${suffix}`

export function buildHiringDemoModel(now: Date = new Date()): HiringHomeModel {
  const inHours = (h: number) => new Date(now.getTime() + h * 3600_000).toISOString()
  const inDays = (d: number) => new Date(now.getTime() + d * 86400_000).toISOString()

  const summary: HiringSummary = {
    activeJobs: 4,
    activeCandidates: 18,
    interviewsSoon: 3,
  }

  const priority: HiringPriority = {
    id: demo('priority-review'),
    kind: 'candidate_review',
    titleKey: 'hrHiring.priorityReviewTitle',
    bodyKey: 'hrHiring.priorityReviewBody',
    title: '6 candidates ready for review',
    body: 'Sales Associate and Warehouse Operative — ranking ready, waiting on your decision.',
    statusTone: 'yellow',
    destination: '/hr/jobs',
    demo: true,
  }

  const upcoming: HiringUpcomingItem[] = [
    {
      id: demo('interview-today'),
      kind: 'interview',
      title: 'Interview · Sara Al-Mutairi',
      subtitle: 'Store Manager · Today, 2:00 PM',
      statusTone: 'blue',
      statusLabelKey: 'hrHiring.statusInterview',
      destination: '/hr/interviews',
      at: inHours(4),
      demo: true,
    },
    {
      id: demo('interview-tomorrow'),
      kind: 'interview',
      title: 'Interview · Bilal Chowdhury',
      subtitle: 'Warehouse Operative · Tomorrow, 10:30 AM',
      statusTone: 'blue',
      statusLabelKey: 'hrHiring.statusInterview',
      destination: '/hr/interviews',
      at: inDays(1),
      demo: true,
    },
    {
      id: demo('feedback-due'),
      kind: 'feedback',
      title: 'Feedback due · Noura Hassan',
      subtitle: 'Sales Associate · Panel interview yesterday',
      statusTone: 'yellow',
      statusLabelKey: 'hrHiring.statusFeedbackDue',
      destination: '/hr/interviews',
      at: inHours(-20),
      demo: true,
    },
    {
      id: demo('offer-action'),
      kind: 'offer',
      title: 'Offer ready · Ahmed Darwish',
      subtitle: 'Customer Care · Approve and send',
      statusTone: 'green',
      statusLabelKey: 'hrHiring.statusOffer',
      destination: '/hr/jobs',
      at: inHours(-2),
      demo: true,
    },
    {
      id: demo('candidate-attention'),
      kind: 'candidate',
      title: 'Needs attention · Layla Farid',
      subtitle: 'Sales Associate · CV ready · next action: shortlist',
      statusTone: 'pink',
      statusLabelKey: 'hrHiring.statusNeedsReview',
      destination: '/hr/jobs',
      at: inHours(-5),
      demo: true,
    },
  ]

  const browse: HiringBrowseKey[] = ['jobs', 'candidates', 'interviews', 'ranking']

  return {
    source: HIRING_DEMO_SOURCE,
    demo: true,
    summary,
    priority,
    upcoming,
    browse,
  }
}
