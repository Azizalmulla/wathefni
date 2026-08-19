import { type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { accessIssueMessage, type AccessIssue } from '@/lib/access'
import { authCopy, isDefaultAuthPrompt, type AuthCopyKey } from '@/lib/authCopy'
import { documentDirection } from '@/lib/dashboardLocale'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { cn } from '@/lib/utils'
import type { DashboardAccess } from '@/types'

function AuthLocaleToggle({
  locale,
  onLocaleChange,
}: {
  locale: RecruitingLocale
  onLocaleChange?: (locale: RecruitingLocale) => void
}) {
  if (!onLocaleChange) return null
  return (
    <Button
      className="h-9 shrink-0 px-3.5 text-xs"
      data-testid="octohr-auth-locale"
      onClick={() => onLocaleChange(locale === 'ar' ? 'en' : 'ar')}
      type="button"
      variant="ghost"
    >
      {recruitingCopy(locale, 'language')}
    </Button>
  )
}

function authFieldLabelClass(locale: RecruitingLocale) {
  return cn(
    'px-1 text-xs font-semibold text-mist',
    locale === 'ar' ? 'tracking-normal' : 'uppercase tracking-[0.16em]',
  )
}

function AuthSurface({
  children,
  locale,
  testId,
  onLocaleChange,
}: {
  children: ReactNode
  locale: RecruitingLocale
  testId: string
  onLocaleChange?: (locale: RecruitingLocale) => void
}) {
  return (
    <main
      className="flex min-h-dvh w-full items-center justify-center bg-wf-frame px-4 py-10 text-text"
      data-testid={testId}
      dir={documentDirection(locale)}
      lang={locale}
    >
      <div className="grid w-full max-w-[52rem] overflow-hidden rounded-[var(--radius-wf-panel)] border border-[#e8dfd0]/75 bg-wf-surface shadow-[0_10px_28px_rgba(24,20,15,0.04)] lg:grid-cols-[minmax(15rem,0.85fr)_minmax(0,1.15fr)]">
        <div className="hidden bg-wf-sidebar px-10 py-12 text-white lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="text-2xl font-semibold tracking-[-0.045em]">OctoHR</div>
            <p className="mt-3 max-w-[16rem] text-sm leading-6 text-white/60">{authCopy(locale, 'authBrandBlurb')}</p>
          </div>
        </div>
        <div className="px-6 py-8 sm:px-10 sm:py-12">
          <div className="mb-8 flex items-start justify-between gap-3">
            <div className="text-xl font-semibold tracking-[-0.045em] lg:hidden">OctoHR</div>
            <div className="ms-auto">
              <AuthLocaleToggle locale={locale} onLocaleChange={onLocaleChange} />
            </div>
          </div>
          {children}
        </div>
      </div>
    </main>
  )
}

export function AuthSessionResolvingPage({
  locale = 'en',
  onLocaleChange,
}: {
  locale?: RecruitingLocale
  onLocaleChange?: (locale: RecruitingLocale) => void
}) {
  return (
    <AuthSurface locale={locale} onLocaleChange={onLocaleChange} testId="octohr-auth-resolving">
      <div className="flex min-h-[12rem] flex-col items-start justify-center gap-5" role="status">
        <Loader2 className="h-6 w-6 animate-spin text-mist" aria-hidden="true" />
        <p className="text-sm text-subtle">{authCopy(locale, 'authCheckingSession')}</p>
      </div>
    </AuthSurface>
  )
}

export function AccessVerificationPage({
  access,
  accessIssue,
  acceptName,
  acceptPassword,
  acceptPhone,
  busy,
  inviteToken,
  locale = 'en',
  notice,
  onLocaleChange,
  onVerify,
  setAcceptName,
  setAcceptPassword,
  setAcceptPhone,
  setAccess,
}: {
  access: DashboardAccess
  accessIssue: AccessIssue
  acceptName: string
  acceptPassword: string
  acceptPhone: string
  busy: boolean
  inviteToken: string
  locale?: RecruitingLocale
  notice?: { text: string; tone: 'info' | 'success' | 'error'; copyKey?: AuthCopyKey }
  onLocaleChange?: (locale: RecruitingLocale) => void
  onVerify: () => void
  setAcceptName: (value: string) => void
  setAcceptPassword: (value: string) => void
  setAcceptPhone: (value: string) => void
  setAccess: (access: DashboardAccess) => void
}) {
  const isInvite = Boolean(inviteToken)
  const heading = authCopy(locale, isInvite ? 'authAcceptInvite' : 'authSignIn')
  const description = authCopy(locale, isInvite ? 'authInviteDescription' : 'authSignInDescription')
  const issueText = accessIssueMessage(accessIssue, locale)
  const noticeText =
    notice?.tone === 'error'
      ? notice.copyKey
        ? authCopy(locale, notice.copyKey)
        : notice.text
      : ''
  const showIssueAlert =
    Boolean(issueText)
    && accessIssue.code !== 'invite_pending'
    && accessIssue.copyKey !== 'authSignInDescription'
    && accessIssue.copyKey !== 'authInviteDescription'
    && !isDefaultAuthPrompt(issueText)
  const alertText = showIssueAlert ? issueText : noticeText

  return (
    <AuthSurface locale={locale} onLocaleChange={onLocaleChange} testId="octohr-auth-surface">
      <h1 className={cn('text-3xl font-semibold text-text', locale === 'ar' ? 'tracking-normal' : 'tracking-[-0.045em]')}>{heading}</h1>
      <p className="mt-2 max-w-md text-[14px] leading-6 text-subtle">{description}</p>

      {alertText ? (
        <div className="mt-5 rounded-2xl border border-rose-300/60 bg-rose-50/85 px-4 py-3 text-sm text-rose-700" role="alert">
          {alertText}
        </div>
      ) : null}

      {isInvite ? (
        <form
          className="mt-8 space-y-4"
          data-testid="octohr-invite-form"
          onSubmit={(event) => {
            event.preventDefault()
            if (!busy) onVerify()
          }}
        >
          <div className="space-y-1.5">
            <label className={authFieldLabelClass(locale)} htmlFor="octohr-invite-name">
              {authCopy(locale, 'authName')}
            </label>
            <Input
              autoComplete="name"
              autoFocus
              className="w-full"
              id="octohr-invite-name"
              name="name"
              onChange={(event) => setAcceptName(event.target.value)}
              placeholder={authCopy(locale, 'authYourName')}
              value={acceptName}
            />
          </div>
          <div className="space-y-1.5">
            <label className={authFieldLabelClass(locale)} htmlFor="octohr-invite-password">
              {authCopy(locale, 'authPassword')}
            </label>
            <Input
              autoComplete="new-password"
              className="w-full"
              id="octohr-invite-password"
              name="new-password"
              onChange={(event) => setAcceptPassword(event.target.value)}
              placeholder={authCopy(locale, 'authCreatePassword')}
              type="password"
              value={acceptPassword}
            />
          </div>
          <div className="space-y-1.5">
            <label className={authFieldLabelClass(locale)} htmlFor="octohr-invite-phone">
              {authCopy(locale, 'authPhoneOptional')}
            </label>
            <Input
              autoComplete="tel"
              className="w-full"
              id="octohr-invite-phone"
              name="phone"
              onChange={(event) => setAcceptPhone(event.target.value)}
              placeholder={authCopy(locale, 'authPhonePlaceholder')}
              value={acceptPhone}
            />
          </div>
          <Button className="mt-2 w-full sm:w-auto" disabled={busy} pending={busy} type="submit">
            {authCopy(locale, 'authAcceptInviteAction')}
          </Button>
        </form>
      ) : (
        <form
          className="mt-8 space-y-4"
          data-testid="octohr-signin-form"
          onSubmit={(event) => {
            event.preventDefault()
            if (!busy) onVerify()
          }}
        >
          <div className="space-y-1.5">
            <label className={authFieldLabelClass(locale)} htmlFor="octohr-email">
              {authCopy(locale, 'authWorkEmail')}
            </label>
            <Input
              autoComplete="username"
              autoFocus
              className="w-full"
              id="octohr-email"
              name="email"
              onChange={(event) => setAccess({ ...access, email: event.target.value })}
              placeholder="karen.d@example.net"
              type="email"
              value={access.email || ''}
            />
          </div>
          <div className="space-y-1.5">
            <label className={authFieldLabelClass(locale)} htmlFor="octohr-password">
              {authCopy(locale, 'authPassword')}
            </label>
            <Input
              autoComplete="current-password"
              className="w-full"
              id="octohr-password"
              name="password"
              onChange={(event) => setAccess({ ...access, password: event.target.value })}
              placeholder={authCopy(locale, 'authPasswordPlaceholder')}
              type="password"
              value={access.password || ''}
            />
          </div>
          <div className="space-y-1.5">
            <label className={authFieldLabelClass(locale)} htmlFor="octohr-company-code">
              {authCopy(locale, 'authCompanyCode')}
            </label>
            <Input
              autoCapitalize="characters"
              autoComplete="organization"
              className="w-full"
              id="octohr-company-code"
              name="company-code"
              onChange={(event) => setAccess({ ...access, companyCode: event.target.value.toUpperCase() })}
              placeholder={authCopy(locale, 'authCompanyCode')}
              spellCheck={false}
              value={access.companyCode}
            />
          </div>
          <Button className="mt-2 w-full sm:w-auto" disabled={busy} pending={busy} type="submit">
            {authCopy(locale, 'authSignIn')}
          </Button>
        </form>
      )}
    </AuthSurface>
  )
}

export function NeedsSettings({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in required</CardTitle>
        <CardDescription>Sign in to your OctoHR workspace from Settings to load the dashboard.</CardDescription>
      </CardHeader>
      <CardContent>
        <Button onClick={onOpenSettings}>Open Settings</Button>
      </CardContent>
    </Card>
  )
}

export function LoadingDashboard({
  busy,
  notice,
  onOpenSettings,
  onRefresh,
}: {
  busy: boolean
  notice: string
  onOpenSettings: () => void
  onRefresh: () => void
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Loading live dashboard data</CardTitle>
        <CardDescription>OctoHR found saved dashboard access and is loading live hiring data before showing metrics.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border border-line bg-panel-muted/60 p-4 text-sm text-subtle">{notice}</div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={onRefresh}>
            {busy ? <Loader2 className="animate-spin" size={16} /> : null}
            Load now
          </Button>
          <Button disabled={busy} onClick={onOpenSettings} variant="secondary">
            Check Settings
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
