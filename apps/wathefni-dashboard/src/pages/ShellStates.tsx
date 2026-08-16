import { Loader2, RefreshCw, UserCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { type AccessIssue } from '@/lib/access'
import { Info } from '@/pages/shared/primitives'
import type { DashboardAccess } from '@/types'

export function AccessVerificationPage({
  access,
  accessIssue,
  acceptName,
  acceptPassword,
  acceptPhone,
  busy,
  inviteToken,
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
  onVerify: () => void
  setAcceptName: (value: string) => void
  setAcceptPassword: (value: string) => void
  setAcceptPhone: (value: string) => void
  setAccess: (access: DashboardAccess) => void
}) {
  if (inviteToken) {
    return (
      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.45fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Complete Your OctoHR Invite</CardTitle>
            <CardDescription>Create your workspace login. Your fixed role is already assigned by the company Owner/Admin.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                if (!busy) onVerify()
              }}
            >
              <Input autoComplete="name" autoFocus name="name" onChange={(event) => setAcceptName(event.target.value)} placeholder="Your name" value={acceptName} />
              <Input autoComplete="new-password" name="new-password" onChange={(event) => setAcceptPassword(event.target.value)} placeholder="Create password" type="password" value={acceptPassword} />
              <Input autoComplete="tel" name="phone" onChange={(event) => setAcceptPhone(event.target.value)} placeholder="WhatsApp phone optional" value={acceptPhone} />
              <Button disabled={busy} type="submit">
                {busy ? <Loader2 className="animate-spin" size={16} /> : <UserCheck size={16} />} Accept invite
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>What Happens Next</CardTitle>
            <CardDescription>OctoHR will sign you into the company workspace and apply your assigned role immediately.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Info label="Workspace" value="Company HR workspace" />
            <Info label="Permissions" value="Fixed by assigned role" />
            <Info label="WhatsApp" value={acceptPhone ? 'Linked after accept' : 'Can be linked later'} />
          </CardContent>
        </Card>
      </div>
    )
  }
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.45fr)]">
      <Card>
        <CardHeader>
          <CardTitle>{accessIssue.title}</CardTitle>
          <CardDescription>{accessIssue.description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (!busy) onVerify()
            }}
          >
            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  autoComplete="username"
                  autoFocus
                  name="email"
                  onChange={(event) => setAccess({ ...access, email: event.target.value })}
                  placeholder="Work email"
                  type="email"
                  value={access.email || ''}
                />
                <Input
                  autoComplete="current-password"
                  name="password"
                  onChange={(event) => setAccess({ ...access, password: event.target.value })}
                  placeholder="Password"
                  type="password"
                  value={access.password || ''}
                />
              </div>
              <Input
                autoComplete="off"
                name="company-code"
                onChange={(event) => setAccess({ ...access, companyCode: event.target.value.toUpperCase() })}
                placeholder="Company code"
                value={access.companyCode}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button disabled={busy} type="submit">
                {busy ? <Loader2 className="animate-spin" size={16} /> : <UserCheck size={16} />} Sign in
              </Button>
              <span className="text-xs text-subtle">Use your invited workspace account.</span>
            </div>
          </form>
          <details className="rounded-2xl border border-line bg-panel-muted/50 p-4">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-subtle">Backup access</summary>
            <div className="mt-3 space-y-3">
              <p className="text-xs leading-5 text-subtle">
                Use a backup access code only if you need to set up or recover the workspace.
              </p>
              <Input
                onChange={(event) => setAccess({ ...access, token: event.target.value })}
                placeholder="Backup access code"
                type="password"
                value={access.token}
              />
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  onChange={(event) => setAccess({ ...access, hrPhone: event.target.value })}
                  placeholder="Registered HR phone"
                  value={access.hrPhone}
                />
                <Input
                  onChange={(event) => setAccess({ ...access, companyCode: event.target.value.toUpperCase() })}
                  placeholder="Company code"
                  value={access.companyCode}
                />
              </div>
            </div>
          </details>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Workspace Access</CardTitle>
          <CardDescription>After sign-in, OctoHR loads your company workspace, modules, and role permissions.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Info label="Company" value={access.companyCode || 'Verified after access check'} />
          <Info label="Your WhatsApp phone" value={access.hrPhone ? 'Ready to link' : 'Can be linked after login'} />
          <Info label="Your role" value="Loaded after access is verified" />
        </CardContent>
      </Card>
    </div>
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
            {busy ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
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
