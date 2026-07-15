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
  return {
    task_id: text(input.task_id, text(input.id)),
    title: text(input.title, text(input.summary, '—')),
    summary: optionalText(input.summary) || optionalText(input.detail),
    status: text(input.status, 'pending'),
    due_at: optionalText(input.due_at) || optionalText(input.due_date),
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
    status: text(input.status, 'pending'),
    submitted_at: optionalText(input.submitted_at) || optionalText(input.created_at),
    preview_path: optionalText(input.preview_path),
    download_path: optionalText(input.download_path),
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
    preview_path: optionalText(input.preview_path),
    download_path: optionalText(input.download_path),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeOnboarding(value: unknown): OnboardingEmployee {
  const input = record(value)
  const employeeValue = input.employee || input.person
  return {
    employee_key: text(input.employee_key, text(record(employeeValue).employee_key)),
    employee: person(employeeValue || input),
    status: text(input.status, 'pending'),
    start_date: optionalText(input.start_date),
    current_step: optionalText(input.current_step),
    documents: Array.isArray(input.documents) ? input.documents.map(normalizeDocument) : undefined,
    items: Array.isArray(input.items) ? input.items.map(normalizeOnboardingItem) : undefined,
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeAttendance(value: unknown): AttendanceException {
  const input = record(value)
  const attendanceId = text(input.attendance_id, text(input.exception_id, text(input.id)))
  const status = text(input.status, 'open')
  return {
    exception_id: attendanceId,
    employee: person(input.employee || input.person),
    exception_type: text(
      input.exception_type,
      text(input.type, status === 'late' ? 'Late arrival' : status === 'absent' ? 'Absence' : 'Attendance exception'),
    ),
    status,
    occurred_at:
      optionalText(input.occurred_at) ||
      optionalText(input.timestamp) ||
      optionalText(input.attendance_date) ||
      optionalText(input.date),
    note: optionalText(input.note) || optionalText(input.notes),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeShift(value: unknown): Shift {
  const input = record(value)
  return {
    shift_id: text(input.shift_id, text(input.id)),
    employee: person(input.employee || input.person),
    status: text(input.status, 'scheduled'),
    starts_at:
      optionalText(input.starts_at) ||
      optionalText(input.start_at) ||
      dateTime(input.shift_date, input.start_time),
    ends_at:
      optionalText(input.ends_at) ||
      optionalText(input.end_at) ||
      dateTime(input.shift_date, input.end_time),
    location: optionalText(input.location),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeSwap(value: unknown): ShiftSwap {
  const input = record(value)
  const requesterShift = record(input.requester_shift)
  return {
    swap_id: text(input.swap_id, text(input.id)),
    requester: person(input.requester || input.employee),
    replacement: input.replacement || input.target ? person(input.replacement || input.target) : null,
    status: text(input.status, 'pending'),
    starts_at:
      optionalText(input.starts_at) ||
      optionalText(input.start_at) ||
      dateTime(
        requesterShift.shift_date || input.shift_date,
        requesterShift.start_time,
      ),
    ends_at:
      optionalText(input.ends_at) ||
      optionalText(input.end_at) ||
      dateTime(
        requesterShift.shift_date || input.shift_date,
        requesterShift.end_time,
      ),
    reason: optionalText(input.reason),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeEmployee(value: unknown): EmployeeSummary {
  const input = record(value)
  const employeeValue = input.employee || input.person || input
  return {
    employee_key: text(input.employee_key, text(record(employeeValue).employee_key)),
    employee: person(employeeValue),
    email: optionalText(input.email) || optionalText(record(employeeValue).email),
    phone: optionalText(input.phone) || optionalText(record(employeeValue).phone),
    started_on:
      optionalText(input.started_on) ||
      optionalText(input.start_date) ||
      optionalText(record(employeeValue).started_on) ||
      optionalText(record(employeeValue).start_date),
    manager_name: optionalText(input.manager_name) || optionalText(record(employeeValue).manager_name),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeAlert(value: unknown): DeliveryAlert {
  const input = record(value)
  return {
    alert_id: text(input.alert_id, text(input.outbound_id, text(input.id))),
    title: text(input.title, text(input.message_kind, text(input.template_key, 'Delivery alert'))),
    summary:
      optionalText(input.summary) ||
      optionalText(input.message) ||
      optionalText(input.last_error),
    status: text(input.status, 'pending'),
    channel: optionalText(input.channel),
    occurred_at: optionalText(input.occurred_at) || optionalText(input.created_at),
    destination: optionalText(input.destination),
    allowed_actions: actions(input.allowed_actions),
  }
}

export function normalizeCandidateSummary(value: unknown): CandidateSummary {
  const input = record(value)
  const overview = record(input.overview)
  const candidate = record(input.candidate || overview.candidate)
  const position = record(input.position || overview.position)
  const ranking = record(input.ranking)
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
  return {
    interview_id: text(input.interview_id, text(input.id)),
    app_key: optionalText(input.app_key),
    candidate: { name: text(candidate.name, 'Candidate'), email: optionalText(candidate.email) },
    position: { code: optionalText(position.code), title: optionalText(position.title) },
    status: text(input.status, 'scheduled'),
    scheduled_at: optionalText(input.scheduled_at) || optionalText(input.scheduled_start),
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
    allowed_actions: actions(input.allowed_actions),
  }
}

export const normalize = {
  tasks: (payload: unknown) => collection(payload, ['tasks', 'hr_tasks'], normalizeTask),
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
  candidates: (payload: unknown) =>
    collection(payload, ['candidates', 'applications'], normalizeCandidateSummary),
  interviews: (payload: unknown) => collection(payload, ['interviews'], normalizeInterview),
  interviewDetail: (payload: unknown) =>
    detail(payload, ['interview'], normalizeInterview),
}
