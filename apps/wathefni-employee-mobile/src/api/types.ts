// Mirrors the backend /app/* payload shapes. Keep in sync with the orchestrator's
// employee-app endpoints in wathefni-orchestrator/app.py.

export type EmployeeProfile = {
  employee_key: string
  company_code: string
  name: string
  phone: string
  email: string
  position_title: string
  department: string
  onboarding_status: string
  locale: 'en' | 'ar'
}

export type ActivateResponse = {
  ok: boolean
  token: string
  refresh_token: string
  expires_at: string
  employee: EmployeeProfile
}

export type EmployeeFeatureKey =
  | 'home'
  | 'profile'
  | 'inbox'
  | 'settings'
  | 'onboarding'
  | 'documents'
  | 'attendance'
  | 'shifts'
  | 'leave'
  | 'payslips'
  | 'compliance_actions'

export type EmployeeFeatureCapability = {
  enabled: boolean
  reason: string | null
  dependency_mode: 'core' | 'all' | 'any'
  module_keys: string[]
  actions: string[]
}

export type MeResponse = EmployeeProfile & {
  ok: boolean
  employee: EmployeeProfile
  account_state: 'active'
  app_state: 'available'
  version: string
  effective_modules: string[]
  enabled_modules: string[]
  enabled_features: EmployeeFeatureKey[]
  features: Record<EmployeeFeatureKey, EmployeeFeatureCapability>
  leave: {
    balances_enabled: boolean
    types: string[]
  }
  leave_balances_enabled: boolean
}

export type OnboardingItem = {
  item_id?: string
  label?: string
  document_type?: string
  item_type?: string
  status?: string
  required?: boolean
  file_id?: string | null
}

export type OnboardingResponse = {
  ok: boolean
  status: string | null
  required_total: number
  received_count: number
  pending_count: number
  pending: OnboardingItem[]
  received: OnboardingItem[]
  next_item: OnboardingItem | null
  can_upload: boolean
}

export type LeaveBalance = {
  leave_type: string
  entitlement_days?: number
  accrued_days?: number
  consumed_days?: number
  balance_days?: number
  period_year?: number
}

export type LeaveRequestRow = {
  leave_id: string
  start_date: string
  end_date: string
  leave_type: string | null
  status: string
  reason: string | null
  requested_at: string | null
  decided_at: string | null
}

export type LeaveResponse = {
  ok: boolean
  balances_enabled: boolean
  types: string[]
  balances: LeaveBalance[]
  requests: LeaveRequestRow[]
}

export type ShiftRow = {
  shift_id: string
  shift_date: string
  start_time: string | null
  end_time: string | null
  status: string
  role: string | null
  location: string | null
}

export type AttendanceRow = {
  attendance_date: string
  status: string
}

export type AttendanceResponse = {
  ok: boolean
  window_days: number
  summary: { present: number; late: number; absent: number }
  records: AttendanceRow[]
}

export type EmployeeDocument = {
  file_id: string
  document_type: string | null
  label: string | null
  item_id: string | null
  filename: string | null
  mime_type: string | null
  size_bytes: number | null
  stored_at: string | null
  has_file: boolean
}

export type DocumentsResponse = {
  ok: boolean
  count: number
  documents: EmployeeDocument[]
}

export type NotificationItem = {
  id: string
  flow: string
  title: string
  body: string | null
  status: string
  created_at: string
  read: boolean
}

export type NotificationsResponse = {
  ok: boolean
  unread: number
  notifications: NotificationItem[]
}
