import type {
  AttendanceResponse,
  EmployeeDocument,
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
    name: locale === 'ar' ? 'نورة الأحمد' : 'Noura Al Ahmad',
    phone: '+965 5555 1234',
    email: '',
    position_title: locale === 'ar' ? 'أخصائية تجربة العملاء' : 'Customer Experience Specialist',
    department: locale === 'ar' ? 'تجربة العملاء' : 'Customer Experience',
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
  balances: [
    { leave_type: 'annual', balance_days: 12, period_year: 2026 },
    { leave_type: 'sick', balance_days: 8, period_year: 2026 },
  ],
  requests: [
    {
      leave_id: 'preview-leave-1',
      start_date: '2026-07-21',
      end_date: '2026-07-23',
      leave_type: 'annual',
      status: 'approved',
      reason: 'Family plans',
      requested_at: '2026-07-10T09:00:00Z',
      decided_at: '2026-07-11T10:00:00Z',
    },
    {
      leave_id: 'preview-leave-2',
      start_date: '2026-08-03',
      end_date: '2026-08-03',
      leave_type: 'sick',
      status: 'requested',
      reason: null,
      requested_at: '2026-07-14T08:30:00Z',
      decided_at: null,
    },
  ],
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
    {
      id: 'preview-message-2',
      flow: 'leave',
      title: 'Leave request approved',
      body: 'Your annual leave request for 21–23 July was approved.',
      status: 'delivered',
      created_at: '2026-07-13T11:30:00Z',
      read: false,
    },
    {
      id: 'preview-message-3',
      flow: 'general',
      title: 'Welcome to your employee app',
      body: 'Your profile and work tools are ready.',
      status: 'delivered',
      created_at: '2026-07-10T08:00:00Z',
      read: true,
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

export const rejectedOnboarding: OnboardingResponse = {
  ok: true,
  status: 'in_progress',
  required_total: 1,
  received_count: 0,
  pending_count: 1,
  pending: [
    {
      item_id: 'personal_photo',
      document_type: 'personal_photo',
      item_type: 'document',
      status: 'rejected',
      required: true,
      file_id: 'preview-rejected',
    },
  ],
  received: [],
  next_item: null,
  can_upload: true,
}

export const reviewOnboarding: OnboardingResponse = {
  ok: true,
  status: 'in_progress',
  required_total: 1,
  received_count: 0,
  pending_count: 1,
  pending: [
    {
      item_id: 'personal_photo',
      document_type: 'personal_photo',
      item_type: 'document',
      status: 'pending',
      required: true,
      file_id: 'preview-under-review',
    },
  ],
  received: [],
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

export const previewUpcomingShifts: ShiftRow[] = [
  {
    shift_id: 'preview-shift-next',
    shift_date: '2026-07-15',
    start_time: '10:00:00',
    end_time: '18:30:00',
    status: 'scheduled',
    role: 'Customer experience',
    location: 'Kuwait City',
  },
  {
    shift_id: 'preview-shift-later',
    shift_date: '2026-07-17',
    start_time: '09:00:00',
    end_time: '17:30:00',
    status: 'scheduled',
    role: 'Customer experience',
    location: 'Kuwait City',
  },
]

export const previewDocuments: EmployeeDocument[] = [
  {
    file_id: 'preview-document-contract',
    document_type: 'employment_contract',
    label: 'Employment contract',
    item_id: 'employment_contract',
    filename: 'employment-contract.pdf',
    mime_type: 'application/pdf',
    size_bytes: 240000,
    stored_at: '2026-07-10T08:00:00Z',
    has_file: true,
  },
  {
    file_id: 'preview-document-id',
    document_type: 'civil_id',
    label: 'Civil ID',
    item_id: 'civil_id',
    filename: 'civil-id.jpg',
    mime_type: 'image/jpeg',
    size_bytes: 180000,
    stored_at: '2026-07-12T08:00:00Z',
    has_file: true,
  },
]
