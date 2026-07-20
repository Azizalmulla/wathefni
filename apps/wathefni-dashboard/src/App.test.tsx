import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import App from './App'
import { ConfirmProvider } from '@/components/ConfirmDialog'

function renderApp() {
  return render(
    <ConfirmProvider>
      <App />
    </ConfirmProvider>,
  )
}

describe('dashboard initial load', () => {
  test('loads saved access and fetches live dashboard data after page refresh', async () => {
    localStorage.setItem('wathefni_dashboard_token', ' saved-token ')
    localStorage.setItem('wathefni_hr_phone', ' 96555511122 ')
    localStorage.setItem('wathefni_company_code', ' wathefni ')

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      const payload = responseFor(path)
      if (!payload) {
        return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
      }
      return jsonResponse(payload)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderApp()

    await screen.findByText('What needs attention today')
    await waitFor(() => {
      expect(calledPaths(fetchMock)).toEqual(
        expect.arrayContaining([
          '/dashboard/prehire/summary',
          '/dashboard/prehire/applications?limit=50&offset=0&sort=newest',
          '/dashboard/prehire/interviews?limit=25&offset=0&status=upcoming',
          '/dashboard/prehire/notifications?limit=25',
          '/dashboard/prehire/reports',
          '/dashboard/prehire/overview/work-queue?limit=25',
          '/dashboard/prehire/assessments?limit=50&offset=0',
          '/dashboard/prehire/assessments/config',
        ]),
      )
    })

    const summaryHeaders = requestHeadersFor(fetchMock, '/dashboard/prehire/summary')
    expect(summaryHeaders.get('Authorization')).toBe('Bearer saved-token')
    expect(summaryHeaders.get('X-HR-Phone')).toBe('96555511122')
    expect(summaryHeaders.get('X-Company-Code')).toBe('WATHEFNI')
    expect(screen.getByText('Top priorities')).toBeInTheDocument()
    expect(screen.getByText('Suggested next action')).toBeInTheDocument()
    expect(screen.getByText('You’re viewing the latest data.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Alerts & Delivery' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Employee App' })).not.toBeInTheDocument()
    expect(screen.queryByText('Employee App')).not.toBeInTheDocument()
  })

  test('loads saved session access without requiring HR phone', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'saved-token')
    localStorage.removeItem('wathefni_hr_phone')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      const payload = responseFor(path)
      if (!payload) {
        return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
      }
      return jsonResponse(payload)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderApp()

    await screen.findByText('What needs attention today')
    const summaryHeaders = requestHeadersFor(fetchMock, '/dashboard/prehire/summary')
    expect(summaryHeaders.get('Authorization')).toBe('Bearer saved-token')
    expect(summaryHeaders.get('X-HR-Phone')).toBeNull()
    expect(summaryHeaders.get('X-Company-Code')).toBe('WATHEFNI')
  })

  test('shows access verification screen when saved token is rejected', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'old-token')
    localStorage.setItem('wathefni_hr_phone', '96555511122')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        {
          detail: {
            error: 'dashboard_auth_failed',
            message: 'The dashboard token was rejected. Re-enter the current token in Settings.',
          },
        },
        401,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderApp()

    expect(await screen.findByRole('heading', { name: 'Sign in to Wathefni' })).toBeInTheDocument()
    expect(screen.getByText(/session expired/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Backup access code')).toBeInTheDocument()
    expect(screen.getByText('Sign in')).toBeInTheDocument()
  })

  test('hides assessment navigation when the module is disabled', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'saved-token')
    localStorage.setItem('wathefni_hr_phone', '96555511122')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      const payload = responseFor(path, { enabledModules: ['pre_hiring'] })
      if (!payload) {
        return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
      }
      return jsonResponse(payload)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderApp()

    await screen.findByText('What needs attention today')
    expect(screen.queryByRole('button', { name: 'Assessments' })).not.toBeInTheDocument()
    expect(screen.queryByText('Assessment ready')).not.toBeInTheDocument()
    expect(screen.queryByText('Send pending assessments')).not.toBeInTheDocument()
    expect(screen.queryByText('Ready for assessment')).not.toBeInTheDocument()
    expect(screen.queryByText('Assessment queue')).not.toBeInTheDocument()
    expect(screen.queryByText('Review interview next steps')).not.toBeInTheDocument()
    expect(screen.getAllByText('Review ready candidates').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Follow up with candidates').length).toBeGreaterThan(0)
    expect(calledPaths(fetchMock)).not.toContain('/dashboard/prehire/assessments?limit=50&offset=0')
    expect(calledPaths(fetchMock)).not.toContain('/dashboard/prehire/assessments/config')
  })

  test('boots a post-hire-only workspace without calling pre-hiring data APIs', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'saved-token')
    localStorage.removeItem('wathefni_hr_phone')
    localStorage.setItem('wathefni_company_code', 'POSTHIREONLY')

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/dashboard/bootstrap') {
        return jsonResponse({
          company_code: 'POSTHIREONLY',
          configured_modules: ['compliance'],
          effective_modules: ['compliance'],
          enabled_modules: ['compliance'],
          module_catalog: [],
          access: {
            role: 'owner',
            permissions: ['compliance.read', 'compliance.manage', 'users.manage', 'settings.manage'],
            user: { company_code: 'POSTHIREONLY', role: 'owner', status: 'active', email: 'owner@example.com' },
          },
          user: { company_code: 'POSTHIREONLY', role: 'owner', status: 'active', email: 'owner@example.com' },
        })
      }
      if (path === '/dashboard/prehire/notifications?limit=25') {
        return jsonResponse({ company_code: 'POSTHIREONLY', enabled_modules: ['compliance'], notifications: [], action_items: [] })
      }
      if (path === '/dashboard/setup/readiness') {
        return jsonResponse({ company_code: 'POSTHIREONLY', ready: true, steps: [] })
      }
      if (path.startsWith('/dashboard/posthire/employees')) {
        return jsonResponse({ company_code: 'POSTHIREONLY', employees: [], total_count: 0, limit: 50, offset: 0 })
      }
      return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderApp()

    expect((await screen.findAllByRole('heading', { name: 'Employees' })).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Employees' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Compliance' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Overview' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Jobs' })).not.toBeInTheDocument()
    await waitFor(() => expect(calledPaths(fetchMock)).toContain('/dashboard/bootstrap'))
    expect(calledPaths(fetchMock)).not.toContain('/dashboard/prehire/summary')
    expect(calledPaths(fetchMock)).not.toContain('/dashboard/prehire/applications?limit=50&offset=0&sort=newest')
  })
})

