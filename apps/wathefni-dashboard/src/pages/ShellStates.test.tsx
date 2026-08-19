import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { AccessVerificationPage, AuthSessionResolvingPage } from './ShellStates'

const access = { token: '', hrPhone: '', companyCode: '', email: '', password: '' }

describe('unauthenticated OctoHR auth surface', () => {
  test('sign-in is OctoHR branded with email, password, and empty company code', () => {
    const setAccess = vi.fn()
    render(
      <AccessVerificationPage
        access={access}
        accessIssue={{ code: 'dashboard_auth_failed', title: 'Sign in to OctoHR', description: 'Enter your work email, password, and company code.' }}
        acceptName=""
        acceptPassword=""
        acceptPhone=""
        busy={false}
        inviteToken=""
        onVerify={() => undefined}
        setAcceptName={() => undefined}
        setAcceptPassword={() => undefined}
        setAcceptPhone={() => undefined}
        setAccess={setAccess}
      />,
    )

    expect(screen.getByTestId('octohr-auth-surface')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getAllByText('OctoHR').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Work email')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByLabelText('Company code')).toHaveValue('')
    expect(screen.queryByPlaceholderText('Backup access code')).not.toBeInTheDocument()
    expect(screen.queryByText('Workspace Access')).not.toBeInTheDocument()
    expect(screen.queryByText(/Wathefni|واثقني/i)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Company code'), { target: { value: 'acme' } })
    expect(setAccess).toHaveBeenCalledWith(expect.objectContaining({ companyCode: 'ACME' }))
  })

  test('invite form has no WhatsApp explainer panel', () => {
    render(
      <AccessVerificationPage
        access={access}
        accessIssue={{ code: 'invite_pending', title: 'Sign in to OctoHR', description: 'Create your workspace password to join this company.' }}
        acceptName=""
        acceptPassword=""
        acceptPhone=""
        busy={false}
        inviteToken="invite-token"
        onVerify={() => undefined}
        setAcceptName={() => undefined}
        setAcceptPassword={() => undefined}
        setAcceptPhone={() => undefined}
        setAccess={() => undefined}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Accept your invite' })).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByLabelText('Phone (optional)')).toBeInTheDocument()
    expect(screen.queryByText('What Happens Next')).not.toBeInTheDocument()
    expect(screen.queryByText(/WhatsApp/i)).not.toBeInTheDocument()
  })

  test('session resolving is a dedicated OctoHR surface without workspace chrome', () => {
    render(<AuthSessionResolvingPage />)
    expect(screen.getByTestId('octohr-auth-resolving')).toBeInTheDocument()
    expect(screen.getByText('Checking your session')).toBeInTheDocument()
    expect(screen.queryByTestId('app-sidebar')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Backup access code')).not.toBeInTheDocument()
  })

  test('Arabic locale uses RTL on the shared auth surface and OctoHR branding', () => {
    const onLocaleChange = vi.fn()
    render(
      <AccessVerificationPage
        access={access}
        accessIssue={{
          code: 'dashboard_auth_failed',
          title: 'Sign in to OctoHR',
          description: 'Enter your work email, password, and company code.',
          copyKey: 'authSignInDescription',
        }}
        acceptName=""
        acceptPassword=""
        acceptPhone=""
        busy={false}
        inviteToken=""
        locale="ar"
        onLocaleChange={onLocaleChange}
        onVerify={() => undefined}
        setAcceptName={() => undefined}
        setAcceptPassword={() => undefined}
        setAcceptPhone={() => undefined}
        setAccess={() => undefined}
      />,
    )

    const surface = screen.getByTestId('octohr-auth-surface')
    expect(surface).toHaveAttribute('dir', 'rtl')
    expect(surface).toHaveAttribute('lang', 'ar')
    expect(screen.getByRole('heading', { name: 'تسجيل الدخول' })).toBeInTheDocument()
    expect(screen.getByLabelText('البريد الإلكتروني للعمل')).toBeInTheDocument()
    expect(screen.getByLabelText('كلمة المرور')).toBeInTheDocument()
    expect(screen.getByLabelText('رمز الشركة')).toBeInTheDocument()
    expect(screen.getAllByText('OctoHR').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Wathefni|واثقني/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('octohr-auth-locale'))
    expect(onLocaleChange).toHaveBeenCalledWith('en')
  })

  test('session-expired copyKey re-translates when locale is Arabic', () => {
    render(
      <AccessVerificationPage
        access={access}
        accessIssue={{
          code: 'dashboard_auth_failed',
          title: 'Sign in to OctoHR',
          description: 'Your session expired. Please sign in again.',
          copyKey: 'authSessionExpired',
        }}
        acceptName=""
        acceptPassword=""
        acceptPhone=""
        busy={false}
        inviteToken=""
        locale="ar"
        onVerify={() => undefined}
        setAcceptName={() => undefined}
        setAcceptPassword={() => undefined}
        setAcceptPhone={() => undefined}
        setAccess={() => undefined}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('انتهت صلاحية جلستك. يرجى تسجيل الدخول مرة أخرى.')
  })
})
