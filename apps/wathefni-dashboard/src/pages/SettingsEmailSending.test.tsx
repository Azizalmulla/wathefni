/** Settings Communications — Email sending UX contract (EN/AR + RTL + simplicity). */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { SettingsPage } from '@/pages/SettingsPage'
import { renderWithProviders } from '@/test/render'
import type { DashboardAccess, DashboardUserAccess, EmailSendingSettingsResponse } from '@/types'

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

function userAccess(): DashboardUserAccess {
  return {
    role: 'owner',
    role_label: 'Owner',
    permissions: ['settings.manage', 'users.manage', 'candidate.import'],
    user: {
      user_id: 'u1',
      name: 'Owner',
      email: 'owner@example.com',
      role: 'owner',
      status: 'active',
      company_code: 'WATHEFNI',
    },
  } as DashboardUserAccess
}

const emailView: EmailSendingSettingsResponse = {
  company_code: 'WATHEFNI',
  current_sender: 'wathefni',
  status: 'ready',
  status_label: 'Ready',
  choices: [
    {
      id: 'wathefni',
      title: 'Send through Wathefni',
      description: 'Ready immediately',
      recommended: false,
      status: 'ready',
      selectable: true,
    },
    {
      id: 'microsoft_mailbox',
      title: 'Send from our Microsoft mailbox',
      description: 'Recommended for Microsoft 365',
      recommended: true,
      status: 'setup_required',
      selectable: false,
    },
    {
      id: 'postmark_company_domain',
      title: 'Send from our company domain',
      description: 'DNS verification required',
      recommended: false,
      status: 'setup_required',
      selectable: false,
    },
  ],
  display_name: 'People Team',
  reply_to: 'hr@example.com',
  visible_from: 'hr@wathefni.ai',
  interview_email_when_calendar_sent: false,
  allow_wathefni_emergency_fallback: false,
  primary_action: { id: 'test', label: 'Test' },
  intake: {
    addresses: [{ address: 'acme@inbound.wathefni.ai', label: 'General' }],
    public_forward_address: null,
    forward_instructions_en: 'Forward CVs to your Wathefni intake address.',
    forward_instructions_ar: 'حوّل السير الذاتية إلى عنوان استقبال وظفني.',
  },
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
  prehireEnabled: true,
  settingsTeamEnabled: true,
  settingsIntegrationsEnabled: true,
  setAccess: vi.fn(),
  setInviteEmail: vi.fn(),
  setInviteName: vi.fn(),
  setInviteRole: vi.fn(),
  setLinkPhone: vi.fn(),
  team: { company_code: 'WATHEFNI', users: [], invites: [] },
  userAccess: userAccess(),
}

describe('Settings Email sending Communications', () => {
  test('source keeps product language only (no SP/RBAC jargon)', () => {
    const src = readFileSync(resolve(__dirname, '../pages/SettingsPage.tsx'), 'utf8')
    expect(src).toContain('Email sending')
    expect(src).toContain('Email & document intake')
    expect(src).toContain('Communications')
    expect(src).toContain('Also send an email with calendar invitations')
    expect(src).toContain('Allow Wathefni emergency fallback')
    expect(src).not.toContain('service principal')
    expect(src).not.toContain('RBAC')
    expect(src).not.toContain('Mail.Send')
    expect(src).not.toContain('postmark_domain_id')
    expect(src).not.toContain('outbound_mailbox_id')
    // EmailSendingCard copy should stay product language
    const cardStart = src.indexOf('function EmailSendingCard')
    const cardEnd = src.indexOf('function EmailDocumentIntakeCard')
    const card = src.slice(cardStart, cardEnd)
    expect(card).not.toMatch(/service principal|RBAC|Mail\.Send|capability ID/i)
  })

  test('renders Email sending choices and intake on desktop EN', async () => {
    document.documentElement.lang = 'en'
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/prehire/integrations/email')) return jsonResponse(emailView)
      if (path.includes('/dashboard/prehire/visibility-policy') || path.includes('/dashboard/prehire/import/settings')) {
        return jsonResponse({ company_code: 'WATHEFNI', prehire_visibility_policy: 'shared_company', auto_admit_explicit_imports: false })
      }
      if (path.includes('/dashboard/prehire/integrations/mailbox')) {
        return jsonResponse({ company_code: 'WATHEFNI', feature: { enabled: false }, connections: [] })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<SettingsPage {...settingsBase} />)

    await waitFor(() => {
      expect(screen.getAllByText('Email sending').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('Send through Wathefni')).toBeInTheDocument()
    expect(screen.getByText('Send from our Microsoft mailbox')).toBeInTheDocument()
    expect(screen.getByText('Send from our company domain')).toBeInTheDocument()
    expect(screen.getByText('Email & document intake')).toBeInTheDocument()
    expect(screen.getByText('acme@inbound.wathefni.ai')).toBeInTheDocument()
    expect(screen.queryByText(/service principal/i)).not.toBeInTheDocument()
  })

  test('AR locale uses RTL on communications cards', async () => {
    document.documentElement.lang = 'ar'
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/prehire/integrations/email')) return jsonResponse(emailView)
      if (path.includes('/dashboard/prehire/visibility-policy') || path.includes('/dashboard/prehire/import/settings')) {
        return jsonResponse({ company_code: 'WATHEFNI', prehire_visibility_policy: 'shared_company', auto_admit_explicit_imports: false })
      }
      if (path.includes('/dashboard/prehire/integrations/mailbox')) {
        return jsonResponse({ company_code: 'WATHEFNI', feature: { enabled: false }, connections: [] })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = renderWithProviders(<SettingsPage {...settingsBase} />)
    await waitFor(() => {
      expect(screen.getAllByText('إرسال البريد').length).toBeGreaterThan(0)
    })
    const rtlNodes = container.querySelectorAll('[dir="rtl"]')
    expect(rtlNodes.length).toBeGreaterThan(0)
    expect(screen.getByText('استقبال البريد والمستندات')).toBeInTheDocument()
  })
})
