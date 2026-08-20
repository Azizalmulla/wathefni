import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import App from '@/App'
import {
  COMPOSITION_MATRIX,
  ROLE_PERMISSIONS_FIXTURE,
  authorityForMatrixRow,
  resolveWorkspaceAuthority,
} from '@/lib/workspaceCapability'
import { HR_WEB_SIDEBAR_COVERAGE_GAPS } from '@/lib/hrWebSurfaceRegistry'
import { renderWithProviders } from '@/test/render'
import type { ModuleWorkspaceCatalog } from '@/lib/moduleWorkspace'

const catalog: ModuleWorkspaceCatalog[] = [
  { key: 'pre_hiring', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'assessments', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'interviews', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'talent', suite: 'post_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'learning', suite: 'post_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'leave', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'attendance', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'onboarding', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'payroll', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
]

const VIEWPORTS = [
  { id: 'desktop', width: 1440, height: 900 },
  { id: 'laptop', width: 1280, height: 800 },
  { id: 'smaller', width: 768, height: 1024 },
] as const

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function ownerPermissions() {
  return [
    ...ROLE_PERMISSIONS_FIXTURE.owner,
    'talent.read',
    'learning.read',
    'benefits.read',
    'er.read',
    'job_architecture.read',
    'preboarding.read',
    'probation.read',
  ]
}

function bootstrap(options: { modules?: string[]; permissions?: string[]; role?: string } = {}) {
  const enabled_modules = options.modules || ['pre_hiring', 'talent', 'learning', 'leave']
  const permissions = options.permissions || ownerPermissions()
  const role = options.role || 'owner'
  return {
    company_code: 'WATHEFNI',
    enabled_modules,
    access: {
      role,
      permissions,
      user: { name: 'Aziz Almulla', email: 'aziz@example.com', company_code: 'WATHEFNI', role, status: 'active' },
    },
    module_catalog: catalog,
    action_inbox: { offerable: true },
  }
}

function responseFor(path: string, options: { modules?: string[]; permissions?: string[]; role?: string } = {}) {
  const boot = bootstrap(options)
  if (path === '/dashboard/bootstrap' || path.endsWith('/dashboard/bootstrap')) return boot
  if (path === '/dashboard/prehire/summary') {
    return {
      ...boot,
      module: 'pre_hiring',
      features: { assessments_enabled: (options.modules || []).includes('assessments') },
      totals: { candidates: 0, applications: 0, active_applications: 0, hired_applications: 0 },
      action_counts: { ready_for_review: 0, assessment_pending: 0, follow_up_needed: 0 },
      next_action: null,
      role_priority: null,
      status_counts: [],
      positions: [],
      recent_applications: [],
    }
  }
  if (path.startsWith('/dashboard/prehire/overview/work-queue')) {
    return { company_code: 'WATHEFNI', ok: true, total: 0, limit: 10, can_view_company_work: true, items: [] }
  }
  if (path.startsWith('/dashboard/prehire/notifications')) {
    return { company_code: 'WATHEFNI', notifications: [], enabled_modules: boot.enabled_modules }
  }
  return null
}

function stubFetch(options: { modules?: string[]; permissions?: string[]; role?: string } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input)
    const payload = responseFor(path, options)
    if (!payload) return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
    return jsonResponse(payload)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function signIn() {
  localStorage.setItem('wathefni_dashboard_token', 'saved-token')
  localStorage.setItem('wathefni_hr_phone', '96555511122')
  localStorage.setItem('wathefni_company_code', 'WATHEFNI')
}

function useDesktopNav() {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 })
  window.matchMedia = ((query: string) => ({
    matches: String(query).includes('min-width: 1024px'),
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
}

afterEach(() => {
  window.history.replaceState({}, '', '/dashboard')
  vi.unstubAllGlobals()
})

describe('HR Web runtime surface explorer (DOM/router/API — no screenshots)', () => {
  test('owner / recruiter / viewer authority does not leak disabled modules or manage surfaces', () => {
    const owner = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'talent', 'leave', 'payroll'],
      access: { role: 'owner', permissions: ownerPermissions() },
      catalog,
      actionInboxOfferable: true,
    })
    const recruiter = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'talent', 'leave', 'payroll'],
      access: { role: 'recruiter', permissions: ROLE_PERMISSIONS_FIXTURE.recruiter },
      catalog,
      actionInboxOfferable: false,
    })
    const viewer = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'talent', 'leave', 'payroll'],
      access: { role: 'viewer', permissions: ['candidates.read', 'jobs.read', 'leave.read'] },
      catalog,
      actionInboxOfferable: false,
    })

    expect(owner.pageAllowed('talent')).toBe(true)
    expect(owner.pageAllowed('leave')).toBe(true)
    expect(owner.pageAllowed('payroll')).toBe(true)
    expect(owner.pageAllowed('settings')).toBe(true)

    expect(recruiter.pageAllowed('talent')).toBe(false)
    expect(recruiter.pageAllowed('payroll')).toBe(false)
    expect(recruiter.pageAllowed('settings')).toBe(false)
    expect(recruiter.pageAllowed('jobs')).toBe(true)

    expect(viewer.pageAllowed('payroll')).toBe(false)
    expect(viewer.pageAllowed('settings')).toBe(false)
    expect(viewer.pageAllowed('talent')).toBe(false)
    expect(viewer.offerable('nav.leave')).toBe(true)
  })

  test('composition matrix still fails closed for module-off destinations', () => {
    for (const row of COMPOSITION_MATRIX) {
      const authority = authorityForMatrixRow(row, catalog)
      for (const id of row.expectNavExcludes) {
        expect(authority.pageAllowed(id), `${row.id} leaked ${id}`).toBe(false)
      }
    }
  })

  test('direct deep link into a disabled module remaps away from that page', async () => {
    signIn()
    window.history.replaceState({}, '', '/dashboard?page=interviews')
    stubFetch({ modules: ['pre_hiring'] })
    renderWithProviders(<App />)
    await screen.findByText(/What needs attention today|ما يحتاج انتباهك اليوم/)
    expect(screen.queryByRole('button', { name: 'Interviews' })).not.toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).not.toHaveTextContent(/Interviews|المقابلات/)
    })
  })

  test('entitled talent deep link opens Talent and lists it in the sidebar', async () => {
    signIn()
    useDesktopNav()
    window.history.replaceState({}, '', '/dashboard?page=talent')
    stubFetch({ modules: ['pre_hiring', 'talent'] })
    renderWithProviders(<App />)
    await screen.findByTestId('app-shell')
    await waitFor(() => {
      expect(screen.getByTestId('app-sidebar')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Talent' })).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/^Talent$|^المواهب$/)
    })
    const authority = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'talent'],
      access: { role: 'owner', permissions: ownerPermissions() },
      catalog,
    })
    expect(authority.pageAllowed('talent')).toBe(true)
    expect(HR_WEB_SIDEBAR_COVERAGE_GAPS).not.toContain('talent')
  })

  test('talent module off remaps an entitled-looking ?page=talent away from Talent', async () => {
    signIn()
    useDesktopNav()
    window.history.replaceState({}, '', '/dashboard?page=talent')
    stubFetch({ modules: ['pre_hiring'] })
    renderWithProviders(<App />)
    await screen.findByText(/What needs attention today|ما يحتاج انتباهك اليوم/)
    expect(screen.queryByRole('button', { name: 'Talent' })).not.toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).not.toHaveTextContent(/^Talent$|^المواهب$/)
    })
  })

  test('EN/AR switches document direction on the signed-in shell', async () => {
    signIn()
    localStorage.setItem('wathefni_recruiting_locale', 'ar')
    stubFetch({ modules: ['pre_hiring'] })
    renderWithProviders(<App />)
    const shell = await screen.findByTestId('app-shell')
    await waitFor(() => {
      expect(document.documentElement.dir).toBe('rtl')
      expect(document.documentElement.lang).toBe('ar')
    })
    expect(shell).toBeInTheDocument()
  })

  test('shell remains present across desktop / laptop / smaller widths', async () => {
    signIn()
    stubFetch({ modules: ['pre_hiring'] })
    for (const vp of VIEWPORTS) {
      window.history.replaceState({}, '', '/dashboard?page=overview')
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: vp.width })
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: vp.height })
      const view = renderWithProviders(<App />)
      await screen.findByTestId('app-shell')
      expect(screen.getByTestId('app-sidebar')).toBeInTheDocument()
      expect(screen.getByTestId('app-main')).toBeInTheDocument()
      view.unmount()
    }
  })

  test('browser back restores the previous page from history after a sidebar navigation', async () => {
    signIn()
    window.history.replaceState({}, '', '/dashboard?page=overview')
    stubFetch({ modules: ['pre_hiring'] })
    renderWithProviders(<App />)
    await screen.findByText(/What needs attention today/)
    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Jobs|الوظائف/)
    })
    window.history.pushState({}, '', '/dashboard?page=overview')
    window.dispatchEvent(new PopStateEvent('popstate'))
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).not.toHaveTextContent(/Jobs|الوظائف/)
    })
  })
})
