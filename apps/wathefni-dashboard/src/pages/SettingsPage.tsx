import { Copy, Inbox, Loader2, LogOut, MessageCircle, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { useConfirm } from '@/components/ConfirmDialog'
import { PlatformIntegrationsPanel } from '@/components/PlatformIntegrationsPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import {
  DashboardApiError,
  checkMailboxNow,
  connectMailbox,
  disconnectMailbox,
  emailSendingPrimaryAction,
  getEmailSendingSettings,
  getImportSettings,
  getMailboxConnections,
  getMailboxLabels,
  getPrehireVisibilityPolicy,
  putPrehireVisibilityPolicy,
  updateEmailSendingSettings,
  updateImportSettings,
  updateMailbox,
} from '@/lib/api'
import { type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { cn, formatDateTime } from '@/lib/utils'
import { friendlyDashboardError, stageLabel } from '@/pages/shared/format'
import {
  currentUserTeamRow,
  hasDashboardPermission,
  isRecoveryAccess,
  readableCapabilities,
  ROLE_LABELS_UI,
} from '@/pages/shared/access'
import { Info } from '@/pages/shared/primitives'
import type {
  DashboardAccess,
  DashboardTeamResponse,
  DashboardUserAccess,
  EmailSendingSettingsResponse,
  MailboxConnection,
  MailboxFeatureStatus,
} from '@/types'

export function SettingsPage({
  access,
  busy,
  createdInviteLink,
  inviteEmail,
  inviteName,
  inviteRole,
  linkPhone,
  onInvite,
  onClearInviteLink,
  onCopyInviteLink,
  onLinkWhatsApp,
  onLogout,
  onSave,
  onUpdateUser,
  prehireEnabled,
  settingsTeamEnabled,
  settingsIntegrationsEnabled,
  setAccess,
  setInviteEmail,
  setInviteName,
  setInviteRole,
  setLinkPhone,
  team,
  userAccess,
}: {
  access: DashboardAccess
  busy: boolean
  createdInviteLink: string
  inviteEmail: string
  inviteName: string
  inviteRole: string
  linkPhone: string
  onInvite: () => void
  onClearInviteLink: () => void
  onCopyInviteLink: (link: string) => void
  onLinkWhatsApp: () => void
  onLogout: () => void
  onSave: () => void
  onUpdateUser: (userId: string, body: { role?: string; status?: string }) => void
  prehireEnabled: boolean
  settingsTeamEnabled?: boolean
  settingsIntegrationsEnabled?: boolean
  setAccess: (access: DashboardAccess) => void
  setInviteEmail: (value: string) => void
  setInviteName: (value: string) => void
  setInviteRole: (value: string) => void
  setLinkPhone: (value: string) => void
  team: DashboardTeamResponse | null
  userAccess: DashboardUserAccess | null
}) {
  const canManageUsers =
    settingsTeamEnabled ?? hasDashboardPermission(userAccess, 'users.manage')
  const canManageSettings =
    settingsIntegrationsEnabled ?? hasDashboardPermission(userAccess, 'settings.manage')
  const canSyncCalendar = hasDashboardPermission(userAccess, 'calendar.sync')
  const canManagePlatformIntegrations = canManageSettings && canSyncCalendar
  const account = userAccess?.user
  const recoveryAccess = isRecoveryAccess(userAccess)
  const fallbackUser = currentUserTeamRow(userAccess)
  const displayedTeamUsers = team?.users?.length ? team.users : fallbackUser ? [fallbackUser] : []
  const confirm = useConfirm()
  const [visibilityPolicy, setVisibilityPolicy] = useState('shared_company')
  const [visibilityVersion, setVisibilityVersion] = useState<number | null>(null)
  const [visibilityUpdatedAt, setVisibilityUpdatedAt] = useState<string | null>(null)
  const [visibilityUpdatedBy, setVisibilityUpdatedBy] = useState<string | null>(null)
  const [visibilityBusy, setVisibilityBusy] = useState(false)
  const [visibilityError, setVisibilityError] = useState<string | null>(null)
  const [platformNotice, setPlatformNotice] = useState<string | null>(null)
  const locale = typeof document !== 'undefined' && document.documentElement.lang === 'ar' ? 'ar' : 'en'

  useEffect(() => {
    if (!prehireEnabled || !canManageSettings) return
    let cancelled = false
    void getPrehireVisibilityPolicy(access)
      .then((payload) => {
        if (cancelled) return
        setVisibilityPolicy(String(payload.prehire_visibility_policy || 'shared_company'))
        setVisibilityVersion(typeof payload.version === 'number' ? payload.version : null)
        setVisibilityUpdatedAt(payload.updated_at ? String(payload.updated_at) : null)
        setVisibilityUpdatedBy(payload.last_updated_by ? String(payload.last_updated_by) : null)
      })
      .catch(() => {
        if (!cancelled) setVisibilityPolicy('shared_company')
      })
    return () => {
      cancelled = true
    }
  }, [access, canManageSettings, prehireEnabled])

  async function saveVisibilityPolicy(next: string) {
    setVisibilityBusy(true)
    setVisibilityError(null)
    try {
      const result = await putPrehireVisibilityPolicy(access, next, {
        expected_version: visibilityVersion,
        expected_updated_at: visibilityUpdatedAt,
      })
      setVisibilityPolicy(String(result.prehire_visibility_policy || next))
      if (typeof result.version === 'number') setVisibilityVersion(result.version)
      if (result.updated_at) setVisibilityUpdatedAt(String(result.updated_at))
      if (result.last_updated_by) setVisibilityUpdatedBy(String(result.last_updated_by))
    } catch (error) {
      setVisibilityError(
        friendlyDashboardError(
          error,
          locale === 'ar' ? 'تعذر حفظ إعداد الرؤية.' : 'Could not save visibility policy.',
          locale as RecruitingLocale,
        ),
      )
      try {
        const latest = await getPrehireVisibilityPolicy(access)
        setVisibilityPolicy(String(latest.prehire_visibility_policy || visibilityPolicy))
        setVisibilityVersion(typeof latest.version === 'number' ? latest.version : null)
        setVisibilityUpdatedAt(latest.updated_at ? String(latest.updated_at) : null)
        setVisibilityUpdatedBy(latest.last_updated_by ? String(latest.last_updated_by) : null)
      } catch {
        /* ignore refresh failure */
      }
    } finally {
      setVisibilityBusy(false)
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_0.8fr]">
      {canManagePlatformIntegrations ? (
        <div className="xl:col-span-2 space-y-2">
          <div>
            <h2 className="text-lg font-semibold text-ink">Platform Integrations</h2>
            <p className="text-sm text-subtle">
              Company Google Workspace and Microsoft 365 connections. Requires settings and calendar sync authority.
            </p>
            {platformNotice ? <p className="mt-1 text-sm text-[#3f6b3a]">{platformNotice}</p> : null}
          </div>
          <PlatformIntegrationsPanel
            access={access}
            locale={locale as RecruitingLocale}
            onNotice={(text, kind) => {
              if (kind === 'error') setPlatformNotice(text)
              else setPlatformNotice(text)
            }}
          />
        </div>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Your signed-in Wathefni workspace identity.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {recoveryAccess ? (
            <div className="rounded-2xl border border-[#e8c47d]/55 bg-[#fff7e6]/80 p-4 text-sm leading-6 text-[#8a5a12]">
              You’re signed in with a backup access code. Create or sign in to a workspace account for everyday use.
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-2">
            <Info label="Name" value={account?.name || 'Not loaded yet'} />
            <Info label="Email" value={account?.email || access.email || 'Not loaded yet'} />
            <Info label="Role" value={(account?.role && ROLE_LABELS_UI[account.role]) || userAccess?.role_label || account?.role_label || 'Not loaded yet'} />
            <Info label="Company / workspace" value={account?.company_code || access.companyCode || 'WATHEFNI'} />
            <Info label="Status" value={account?.status ? stageLabel(account.status) : 'Not loaded yet'} />
            <Info label="Workspace" value="Wathefni HR" />
          </div>
          {prehireEnabled && canManageSettings ? (
            <div className="rounded-2xl border border-line bg-panel-muted/50 p-4">
              <div className="text-sm font-semibold text-text">
                {locale === 'ar' ? 'سياسة ظهور التوظيف' : 'Pre-hiring visibility'}
              </div>
              <p className="mt-1 text-xs leading-5 text-subtle">
                {locale === 'ar'
                  ? 'تحدد من يرى الوظائف والمرشحين في الشركة. المسؤولون يحتفظون بالنظرة الشاملة.'
                  : 'Controls who sees jobs and candidates. Company Admin / HR Admin / HR Manager keep company-wide oversight.'}
              </p>
              <Select
                className="mt-3"
                disabled={visibilityBusy}
                onChange={(event) => void saveVisibilityPolicy(event.target.value)}
                value={visibilityPolicy}
              >
                <option value="shared_company">{locale === 'ar' ? 'مشترك على مستوى الشركة' : 'Shared company'}</option>
                <option value="assigned_only">{locale === 'ar' ? 'المسند فقط' : 'Assigned only'}</option>
                <option value="hybrid">{locale === 'ar' ? 'هجين (ملخص عام / تفاصيل مسندة)' : 'Hybrid (company summary / assigned detail)'}</option>
              </Select>
              {(visibilityUpdatedBy || visibilityUpdatedAt) ? (
                <p className="mt-2 text-[11px] text-subtle">
                  {locale === 'ar' ? 'آخر تحديث' : 'Last updated'}
                  {visibilityUpdatedBy ? `: ${visibilityUpdatedBy}` : ''}
                  {visibilityUpdatedAt ? ` · ${new Date(visibilityUpdatedAt).toLocaleString(locale === 'ar' ? 'ar-KW' : 'en-GB')}` : ''}
                </p>
              ) : null}
              {visibilityError ? (
                <p className="mt-2 text-xs leading-5 text-[#9b3d3d]">{visibilityError}</p>
              ) : null}
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={busy} onClick={onLogout} variant="secondary">
              <LogOut size={16} /> Log out
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Workspace Access</CardTitle>
          <CardDescription>Your role, capabilities, and linked WhatsApp identity.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-line bg-panel-muted/60 p-3">
            <div className="text-xs uppercase tracking-wide text-subtle">What you can do</div>
            <div className="mt-2 space-y-1 text-sm leading-6 text-text">
              {readableCapabilities(userAccess).length ? (
                readableCapabilities(userAccess).map((capability) => <div key={capability}>{capability}</div>)
              ) : (
                <div className="text-subtle">Verify access to load your role capabilities.</div>
              )}
            </div>
          </div>
          <div className="rounded-lg border border-line bg-panel-muted/60 p-3">
            <div className="text-xs uppercase tracking-wide text-subtle">WhatsApp identity</div>
            <div className="mt-3 flex gap-2">
              <Input onChange={(event) => setLinkPhone(event.target.value)} placeholder="WhatsApp phone" value={linkPhone} />
              <Button disabled={busy} onClick={onLinkWhatsApp} variant="secondary">Link</Button>
            </div>
            <p className="mt-2 text-xs leading-5 text-subtle">Dashboard login and WhatsApp conversations stay separate. Linking lets Wathefni map WhatsApp AI actions to this user.</p>
          </div>
          <details className="rounded-lg border border-line bg-panel-muted/45 p-3">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-subtle">Backup access</summary>
            <div className="mt-3 space-y-3">
              <p className="text-xs leading-5 text-subtle">
                Use this only to set up or recover workspace access. For everyday use, sign in with a workspace email and password.
              </p>
              <Input
                onChange={(event) => setAccess({ ...access, token: event.target.value })}
                placeholder="Backup access code"
                type="password"
                value={access.token}
              />
              <div className="grid gap-3 md:grid-cols-2">
                <Input onChange={(event) => setAccess({ ...access, hrPhone: event.target.value })} placeholder="Registered HR phone" value={access.hrPhone} />
                <Input
                  onChange={(event) => setAccess({ ...access, companyCode: event.target.value.toUpperCase() })}
                  placeholder="Company code"
                  value={access.companyCode}
                />
              </div>
              <Button disabled={busy} onClick={onSave} variant="secondary">
                Use backup access
              </Button>
            </div>
          </details>
        </CardContent>
      </Card>
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle>Team Access</CardTitle>
          <CardDescription>Invite team members and assign one of Wathefni’s built-in roles.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {canManageUsers ? (
            <div className="space-y-3 rounded-2xl border border-line bg-panel-muted/50 p-4">
              <div className="grid gap-3 lg:grid-cols-[1fr_1fr_220px_auto]">
                <Input onChange={(event) => setInviteName(event.target.value)} placeholder="Name optional" value={inviteName} />
                <Input onChange={(event) => setInviteEmail(event.target.value)} placeholder="Email" type="email" value={inviteEmail} />
                <Select onChange={(event) => setInviteRole(event.target.value)} value={inviteRole}>
                  {Object.entries(ROLE_LABELS_UI).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </Select>
                <Button disabled={busy} onClick={onInvite}><Plus size={16} /> Create invite link</Button>
              </div>
              <p className="text-xs leading-5 text-subtle">
                Wathefni creates a secure invite link for each team member - share it with them directly.
              </p>
              {createdInviteLink ? (
                <div className="rounded-2xl border border-[#e8c47d]/55 bg-[#fff7e6]/80 p-4">
                  <div className="text-sm font-semibold text-text">Invite link ready</div>
                  <p className="mt-1 text-xs leading-5 text-subtle">Share this invite link with the new team member. It expires automatically.</p>
                  <div className="mt-3 flex flex-col gap-2 md:flex-row">
                    <Input readOnly value={createdInviteLink} />
                    <Button onClick={() => onCopyInviteLink(createdInviteLink)} variant="secondary"><Copy size={16} /> Copy link</Button>
                    <Button onClick={onClearInviteLink} variant="ghost">Dismiss</Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="rounded-2xl border border-line bg-panel-muted/50 p-4 text-sm text-subtle">Only Owners/Admins can invite users or change team access.</div>
          )}
          {team?.invites?.length ? (
            <div className="rounded-2xl border border-line/55 bg-panel/70 p-4">
              <div className="text-sm font-semibold text-text">Pending invites</div>
              <div className="mt-3 grid gap-2">
                {team.invites.map((invite) => (
                  <div className="flex flex-col gap-1 rounded-xl bg-white/35 p-3 text-sm md:flex-row md:items-center md:justify-between" key={invite.invite_id}>
                    <div>
                      <div className="font-medium text-text">{invite.email}</div>
                      <div className="text-xs text-subtle">{ROLE_LABELS_UI[invite.role] || invite.role} · Expires {invite.expires_at ? formatDateTime(invite.expires_at) : 'soon'}</div>
                    </div>
                    <Badge tone="warning">Pending</Badge>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="overflow-x-auto rounded-3xl border border-line/55 bg-panel/75">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-[#f7f1e7]/72 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  {canManageUsers || team?.directory_view === 'admin' ? (
                    <>
                      <th className="px-4 py-3">Email</th>
                      <th className="px-4 py-3">Phone</th>
                      <th className="px-4 py-3">WhatsApp</th>
                    </>
                  ) : null}
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Status</th>
                  {canManageUsers || team?.directory_view === 'admin' ? (
                    <th className="px-4 py-3">Last active</th>
                  ) : null}
                  {canManageUsers ? <th className="px-4 py-3">Actions</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-line/45 bg-panel/42">
                {displayedTeamUsers.map((user) => (
                  <tr key={user.user_id}>
                    <td className="px-4 py-3 font-medium text-text">{user.name || 'Invited user'}</td>
                    {canManageUsers || team?.directory_view === 'admin' ? (
                      <>
                        <td className="px-4 py-3 text-subtle">{user.email || (user.is_self ? '—' : 'Hidden')}</td>
                        <td className="px-4 py-3 text-subtle">{user.phone || (user.is_self ? 'Not linked' : 'Hidden')}</td>
                        <td className="px-4 py-3">
                          <Badge tone={user.whatsapp_linked ? 'success' : 'muted'}>{user.whatsapp_linked ? 'WhatsApp linked' : 'Not linked'}</Badge>
                        </td>
                      </>
                    ) : null}
                    <td className="px-4 py-3">
                      {canManageUsers ? (
                        <Select
                          onChange={async (event) => {
                            const nextRole = event.target.value
                            if (nextRole === user.role) return
                            if (
                              !(await confirm({
                                title: 'Change role?',
                                body: `Change ${user.name || user.email}'s role to ${ROLE_LABELS_UI[nextRole] || nextRole}? This changes what they can see and do in the workspace.`,
                                confirmLabel: 'Change role',
                                destructive: true,
                              }))
                            ) {
                              return
                            }
                            onUpdateUser(user.user_id, { role: nextRole })
                          }}
                          value={user.role}
                        >
                          {Object.entries(ROLE_LABELS_UI).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                        </Select>
                      ) : ROLE_LABELS_UI[user.role] || user.role_label || user.role}
                    </td>
                    <td className="px-4 py-3"><Badge tone={user.status === 'active' ? 'success' : user.status === 'disabled' ? 'danger' : 'warning'}>{stageLabel(user.status)}</Badge></td>
                    {canManageUsers || team?.directory_view === 'admin' ? (
                      <td className="px-4 py-3 text-subtle">{user.last_active_at ? formatDateTime(user.last_active_at) : 'No activity yet'}</td>
                    ) : null}
                    {canManageUsers ? (
                      <td className="px-4 py-3">
                        {user.status !== 'disabled' && team?.users?.length ? (
                          <Button
                            onClick={async () => {
                              if (
                                !(await confirm({
                                  title: 'Deactivate user?',
                                  body: `${user.name || user.email} will immediately lose access to this workspace. You can re-invite them later.`,
                                  confirmLabel: 'Deactivate',
                                  destructive: true,
                                }))
                              ) {
                                return
                              }
                              onUpdateUser(user.user_id, { status: 'disabled' })
                            }}
                            size="sm"
                            variant="secondary"
                          >
                            Deactivate
                          </Button>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                ))}
                {!displayedTeamUsers.length ? (
                  <tr><td className="px-4 py-6 text-subtle" colSpan={8}>{team ? 'No team members yet.' : 'Team members are loading...'}</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      {prehireEnabled && canManageUsers ? <IntegrationsCard access={access} /> : null}
      {prehireEnabled && hasDashboardPermission(userAccess, 'candidate.import') ? <IntakeSettingsCard access={access} /> : null}
      {canManageSettings ? (
        <div className="xl:col-span-2 space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-ink">{locale === 'ar' ? 'الاتصالات' : 'Communications'}</h2>
            <p className="text-sm text-subtle">
              {locale === 'ar' ? 'كيف ترسل وظفني الرسائل وكيف تستقبل المستندات.' : 'How Wathefni sends messages and receives documents.'}
            </p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <EmailSendingCard access={access} locale={locale as RecruitingLocale} />
            <EmailDocumentIntakeCard access={access} locale={locale as RecruitingLocale} />
          </div>
        </div>
      ) : null}
    </div>
  )
}

function statusTone(status: string) {
  if (status === 'ready') return 'success' as const
  if (status === 'verifying') return 'warning' as const
  if (status === 'error') return 'danger' as const
  return 'muted' as const
}

function EmailSendingCard({ access, locale }: { access: DashboardAccess; locale: RecruitingLocale }) {
  const isAr = locale === 'ar'
  const [view, setView] = useState<EmailSendingSettingsResponse | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [replyTo, setReplyTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    const data = await getEmailSendingSettings(access)
    setView(data)
    setDisplayName(data.display_name || '')
    setReplyTo(data.reply_to || '')
  }, [access])

  useEffect(() => {
    let active = true
    void reload()
      .catch((err) => {
        if (active) setError(friendlyDashboardError(err, isAr ? 'تعذر تحميل إعدادات البريد.' : 'Could not load email settings.', locale))
      })
    return () => {
      active = false
    }
  }, [reload, isAr, locale])

  if (!view && !error) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-sm text-subtle">
          <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading…'}
        </CardContent>
      </Card>
    )
  }

  const save = async (patch: Record<string, unknown>) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const next = await updateEmailSendingSettings(access, patch)
      setView(next)
      setDisplayName(next.display_name || '')
      setReplyTo(next.reply_to || '')
      setNotice(isAr ? 'تم الحفظ.' : 'Saved.')
    } catch (err) {
      setError(friendlyDashboardError(err, isAr ? 'تعذر الحفظ.' : 'Could not save.', locale))
    } finally {
      setBusy(false)
    }
  }

  const runPrimary = async () => {
    if (!view?.primary_action) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const res = await emailSendingPrimaryAction(access, { action: view.primary_action.id as 'connect' | 'verify' | 'test' })
      if (res.view) setView(res.view)
      setNotice(res.message || (res.ok ? (isAr ? 'تم.' : 'Done.') : undefined) || null)
    } catch (err) {
      setError(friendlyDashboardError(err, isAr ? 'تعذر تنفيذ الإجراء.' : 'Could not complete that action.', locale))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{isAr ? 'إرسال البريد' : 'Email sending'}</CardTitle>
            <CardDescription>
              {isAr ? 'كيف ترسل وظفني رسائل المرشحين والموظفين؟' : 'How should Wathefni send candidate and employee emails?'}
            </CardDescription>
          </div>
          {view ? <Badge tone={statusTone(view.status)}>{view.status_label}</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4" dir={isAr ? 'rtl' : 'ltr'}>
        {error ? <p className="text-xs text-rose-600">{error}</p> : null}
        {notice ? <p className="text-xs text-emerald-700">{notice}</p> : null}
        {view ? (
          <>
            <div className="space-y-2">
              {view.choices.map((choice) => {
                const selected = view.current_sender === choice.id
                return (
                  <label
                    key={choice.id}
                    className={cn(
                      'flex cursor-pointer items-start gap-3 rounded-2xl border p-3 transition',
                      selected ? 'border-ink/30 bg-white/70' : 'border-line bg-panel-muted/40',
                      !choice.selectable && choice.id !== 'wathefni' ? 'opacity-90' : '',
                    )}
                  >
                    <input
                      type="radio"
                      className="mt-1"
                      name="email-sender"
                      checked={selected}
                      disabled={busy || (!choice.selectable && choice.id !== 'wathefni' && choice.id !== view.current_sender)}
                      onChange={() => {
                        if (!choice.selectable && choice.id !== 'wathefni') {
                          setError(
                            isAr
                              ? 'هذا الخيار غير جاهز بعد. استخدم Connect أو Verify أولاً.'
                              : 'That option is not ready yet. Use Connect or Verify first.',
                          )
                          return
                        }
                        void save({ current_sender: choice.id })
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-text">
                        <span>{choice.title}</span>
                        {choice.recommended ? <Badge tone="success">{isAr ? 'موصى به' : 'Recommended'}</Badge> : null}
                        <Badge tone={statusTone(choice.status)}>
                          {choice.status === 'ready'
                            ? isAr
                              ? 'جاهز'
                              : 'Ready'
                            : choice.status === 'verifying'
                              ? isAr
                                ? 'جارٍ التحقق'
                                : 'Verifying'
                              : choice.status === 'error'
                                ? isAr
                                  ? 'خطأ'
                                  : 'Error'
                                : isAr
                                  ? 'يلزم الإعداد'
                                  : 'Setup required'}
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-subtle">{choice.description}</p>
                    </div>
                  </label>
                )
              })}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-xs text-subtle">
                <span>{isAr ? 'اسم المرسل' : 'Sender display name'}</span>
                <Input
                  value={displayName}
                  disabled={busy}
                  onChange={(e) => setDisplayName(e.target.value)}
                  onBlur={() => {
                    if ((view.display_name || '') !== displayName) void save({ display_name: displayName || null })
                  }}
                  placeholder={isAr ? 'مثال: الموارد البشرية' : 'e.g. People Team'}
                />
              </label>
              <label className="space-y-1 text-xs text-subtle">
                <span>{isAr ? 'الرد إلى' : 'Reply-To'}</span>
                <Input
                  value={replyTo}
                  disabled={busy}
                  onChange={(e) => setReplyTo(e.target.value)}
                  onBlur={() => {
                    if ((view.reply_to || '') !== replyTo) void save({ reply_to: replyTo || null })
                  }}
                  placeholder="hr@company.com"
                />
              </label>
            </div>

            <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/70 bg-white/55 p-4">
              <div className="min-w-0">
                <div className="text-sm font-medium text-text">
                  {isAr ? 'أرسل أيضاً بريداً مع دعوات التقويم' : 'Also send an email with calendar invitations'}
                </div>
                <p className="mt-1 text-xs leading-5 text-subtle">
                  {isAr
                    ? 'عند إرسال دعوة تقويم للمرشح، أرسل أيضاً رسالة وظفني. اتركه مغلقاً لتجنب التكرار.'
                    : 'When a calendar invite already went to the candidate, also send a Wathefni email. Leave off to avoid duplicates.'}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={view.interview_email_when_calendar_sent}
                disabled={busy}
                onClick={() => void save({ interview_email_when_calendar_sent: !view.interview_email_when_calendar_sent })}
                className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${view.interview_email_when_calendar_sent ? 'bg-emerald-500' : 'bg-subtle/40'} disabled:opacity-60`}
              >
                <span
                  className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${view.interview_email_when_calendar_sent ? 'translate-x-5' : 'translate-x-1'}`}
                />
              </button>
            </div>

            {view.current_sender !== 'wathefni' ? (
              <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/70 bg-white/55 p-4">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-text">
                    {isAr ? 'السماح بإرسال طارئ عبر وظفني' : 'Allow Wathefni emergency fallback'}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-subtle">
                    {isAr
                      ? 'إذا تعذّر الإرسال من بريد شركتك، اسمح لوظفني بالإرسال مؤقتاً وسجّل ذلك بوضوح.'
                      : 'If your company sender is unavailable, allow Wathefni to send temporarily and record it clearly.'}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={!!view.allow_wathefni_emergency_fallback}
                  disabled={busy}
                  onClick={() => void save({ allow_wathefni_emergency_fallback: !view.allow_wathefni_emergency_fallback })}
                  className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${view.allow_wathefni_emergency_fallback ? 'bg-emerald-500' : 'bg-subtle/40'} disabled:opacity-60`}
                >
                  <span
                    className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${view.allow_wathefni_emergency_fallback ? 'translate-x-5' : 'translate-x-1'}`}
                  />
                </button>
              </div>
            ) : null}

            {view.hr_notice ? <p className="text-xs text-amber-800">{view.hr_notice}</p> : null}

            {view.primary_action ? (
              <Button type="button" disabled={busy} onClick={() => void runPrimary()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {view.primary_action.label}
              </Button>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

function EmailDocumentIntakeCard({ access, locale }: { access: DashboardAccess; locale: RecruitingLocale }) {
  const isAr = locale === 'ar'
  const [view, setView] = useState<EmailSendingSettingsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void getEmailSendingSettings(access)
      .then((data) => {
        if (active) setView(data)
      })
      .catch((err) => {
        if (active) setError(friendlyDashboardError(err, isAr ? 'تعذر تحميل عنوان الاستقبال.' : 'Could not load intake address.', locale))
      })
    return () => {
      active = false
    }
  }, [access, isAr, locale])

  const addresses = view?.intake?.addresses || []
  const instructions = isAr ? view?.intake?.forward_instructions_ar : view?.intake?.forward_instructions_en

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isAr ? 'استقبال البريد والمستندات' : 'Email & document intake'}</CardTitle>
        <CardDescription>
          {isAr ? 'عنوان وظفني الحالي لتحويل السير الذاتية والمستندات.' : 'Your current Wathefni address for forwarding CVs and documents.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3" dir={isAr ? 'rtl' : 'ltr'}>
        {error ? <p className="text-xs text-rose-600">{error}</p> : null}
        {addresses.length ? (
          <ul className="space-y-2">
            {addresses.map((row) => (
              <li key={row.address} className="rounded-2xl border border-line bg-panel-muted/50 px-3 py-2 text-sm text-text">
                <code className="font-medium">{row.address}</code>
                {row.label ? <div className="text-xs text-subtle">{row.label}</div> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-subtle">{isAr ? 'لا يوجد عنوان استقبال بعد.' : 'No intake address is set up yet.'}</p>
        )}
        {instructions ? <p className="text-xs leading-5 text-subtle">{instructions}</p> : null}
      </CardContent>
    </Card>
  )
}

function IntakeSettingsCard({ access }: { access: DashboardAccess }) {
  const [autoAdmit, setAutoAdmit] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const confirm = useConfirm()

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const data = await getImportSettings(access)
        if (active) setAutoAdmit(data.auto_admit_explicit_imports)
      } catch {
        if (active) setAutoAdmit(null)
      }
    })()
    return () => {
      active = false
    }
  }, [access])

  if (autoAdmit === null) return null

  const toggle = async () => {
    const next = !autoAdmit
    if (
      !(await confirm({
        title: next ? 'Turn on auto-add?' : 'Turn off auto-add?',
        body: next
          ? 'Matching imported candidates will be added to your pipeline automatically without Intake review. Continue?'
          : 'All imported candidates will go to Intake review first before entering your pipeline. Continue?',
        confirmLabel: next ? 'Turn on' : 'Turn off',
      }))
    ) {
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await updateImportSettings(access, next)
      setAutoAdmit(data.auto_admit_explicit_imports)
    } catch (err) {
      setError(friendlyDashboardError(err, 'We couldn’t update this setting right now. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Candidate intake</CardTitle>
        <CardDescription>How imported and emailed CVs enter your pipeline.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/70 bg-white/55 p-4">
          <div className="min-w-0">
            <div className="text-sm font-medium text-text">Auto-add candidates with a clear role</div>
            <p className="mt-1 text-xs leading-5 text-subtle">
              When a CV arrives with a role that clearly matches an open position (a role-specific inbox, or an exact
              role in your sheet), add the candidate to Candidates automatically. They are labelled, never messaged, and
              never ranked without your review. Turn this off to review every import in Intake first.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={autoAdmit}
            disabled={busy}
            onClick={() => void toggle()}
            className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${autoAdmit ? 'bg-emerald-500' : 'bg-subtle/40'} disabled:opacity-60`}
          >
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${autoAdmit ? 'translate-x-5' : 'translate-x-1'}`} />
          </button>
        </div>
        {error ? <p className="text-xs text-rose-600">{error}</p> : null}
      </CardContent>
    </Card>
  )
}

function IntegrationsCard({ access }: { access: DashboardAccess }) {
  const [feature, setFeature] = useState<MailboxFeatureStatus | null>(null)
  const [connection, setConnection] = useState<MailboxConnection | null>(null)
  const [labels, setLabels] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'warning'; text: string } | null>(null)
  const confirm = useConfirm()

  const reload = useCallback(async () => {
    try {
      const data = await getMailboxConnections(access)
      setFeature(data.feature)
      setConnection(data.connections[0] || null)
    } catch {
      setFeature(null)
    }
  }, [access])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const outcome = params.get('mailbox')
    if (!outcome) return
    if (outcome === 'connected') setNotice({ tone: 'success', text: 'Recruitment inbox connected. Choose a label/folder, then turn on Auto-import.' })
    else if (outcome === 'failed') setNotice({ tone: 'warning', text: 'We could not connect that inbox. Please try again.' })
    else if (outcome === 'unavailable') setNotice({ tone: 'warning', text: 'Email inbox import is not available yet.' })
    params.delete('mailbox')
    const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
    window.history.replaceState({}, '', next)
  }, [])

  const loadLabels = useCallback(async (mailboxId: string) => {
    try {
      const data = await getMailboxLabels(access, mailboxId)
      setLabels(data.labels)
    } catch {
      setLabels([])
      setNotice({ tone: 'warning', text: 'Reconnect the inbox to load folders.' })
      void reload()
    }
  }, [access, reload])

  useEffect(() => {
    if (connection?.status === 'connected' && connection.has_credentials) void loadLabels(connection.mailbox_id)
  }, [connection?.mailbox_id, connection?.status, connection?.has_credentials, loadLabels])

  if (!feature?.enabled) return null

  const connect = async () => {
    setBusy(true)
    setNotice(null)
    try {
      const data = await connectMailbox(access, {})
      window.location.href = data.authorize_url
    } catch (error) {
      setNotice({ tone: 'warning', text: friendlyDashboardError(error, 'We couldn’t start the inbox connection right now. Please try again.') })
      setBusy(false)
    }
  }

  const setLabel = async (label: string) => {
    if (!connection) return
    setBusy(true)
    try {
      const res = await updateMailbox(access, connection.mailbox_id, { label_filter: label || null })
      setConnection(res.connection)
    } finally {
      setBusy(false)
    }
  }

  const toggleAuto = async () => {
    if (!connection) return
    const next = !connection.auto_import
    if (
      !(await confirm({
        title: next ? 'Turn on auto-import?' : 'Turn off auto-import?',
        body: next
          ? 'Wathefni will automatically import new CVs from this inbox folder. Continue?'
          : 'Wathefni will stop importing CVs from this inbox automatically. Continue?',
        confirmLabel: next ? 'Turn on' : 'Turn off',
      }))
    ) {
      return
    }
    setBusy(true)
    try {
      const res = await updateMailbox(access, connection.mailbox_id, { auto_import: next })
      setConnection(res.connection)
    } finally {
      setBusy(false)
    }
  }

  const checkNow = async () => {
    if (!connection) return
    setBusy(true)
    setNotice(null)
    try {
      const res = await checkMailboxNow(access, connection.mailbox_id)
      setNotice({ tone: 'success', text: res.message })
      void reload()
    } catch (error) {
      setNotice({ tone: 'warning', text: error instanceof DashboardApiError && error.code === 'mailbox_needs_reconnect' ? 'This inbox needs reconnecting.' : 'Could not check the inbox right now.' })
      void reload()
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    if (!connection) return
    if (
      !(await confirm({
        title: 'Disconnect this inbox?',
        body: 'Wathefni will stop importing CVs from this inbox and remove its connection. You can reconnect later, but it will need to be set up again.',
        confirmLabel: 'Disconnect inbox',
        destructive: true,
      }))
    ) {
      return
    }
    setBusy(true)
    try {
      await disconnectMailbox(access, connection.mailbox_id)
      setConnection(null)
      setLabels([])
      setNotice({ tone: 'success', text: 'Inbox disconnected.' })
    } finally {
      setBusy(false)
    }
  }

  const connected = connection?.status === 'connected' && connection.has_credentials
  const needsReconnect = !!connection && (connection.status === 'needs_reconnect' || connection.status === 'error')

  return (
    <Card className="xl:col-span-2">
      <CardHeader>
        <CardTitle>Integrations</CardTitle>
        <CardDescription>Connect a recruitment inbox so CVs emailed to you land in Import Review automatically.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {notice ? (
          <div className={cn('rounded-2xl border p-3 text-sm leading-6', notice.tone === 'success' ? 'border-emerald-300/60 bg-emerald-50/70 text-emerald-800' : 'border-[#e8c47d]/55 bg-[#fff7e6]/80 text-[#8a5a12]')}>
            {notice.text}
          </div>
        ) : null}

        <div className="rounded-2xl border border-line bg-panel-muted/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/70 text-text"><Inbox size={18} /></span>
              <div>
                <div className="text-sm font-semibold text-text">Recruitment inbox</div>
                <div className="text-xs text-subtle">
                  {connection?.email_address ? connection.email_address : 'Gmail / Google Workspace'}
                </div>
              </div>
            </div>
            <Badge tone={connected ? 'success' : needsReconnect ? 'danger' : 'warning'}>{connection ? connection.status_label : 'Not connected'}</Badge>
          </div>

          {!connection || needsReconnect ? (
            <div className="mt-4">
              <Button disabled={busy} onClick={connect}>
                {busy ? <Loader2 className="animate-spin" size={16} /> : <MessageCircle size={16} />}
                {needsReconnect ? 'Reconnect inbox' : 'Connect recruitment inbox'}
              </Button>
              {!feature.gmail_oauth_ready ? (
                <p className="mt-2 text-xs leading-5 text-subtle">Email connection isn’t available for your workspace yet. Please check back soon.</p>
              ) : null}
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <div className="grid gap-2 md:grid-cols-[1fr_auto] md:items-end">
                <label className="space-y-1">
                  <span className="text-xs uppercase tracking-wide text-subtle">Folder / label to import from</span>
                  <Select disabled={busy} onChange={(event) => void setLabel(event.target.value)} value={connection.label_filter || ''}>
                    <option value="">All mail (not recommended)</option>
                    {connection.label_filter && !labels.includes(connection.label_filter) ? (
                      <option value={connection.label_filter}>{connection.label_filter}</option>
                    ) : null}
                    {labels.map((label) => <option key={label} value={label}>{label}</option>)}
                  </Select>
                </label>
                <Button disabled={busy} onClick={checkNow} variant="secondary">
                  {busy ? <Loader2 className="animate-spin" size={16} /> : <Loader2 size={16} />} Check now
                </Button>
              </div>

              <div className="flex items-center justify-between rounded-xl border border-line/55 bg-panel/70 p-3">
                <div>
                  <div className="text-sm font-medium text-text">Auto-import</div>
                  <div className="text-xs text-subtle">{connection.auto_import ? 'New CVs import automatically.' : 'Off - use Check now to import manually.'}</div>
                </div>
                <Button disabled={busy} onClick={toggleAuto} variant={connection.auto_import ? 'secondary' : 'default'}>
                  {connection.auto_import ? 'Turn off' : 'Turn on'}
                </Button>
              </div>

              <p className="text-xs leading-5 text-subtle">Imported CVs go to Import Review / Needs role. Wathefni only reads this inbox - it never sends, deletes, or marks email as read.</p>
              <Button disabled={busy} onClick={disconnect} variant="ghost">Disconnect inbox</Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
