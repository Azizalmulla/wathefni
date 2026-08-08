import type {
  OnboardingCompletion,
  OnboardingCompletionState,
  OnboardingItem,
  OnboardingResponse,
} from '@/api/types'

/** Canonical completion states. Backend: onboarding_completion_contract. */
export const COMPLETION_STATES = new Set<OnboardingCompletionState>([
  'not_started',
  'in_progress',
  'waiting_on_employee',
  'waiting_on_hr',
  'blocked',
  'completed',
  'reopened',
])

/** Canonical Wave 2A checklist states from GET /app/onboarding (shared contract). */
export const WAVE2A_STATUSES = new Set([
  'pending',
  'in_progress',
  'submitted',
  'processing',
  'accepted',
  'rejected',
  'replacement_required',
  'waived',
  'blocked',
])

export type OnboardingLifecycleProjection = {
  lifecycleVersion: '2a'
  yourActions: OnboardingItem[]
  beingReviewed: OnboardingItem[]
  handledByOthers: OnboardingItem[]
  completed: OnboardingItem[]
  acceptedCount: number
  requiredTotal: number
  canUpload: boolean
  /** Canonical snapshot as returned by the backend. Never recomputed here. */
  completion: OnboardingCompletion | null
  completionState: OnboardingCompletionState | null
  contractOk: true
}

export type OnboardingContractFailure = {
  contractOk: false
  reason: string
  lifecycleVersion: string | null
}

export type OnboardingProjectionResult = OnboardingLifecycleProjection | OnboardingContractFailure

type ContractLogItem = {
  item_id: string | null
  status: string | null
  group: string | null
  actions: string[]
  has_rejection: boolean
  has_file: boolean
  unknown_status: boolean
}

/** Safe (no PII / no file contents) contract log for Wave 2A canary diagnosis. */
export function logOnboardingContract(data: OnboardingResponse): void {
  const groups = {
    your_actions: data.your_actions ?? data.groups?.your_actions ?? [],
    being_reviewed: data.being_reviewed ?? data.groups?.being_reviewed ?? [],
    handled_by_others: data.handled_by_others ?? data.groups?.handled_by_others ?? [],
    completed: data.completed ?? data.groups?.completed ?? [],
  }
  const items: ContractLogItem[] = Object.entries(groups).flatMap(([groupName, rows]) =>
    rows.map((item) => {
      const status = typeof item.status === 'string' ? item.status : null
      return {
        item_id: item.item_id ?? null,
        status,
        group: item.group ?? groupName,
        actions: Array.isArray(item.actions) ? item.actions.map(String) : [],
        has_rejection: Boolean(item.rejection_reason),
        has_file: Boolean(item.file_id),
        unknown_status: Boolean(status && !WAVE2A_STATUSES.has(status)),
      }
    }),
  )
  const payload = {
    tag: 'onboarding_wave2a_contract',
    lifecycle_version: data.lifecycle_version ?? null,
    accepted_count: data.accepted_count ?? null,
    required_total: data.required_total ?? null,
    group_counts: {
      your_actions: groups.your_actions.length,
      being_reviewed: groups.being_reviewed.length,
      handled_by_others: groups.handled_by_others.length,
      completed: groups.completed.length,
    },
    // Legacy alias sizes — if the UI ever reads these, grouping will be wrong.
    legacy_alias_counts: {
      pending: (data.pending ?? []).length,
      received: (data.received ?? []).length,
    },
    unknown_status_count: items.filter((i) => i.unknown_status).length,
    focus: items.filter((i) =>
      ['civil_id', 'employment_contract', 'personal_photo', 'offer_letter', 'bank_details'].includes(
        String(i.item_id || ''),
      ),
    ),
    items,
  }
  // eslint-disable-next-line no-console
  console.info(JSON.stringify(payload))
}

/**
 * Map GET /app/onboarding → Wave 2A sections using exact API fields.
 * Does not fall back to legacy pending/received (those aliases mix completed+being_reviewed).
 */
export function projectOnboardingLifecycle(data: OnboardingResponse): OnboardingProjectionResult {
  logOnboardingContract(data)
  const version = String(data.lifecycle_version || '').trim().toLowerCase()
  if (version !== '2a') {
    return {
      contractOk: false,
      reason: 'lifecycle_version_not_2a',
      lifecycleVersion: data.lifecycle_version ?? null,
    }
  }

  const yourActions = Array.isArray(data.your_actions)
    ? data.your_actions
    : Array.isArray(data.groups?.your_actions)
      ? data.groups!.your_actions!
      : []
  const beingReviewed = Array.isArray(data.being_reviewed)
    ? data.being_reviewed
    : Array.isArray(data.groups?.being_reviewed)
      ? data.groups!.being_reviewed!
      : []
  const handledByOthers = Array.isArray(data.handled_by_others)
    ? data.handled_by_others
    : Array.isArray(data.groups?.handled_by_others)
      ? data.groups!.handled_by_others!
      : []
  const completed = Array.isArray(data.completed)
    ? data.completed
    : Array.isArray(data.groups?.completed)
      ? data.groups!.completed!
      : []

  const completion = data.completion && typeof data.completion === 'object' ? data.completion : null
  const rawState = String(completion?.state || '').trim().toLowerCase()
  const completionState = COMPLETION_STATES.has(rawState as OnboardingCompletionState)
    ? (rawState as OnboardingCompletionState)
    : null
  if (completion && !completionState) {
    // eslint-disable-next-line no-console
    console.info(
      JSON.stringify({ tag: 'onboarding_completion_unknown_state', state: rawState || null }),
    )
  }

  return {
    contractOk: true,
    lifecycleVersion: '2a',
    yourActions,
    beingReviewed,
    handledByOthers,
    completed,
    acceptedCount: Number(data.accepted_count ?? 0),
    requiredTotal: Number(data.required_total ?? 0),
    canUpload: Boolean(data.can_upload),
    completion,
    completionState,
  }
}

/** Localized label for a canonical completion state. */
export function completionStateLabel(
  state: OnboardingCompletionState | null,
  t: (key: string) => string,
): string {
  return state ? t(`onboarding.completion.${state}`) : t('status.unknown')
}

/**
 * "What happens next". The backend message wins: a state alone cannot say who
 * owns the work (`reopened` can be waiting on the employee or on HR), so a
 * local state→copy table contradicts the canonical contract. The per-state
 * string is only the offline/older-payload fallback, never a second source.
 */
export function completionNextActionMessage(
  completion: OnboardingCompletion | null,
  state: OnboardingCompletionState | null,
  locale: string,
  t: (key: string) => string,
): string {
  const action = completion?.next_action
  const arabic = String(locale).toLowerCase().startsWith('ar')
  const fromServer = String((arabic ? action?.message_ar : action?.message_en) || action?.message || '')
  if (fromServer) return fromServer
  return state ? t(`onboarding.next.${state}`) : ''
}

/** Chip label from canonical item.status only — never review_status. */
export function onboardingStatusLabel(
  status: string | null | undefined,
  t: (key: string) => string,
): string {
  const normalized = String(status || '').trim().toLowerCase()
  if (!normalized) return t('status.unknown')
  if (!WAVE2A_STATUSES.has(normalized)) {
    // eslint-disable-next-line no-console
    console.info(
      JSON.stringify({
        tag: 'onboarding_wave2a_unknown_status',
        status: normalized,
      }),
    )
    return t('status.unknown')
  }
  return t(`status.${normalized}`)
}
