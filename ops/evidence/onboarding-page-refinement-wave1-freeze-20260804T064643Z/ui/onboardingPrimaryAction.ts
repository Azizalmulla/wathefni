/** Derive the Onboarding queue primary action from existing checklist ownership/status. */

export type OnboardingPrimaryKind = 'remind' | 'open_checklist' | 'review' | 'view_details'

export type OnboardingPrimaryInput = {
  pending_count?: number | null
  next_owner?: string | null
  next_owner_group?: string | null
  next_item_label?: string | null
  next_item_status?: string | null
  next_item_storage_status?: string | null
  /** When detail is loaded, prefer its next open item + document index. */
  detail?: {
    employee_key?: string
    next_owner?: string | null
    next_owner_group?: string | null
    next_item_label?: string | null
    document_index?: Record<string, string>
    items?: OnboardingPrimaryItem[]
    pending?: OnboardingPrimaryItem[]
  } | null
  employee_key?: string
  canRemind?: boolean
}

export type OnboardingPrimaryItem = {
  item_id?: string | null
  document_type?: string | null
  label?: string | null
  status?: string | null
  storage_status?: string | null
  owner?: string | null
  owner_group?: string | null
  authority?: string | null
  category?: string | null
  required?: boolean | null
  blocked_by?: string[] | null
}

const CLOSED = new Set([
  'received',
  'complete',
  'completed',
  'verified',
  'waived',
  'cancelled_onboarding',
  'abandoned_employment_ended',
  'retired_legacy',
])

const UPLOADED_STORAGE = new Set(['stored', 'ok', 'uploaded', 'stored_with_fallback'])

/** Existing status labels that already mean “awaiting HR review” — do not invent new ones. */
const REVIEW_STATUS = new Set(['uploaded', 'submitted', 'needs_review', 'pending_review', 'awaiting_review'])

export function itemLooksUploaded(
  item: { status?: string | null; storage_status?: string | null },
  fileId?: string | null,
): boolean {
  const st = String(item.status || '').toLowerCase()
  if (REVIEW_STATUS.has(st)) return true
  const storage = String(item.storage_status || '').toLowerCase()
  if (UPLOADED_STORAGE.has(storage)) return true
  return Boolean(fileId)
}

export function resolveOwnerGroup(item: OnboardingPrimaryItem | null | undefined, fallback?: string | null): string {
  if (item?.owner_group) return String(item.owner_group).toLowerCase()
  const auth = String(item?.authority || '').toLowerCase()
  const cat = String(item?.category || '').toLowerCase()
  const id = String(item?.item_id || '').toLowerCase()
  if (auth === 'ess' || cat === 'payroll_bank' || id === 'bank_details') return 'payroll'
  if (auth === 'compliance_mirror' || cat === 'compliance_gov') return 'compliance'
  if (['account_access_created', 'attendance_device_id', 'access_card_issued', 'asset_handover', 'app_invite_sent'].includes(id)) {
    return 'it'
  }
  if (String(item?.owner || '').toLowerCase() === 'employee') return 'employee'
  if (fallback) return String(fallback).toLowerCase()
  if (String(item?.owner || '').toLowerCase() === 'employee') return 'employee'
  const owner = String(item?.owner || fallback || '').toLowerCase()
  if (owner === 'employee') return 'employee'
  if (owner) return 'hr'
  return ''
}

function openItems(detail: NonNullable<OnboardingPrimaryInput['detail']>): OnboardingPrimaryItem[] {
  const all = (detail.items && detail.items.length ? detail.items : detail.pending || []) as OnboardingPrimaryItem[]
  return all.filter((i) => {
    const st = String(i.status || '').toLowerCase()
    if (CLOSED.has(st)) return false
    if (i.required === false) return false
    return true
  })
}

/**
 * Primary row action for a hire.
 * 1. uploaded / awaiting review → review
 * 2. employee-owned missing item → remind
 * 3. HR (or IT/payroll/compliance) owned → open_checklist
 * 4. no actionable blocker → view_details
 */
export function onboardingPrimaryAction(input: OnboardingPrimaryInput): OnboardingPrimaryKind {
  const pendingCount = Number(input.pending_count || 0)
  let group = String(input.next_owner_group || '').toLowerCase()
  let uploaded = itemLooksUploaded({
    status: input.next_item_status,
    storage_status: input.next_item_storage_status,
  })
  let hasNext = Boolean(input.next_item_label) || pendingCount > 0

  const detail = input.detail
  if (detail && (!input.employee_key || !detail.employee_key || detail.employee_key === input.employee_key)) {
    const pending = openItems(detail)
    hasNext = hasNext || pending.length > 0
    const next =
      pending.find((i) => !i.blocked_by?.length) ||
      pending.find((i) => i.label && i.label === detail.next_item_label) ||
      pending[0] ||
      null
    if (next) {
      const idx = detail.document_index || {}
      const fileId = idx[String(next.item_id || '')] || idx[String(next.document_type || '')] || null
      uploaded = itemLooksUploaded(next, fileId)
      group = resolveOwnerGroup(next, detail.next_owner_group || input.next_owner_group)
    } else {
      group = String(detail.next_owner_group || group).toLowerCase()
    }
  }

  if (!group) {
    const owner = String(input.next_owner || detail?.next_owner || '').toLowerCase()
    group = owner === 'employee' ? 'employee' : owner ? 'hr' : ''
  }

  if (uploaded) return 'review'

  if (!hasNext) return 'view_details'

  if (group === 'employee') {
    return input.canRemind === false ? 'view_details' : 'remind'
  }

  if (group === 'hr' || group === 'it' || group === 'payroll' || group === 'compliance') {
    return 'open_checklist'
  }

  // Pending work with unknown owner — open the checklist rather than nudge the employee.
  return 'open_checklist'
}
