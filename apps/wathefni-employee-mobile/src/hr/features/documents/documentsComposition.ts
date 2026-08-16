import type { DocumentReview } from '@hr/api/types'
import type { StatusTone } from '@/components/ui'
import {
  DOCUMENTS_DEMO_EMP_PREFIX,
  DOCUMENTS_DEMO_SOURCE,
  DOCUMENTS_DEMO_TYPE_PREFIX,
} from './documentsDemoGate'

export function docStatusLabelKey(status: string | null | undefined): string {
  switch ((status || '').trim().toLowerCase()) {
    case 'needs_review':
      return 'hrDocuments.statusNeedsReview'
    case 'valid':
      return 'hrDocuments.statusValid'
    case 'expired':
      return 'hrDocuments.statusExpired'
    case 'expiring_soon':
      return 'hrDocuments.statusExpiring'
    case 'missing':
      return 'hrDocuments.statusMissing'
    default:
      return 'hrDocuments.statusNeedsReview'
  }
}

export function docStatusTone(status: string | null | undefined): StatusTone {
  switch ((status || '').trim().toLowerCase()) {
    case 'needs_review':
      return 'yellow'
    case 'valid':
      return 'green'
    case 'expired':
    case 'missing':
      return 'pink'
    case 'expiring_soon':
      return 'blue'
    default:
      return 'yellow'
  }
}

/** True only when expiry urgency or missing/expired status warrants a callout. */
export function documentNeedsAttention(item: {
  status?: string | null
  days_until_expiry?: number | null
}): boolean {
  const status = (item.status || '').trim().toLowerCase()
  if (status === 'expired' || status === 'missing') return true
  if (typeof item.days_until_expiry === 'number' && item.days_until_expiry <= 14) return true
  return false
}

export function documentAttentionBodyKey(item: {
  status?: string | null
  days_until_expiry?: number | null
}): string {
  const status = (item.status || '').trim().toLowerCase()
  if (status === 'expired') return 'hrDocuments.attentionExpired'
  if (status === 'missing') return 'hrDocuments.attentionMissing'
  return 'hrDocuments.attentionExpiring'
}


export function queueSubtitle(
  item: DocumentReview,
  t: (k: string, p?: Record<string, string | number>) => string,
): string {
  const parts: string[] = [item.name]
  if (typeof item.days_until_expiry === 'number') {
    parts.push(t('hrDocuments.daysUntil', { count: item.days_until_expiry }))
  } else if (item.expiry_date) {
    parts.push(item.expiry_date)
  }
  if (item.source === 'onboarding') parts.push(t('hrDocuments.sourceOnboarding'))
  return parts.filter(Boolean).join(' · ')
}

export function buildDocumentsDemoQueue(): {
  source: typeof DOCUMENTS_DEMO_SOURCE
  compliance: DocumentReview[]
  onboardingFallback: DocumentReview[]
} {
  const emp = (s: string) => `${DOCUMENTS_DEMO_EMP_PREFIX}${s}`
  const typ = (s: string) => `${DOCUMENTS_DEMO_TYPE_PREFIX}${s}`

  const compliance: DocumentReview[] = [
    {
      document_id: `${emp('sara')}:${typ('civil')}`,
      source: 'compliance',
      employee: {
        name: 'Sara Al-Mutairi',
        employee_key: emp('sara'),
        department: 'Retail',
        position_title: 'Store Manager',
      },
      name: 'Civil ID',
      document_type: typ('civil'),
      status: 'needs_review',
      expiry_date: '2027-03-15',
      days_until_expiry: 210,
      last_checked_at: '2026-08-09T14:20:00+03:00',
      extraction_confidence: 0.92,
      has_file: true,
      preview_path: '/dashboard/mobile/documents/files/demo-civil',
      download_path: '/dashboard/mobile/documents/files/demo-civil?disposition=attachment',
      destination: `/documents/${emp('sara')}/${typ('civil')}`,
      allowed_actions: ['review'],
    },
    {
      document_id: `${emp('noura')}:${typ('passport')}`,
      source: 'compliance',
      employee: {
        name: 'Noura Hassan',
        employee_key: emp('noura'),
        department: 'Sales',
        position_title: 'Sales Associate',
      },
      name: 'Passport',
      document_type: typ('passport'),
      status: 'needs_review',
      expiry_date: '2026-09-01',
      days_until_expiry: 22,
      last_checked_at: '2026-08-08T09:00:00+03:00',
      last_reminded_at: '2026-08-07T11:00:00+03:00',
      reminder_count: 1,
      extraction_confidence: 0.78,
      has_file: true,
      preview_path: '/dashboard/mobile/documents/files/demo-pass',
      destination: `/documents/${emp('noura')}/${typ('passport')}`,
      allowed_actions: ['review'],
    },
    {
      document_id: `${emp('ahmed')}:${typ('residency')}`,
      source: 'compliance',
      employee: {
        name: 'Ahmed Darwish',
        employee_key: emp('ahmed'),
        department: 'Support',
        position_title: 'Customer Care',
      },
      name: 'Residency',
      document_type: typ('residency'),
      status: 'needs_review',
      expiry_date: '2026-08-20',
      days_until_expiry: 10,
      last_checked_at: '2026-08-10T07:30:00+03:00',
      extraction_confidence: 0.61,
      has_file: true,
      preview_path: '/dashboard/mobile/documents/files/demo-res',
      destination: `/documents/${emp('ahmed')}/${typ('residency')}`,
      allowed_actions: ['review'],
    },
  ]

  const onboardingFallback: DocumentReview[] = [
    {
      document_id: `${emp('bilal')}:civil_id`,
      source: 'onboarding',
      employee: {
        name: 'Bilal Chowdhury',
        employee_key: emp('bilal'),
        department: 'Warehouse',
        position_title: 'Warehouse Operative',
      },
      name: 'Civil ID (onboarding)',
      document_type: 'civil_id',
      status: 'processing',
      has_file: true,
      preview_path: '/dashboard/mobile/documents/files/demo-ob',
      destination: `/onboarding/${emp('bilal')}`,
      allowed_actions: ['preview'],
    },
  ]

  return { source: DOCUMENTS_DEMO_SOURCE, compliance, onboardingFallback }
}
