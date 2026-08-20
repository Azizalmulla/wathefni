import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ConfirmProvider } from '@/components/ConfirmDialog'

import SetupConsoleApp from './SetupConsoleApp'

function renderConsole() {
  return render(
    <ConfirmProvider>
      <SetupConsoleApp />
    </ConfirmProvider>,
  )
}

/** Selecting a company opens Modules & Access; classic cards stay under Classic setup. */
async function selectCompany(companyName = /Acme Company/) {
  fireEvent.click(await screen.findByRole('button', { name: companyName }, { timeout: 8000 }))
}

async function selectCompanyClassicSetup(companyName = /Acme Company/) {
  await selectCompany(companyName)
  fireEvent.click(await screen.findByRole('button', { name: 'Classic setup' }))
}

function authHeader(init?: RequestInit) {
  const headers = init?.headers
  if (!headers) return null
  if (typeof (headers as Headers).get === 'function') return (headers as Headers).get('Authorization')
  if (Array.isArray(headers)) {
    const hit = headers.find(([key]) => key.toLowerCase() === 'authorization')
    return hit?.[1] ?? null
  }
  const record = headers as Record<string, string>
  return record.Authorization || record.authorization || null
}

describe('setup console', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.unstubAllGlobals()
    window.history.replaceState({}, '', '/')
  })
  test('exchanges operator secret for a persistent session and loads companies', async () => {
    const fetchMock = mockSetupApi()
    renderConsole()

    const tokenInput = await screen.findByLabelText('Operator token')
    expect(tokenInput).toHaveAttribute('type', 'password')
    expect(screen.getByText(/This is not the HR dashboard/i)).toBeInTheDocument()
    expect(screen.getByText(/dashboard owner session is rejected/i)).toBeInTheDocument()
    fireEvent.change(tokenInput, { target: { value: ' operator-secret ' } })
    fireEvent.change(screen.getByLabelText('Authorised operator phone'), {
      target: { value: ' 96590000000 ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Connect securely' }))

    await screen.findByRole('heading', { name: 'Companies' })
    await screen.findByRole('button', { name: /Acme Company/ })

    expect(localStorage.getItem('wathefni_setup_access_token')).toBe('access-session-token')
    expect(localStorage.getItem('wathefni_setup_refresh_token')).toBe('refresh-session-token')
    expect(localStorage.getItem('wathefni_setup_operator_phone')).toBe('96590000000')
    expect(sessionStorage.getItem('wathefni_setup_operator_token')).toBeNull()

    const loginCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes('/dashboard/superadmin/setup/auth/login'),
    )
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({
      operator_token: 'operator-secret',
      phone: '96590000000',
    })

    const listCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes('/dashboard/superadmin/setup/companies?q=&limit=20&offset=0'),
    )
    const headers = listCall?.[1]?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer access-session-token')
    expect(headers.get('X-HR-Phone')).toBe('96590000000')
  })

  test('restores persisted session access and loads the company list immediately', async () => {
    localStorage.setItem('wathefni_setup_access_token', 'saved-access-token')
    localStorage.setItem('wathefni_setup_refresh_token', 'saved-refresh-token')
    localStorage.setItem('wathefni_setup_operator_phone', '96591111111')
    const fetchMock = mockSetupApi()

    renderConsole()

    await screen.findByRole('button', { name: /Acme Company/ }, { timeout: 8000 })
    expect(screen.queryByLabelText('Operator token')).not.toBeInTheDocument()
    const sessionCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/auth/session'))
    expect(authHeader(sessionCall?.[1])).toBe('Bearer saved-access-token')
    const listCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/companies?q='))
    expect(authHeader(listCall?.[1])).toBe('Bearer saved-access-token')
  })

  test('searches companies as you type without requiring the search button', async () => {
    seedSession()
    const fetchMock = mockSetupApi()
    renderConsole()
    await screen.findByRole('heading', { name: 'Companies' }, { timeout: 8000 })
    fireEvent.change(screen.getByPlaceholderText('Name or company code'), { target: { value: 'WATHEFNI' } })
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) => String(input).includes('q=WATHEFNI')),
      ).toBe(true)
    })
  })

  test(
    'groups modules, keeps employee app selectable behind its platform gate, and separates channels',
    async () => {
    seedSession()
    const fetchMock = mockSetupApi()
    renderConsole()

    await screen.findByRole('heading', { name: 'Companies' }, { timeout: 8000 })
    await selectCompany()

    expect(await screen.findByRole('heading', { name: 'Modules & Access' })).toBeInTheDocument()
    expect(window.location.search).toContain('company=ACME')
    expect(screen.getByText('Pre Hire')).toBeInTheDocument()
    expect(screen.getByText('Post Hire')).toBeInTheDocument()
    expect(screen.getByText(/Selected company/i)).toBeInTheDocument()

    const employeeRow = screen.getByText('Employee App').closest('label')
    expect(employeeRow).not.toBeNull()
    expect(within(employeeRow!).getByRole('checkbox')).toBeEnabled()
    expect(employeeRow!.querySelector('[data-effective-state="unavailable_deployment"]')).not.toBeNull()

    const performanceRow = screen.getByText('Performance').closest('label')
    expect(performanceRow).not.toBeNull()
    expect(within(performanceRow!).getByRole('checkbox')).toBeDisabled()
    expect(within(performanceRow!).getByText(/Blocked by a deployment allowlist/i)).toBeInTheDocument()

    expect(screen.getByRole('button', { name: /Apply Hiring Assessment Suite/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Classic setup' }))
    expect(screen.getByRole('heading', { name: 'Company WhatsApp Business account' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'HR-user WhatsApp identity' })).toBeInTheDocument()
    expect(screen.getByText(/shared provider account and sender/i)).toBeInTheDocument()
    expect(screen.getByText(/individual HR or Owner phone/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Mark policy reviewed' }))
    await waitFor(() => {
      const reviewCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/ACME/settings') && init?.method === 'PATCH',
      )
      expect(JSON.parse(String(reviewCall?.[1]?.body))).toEqual({ channel_policy_reviewed: true })
    })
  },
  20000,
  )

  test(
    'auto-includes hard dependencies, keeps soft recommendations optional, and previews app surfaces',
    async () => {
    seedSession()
    const fetchMock = mockSetupApi()
    renderConsole()

    await screen.findByRole('heading', { name: 'Companies' }, { timeout: 8000 })
    await selectCompany()
    await screen.findByRole('heading', { name: 'Modules & Access' })

    const preHiringRow = screen.getByText('Pre-Hiring').closest('label')
    fireEvent.click(within(preHiringRow!).getByRole('checkbox'))
    expect(within(preHiringRow!).getByRole('checkbox')).not.toBeChecked()

    const assessmentsRow = screen.getByText('Assessments').closest('label')
    fireEvent.click(within(assessmentsRow!).getByRole('checkbox'))
    expect(await screen.findByText(/Assessments requires Pre-Hiring, so Pre-Hiring was included/)).toBeInTheDocument()
    expect(within(preHiringRow!).getByRole('checkbox')).toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: /Apply Workforce Operations/ }))
    const shiftsRow = screen.getByText('Shifts').closest('label')
    expect(within(shiftsRow!).getByRole('checkbox')).toBeChecked()
    fireEvent.click(within(shiftsRow!).getByRole('checkbox'))
    expect(within(shiftsRow!).getByRole('checkbox')).not.toBeChecked()
    expect(screen.getByText(/Recommended with selection/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\+ Shifts/ })).toBeInTheDocument()

    const payrollRow = screen.getAllByText('Payroll').find((node) => node.closest('label'))?.closest('label')
    expect(payrollRow).not.toBeNull()
    expect(within(payrollRow!).getByRole('checkbox')).toBeChecked()

    const employeeRow = screen.getByText('Employee App').closest('label')
    fireEvent.click(within(employeeRow!).getByRole('checkbox'))
    expect(within(employeeRow!).getByText('Configured, awaiting platform activation')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Employee App surface preview' })).toBeInTheDocument()
    expect(screen.getByText(/Surfaces below appear when WATHEFNI_EMPLOYEE_APP is ON/)).toBeInTheDocument()
    expect(screen.getByText(/Attendance status/)).toBeInTheDocument()
    expect(screen.queryByText(/Payroll/i, { selector: 'li' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save modules' }))
    await waitFor(() => {
      const modulesCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/ACME/modules') && init?.method === 'PATCH',
      )
      const body = JSON.parse(String(modulesCall?.[1]?.body))
      expect(body.modules).toEqual(expect.arrayContaining(['assessments', 'pre_hiring', 'payroll', 'attendance', 'leave', 'employee_app']))
      expect(body.modules).not.toContain('shifts')
    })
  },
  20000,
  )

  test('creates and selects a company, then saves profile changes', async () => {
    seedSession()
    const fetchMock = mockSetupApi()
    renderConsole()

    await screen.findByRole('button', { name: /Acme Company/ }, { timeout: 8000 })
    fireEvent.change(screen.getByLabelText('Company code'), { target: { value: 'northstar' } })
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Northstar Co' } })
    fireEvent.change(screen.getByLabelText('Country'), { target: { value: 'kw' } })
    fireEvent.change(screen.getByLabelText('Currency'), { target: { value: 'kwd' } })
    fireEvent.change(screen.getByLabelText('Timezone'), { target: { value: 'Asia/Kuwait' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create and select' }))

    const createCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input) === '/dashboard/superadmin/setup/companies' && init?.method === 'POST',
    )
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      company_code: 'NORTHSTAR',
      name: 'Northstar Co',
      country: 'KW',
      timezone: 'Asia/Kuwait',
      currency: 'KWD',
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Classic setup' }))
    const profileHeading = await screen.findByRole('heading', { name: 'Company profile' })
    const profileCard = profileHeading.closest('section')
    expect(profileCard).not.toBeNull()
    fireEvent.change(within(profileCard!).getByLabelText('Display name'), {
      target: { value: 'Northstar Group' },
    })
    fireEvent.click(within(profileCard!).getByRole('button', { name: 'Save profile' }))

    await waitFor(() => {
      const profileCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/NORTHSTAR/profile') && init?.method === 'PATCH',
      )
      expect(profileCall).toBeDefined()
      expect(JSON.parse(String(profileCall?.[1]?.body))).toMatchObject({ name: 'Northstar Group' })
    })
  })

  test(
    'creates a copy-only Owner invite link without claiming delivery',
    async () => {
    seedSession()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    mockSetupApi()
    renderConsole()

    await screen.findByRole('heading', { name: 'Companies' }, { timeout: 8000 })
    await selectCompanyClassicSetup()
    await screen.findByRole('heading', { name: 'First Company Admin' })
    fireEvent.change(screen.getByLabelText('Owner name'), { target: { value: 'Aisha Owner' } })
    fireEvent.change(screen.getByLabelText('Owner email'), { target: { value: 'aisha@acme.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create owner invite' }))

    expect(await screen.findByText(/invite created — copy and share it securely/i)).toBeInTheDocument()
    expect(screen.getByText(/day-to-day invites and role changes stay in settings/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy invite link' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('?invite=invite-smoke-token')))
  },
  20000,
  )

  test('shows lifecycle state and requires a reason to disable', async () => {
    seedSession()
    const fetchMock = mockSetupApi()
    renderConsole()

    await selectCompanyClassicSetup()
    const lifecycleHeading = await screen.findByRole('heading', { name: 'Company lifecycle' })
    const lifecycleCard = lifecycleHeading.closest('section')
    expect(lifecycleCard).not.toBeNull()
    expect(within(lifecycleCard!).getAllByText('Active').length).toBeGreaterThan(0)
    expect(within(lifecycleCard!).getByRole('button', { name: 'Disable' })).toBeEnabled()
    expect(within(lifecycleCard!).getByRole('button', { name: 'Archive' })).toBeEnabled()

    fireEvent.click(within(lifecycleCard!).getByRole('button', { name: 'Disable' }))
    expect(screen.queryByText('Disable ACME?')).not.toBeInTheDocument()

    fireEvent.change(within(lifecycleCard!).getByLabelText('Reason for lifecycle change'), {
      target: { value: 'Staging dress rehearsal disable' },
    })
    fireEvent.click(within(lifecycleCard!).getByRole('button', { name: 'Disable' }))
    expect(await screen.findByText('Disable ACME?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => {
      const lifecycleCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/ACME/lifecycle') && init?.method === 'PATCH',
      )
      expect(JSON.parse(String(lifecycleCall?.[1]?.body))).toEqual({
        status: 'disabled',
        reason: 'Staging dress rehearsal disable',
      })
    })
  })
})

function seedSession() {
  localStorage.setItem('wathefni_setup_access_token', 'session-token')
  localStorage.setItem('wathefni_setup_refresh_token', 'refresh-token')
  localStorage.setItem('wathefni_setup_operator_phone', '96590000000')
}

function mockSetupApi() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.includes('/dashboard/superadmin/setup/auth/login') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body || '{}')) as { phone?: string }
      return jsonResponse({
        ok: true,
        access_token: 'access-session-token',
        refresh_token: 'refresh-session-token',
        phone: String(body.phone || '').trim(),
        expires_at: new Date(Date.now() + 8 * 3600_000).toISOString(),
        refresh_expires_at: new Date(Date.now() + 30 * 86400_000).toISOString(),
        access_ttl_seconds: 28800,
        refresh_ttl_seconds: 2592000,
      })
    }
    if (path.includes('/dashboard/superadmin/setup/auth/session')) {
      return jsonResponse({ ok: true, phone: '96590000000', auth_source: 'setup_session' })
    }
    if (path.includes('/dashboard/superadmin/setup/auth/refresh') && init?.method === 'POST') {
      return jsonResponse({
        ok: true,
        access_token: 'rotated-access-token',
        refresh_token: 'rotated-refresh-token',
        phone: '96590000000',
        expires_at: new Date(Date.now() + 8 * 3600_000).toISOString(),
        refresh_expires_at: new Date(Date.now() + 30 * 86400_000).toISOString(),
      })
    }
    if (path.includes('/dashboard/superadmin/setup/auth/logout') && init?.method === 'POST') {
      return jsonResponse({ ok: true, revoked: true })
    }
    if (path.includes('/launch-readiness')) {
      return jsonResponse({
        ok: true,
        company_code: 'ACME',
        overall: 'ready',
        items: [],
      })
    }
    if (path.includes('/dashboard/superadmin/setup/companies?')) {
      return jsonResponse({
        companies: [
          {
            company_code: 'ACME',
            name: 'Acme Company',
            ready: false,
            status: 'active',
            lifecycle: { status: 'active' },
          },
        ],
        total_count: 1,
        limit: 20,
        offset: 0,
      })
    }
    if (path === '/dashboard/superadmin/setup/companies' && init?.method === 'POST') {
      return jsonResponse({ created: true })
    }
    if (path.endsWith('/owner') && init?.method === 'POST') {
      return jsonResponse({ invite_token: 'invite-smoke-token' })
    }
    if (path.endsWith('/profile') && init?.method === 'PATCH') return jsonResponse({ ok: true })
    if (path.endsWith('/modules') && init?.method === 'PATCH') return jsonResponse({ ok: true, modules: [] })
    if (path.endsWith('/lifecycle') && init?.method === 'PATCH') {
      return jsonResponse({ ok: true, status: 'disabled', readiness: { ...companyDetail(path).readiness, status: 'disabled', ready: false } })
    }
    if (path.includes('/dashboard/superadmin/setup/companies/')) return jsonResponse(companyDetail(path))
    return jsonResponse({ detail: `Unexpected request: ${path}` }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function companyDetail(path: string) {
  const companyCode = path.includes('NORTHSTAR') ? 'NORTHSTAR' : 'ACME'
  return {
    readiness: {
      company_code: companyCode,
      name: companyCode === 'NORTHSTAR' ? 'Northstar Co' : 'Acme Company',
      country: 'KW',
      timezone: 'Asia/Kuwait',
      currency: 'KWD',
      modules: ['pre_hiring'],
      status: 'active',
      lifecycle: { status: 'active', reason: null },
      steps: [
        { key: 'company', label: 'Company created', done: true },
        { key: 'modules', label: 'Modules selected', done: true },
        { key: 'owner', label: 'Owner invited', done: false },
      ],
      ready: false,
    },
    available_modules: [
      {
        key: 'pre_hiring',
        label: 'Pre-Hiring',
        suite: 'pre_hire',
        audience: 'candidate',
        configured: true,
        platform_available: true,
        effective: true,
      },
      {
        key: 'assessments',
        label: 'Assessments',
        suite: 'pre_hire',
        audience: 'candidate',
        configured: false,
        platform_available: true,
        effective: false,
        depends_on: ['pre_hiring'],
        recommended_with: ['video_interviews'],
        recommendation_copy: 'Requires Pre-Hiring. Works best with Video Interviews.',
      },
      {
        key: 'video_interviews',
        label: 'Video Interviews',
        suite: 'pre_hire',
        audience: 'candidate',
        configured: false,
        platform_available: true,
        effective: false,
        depends_on: ['pre_hiring'],
      },
      {
        key: 'attendance',
        label: 'Attendance',
        suite: 'post_hire',
        audience: 'employee',
        configured: false,
        platform_available: true,
        effective: false,
        recommended_with: ['shifts'],
        recommendation_copy: 'Works alone. Recommend Shifts when the company uses scheduled shift work.',
        app_surface_key: 'attendance',
        app_surface_label: 'Attendance status',
      },
      {
        key: 'shifts',
        label: 'Shifts',
        suite: 'post_hire',
        audience: 'employee',
        configured: false,
        platform_available: true,
        effective: false,
        app_surface_key: 'shifts',
        app_surface_label: 'Today and upcoming shifts',
      },
      {
        key: 'leave',
        label: 'Leave',
        suite: 'post_hire',
        audience: 'employee',
        configured: false,
        platform_available: true,
        effective: false,
        app_surface_key: 'leave',
        app_surface_label: 'Leave requests and status',
      },
      {
        key: 'payroll',
        label: 'Payroll',
        suite: 'post_hire',
        audience: 'employee',
        configured: false,
        platform_available: true,
        effective: false,
        recommended_with: ['attendance', 'leave'],
        recommendation_copy: 'Works alone. Recommend Attendance and Leave. HR-dashboard-first for V1.',
      },
      {
        key: 'employee_app',
        label: 'Employee App',
        suite: 'post_hire',
        audience: 'employee',
        configured: false,
        platform_available: false,
        effective: false,
        can_enable: false,
        can_select: true,
        usable: false,
        stored_enabled: false,
        app_surface_key: 'inbox',
        app_surface_label: 'In-app inbox and push',
        effective_state: {
          effective_state: 'unavailable_deployment',
          usable: false,
          stored_enabled: false,
          can_enable: false,
          label_en: 'Unavailable in this deployment',
          deployment: {
            reason_code: 'unavailable_deployment',
            message_en: 'Unavailable in this deployment.',
          },
        },
      },
      {
        key: 'performance',
        label: 'Performance',
        suite: 'post_hire',
        audience: 'employee',
        configured: false,
        platform_available: true,
        effective: false,
        can_enable: false,
        can_select: false,
        usable: false,
        stored_enabled: false,
        effective_state: {
          effective_state: 'unavailable_deployment',
          usable: false,
          stored_enabled: false,
          can_enable: false,
          label_en: 'Unavailable in this deployment',
          deployment: {
            reason_code: 'pilot_allowlist',
            message_en: 'Blocked by a deployment allowlist or pilot gate.',
          },
          blockers: [
            {
              code: 'pilot_allowlist',
              message_en: 'Blocked by a deployment allowlist or pilot gate.',
            },
          ],
        },
      },
    ],
    module_bundles: [
      {
        id: 'hiring_assessment_suite',
        label: 'Hiring Assessment Suite',
        description: 'Full candidate evaluation with assessments and video interviews.',
        modules: ['pre_hiring', 'assessments', 'video_interviews'],
      },
      {
        id: 'workforce_operations',
        label: 'Workforce Operations',
        description: 'Suggested package for shift-based operations.',
        modules: ['shifts', 'attendance', 'leave', 'payroll'],
      },
    ],
    module_guidance: {
      bundles: [],
      app_surfaces: [],
      missing_dependencies: [],
      expanded_modules: ['pre_hiring'],
    },
    users: [
      {
        user_id: 'owner-1',
        name: 'Mona Owner',
        email: 'owner@acme.test',
        role: 'owner',
        status: 'active',
      },
    ],
    channel_policy: {
      reviewed: false,
      company_channel_accounts_enabled: true,
      pre_hiring: { status: 'active', capability: 'recruitment' },
      post_hiring: { status: 'disabled', capability: 'employee_service' },
      hr_admin: { status: 'active', capability: 'administration' },
    },
    channel_account: {
      provider: 'octopus',
      provider_account_id: 'WABA-123',
      sender_phone: '96550000000',
      audiences: ['candidate'],
      status: 'active',
      verified: true,
    },
  }
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