function responseFor(path: string, options: { enabledModules?: string[] } = {}) {
  const enabledModules = options.enabledModules || ['pre_hiring', 'assessments']
  if (path === '/dashboard/prehire/summary') {
    return {
      company_code: 'WATHEFNI',
      module: 'pre_hiring',
      enabled_modules: enabledModules,
      features: { assessments_enabled: enabledModules.includes('assessments') },
      totals: { candidates: 1, applications: 1, active_applications: 1, hired_applications: 0 },
      action_counts: {
        ready_for_review: 1,
        assessment_pending: enabledModules.includes('assessments') ? 1 : 0,
        follow_up_needed: 0,
      },
      next_action: {
        action: 'ready_for_review',
        priority: 70,
        reason: '1 candidate ready for an HR decision',
        total_matching: 1,
        destination: { page: 'candidates', filters: { review_status: 'ready' } },
        label: 'suggested_next_action',
      },
      role_priority: null,
      status_counts: [{ status: 'screening', count: 1 }],
      positions: [
        {
          position_code: 'ACCOUNTING_EXCEL',
          position_title: 'Accounting Excel',
          application_count: 1,
          active_count: 1,
        },
      ],
      recent_applications: [applicationSummary()],
    }
  }
  if (path.startsWith('/dashboard/prehire/overview/work-queue')) {
    return {
      company_code: 'WATHEFNI',
      ok: true,
      as_of: '2026-07-20T00:00:00+00:00',
      total: 1,
      limit: 25,
      items: [
        {
          action_type: 'ready_for_review',
          app_key: 'APP-1',
          candidate_name: 'Hamad Almulla',
          reason: 'Candidate is ready for an HR decision',
          priority: 70,
          age_hours: 12,
          destination: { page: 'candidates', filters: { review_status: 'ready' } },
          authority_source: 'prehire_overview.ready_for_review',
          as_of: '2026-07-20T00:00:00+00:00',
        },
      ],
    }
  }
  if (path === '/dashboard/prehire/applications?limit=50&offset=0&sort=newest') {
    return {
      company_code: 'WATHEFNI',
      total: 1,
      limit: 50,
      offset: 0,
      applications: [applicationSummary()],
    }
  }
  if (path === '/dashboard/prehire/notifications?limit=25') {
    return { company_code: 'WATHEFNI', notifications: [] }
  }
  if (path === '/dashboard/prehire/reports') {
    return {
      company_code: 'WATHEFNI',
      summary: {},
      exports: {},
      breakdowns: {
        applications_by_stage: [],
        candidates_by_role: [],
        followups_by_type: [],
      },
    }
  }
  if (path === '/dashboard/prehire/interviews?limit=25&offset=0&status=upcoming') {
    return {
      company_code: 'WATHEFNI',
      total: 0,
      status_counts: [],
      feedback_counts: [],
      interviews: [],
    }
  }
  if (path === '/dashboard/prehire/assessments?limit=50&offset=0') {
    return {
      company_code: 'WATHEFNI',
      ok: true,
      enabled: true,
      total: 0,
      limit: 50,
      offset: 0,
      status_counts: [],
      attempts: [],
    }
  }
  if (path === '/dashboard/prehire/assessments/config') {
    return { company_code: 'WATHEFNI', enabled: true }
  }
  return null
}

function applicationSummary() {
  return {
    app_key: 'APP-1',
    company_code: 'WATHEFNI',
    phone: '96550000000',
    candidate: { name: 'Hamad Almulla' },
    position: { code: 'ACCOUNTING_EXCEL', title: 'Accounting Excel' },
    status: 'screening',
    current_step: 'screening',
    screening_status: 'pending',
    cv: { received: true, preview_available: true },
  }
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function calledPaths(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.map(([input]) => String(input))
}

function requestHeadersFor(fetchMock: ReturnType<typeof vi.fn>, path: string) {
  const call = fetchMock.mock.calls.find(([input]) => String(input) === path)
  expect(call).toBeDefined()
  return call?.[1]?.headers as Headers
}
