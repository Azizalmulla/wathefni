import { fireEvent, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test, vi } from 'vitest'

import { PlatformIntegrationsPanel } from '@/components/PlatformIntegrationsPanel'
import { SettingsPage } from '@/pages/SettingsPage'
import { renderWithProviders } from '@/test/render'
import type { DashboardAccess, DashboardUserAccess } from '@/types'

const access = {
  token: 'test-token',
  companyCode: 'WATHEFNI',
  baseUrl: 'http://localhost',
  hrPhone: '+96500000000',
} as DashboardAccess

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function userAccess(permissions: string[], role: string): DashboardUserAccess {
  return {
    role,
    role_label: role,
    permissions,
    user: {
      user_id: 'u1',
      name: role === 'owner' ? 'Owner' : 'HR Admin',
      email: `${role}@example.com`,
      role,
      status: 'active',
      company_code: 'WATHEFNI',
    },
  } as DashboardUserAccess
}

const settingsBase = {
  access,
  busy: false,
  createdInviteLink: '',
  inviteEmail: '',
  inviteName: '',
  inviteRole: 'hr_manager',
  linkPhone: '',
  onInvite: vi.fn(),
  onClearInviteLink: vi.fn(),
  onCopyInviteLink: vi.fn(),
  onLinkWhatsApp: vi.fn(),
  onLogout: vi.fn(),
  onSave: vi.fn(),
  onUpdateUser: vi.fn(),
  prehireEnabled: false,
  setAccess: vi.fn(),
  setInviteEmail: vi.fn(),
  setInviteName: vi.fn(),
  setInviteRole: vi.fn(),
  setLinkPhone: vi.fn(),
  team: { company_code: 'WATHEFNI', users: [], invites: [] },
}

describe('Settings Platform Integrations authority', () => {
  test('source dual-gates Platform Integrations on settings.manage and calendar.sync', () => {
    const src = readFileSync(resolve(__dirname, '../pages/SettingsPage.tsx'), 'utf8')
    expect(src).toContain('PlatformIntegrationsPanel')
    expect(src).toContain("hasDashboardPermission(userAccess, 'settings.manage')")
    expect(src).toContain("hasDashboardPermission(userAccess, 'calendar.sync')")
    expect(src).toContain('canManagePlatformIntegrations')
    expect(src).toContain('variant="integrations"')
    expect(src).toContain('variant="advanced"')
  })

  test('owner with settings.manage + calendar.sync sees Integrations and Advanced tools', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/platform/integrations')) {
        return jsonResponse({ ok: true, integrations: [] })
      }
      if (path.includes('/dashboard/calendar/sync/connections')) {
        return jsonResponse({ ok: true, connections: [], count: 0 })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <SettingsPage
        {...settingsBase}
        userAccess={userAccess(['settings.manage', 'calendar.sync', 'users.manage'], 'owner')}
      />,
    )

    expect(await screen.findByRole('tab', { name: /^Integrations$/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^Advanced$/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /^Integrations$/i }))
    expect(await screen.findByText(/Google and Microsoft/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Connect Microsoft 365/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Prepare backup calendar connection/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ensure legacy operator/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /^Advanced$/i }))
    expect(await screen.findByRole('button', { name: /Prepare backup calendar connection/i })).toBeInTheDocument()
  })

  test('hr_admin with settings.manage but without calendar.sync does not see Integrations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ ok: true })),
    )

    renderWithProviders(
      <SettingsPage
        {...settingsBase}
        userAccess={userAccess(['settings.manage', 'calendar.manage', 'calendar.company', 'audit.read'], 'hr_admin')}
      />,
    )

    expect(await screen.findByRole('tab', { name: /^My account$/i })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /^Integrations$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^Advanced$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Connect Microsoft 365/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ensure legacy operator/i })).not.toBeInTheDocument()
  })

  test('integrations variant hides legacy tools; advanced variant exposes them', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/platform/integrations')) {
        return jsonResponse({ ok: true, integrations: [] })
      }
      if (path.includes('/dashboard/calendar/sync/connections')) {
        return jsonResponse({ ok: true, connections: [], count: 0 })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = renderWithProviders(<PlatformIntegrationsPanel access={access} locale="en" variant="integrations" />)

    expect(await screen.findByText(/Google and Microsoft/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Connect Google Workspace/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Prepare backup calendar connection/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ensure legacy operator/i })).not.toBeInTheDocument()

    rerender(<PlatformIntegrationsPanel access={access} locale="en" variant="advanced" />)
    expect(await screen.findByRole('button', { name: /Prepare backup calendar connection/i })).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
  })
})
