import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import App from './App'
import { renderWithProviders } from '@/test/render'

function renderApp() {
  return renderWithProviders(<App />)
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
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Good (morning|afternoon|evening), Aziz/)
    await waitFor(() => {
      expect(calledPaths(fetchMock)).toEqual(
        expect.arrayContaining([
          '/dashboard/prehire/summary',
          '/dashboard/prehire/notifications?limit=25&scope=mine',
          '/dashboard/prehire/overview/work-queue?limit=10&scope=mine',
        ]),
      )
    })
    // Reports are no longer part of the Overview boot path (Wave 1).
    expect(calledPaths(fetchMock)).not.toContain('/dashboard/prehire/reports')
    // Wave 3: Overview must not warm Candidates / Interviews / Assessments / Jobs lists.
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
    const paths = calledPaths(fetchMock)
    expect(paths.some((path) => path.startsWith('/dashboard/prehire/applications'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/dashboard/prehire/interviews'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/dashboard/prehire/assessments'))).toBe(false)
    expect(paths.some((path) => path.includes('/dashboard/prehire/positions'))).toBe(false)

    const summaryHeaders = requestHeadersFor(fetchMock, '/dashboard/prehire/summary')
    expect(summaryHeaders.get('Authorization')).toBe('Bearer saved-token')
    expect(summaryHeaders.get('X-HR-Phone')).toBe('96555511122')
    expect(summaryHeaders.get('X-Company-Code')).toBe('WATHEFNI')
    expect(screen.getByText('Top priorities')).toBeInTheDocument()
    expect(screen.getByText('Suggested next action')).toBeInTheDocument()
    expect(screen.getByText('You’re viewing the latest data.')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('mobile-nav-more'))
    expect(screen.getByRole('menuitem', { name: 'Alerts & Delivery' })).toBeInTheDocument()
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

    expect(await screen.findByRole('heading', { name: 'Sign in to OctoHR' })).toBeInTheDocument()
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

  test('hides Interviews nav for bare pre_hiring and remaps direct URL (EN + AR mobile chip)', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'saved-token')
    localStorage.setItem('wathefni_hr_phone', '96555511122')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    localStorage.setItem('wathefni_recruiting_locale', 'ar')
    window.history.replaceState({}, '', '/dashboard?page=interviews')

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

    await screen.findByText(/ما يحتاج انتباهك اليوم|What needs attention today/)
    expect(screen.queryByRole('button', { name: 'Interviews' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'المقابلات' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Assessments' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'التقييمات' })).not.toBeInTheDocument()
    // Direct URL ?page=interviews remaps to an allowed page once authority settles.
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).not.toHaveTextContent(/Interviews|المقابلات/)
    })

    fireEvent.click(screen.getByTestId('mobile-nav-more'))
    expect(screen.queryByRole('menuitem', { name: 'التقييمات' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'المقابلات' })).not.toBeInTheDocument()
  })

  test('Wave1: Overview My/Company scope switch does not refresh summary or reports', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'saved-token')
    localStorage.setItem('wathefni_hr_phone', '96555511122')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      const payload = responseFor(path)
      if (!payload) return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
      return jsonResponse(payload)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderApp()
    await screen.findByText('What needs attention today')
    const before = calledPaths(fetchMock).filter((path) =>
      path.startsWith('/dashboard/prehire/summary')
      || path.startsWith('/dashboard/prehire/reports')
      || path.includes('work-queue')
      || path.includes('notifications'),
    )
    const summaryBefore = before.filter((path) => path.startsWith('/dashboard/prehire/summary')).length
    const reportsBefore = before.filter((path) => path.startsWith('/dashboard/prehire/reports')).length

    fireEvent.click(screen.getByRole('button', { name: 'Company work' }))
    await waitFor(() => {
      expect(calledPaths(fetchMock)).toEqual(
        expect.arrayContaining([
          '/dashboard/prehire/overview/work-queue?limit=10&scope=company',
        ]),
      )
    })

    const after = calledPaths(fetchMock)
    expect(after.filter((path) => path.startsWith('/dashboard/prehire/summary')).length).toBe(summaryBefore)
    expect(after.filter((path) => path.startsWith('/dashboard/prehire/reports')).length).toBe(reportsBefore)

    fireEvent.click(screen.getByRole('button', { name: 'My work' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'My work' })).toHaveClass('bg-[#23211d]')
    })
    expect(screen.getByRole('button', { name: 'My work' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Company work' })).not.toBeDisabled()

    // Wave 2: top-level work-queue View all removed (no cross-module queue page).
    // Roles "View all" may still exist — only assert the follow-up miswire is gone.
    const workHeading = screen.getAllByRole('heading', { name: /My work|Company work/i })[0]
    const workSection = workHeading.closest('section')
    expect(workSection).toBeTruthy()
    const viewAllInWork = within(workSection as HTMLElement).queryAllByRole('button', { name: /View all|عرض الكل/i })
    expect(viewAllInWork).toHaveLength(0)
  })

  test('Wave3: Candidates page issues a single bounded applications page', async () => {
    localStorage.setItem('wathefni_dashboard_token', 'saved-token')
    localStorage.setItem('wathefni_hr_phone', '96555511122')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      const payload = responseFor(path)
      if (!payload) return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
      return jsonResponse(payload)
    })
    vi.stubGlobal('fetch', fetchMock)

    renderApp()
    await screen.findByText('What needs attention today')
    fireEvent.click(screen.getByRole('button', { name: 'Candidates' }))
    await waitFor(() => {
      expect(calledPaths(fetchMock).some((path) => path.startsWith('/dashboard/prehire/applications'))).toBe(true)
    })
    const appCalls = calledPaths(fetchMock).filter((path) => path.startsWith('/dashboard/prehire/applications'))
    expect(appCalls.length).toBeLessThanOrEqual(3)
    expect(appCalls.some((path) => path.includes('limit=100') && path.includes('offset=0'))).toBe(true)
    expect(appCalls.some((path) => path.includes('offset=100'))).toBe(false)
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

    // Compliance-only bootstrap lands on Compliance; Employees stays offerable via admin soft gate.
    expect((await screen.findAllByRole('heading', { name: 'Compliance' })).length).toBeGreaterThan(0)
    expect(screen.getByTestId('mobile-active-route-chip')).toHaveTextContent('Compliance')
    fireEvent.click(screen.getByTestId('mobile-nav-more'))
    expect(screen.getByRole('menuitem', { name: 'Employees' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Compliance' })).toBeInTheDocument()
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
      access: {
        role: 'owner',
        permissions: ['prehire.read', 'jobs.read', 'candidates.read', 'candidate.manage', 'interview.manage', 'assessment.manage', 'report.export', 'users.manage', 'settings.manage', 'audit.read'],
        user: { name: 'Aziz Almulla', email: 'aziz@example.com', company_code: 'WATHEFNI', role: 'owner', status: 'active' },
      },
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
      limit: 10,
      can_view_company_work: true,
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
  if (path.startsWith('/dashboard/prehire/applications?')) {
    return {
      company_code: 'WATHEFNI',
      total: 1,
      limit: 50,
      offset: 0,
      view: 'all',
      applications: [applicationSummary()],
    }
  }
  if (path === '/dashboard/prehire/candidates/feature') {
    return {
      ok: true,
      flag: 'WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL',
      master_enabled: true,
      allowed_tenants: ['WATHEFNI'],
      company_code: 'WATHEFNI',
      enabled_for_company: true,
    }
  }
  if (path === '/dashboard/prehire/talent-pool/classification/feature' || path.includes('classification/feature')) {
    return {
      ok: true,
      enabled_for_company: false,
      ui_enabled: false,
    }
  }
  if (path.startsWith('/dashboard/prehire/positions')) {
    return {
      company_code: 'WATHEFNI',
      positions: [
        {
          position_code: 'ACCOUNTING_EXCEL',
          position_title: 'Accounting Excel',
          application_count: 1,
          active_count: 1,
        },
      ],
      total: 1,
      limit: 200,
      offset: 0,
    }
  }
  if (path === '/dashboard/prehire/candidates/saved-views') {
    return { company_code: 'WATHEFNI', views: [] }
  }
  if (path.startsWith('/dashboard/prehire/notifications?')) {
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
