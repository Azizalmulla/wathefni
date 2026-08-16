import type {
  AttendanceException,
  CandidateSummary,
  DeliveryAlert,
  DocumentReview,
  EmployeeSummary,
  HRTask,
  InterviewSummary,
  MobileCollection,
  MobileDetail,
  OnboardingChecklistItem,
  OnboardingEmployee,
  PersonIdentity,
  Shift,
  ShiftSwap,
} from './types'

type UnknownRecord = Record<string, unknown>

function record(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as UnknownRecord) : {}
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function dateTime(date: unknown, time: unknown): string | null {
  const day = optionalText(date)
  const clock = optionalText(time)
  if (!day) return null
  if (!clock) return day
  if (/^\d{2}:\d{2}(:\d{2})?$/.test(clock)) return `${day}T${clock}`
  return clock
}

function actions(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function person(value: unknown): PersonIdentity {
  const input = record(value)
  return {
    employee_key: optionalText(input.employee_key) || undefined,
    name: text(input.name, text(input.display_name, '—')),
    position_title: optionalText(input.position_title),
    department: optionalText(input.department),
    employment_status: optionalText(input.employment_status),
    onboarding_status: optionalText(input.onboarding_status),
  }
}

function listPayload(payload: unknown, keys: string[]): { source: UnknownRecord; items: unknown[] } {
  const source = record(payload)
  for (const key of ['items', ...keys]) {
    if (Array.isArray(source[key])) return { source, items: source[key] as unknown[] }
  }
  return { source, items: [] }
}

function detailPayload(payload: unknown, keys: string[]): { source: UnknownRecord; item: unknown } {
  const source = record(payload)
  for (const key of ['item', ...keys]) {
    if (source[key] && typeof source[key] === 'object') return { source, item: source[key] }
  }
  return { source, item: source }
}

function collection<T>(payload: unknown, keys: string[], normalize: (value: unknown) => T): MobileCollection<T> {
  const value = listPayload(payload, keys)
  return {
    ok: true,
    items: value.items.map(normalize),
    generated_at: optionalText(value.source.generated_at),
    stale: value.source.stale === true,
    total: numberOrNull(value.source.total) ?? numberOrNull(value.source.total_count) ?? undefined,
    limit: numberOrNull(value.source.limit) ?? undefined,
    offset: numberOrNull(value.source.offset) ?? undefined,
    has_more: value.source.has_more === true,
  }
}

function normalizeCandidatesCollection(payload: unknown): import('./types').CandidatesCollection {
  const base = collection(payload, ['candidates', 'applications', 'items'], normalizeCandidateSummary)
  const source = record(payload)
  return {
    ...base,
    requires_position: source.requires_position === true,
    ranking_unavailable: source.ranking_unavailable === true,
    ranking_error: optionalText(source.ranking_error),
    message: optionalText(source.message),
  }
}

function normalizePosition(value: unknown): import('./types').PrehirePositionSummary {
  const input = record(value)
  return {
    position_code: text(input.position_code, text(input.code)),
    title: optionalText(input.title) || optionalText(input.position_title),
    status: optionalText(input.status),
    department: optionalText(input.department),
    open_count: numberOrNull(input.open_count),
    ready_for_review: numberOrNull(input.ready_for_review),
  }
}

function normalizePositionsCollection(payload: unknown): import('./types').PositionsCollection {
  const source = record(payload)
  const rows = Array.isArray(source.positions)
    ? source.positions
    : Array.isArray(source.items)
      ? source.items
      : []
  return {
    ok: true,
    items: rows.map(normalizePosition),
    total: numberOrNull(source.total_count) ?? numberOrNull(source.total) ?? undefined,
    limit: numberOrNull(source.limit) ?? undefined,
    offset: numberOrNull(source.offset) ?? undefined,
    has_more: source.has_more === true,
  }
}

function detail<T>(payload: unknown, keys: string[], normalize: (value: unknown) => T): MobileDetail<T> {
  const value = detailPayload(payload, keys)
  return {
    ok: true,
    item: normalize(value.item),
    generated_at: optionalText(value.source.generated_at),
    stale: value.source.stale === true,
  }
}

export function normalizeTask(value: unknown): HRTask {
  const input = record(value)
  const employee = input.employee ? person(input.employee) : null
  return {
    task_id: text(input.task_id, text(input.id)),
    task_type: optionalText(input.task_type),
    source: optionalText(input.source),
    title: text(input.title, 'HR task'),
    detail: optionalText(input.detail),
    employee,
    status: text(input.status, 'open'),
    priority: optionalText(input.priority),
    created_at: optionalText(input.created_at),
    updated_at: optionalText(input.updated_at),
    destination: optionalText(input.destination),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeDocument(value: unknown): DocumentReview {
  const input = record(value)
  const employee = input.employee ? person(input.employee) : null
  return {
    document_id: text(input.document_id, text(input.id)),
    source:
      input.source === 'compliance' || input.source === 'onboarding'
        ? input.source
        : null,
    employee,
    name: text(input.name, text(input.label, text(input.filename, 'Document'))),
    document_type: optionalText(input.document_type) || optionalText(input.type),
    status: text(input.status, 'needs_review'),
    status_label: optionalText(input.status_label),
    expiry_date: optionalText(input.expiry_date),
    days_until_expiry: numberOrNull(input.days_until_expiry),
    last_checked_at: optionalText(input.last_checked_at),
    last_reminded_at: optionalText(input.last_reminded_at),
    reminder_count: numberOrNull(input.reminder_count) ?? undefined,
    extraction_confidence: numberOrNull(input.extraction_confidence ?? input.confidence),
    has_file: input.has_file === true || Boolean(optionalText(input.preview_path)),
    preview_path: optionalText(input.preview_path),
    download_path: optionalText(input.download_path),
    destination: optionalText(input.destination),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeOnboardingItem(value: unknown): OnboardingChecklistItem {
  const input = record(value)
  return {
    item_id: text(input.item_id, text(input.id)),
    label: text(input.label, 'Onboarding item'),
    item_type: optionalText(input.item_type),
    document_type: optionalText(input.document_type),
    required: input.required === true,
    status: text(input.status, 'pending'),
    group: optionalText(input.group),
    is_bank_ess: input.is_bank_ess === true,
    has_file: input.has_file === true || Boolean(optionalText(input.preview_path)),
    preview_path: optionalText(input.preview_path),
    download_path: optionalText(input.download_path),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeOnboarding(value: unknown): OnboardingEmployee {
  const input = record(value)
  const employeeValue = input.employee || input.person
  const hrItems = Array.isArray(input.hr_actionable_items)
    ? input.hr_actionable_items.map(normalizeOnboardingItem)
    : Array.isArray(input.items)
      ? input.items.map(normalizeOnboardingItem)
      : undefined
  const waiting = Array.isArray(input.waiting_on_employee_items)
    ? input.waiting_on_employee_items.map(normalizeOnboardingItem)
    : undefined
  return {
    employee_key: text(input.employee_key, text(record(employeeValue).employee_key)),
    employee: person(employeeValue || input),
    status: text(input.status, 'pending'),
    pending_count: numberOrNull(input.pending_count) ?? undefined,
    received_count: numberOrNull(input.received_count) ?? undefined,
    hr_actionable_count:
      numberOrNull(input.hr_actionable_count) ?? (hrItems ? hrItems.length : undefined),
    hr_mutate_enabled: input.hr_mutate_enabled === true,
    hr_actionable_items: hrItems,
    waiting_on_employee_items: waiting,
    items: hrItems,
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeAttendance(value: unknown): AttendanceException {
  const input = record(value)
  const attendanceId = text(input.attendance_id, text(input.exception_id, text(input.id)))
  const status = text(input.status, 'open')
  const kindRaw = optionalText(input.exception_kind)
  const kind =
    kindRaw === 'absence' ||
    kindRaw === 'lateness' ||
    kindRaw === 'early_leave' ||
    kindRaw === 'missing_check_in' ||
    kindRaw === 'missing_check_out' ||
    kindRaw === 'incomplete_session'
      ? kindRaw
      : null
  const late = numberOrNull(input.late_minutes) ?? 0
  const early = numberOrNull(input.early_leave_minutes) ?? 0
  const actionMode =
    optionalText(input.action_mode) === 'request_correction' ||
    actions(input.allowed_actions).includes('resolve')
      ? 'request_correction'
      : 'read'
  return {
    attendance_id: attendanceId,
    exception_id: attendanceId,
    employee: person(input.employee || input.person),
    exception_kind: kind,
    is_exception: input.is_exception === true || Boolean(kind),
    status,
    attendance_date: optionalText(input.attendance_date) || optionalText(input.date),
    scheduled_start: optionalText(input.scheduled_start),
    scheduled_end: optionalText(input.scheduled_end),
    check_in_at: optionalText(input.check_in_at),
    check_out_at: optionalText(input.check_out_at),
    late_minutes: late,
    early_leave_minutes: early,
    occurred_at:
      optionalText(input.occurred_at) ||
      optionalText(input.timestamp) ||
      optionalText(input.attendance_date) ||
      optionalText(input.date),
    note: optionalText(input.note) || optionalText(input.notes),
    updated_at: optionalText(input.updated_at),
    action_mode: actionMode,
    allowed_actions: actions(input.allowed_actions),
    destination: optionalText(input.destination),
  }
}

export function normalizeShift(value: unknown): Shift {
  const input = record(value)
  const statusRaw = optionalText(input.status) || optionalText(input.ui_state) || 'scheduled'
  return {
    shift_id: text(input.shift_id, text(input.id)),
    employee: person(input.employee || input.person),
    status: statusRaw,
    shift_date: optionalText(input.shift_date) || optionalText(input.date),
    starts_at:
      optionalText(input.starts_at) ||
      optionalText(input.start_at) ||
      dateTime(input.shift_date, input.start_time),
    ends_at:
      optionalText(input.ends_at) ||
      optionalText(input.end_at) ||
      dateTime(input.shift_date, input.end_time),
    location: optionalText(input.location),
    role: optionalText(input.role) || optionalText(input.assignment_type),
    timezone: optionalText(input.timezone),
    updated_at: optionalText(input.updated_at),
    allowed_actions: actions(input.allowed_actions),
    destination: optionalText(input.destination),
  }
}

export function normalizeSwap(value: unknown): ShiftSwap {
  const input = record(value)
  const requesterShiftRaw = input.requester_shift
  const targetShiftRaw = input.target_shift
  const requesterShift = requesterShiftRaw ? normalizeShift(requesterShiftRaw) : null
  const targetShift = targetShiftRaw ? normalizeShift(targetShiftRaw) : null
  const statusRaw = optionalText(input.status)
  // Canonical statuses only — never invent a non-Ops placeholder.
  const status =
    statusRaw === 'requested' ||
    statusRaw === 'approved' ||
    statusRaw === 'rejected' ||
    statusRaw === 'cancelled'
      ? statusRaw
      : statusRaw || 'requested'
  return {
    swap_id: text(input.swap_id, text(input.id)),
    requester: person(input.requester || input.employee),
    replacement: input.replacement || input.target ? person(input.replacement || input.target) : null,
    status,
    shift_date:
      optionalText(input.shift_date) ||
      requesterShift?.shift_date ||
      optionalText(record(requesterShiftRaw).shift_date),
    starts_at:
      optionalText(input.starts_at) ||
      optionalText(input.start_at) ||
      requesterShift?.starts_at ||
      dateTime(
        record(requesterShiftRaw).shift_date || input.shift_date,
        record(requesterShiftRaw).start_time,
      ),
    ends_at:
      optionalText(input.ends_at) ||
      optionalText(input.end_at) ||
      requesterShift?.ends_at ||
      dateTime(
        record(requesterShiftRaw).shift_date || input.shift_date,
        record(requesterShiftRaw).end_time,
      ),
    reason: optionalText(input.reason),
    decision_note: optionalText(input.decision_note),
    requested_at: optionalText(input.requested_at),
    decided_at: optionalText(input.decided_at),
    updated_at: optionalText(input.updated_at),
    requester_shift_id: optionalText(input.requester_shift_id),
    target_shift_id: optionalText(input.target_shift_id),
    requester_shift: requesterShift,
    target_shift: targetShift,
    allowed_actions: actions(input.allowed_actions),
    destination: optionalText(input.destination),
  }
}

export function normalizeEmployee(value: unknown): EmployeeSummary {
  const input = record(value)
  const employeeValue = input.employee || input.person || input
  const nested = record(employeeValue)
  // Prefer nested person fields; allow top-level onboarding_status fallbacks.
  const identity = person({
    ...nested,
    onboarding_status: nested.onboarding_status ?? input.onboarding_status,
    employment_status: nested.employment_status ?? input.employment_status,
  })
  return {
    employee_key: text(input.employee_key, text(nested.employee_key)),
    employee: identity,
    email: optionalText(input.email) || optionalText(nested.email),
    phone: optionalText(input.phone) || optionalText(nested.phone),
    started_on:
      optionalText(input.started_on) ||
      optionalText(input.start_date) ||
      optionalText(nested.started_on) ||
      optionalText(nested.start_date),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeAlert(value: unknown): DeliveryAlert {
  const input = record(value)
  const employee = record(input.employee)
  return {
    alert_id: text(input.alert_id, text(input.outbound_id, text(input.message_id, text(input.id)))),
    title: text(
      input.title,
      text(input.flow_label, text(input.message_kind, text(input.template_key, 'Delivery alert'))),
    ),
    summary:
      optionalText(input.summary) ||
      optionalText(input.reason) ||
      optionalText(input.message) ||
      optionalText(input.last_error),
    status: text(input.status, 'pending'),
    kind: optionalText(input.kind),
    channel:
      optionalText(input.channel) ||
      optionalText(input.channel_used) ||
      optionalText(input.flow_label) ||
      optionalText(input.flow),
    flow: optionalText(input.flow),
    flow_label: optionalText(input.flow_label),
    occurred_at:
      optionalText(input.occurred_at) ||
      optionalText(input.last_attempt_at) ||
      optionalText(input.updated_at) ||
      optionalText(input.created_at),
    suggested_action: optionalText(input.suggested_action),
    attempts: typeof input.attempts === 'number' ? input.attempts : Number(input.attempts) || 0,
    has_task: input.has_task === true,
    employee: {
      employee_key:
        optionalText(employee.employee_key) || optionalText(input.employee_key) || undefined,
      name: optionalText(employee.name) || optionalText(input.employee_name) || undefined,
    },
    destination: optionalText(input.destination),
    allowed_actions: (() => {
      const list = actions(input.allowed_actions)
      return list.length ? list : ['read']
    })(),
  }
}

export function normalizeCandidateSummary(value: unknown): CandidateSummary {
  const input = record(value)
  const overview = record(input.overview)
  const candidate = record(input.candidate || overview.candidate)
  const position = record(input.position || overview.position)
  const ranking = record(input.ranking)
  const communication = record(input.communication || overview.communication)
  const waitingForHr = Array.isArray(input.waiting_for_hr)
    ? input.waiting_for_hr
    : Array.isArray(overview.waiting_for_hr)
      ? overview.waiting_for_hr
      : []
  return {
    app_key: text(input.app_key, text(input.id)),
    candidate: {
      name: text(candidate.name, 'Candidate'),
      email: optionalText(candidate.email),
    },
    position: {
      code: optionalText(position.code),
      title: optionalText(position.title),
    },
    status: text(input.status, text(overview.status, 'review_pending')),
    canonical_stage: optionalText(input.canonical_stage) || optionalText(overview.canonical_stage),
    status_label: optionalText(input.status_label) || optionalText(overview.status_label),
    intake_source: optionalText(input.intake_source) || optionalText(overview.intake_source),
    communication_status: optionalText(input.communication_status) || optionalText(communication.status),
    next_human_action: waitingForHr.length ? optionalText(waitingForHr[0]) : null,
    score: numberOrNull(input.score ?? ranking.score),
    confidence:
      typeof (input.confidence ?? ranking.confidence) === 'string' ||
      typeof (input.confidence ?? ranking.confidence) === 'number'
        ? (input.confidence ?? ranking.confidence) as string | number
        : null,
    updated_at: optionalText(input.updated_at),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeInterview(value: unknown): InterviewSummary {
  const input = record(value)
  const candidate = record(input.candidate)
  const position = record(input.position)
  const communication = record(input.communication)
  const meeting = record(input.meeting)
  return {
    interview_id: text(input.interview_id, text(input.id)),
    app_key: optionalText(input.app_key),
    candidate: { name: text(candidate.name, 'Candidate'), email: optionalText(candidate.email) },
    position: { code: optionalText(position.code), title: optionalText(position.title) },
    status: text(input.status, 'scheduled'),
    application_stage: optionalText(input.application_stage),
    application_stage_label: optionalText(input.application_stage_label),
    interview_type: optionalText(input.interview_type),
    feedback_status: optionalText(input.feedback_status),
    scheduled_at: optionalText(input.scheduled_at) || optionalText(input.scheduled_start),
    scheduled_end: optionalText(input.scheduled_end),
    timezone: optionalText(input.timezone),
    meeting: {
      type: optionalText(meeting.type),
      join_url: optionalText(meeting.join_url),
    },
    notes: optionalText(input.notes),
    communication_status:
      optionalText(input.communication_status) ||
      optionalText(communication.status) ||
      (communication.candidate_notified === true
        ? 'Candidate notified'
        : communication.candidate_invited === true
          ? 'Invite sent'
          : communication.calendar_invite_sent === true
            ? 'Calendar sent'
            : null),
    invitation_status: optionalText(input.invitation_status),
    candidate_confirmation: optionalText(input.candidate_confirmation),
    notes_status: optionalText(input.notes_status),
    next_human_action: optionalText(input.next_human_action),
    ai_summary: record(input.ai_summary),
    ai_advisory: input.ai_advisory === true ? true : undefined,
    updated_at: optionalText(input.updated_at),
    notes_version: numberOrNull(input.notes_version),
    allowed_actions: actions(input.allowed_actions),
  }
}

export const normalize = {
  tasks: (payload: unknown) => collection(payload, ['tasks', 'hr_tasks'], normalizeTask),
  taskDetail: (payload: unknown) => detail(payload, ['task'], normalizeTask),
  onboarding: (payload: unknown) => collection(payload, ['onboarding', 'employees'], normalizeOnboarding),
  onboardingDetail: (payload: unknown) =>
    detail(payload, ['onboarding', 'employee'], normalizeOnboarding),
  documents: (payload: unknown) => collection(payload, ['documents'], normalizeDocument),
  documentDetail: (payload: unknown) =>
    detail(payload, ['document'], normalizeDocument),
  attendance: (payload: unknown) =>
    collection(payload, ['exceptions', 'attendance'], normalizeAttendance),
  attendanceDetail: (payload: unknown) =>
    detail(payload, ['attendance'], normalizeAttendance),
  shifts: (payload: unknown) => collection(payload, ['shifts'], normalizeShift),
  swaps: (payload: unknown) => collection(payload, ['shift_swaps', 'swaps'], normalizeSwap),
  swapDetail: (payload: unknown) => detail(payload, ['shift_swap', 'swap'], normalizeSwap),
  employees: (payload: unknown) => collection(payload, ['employees'], normalizeEmployee),
  employeeDetail: (payload: unknown) => detail(payload, ['employee'], normalizeEmployee),
  alerts: (payload: unknown) => collection(payload, ['delivery_alerts', 'alerts'], normalizeAlert),
  candidates: (payload: unknown) => normalizeCandidatesCollection(payload),
  positions: (payload: unknown) => normalizePositionsCollection(payload),
  interviews: (payload: unknown) => collection(payload, ['interviews'], normalizeInterview),
  interviewDetail: (payload: unknown) =>
    detail(payload, ['interview'], normalizeInterview),
}
