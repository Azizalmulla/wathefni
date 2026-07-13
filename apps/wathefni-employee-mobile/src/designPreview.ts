import type {
  AttendanceResponse,
  EmployeeProfile,
  LeaveResponse,
  NotificationsResponse,
  OnboardingResponse,
  ShiftRow,
} from '@/api/types'
import type { HomeFeatureSet } from '@/features/home/HomeView'
import type { AppLocale } from '@/i18n'

// Synthetic, opt-in fixtures for visual review. The flag is omitted from every
// normal build profile, and the fixtures never enter AuthProvider, secure
// storage, navigation authority, or production API traffic.
export const DESIGN_PREVIEW_ENABLED =
  process.env.EXPO_PUBLIC_DESIGN_PREVIEW === '1'

export function previewProfile(locale: AppLocale): EmployeeProfile {
  return {
    employee_key: 'design-preview-only',
    company_code: 'PREVIEW',
    name: locale === 'ar' ? 'موظف تجريبي' : 'Preview Employee',
    phone: '',
    email: '',
    position_title: '',
    department: '',
    onboarding_status: 'in_progress',
    locale,
  }
}

export const multiFeatures: HomeFeatureSet = {
  shifts: true,
  attendance: true,
  leave: true,
  onboarding: true,
  documents: true,
}

export const minimalFeatures: HomeFeatureSet = {
  shifts: false,
  attendance: false,
  leave: false,
  onboarding: false,
  documents: false,
}

export const previewShift: ShiftRow = {
  shift_id: 'preview-shift',
  shift_date: '2026-07-14',
  start_time: '09:00:00',
  end_time: '17:30:00',
  status: 'scheduled',
  role: null,
  location: 'Customer Support',
}

export const previewAttendance: AttendanceResponse = {
  ok: true,
  window_days: 30,
  summary: { present: 18, late: 1, absent: 0 },
  records: [{ attendance_date: '2026-07-14', status: 'present' }],
}

export const previewLeave: LeaveResponse = {
  ok: true,
  balances_enabled: true,
  types: ['annual', 'sick'],
  balances: [{ leave_type: 'annual', balance_days: 12, period_year: 2026 }],
  requests: [],
}

export const previewNotifications: NotificationsResponse = {
  ok: true,
  unread: 2,
  notifications: [
    {
      id: 'preview-message',
      flow: 'onboarding',
      title: 'Policy update',
      body: null,
      status: 'delivered',
      created_at: '2026-07-14T08:00:00Z',
      read: false,
    },
  ],
}

export const emptyNotifications: NotificationsResponse = {
  ok: true,
  unread: 0,
  notifications: [],
}

export const previewOnboarding: OnboardingResponse = {
  ok: true,
  status: 'in_progress',
  required_total: 2,
  received_count: 1,
  pending_count: 1,
  pending: [
    {
      item_id: 'personal_photo',
      document_type: 'personal_photo',
      item_type: 'document',
      status: 'pending',
      required: true,
      file_id: null,
    },
  ],
  received: [
    {
      item_id: 'employment_contract',
      document_type: 'employment_contract',
      item_type: 'document',
      status: 'reviewed',
      required: true,
      file_id: 'preview-reviewed',
    },
  ],
  next_item: null,
  can_upload: true,
}

export const completedOnboarding: OnboardingResponse = {
  ok: true,
  status: 'completed',
  required_total: 1,
  received_count: 1,
  pending_count: 0,
  pending: [],
  received: [
    {
      item_id: 'personal_photo',
      document_type: 'personal_photo',
      item_type: 'document',
      status: 'completed',
      required: true,
      file_id: 'preview-complete',
    },
  ],
  next_item: null,
  can_upload: true,
}
