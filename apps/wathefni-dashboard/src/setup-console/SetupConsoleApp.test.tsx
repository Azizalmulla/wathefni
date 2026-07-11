import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ConfirmProvider } from '@/components/ConfirmDialog'

import SetupConsoleApp from './SetupConsoleApp'

function renderConsole() {
  return render(
    <ConfirmProvider>
      <SetupConsoleApp />
    </ConfirmProvider>,
  )
}

describe('setup console', () => {
  test('keeps operator credentials in session storage and loads companies after connect', async () => {
    const fetchMock = mockSetupApi()
    renderConsole()

    const tokenInput = screen.getByLabelText('Operator token')
    expect(tokenInput).toHaveAttribute('type', 'password')
    fireEvent.change(tokenInput, { target: { value: ' operator-secret ' } })
    fireEvent.change(screen.getByLabelText('Authorised operator phone'), {
      target: { value: ' 96590000000 ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Connect securely' }))

    await screen.findByRole('heading', { name: 'Companies' })
    await screen.findByRole('button', { name: /Acme Company/ })

    expect(sessionStorage.getItem('wathefni_setup_operator_token')).toBe('operator-secret')
    expect(sessionStorage.getItem('wathefni_setup_operator_phone')).toBe('96590000000')
    expect(localStorage.getItem('wathefni_setup_operator_token')).toBeNull()

    const listCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes('/dashboard/superadmin/setup/companies?q=&limit=20&offset=0'),
    )
    const headers = listCall?.[1]?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer operator-secret')
    expect(headers.get('X-HR-Phone')).toBe('96590000000')
  })

  test('restores session access and loads the company list immediately', async () => {
    sessionStorage.setItem('wathefni_setup_operator_token', 'saved-session-token')
    sessionStorage.setItem('wathefni_setup_operator_phone', '96591111111')
    const fetchMock = mockSetupApi()

    renderConsole()

    await screen.findByRole('button', { name: /Acme Company/ })
    expect(screen.queryByLabelText('Operator token')).not.toBeInTheDocument()
    const listCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/companies?q='))
    expect((listCall?.[1]?.headers as Headers).get('Authorization')).toBe('Bearer saved-session-token')
  })

  test('groups modules, keeps employee app selectable behind its platform gate, and separates channels', async () => {
    seedSession()
    const fetchMock = mockSetupApi()
    renderConsole()

    fireEvent.click(await screen.findByRole('button', { name: /Acme Company/ }))

    expect(await screen.findByRole('heading', { name: 'Canonical modules' })).toBeInTheDocument()
    expect(screen.getByText('Pre Hiring')).toBeInTheDocument()
    expect(screen.getByText('Workforce')).toBeInTheDocument()

    const employeeRow = screen.getByText('Employee App').closest('label')
    expect(employeeRow).not.toBeNull()
    expect(within(employeeRow!).getByRole('checkbox')).toBeEnabled()
    expect(within(employeeRow!).getByText('Platform unavailable')).toBeInTheDocument()
    expect(within(employeeRow!).getByText('Not enabled')).toBeInTheDocument()

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
  })

  test('creates and selects a company, then saves profile changes', async () => {
    seedSession()
    const fetchMock = mockSetupApi()
    renderConsole()

    await screen.findByRole('button', { name: /Acme Company/ })
    fireEvent.change(screen.getByLabelText('Company code'), { target: { value: 'northstar' } })
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Northstar Co' } })
    fireEvent.change(screen.getByLabelText('Country'), { target: { value: 'kw' } })
    fireEvent.change(screen.getByLabelText('Currency'), { target: { value: 'kwd' } })
    fireEvent.change(screen.getByLabelText('Timezone'), { target: { value: 'Asia/Kuwait' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create and select' }))

    const profileHeading = await screen.findByRole('heading', { name: 'Company profile' })
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

  test('creates a copy-only Owner invite link without claiming delivery', async () => {
    seedSession()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    mockSetupApi()
    renderConsole()

    fireEvent.click(await screen.findByRole('button', { name: /Acme Company/ }))
    await screen.findByRole('heading', { name: 'Owner invite' })
    fireEvent.change(screen.getByLabelText('Owner name'), { target: { value: 'Aisha Owner' } })
    fireEvent.change(screen.getByLabelText('Owner email'), { target: { value: 'aisha@acme.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create owner invite' }))

    expect(await screen.findByText(/invite created — copy and share it securely/i)).toBeInTheDocument()
    expect(screen.getByText(/the console does not send invitations/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy invite link' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('?invite=invite-smoke-token')))
  })
})

function seedSession() {
  sessionStorage.setItem('wathefni_setup_operator_token', 'session-token')
  sessionStorage.setItem('wathefni_setup_operator_phone', '96590000000')
}

function mockSetupApi() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.includes('/dashboard/superadmin/setup/companies?')) {
      return jsonResponse({
        companies: [{ company_code: 'ACME', name: 'Acme Company', ready: false }],
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
        label: 'Pre-hiring',
        suite: 'pre_hiring',
        audience: 'candidates',
        configured: true,
        platform_available: true,
        effective: true,
      },
      {
        key: 'employee_app',
        label: 'Employee App',
        suite: 'workforce',
        audience: 'employees',
        configured: false,
        platform_available: false,
        effective: false,
      },
    ],
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
