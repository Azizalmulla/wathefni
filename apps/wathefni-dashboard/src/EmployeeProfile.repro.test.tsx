import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import App from './App'
import { renderWithProviders } from '@/test/render'

function renderApp() {
  return renderWithProviders(<App />)
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Real production payload shapes (captured 2026-07-05 via a direct DB/backend
// check) for a Wathefni employee — used verbatim to reproduce the dashboard
// crash reported when opening an employee profile from the directory.
function summaryResponse() {
  return {
    company_code: 'WATHEFNI',
    module: 'pre_hiring',
    enabled_modules: ['pre_hiring', 'onboarding', 'compliance', 'attendance', 'leave', 'payroll', 'shifts'],
    access: {
      role: 'owner',
      permissions: ['employees.read', 'settings.manage', 'users.manage'],
      user: { company_code: 'WATHEFNI', role: 'owner', status: 'active', email: 'owner@example.com' },
    },
    features: { assessments_enabled: false },
    totals: { candidates: 0, applications: 0, active_applications: 0, hired_applications: 0 },
    status_counts: [],
    positions: [],
    recent_applications: [],
  }
}

function employeesListResponse() {
  return {
    company_code: 'WATHEFNI',
    employees: [
      {
        employee_key: 'WATHEFNI-96550252254',
        name: 'Talal Fadhli',
        phone: '96550252254',
        email: 'talalabdalla89@gmail.com',
        position_title: 'Social Media Manager',
        department: '',
        onboarding_status: 'in_progress',
        employment_status: 'active',
      },
    ],
  }
}

function employeeProfileResponse() {
  return {
    company_code: 'WATHEFNI',
    employee: {
      employee_key: 'WATHEFNI-96550252254',
      name: 'Talal Fadhli',
      phone: '96550252254',
      email: 'talalabdalla89@gmail.com',
      position_title: 'Social Media Manager',
      department: '',
      onboarding_status: 'in_progress',
      employment_status: 'active',
      start_date: null,
      updated_at: '2026-06-09T19:17:43.087577+00:00',
      hired_at: '2026-05-12T20:43:01.670538+00:00',
      documents_pending: 4,
      documents_complete: 0,
    },
    available_modules: ['onboarding', 'compliance', 'attendance', 'shifts', 'leave', 'payroll'],
    sections: {
      onboarding: {
        status: 'in_progress',
        outstanding_count: 4,
        complete_count: 0,
        outstanding: [
          { item_id: 'personal_photo', label: 'Personal photo', status: 'pending' },
          { item_id: 'civil_id', label: 'Civil ID (front + back)', status: 'pending' },
          { item_id: 'passport', label: 'Passport (photo page)', status: 'pending' },
          { item_id: 'bank_details', label: 'Bank account (IBAN)', status: 'pending' },
        ],
      },
      compliance: {
        expired: 0,
        expiring_soon: 0,
        missing: 5,
        needs_review: 0,
        valid: 0,
        needs_attention: 5,
        total_documents: 5,
        documents: [
          { document_type: 'residency', document_label: 'Residency (Iqama)', status: 'missing', status_label: 'Missing', tone: 'warning', expiry_date: null, days_until_expiry: null, last_reminded_at: null, reminder_count: 0 },
        ],
      },
      attendance: {
        window_days: 14,
        present: 0,
        late: 0,
        absent: 0,
        recent: [{ date: '2026-06-09', status: 'present', late_minutes: 0 }],
      },
      leave: {
        pending_count: 0,
        items: [],
        // NOTE: no `balances_enabled` / `balances` keys — matches the real
        // production response exactly (backend does not send them yet).
      },
      shifts: { upcoming_count: 0, items: [] },
      payroll: { items: [] },
      documents: { count: 0, items: [] },
    },
    next_actions: [
      { module: 'onboarding', label: '4 onboarding documents still needed', page: 'onboarding' },
      { module: 'compliance', label: '5 documents need attention', page: 'compliance' },
    ],
    next_actions_summary: null,
    next_actions_enabled: false,
    doc_upload_enabled: false,
    hr_mutate_enabled: false,
  }
}

describe('employee profile click (production data repro)', () => {
  test('opening an employee from the directory does not crash the dashboard', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'saved-token')
    localStorage.setItem('wathefni_hr_phone', '96599338566')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/dashboard/prehire/summary') return jsonResponse(summaryResponse())
      if (path.startsWith('/dashboard/prehire/applications')) return jsonResponse({ company_code: 'WATHEFNI', total: 0, limit: 50, offset: 0, applications: [] })
      if (path.startsWith('/dashboard/prehire/notifications')) return jsonResponse({ company_code: 'WATHEFNI', notifications: [] })
      if (path.startsWith('/dashboard/prehire/overview/work-queue')) {
        return jsonResponse({ company_code: 'WATHEFNI', items: [], can_view_company_work: false })
      }
      if (path === '/dashboard/prehire/reports') return jsonResponse({ company_code: 'WATHEFNI', summary: {}, exports: {}, breakdowns: { applications_by_stage: [], candidates_by_role: [], followups_by_type: [] } })
      if (path.startsWith('/dashboard/prehire/interviews')) return jsonResponse({ company_code: 'WATHEFNI', total: 0, status_counts: [], feedback_counts: [], interviews: [] })
      if (path === '/dashboard/posthire/employees') return jsonResponse(employeesListResponse())
      if (path === '/dashboard/posthire/employees/WATHEFNI-96550252254') return jsonResponse(employeeProfileResponse())
      return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    renderApp()

    // This fixture boots into a post-hire-capable workspace. On mobile the
    // PRE-HIRING rail is compact; Post-Hire routes live under More.
    const direct = screen.queryByRole('button', { name: 'Employees' })
    if (direct) {
      fireEvent.click(direct)
    } else {
      fireEvent.click(await screen.findByTestId('mobile-nav-more'))
      fireEvent.click(await screen.findByRole('menuitem', { name: 'Employees' }))
    }
    const nameHits = await screen.findAllByText('Talal Fadhli')
    fireEvent.click(nameHits[0])

    // If the profile crashed, the error boundary replaces the whole tree with
    // this text instead of the profile content.
    await waitFor(() => {
      expect(screen.queryByText('Something interrupted the dashboard')).not.toBeInTheDocument()
    })
    expect(await screen.findByTestId('employee-profile')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Back to directory|العودة إلى الدليل/ })).toBeInTheDocument()

    const renderErrors = consoleErrorSpy.mock.calls.filter((call) => String(call[0]).includes('Dashboard render error'))
    if (renderErrors.length > 0) {
      // eslint-disable-next-line no-console
      console.log('CAPTURED RENDER ERROR:', renderErrors[0][1])
    }
    expect(renderErrors).toHaveLength(0)
    consoleErrorSpy.mockRestore()
  })
})
