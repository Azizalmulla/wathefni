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
  createIntakeAddress,
  disableIntakeAddress,
  disconnectMailbox,
  emailSendingPrimaryAction,
  getEmailSendingSettings,
  getImportSettings,
  getMailboxConnections,
  getMailboxLabels,
  getPrehireVisibilityPolicy,
  putPrehireVisibilityPolicy,
  rotateIntakeAddress,
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
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type {
  DashboardAccess,
  DashboardTeamResponse,
  DashboardUserAccess,
  EmailSendingSettingsResponse,
  MailboxConnection,
  MailboxFeatureStatus,
  PositionSummary,
} from '@/types'
import { addressHoldPresentation } from '@/lib/inboundIntakePresentation'

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
  positions = [],
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
  positions?: PositionSummary[]
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
  const [visibilityPolicy, setVisibilityPolicy] = useState<string | null>(null)
  const [visibilityVersion, setVisibilityVersion] = useState<number | null>(null)
  const [visibilityUpdatedAt, setVisibilityUpdatedAt] = useState<string | null>(null)
  const [visibilityUpdatedBy, setVisibilityUpdatedBy] = useState<string | null>(null)
  const [visibilityBusy, setVisibilityBusy] = useState(false)
  const [visibilityError, setVisibilityError] = useState<string | null>(null)
  const [platformNotice, setPlatformNotice] = useState<string | null>(null)
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'

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
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="settings-workspace" data-settings>
      <div className="min-w-0 max-w-2xl space-y-1" data-settings-purpose>
        <p className="text-[13px] text-subtle/90">
          {isAr
            ? 'أدِر من ينتمي هنا، وكيف يسجّلون الدخول، وكيف يتصل وثّفني بأدوات الشركة — دون تغيير صلاحيات الأدوار أو ملكية التسليم.'
            : 'Manage who belongs here, how they sign in, and how Wathefni connects company tools — without changing role permissions or delivery ownership.'}
        </p>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1fr_0.8fr]">
      {canManagePlatformIntegrations ? (
        <div className="xl:col-span-2 space-y-2" data-settings-integrations>
          <div>
            <h2 className="text-[15px] font-semibold text-ink">{isAr ? 'اتصالات المنصة' : 'Company connections'}</h2>
            <p className="text-[13px] text-subtle">
              {isAr
                ? 'ربط Google Workspace وMicrosoft 365 للتقويم والبريد عندما تملك صلاحية الإعدادات ومزامنة التقويم.'
                : 'Connect Google Workspace and Microsoft 365 for calendar and email when you have settings and calendar access.'}
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
      <Card data-settings-account>
        <CardHeader>
          <CardTitle>{isAr ? 'الحساب' : 'Account'}</CardTitle>
          <CardDescription>{isAr ? 'هويتك الموقَّعة في مساحة عمل وثّفني.' : 'Your signed-in Wathefni workspace identity.'}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {recoveryAccess ? (
            <div className="rounded-2xl border border-[#e8c47d]/55 bg-[#fff7e6]/80 p-4 text-sm leading-6 text-[#8a5a12]">
              You’re signed in with a backup access code. Create or sign in to a workspace account for everyday use.
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-2">
            <Info label={isAr ? 'الاسم' : 'Name'} value={account?.name || (isAr ? 'لم يُحمّل بعد' : 'Not loaded yet')} />
            <Info label={isAr ? 'البريد' : 'Email'} value={account?.email || access.email || (isAr ? 'لم يُحمّل بعد' : 'Not loaded yet')} />
            <Info label={isAr ? 'الدور' : 'Role'} value={(account?.role && ROLE_LABELS_UI[account.role]) || userAccess?.role_label || account?.role_label || (isAr ? 'لم يُحمّل بعد' : 'Not loaded yet')} />
            <Info label={isAr ? 'الشركة' : 'Company'} value={account?.company_code || access.companyCode || 'WATHEFNI'} />
            <Info label={isAr ? 'الحالة' : 'Status'} value={account?.status ? stageLabel(account.status) : (isAr ? 'لم يُحمّل بعد' : 'Not loaded yet')} />
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
                disabled={visibilityBusy || visibilityPolicy == null}
                onChange={(event) => void saveVisibilityPolicy(event.target.value)}
                value={visibilityPolicy ?? ''}
              >
                {visibilityPolicy == null ? (
                  <option value="">{locale === 'ar' ? 'جاري التحميل…' : 'Loading…'}</option>
                ) : null}
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
              <LogOut size={16} /> {isAr ? 'تسجيل الخروج' : 'Log out'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card data-settings-access>
        <CardHeader>
          <CardTitle>{isAr ? 'الوصول' : 'Your access'}</CardTitle>
          <CardDescription>{isAr ? 'دورك، وما يمكنك فعله، وربط واتساب.' : 'Your role, what you can do, and WhatsApp linking.'}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <details className="rounded-lg border border-line bg-panel-muted/60 p-3">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-subtle">{isAr ? 'ما يمكنك فعله' : 'What you can do'}</summary>
            <div className="mt-2 space-y-1 text-sm leading-6 text-text">
              {readableCapabilities(userAccess).length ? (
                readableCapabilities(userAccess).map((capability) => <div key={capability}>{capability}</div>)
              ) : (
                <div className="text-subtle">{isAr ? 'تحقق من الوصول لتحميل صلاحيات دورك.' : 'Verify access to load your role capabilities.'}</div>
              )}
            </div>
          </details>
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
      <Card className="xl:col-span-2" data-settings-team>
        <CardHeader>
          <CardTitle>{isAr ? 'الفريق' : 'Team'}</CardTitle>
          <CardDescription>{isAr ? 'ادعُ أعضاء الفريق وعيّن أدوار وثّفني المدمجة.' : 'Invite teammates and assign Wathefni’s built-in roles.'}</CardDescription>
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
      {prehireEnabled && hasDashboardPermission(userAccess, 'candidate.import') ? <IntakeSettingsCard access={access} locale={locale as RecruitingLocale} /> : null}
      {canManageSettings ? (
        <div className="xl:col-span-2 space-y-4" data-settings-communications>
          <div>
            <h2 className="text-[15px] font-semibold text-ink">{isAr ? 'الاتصالات' : 'Communications'}</h2>
            <p className="text-[13px] text-subtle">
              {isAr ? 'كيف يرسل وثّفني الرسائل ويستقبل المستندات.' : 'How Wathefni sends messages and receives documents.'}
            </p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <EmailSendingCard access={access} locale={locale as RecruitingLocale} />
            <EmailDocumentIntakeCard access={access} locale={locale as RecruitingLocale} positions={positions} />
          </div>
          {prehireEnabled && canManageUsers ? (
            <MailboxConnectorCard access={access} locale={locale as RecruitingLocale} />
          ) : null}
        </div>
      ) : null}
      </div>
      <p className="text-[11.5px] text-subtle/75" data-settings-ownership>
        {isAr
          ? 'الإعدادات تدير الوصول والاتصالات. إطلاق الوحدات في وحدة الإعداد، وفشل التسليم في التنبيهات والتسليم.'
          : 'Settings manages access and connections. Module launch stays in Setup Console; delivery failures stay in Alerts & Delivery.'}
      </p>
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

function EmailDocumentIntakeCard({
  access,
  locale,
  positions = [],
}: {
  access: DashboardAccess
  locale: RecruitingLocale
  positions?: PositionSummary[]
}) {
  const isAr = locale === 'ar'
  const confirm = useConfirm()
  const [view, setView] = useState<EmailSendingSettingsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [label, setLabel] = useState('')
  const [aliasMode, setAliasMode] = useState<'general' | 'job'>('general')
  const [positionCode, setPositionCode] = useState('')
  const [copied, setCopied] = useState<string | null>(null)
  const openJobs = positions.filter((job) => String(job.status || '').toLowerCase() === 'open')

  const reload = useCallback(async () => {
    const data = await getEmailSendingSettings(access)
    setView(data)
  }, [access])

  useEffect(() => {
    let active = true
    void reload()
      .then(() => {
        if (!active) return
        setError(null)
      })
      .catch((err) => {
        if (active) setError(friendlyDashboardError(err, isAr ? 'تعذر تحميل عنوان الاستقبال.' : 'Could not load intake address.', locale))
      })
    return () => {
      active = false
    }
  }, [reload, isAr, locale])

  const intake = view?.intake
  const feature = intake?.feature
  const addresses = intake?.addresses || []
  const activeAddresses = addresses.filter((row) => (row.status || 'active') === 'active')
  const instructions = isAr ? intake?.forward_instructions_ar : intake?.forward_instructions_en
  const steps = isAr ? intake?.setup_steps_ar || [] : intake?.setup_steps_en || []
  const health = feature?.health
  const enabled = Boolean(feature?.enabled)
  const allowlisted = feature?.allowlisted !== false

  const copyAddress = async (address: string) => {
    try {
      await navigator.clipboard.writeText(address)
      setCopied(address)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      setError(isAr ? 'تعذر نسخ العنوان.' : 'Could not copy the address.')
    }
  }

  const createAddress = async () => {
    if (aliasMode === 'job' && !positionCode) {
      setError(isAr ? 'اختر وظيفة مفتوحة للاسم المستعار.' : 'Pick an open job for the alias.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const job = openJobs.find((row) => row.position_code === positionCode)
      await createIntakeAddress(access, {
        label: label.trim() || null,
        position_code: aliasMode === 'job' ? positionCode : null,
        position_title: aliasMode === 'job' ? job?.position_title || positionCode : null,
      })
      setLabel('')
      setPositionCode('')
      setAliasMode('general')
      await reload()
    } catch (err) {
      setError(friendlyDashboardError(err, isAr ? 'تعذر إنشاء عنوان الاستقبال.' : 'Could not create an intake address.', locale))
    } finally {
      setBusy(false)
    }
  }

  const rotateAddress = async (intakeId: string, address: string) => {
    if (
      !(await confirm({
        title: isAr ? 'تدوير العنوان؟' : 'Rotate this address?',
        body: isAr
          ? `سيتم إيقاف ${address} وإنشاء عنوان جديد. حدّث قاعدة التحويل في بريد شركتك.`
          : `${address} will be disabled and a new address created. Update your company forwarding rule.`,
        confirmLabel: isAr ? 'تدوير' : 'Rotate',
      }))
    ) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await rotateIntakeAddress(access, intakeId)
      await reload()
    } catch (err) {
      setError(friendlyDashboardError(err, isAr ? 'تعذر تدوير العنوان.' : 'Could not rotate the address.', locale))
    } finally {
      setBusy(false)
    }
  }

  const disableAddress = async (intakeId: string, address: string) => {
    if (
      !(await confirm({
        title: isAr ? 'إيقاف العنوان؟' : 'Disable this address?',
        body: isAr
          ? `لن يستقبل ${address} سيرًا جديدة بعد الآن.`
          : `${address} will stop accepting new CVs.`,
        confirmLabel: isAr ? 'إيقاف' : 'Disable',
      }))
    ) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await disableIntakeAddress(access, intakeId)
      await reload()
    } catch (err) {
      setError(friendlyDashboardError(err, isAr ? 'تعذر إيقاف العنوان.' : 'Could not disable the address.', locale))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card data-testid="email-document-intake-card">
      <CardHeader>
        <CardTitle>{isAr ? 'استقبال البريد والمستندات' : 'Email & document intake'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'أنشئ عنواناً عاماً أو اسماً مستعاراً لوظيفة، ثم حوّل بريد التوظيف إليه. هذا هو المسار الافتراضي.'
            : 'Create a general address or a job-specific alias, then forward recruitment mail to it. This is the default product path.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4" dir={isAr ? 'rtl' : 'ltr'}>
        {error ? <p className="text-xs text-rose-600">{error}</p> : null}

        <div className="flex flex-wrap items-center gap-2 text-xs text-subtle">
          <Badge tone={enabled ? 'success' : 'muted'}>
            {enabled ? (isAr ? 'مفعّل' : 'Enabled') : isAr ? 'غير مفعّل' : 'Not enabled'}
          </Badge>
          {health?.last_received_at ? (
            <span>
              {isAr ? 'آخر استلام:' : 'Last received:'} {formatDateTime(health.last_received_at)}
              {typeof health.received_7d === 'number' ? ` · ${health.received_7d} / 7d` : null}
            </span>
          ) : (
            <span>{isAr ? 'لم يُستلم بريد بعد عبر هذا المسار.' : 'No mail received on this path yet.'}</span>
          )}
        </div>

        {!allowlisted ? (
          <p className="text-sm text-subtle">
            {isAr
              ? 'استقبال التحويل متاح حالياً لمستأجري وظفني والاختبار فقط.'
              : 'Forwarded intake is limited to Wathefni and test tenants in this phase.'}
          </p>
        ) : null}

        {enabled ? (
          <>
            {activeAddresses.length ? (
              <ul className="space-y-2">
                {activeAddresses.map((row) => {
                  const hold = addressHoldPresentation(Boolean(row.role_bound), locale)
                  return (
                    <li key={row.intake_id || row.address} className="rounded-2xl border border-line bg-panel-muted/50 px-3 py-3 text-sm text-text">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0 space-y-1">
                          <code className="font-medium break-all">{row.address}</code>
                          {row.label ? <div className="text-xs text-subtle">{row.label}</div> : null}
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <Badge tone={hold.tone}>{hold.label}</Badge>
                            <span className="text-subtle">
                              {row.role_bound
                                ? `${row.position_title || row.position_code}`
                                : hold.hint}
                            </span>
                          </div>
                          {row.health?.last_received_at ? (
                            <div className="text-xs text-subtle">
                              {isAr ? 'آخر استلام:' : 'Last received:'} {formatDateTime(row.health.last_received_at)}
                            </div>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void copyAddress(row.address)}>
                            <Copy size={14} /> {copied === row.address ? (isAr ? 'تم' : 'Copied') : isAr ? 'نسخ' : 'Copy'}
                          </Button>
                          {row.intake_id ? (
                            <>
                              <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void rotateAddress(row.intake_id!, row.address)}>
                                {isAr ? 'تدوير' : 'Rotate'}
                              </Button>
                              <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => void disableAddress(row.intake_id!, row.address)}>
                                {isAr ? 'إيقاف' : 'Disable'}
                              </Button>
                            </>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="text-sm text-subtle">{isAr ? 'لا يوجد عنوان استقبال بعد.' : 'No intake address is set up yet.'}</p>
            )}

            <div className="space-y-3 rounded-2xl border border-line/70 bg-panel/40 p-3" data-testid="intake-alias-create">
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={aliasMode === 'general' ? 'default' : 'secondary'}
                  onClick={() => setAliasMode('general')}
                >
                  {isAr ? 'عنوان عام' : 'General address'}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={aliasMode === 'job' ? 'default' : 'secondary'}
                  onClick={() => setAliasMode('job')}
                >
                  {isAr ? 'اسم مستعار لوظيفة' : 'Job-specific alias'}
                </Button>
              </div>
              <p className="text-xs text-subtle">
                {aliasMode === 'job'
                  ? addressHoldPresentation(true, locale).hint
                  : addressHoldPresentation(false, locale).hint}
              </p>
              <div className="flex flex-wrap items-end gap-2">
                <div className="min-w-[12rem] flex-1">
                  <label className="mb-1 block text-xs text-subtle">{isAr ? 'تسمية اختيارية' : 'Optional label'}</label>
                  <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={isAr ? 'مثل: التوظيف العام' : 'e.g. General careers'} />
                </div>
                {aliasMode === 'job' ? (
                  <div className="min-w-[12rem] flex-1">
                    <label className="mb-1 block text-xs text-subtle">{isAr ? 'وظيفة مفتوحة' : 'Open job'}</label>
                    <Select value={positionCode} onChange={(e) => setPositionCode(e.target.value)}>
                      <option value="">{isAr ? 'اختر وظيفة…' : 'Select a job…'}</option>
                      {openJobs.map((job) => (
                        <option key={job.position_code} value={job.position_code}>
                          {job.position_title || job.position_code}
                        </option>
                      ))}
                    </Select>
                  </div>
                ) : null}
                <Button type="button" disabled={busy} onClick={() => void createAddress()}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus size={16} />}
                  {aliasMode === 'job'
                    ? isAr
                      ? 'إنشاء اسم مستعار'
                      : 'Create alias'
                    : isAr
                      ? 'إنشاء عنوان'
                      : 'Create address'}
                </Button>
              </div>
            </div>
          </>
        ) : allowlisted ? (
          <p className="text-sm text-subtle">
            {isAr ? 'الاستقبال غير مفعّل لهذا المستأجر حالياً.' : 'Intake is not enabled for this tenant right now.'}
          </p>
        ) : null}

        {instructions ? <p className="text-xs leading-5 text-subtle">{instructions}</p> : null}
        {steps.length ? (
          <ol className="list-decimal space-y-1 ps-4 text-xs leading-5 text-subtle">
            {steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        ) : null}
      </CardContent>
    </Card>
  )
}

function IntakeSettingsCard({ access, locale = 'en' }: { access: DashboardAccess; locale?: RecruitingLocale }) {
  const isAr = locale === 'ar'
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
          ? 'Matching imported candidates will be added to your pipeline automatically. Continue?'
          : 'Imported candidates without a clear job will stay held until you assign one. Continue?',
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
    <Card data-settings-intake>
      <CardHeader>
        <CardTitle>{isAr ? 'استقبال المرشحين' : 'Candidate intake'}</CardTitle>
        <CardDescription>{isAr ? 'كيف تدخل السير الذاتية المستوردة والمرسلة بالبريد إلى المسار.' : 'How imported and emailed CVs enter your hiring pipeline.'}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/70 bg-white/55 p-4">
          <div className="min-w-0">
            <div className="text-sm font-medium text-text">{isAr ? 'إضافة المرشحين تلقائياً عند وضوح الدور' : 'Auto-add candidates with a clear role'}</div>
            <p className="mt-1 text-xs leading-5 text-subtle">
              {isAr
                ? 'عند وصول سيرة ذاتية بدور يطابق وظيفة مفتوحة بوضوح، تُضاف إلى المرشحين تلقائياً — دون مراسلة أو ترتيب دون مراجعتك. أوقف هذا لمراجعة كل استيراد أولاً.'
                : 'When a CV clearly matches an open role, add the candidate automatically. They are labelled, never messaged, and never ranked without your review. Turn this off to review every import first.'}
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

/** Wave D5 — optional premium Gmail / M365 mailbox connector (durable pipeline). */
function MailboxConnectorCard({ access, locale }: { access: DashboardAccess; locale: RecruitingLocale }) {
  const isAr = locale === 'ar'
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
    if (outcome === 'connected') {
      setNotice({
        tone: 'success',
        text: isAr
          ? 'تم ربط صندوق التوظيف. اختر مجلداً ثم فعّل المزامنة.'
          : 'Recruitment mailbox connected. Choose a folder, then enable sync.',
      })
    } else if (outcome === 'failed') {
      setNotice({
        tone: 'warning',
        text: isAr ? 'تعذر ربط الصندوق. حاول مرة أخرى.' : 'We could not connect that mailbox. Please try again.',
      })
    } else if (outcome === 'unavailable') {
      setNotice({
        tone: 'warning',
        text: isAr ? 'ربط صندوق البريد غير متاح حالياً.' : 'Mailbox connection is not available yet.',
      })
    }
    params.delete('mailbox')
    const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
    window.history.replaceState({}, '', next)
  }, [isAr])

  const loadLabels = useCallback(async (mailboxId: string) => {
    try {
      const data = await getMailboxLabels(access, mailboxId)
      setLabels(data.labels)
    } catch {
      setLabels([])
      setNotice({
        tone: 'warning',
        text: isAr ? 'أعد ربط الصندوق لتحميل المجلدات.' : 'Reconnect the mailbox to load folders.',
      })
      void reload()
    }
  }, [access, isAr, reload])

  useEffect(() => {
    if (connection?.status === 'connected' && connection.has_credentials) void loadLabels(connection.mailbox_id)
  }, [connection?.mailbox_id, connection?.status, connection?.has_credentials, loadLabels])

  // Hidden unless premium flag + OAuth ready (fail-closed). Forwarding remains default.
  if (!feature?.enabled) return null

  const connect = async () => {
    setBusy(true)
    setNotice(null)
    try {
      const data = await connectMailbox(access, {})
      window.location.href = data.authorize_url
    } catch (error) {
      setNotice({
        tone: 'warning',
        text: friendlyDashboardError(
          error,
          isAr ? 'تعذر بدء ربط الصندوق.' : 'Could not start the mailbox connection.',
          locale,
        ),
      })
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

  const toggleSync = async () => {
    if (!connection) return
    const next = !connection.auto_import
    if (
      !(await confirm({
        title: next
          ? isAr
            ? 'تفعيل المزامنة؟'
            : 'Enable sync?'
          : isAr
            ? 'إيقاف المزامنة؟'
            : 'Pause sync?',
        body: next
          ? isAr
            ? 'ستُدخل الرسائل الجديدة من هذا المجلد إلى مسار الاستقبال الآمن نفسه المستخدم في التحويل.'
            : 'New mail from this folder will enter the same durable intake pipeline used by forwarding.'
          : isAr
            ? 'سيتوقف سحب الرسائل تلقائياً. يمكنك المزامنة يدوياً لاحقاً.'
            : 'Wathefni will stop pulling mail automatically. You can sync manually later.',
        confirmLabel: next ? (isAr ? 'تفعيل' : 'Enable') : isAr ? 'إيقاف' : 'Pause',
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
      setNotice({
        tone: 'warning',
        text:
          error instanceof DashboardApiError && error.code === 'mailbox_needs_reconnect'
            ? isAr
              ? 'هذا الصندوق يحتاج إعادة ربط.'
              : 'This mailbox needs reconnecting.'
            : isAr
              ? 'تعذر فحص الصندوق الآن.'
              : 'Could not check the mailbox right now.',
      })
      void reload()
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    if (!connection) return
    if (
      !(await confirm({
        title: isAr ? 'قطع اتصال الصندوق؟' : 'Disconnect this mailbox?',
        body: isAr
          ? 'سيتوقف سحب السير ويُحذف الربط. يمكنك إعادة الربط لاحقاً.'
          : 'Wathefni will stop syncing CVs and remove this connection. You can reconnect later.',
        confirmLabel: isAr ? 'قطع الاتصال' : 'Disconnect',
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
      setNotice({ tone: 'success', text: isAr ? 'تم قطع الاتصال.' : 'Mailbox disconnected.' })
    } finally {
      setBusy(false)
    }
  }

  const connected = connection?.status === 'connected' && connection.has_credentials
  const needsReconnect = !!connection && (connection.status === 'needs_reconnect' || connection.status === 'error')
  const lastSync = connection?.last_synced_at
    ? new Date(connection.last_synced_at).toLocaleString(isAr ? 'ar-KW' : 'en-GB')
    : isAr
      ? 'لا يوجد بعد'
      : 'Never'

  return (
    <Card className="xl:col-span-2" data-testid="mailbox-connector-card" dir={isAr ? 'rtl' : 'ltr'}>
      <CardHeader>
        <CardTitle>{isAr ? 'ربط صندوق التوظيف (اختياري)' : 'Recruitment mailbox connector (optional)'}</CardTitle>
        <CardDescription>
          {isAr
            ? 'مسار مميز للشركات التي لا تريد التحويل. المسار الافتراضي يبقى تحويل البريد إلى عنوان وظفني.'
            : 'Premium path for companies that prefer not to forward. Forwarding to a Wathefni address remains the default product.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {notice ? (
          <div
            className={cn(
              'rounded-2xl border p-3 text-sm leading-6',
              notice.tone === 'success'
                ? 'border-emerald-300/60 bg-emerald-50/70 text-emerald-800'
                : 'border-[#e8c47d]/55 bg-[#fff7e6]/80 text-[#8a5a12]',
            )}
          >
            {notice.text}
          </div>
        ) : null}

        <p className="text-xs leading-5 text-subtle">
          {isAr
            ? 'الصلاحيات قراءة فقط. كل رسالة تدخل مسار الحجر والفحص والإضافة الصريحة نفسه المستخدم في التحويل.'
            : 'Read-only permissions. Every message enters the same quarantine, scan, and explicit-admit pipeline as forwarded mail.'}
        </p>

        <div className="rounded-2xl border border-line bg-panel-muted/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/70 text-text">
                <Inbox size={18} />
              </span>
              <div>
                <div className="text-sm font-semibold text-text">
                  {isAr ? 'صندوق التوظيف' : 'Recruitment mailbox'}
                </div>
                <div className="text-xs text-subtle">
                  {connection?.email_address
                    ? connection.email_address
                    : isAr
                      ? 'Gmail أو Microsoft 365'
                      : 'Gmail or Microsoft 365'}
                </div>
                <div className="mt-1 text-xs text-subtle">
                  {isAr ? 'آخر مزامنة' : 'Last sync'}: {lastSync}
                </div>
              </div>
            </div>
            <Badge tone={connected ? 'success' : needsReconnect ? 'danger' : 'warning'}>
              {connection
                ? connection.status_label
                : isAr
                  ? 'غير متصل'
                  : 'Not connected'}
            </Badge>
          </div>

          {!connection || needsReconnect ? (
            <div className="mt-4 space-y-2">
              <Button disabled={busy} onClick={connect}>
                {busy ? <Loader2 className="animate-spin" size={16} /> : <MessageCircle size={16} />}
                {needsReconnect
                  ? isAr
                    ? 'إعادة الربط'
                    : 'Reconnect'
                  : isAr
                    ? 'ربط صندوق التوظيف'
                    : 'Connect recruitment mailbox'}
              </Button>
              {!feature.gmail_oauth_ready && !(feature as { m365_oauth_ready?: boolean }).m365_oauth_ready ? (
                <p className="text-xs leading-5 text-subtle">
                  {isAr
                    ? 'ربط الصندوق غير مفعّل لمساحتك بعد.'
                    : 'Mailbox connection is not enabled for your workspace yet.'}
                </p>
              ) : null}
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <div className="grid gap-2 md:grid-cols-[1fr_auto] md:items-end">
                <label className="space-y-1">
                  <span className="text-xs uppercase tracking-wide text-subtle">
                    {isAr ? 'المجلد / التسمية للقراءة' : 'Folder / label to read'}
                  </span>
                  <Select disabled={busy} onChange={(event) => void setLabel(event.target.value)} value={connection.label_filter || ''}>
                    <option value="">{isAr ? 'كل البريد (غير مستحسن)' : 'All mail (not recommended)'}</option>
                    {connection.label_filter && !labels.includes(connection.label_filter) ? (
                      <option value={connection.label_filter}>{connection.label_filter}</option>
                    ) : null}
                    {labels.map((label) => (
                      <option key={label} value={label}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </label>
                <Button disabled={busy} onClick={checkNow} variant="secondary">
                  {busy ? <Loader2 className="animate-spin" size={16} /> : null}
                  {isAr ? 'مزامنة الآن' : 'Sync now'}
                </Button>
              </div>

              <div className="flex items-center justify-between rounded-xl border border-line/55 bg-panel/70 p-3">
                <div>
                  <div className="text-sm font-medium text-text">{isAr ? 'المزامنة التلقائية' : 'Automatic sync'}</div>
                  <div className="text-xs text-subtle">
                    {connection.auto_import
                      ? isAr
                        ? 'مفعّلة — السحب الدوري مسموح.'
                        : 'On — scheduled pulls are allowed.'
                      : isAr
                        ? 'متوقفة — استخدم مزامنة الآن يدوياً.'
                        : 'Paused — use Sync now manually.'}
                  </div>
                </div>
                <Button disabled={busy} onClick={toggleSync} variant={connection.auto_import ? 'secondary' : 'default'}>
                  {connection.auto_import ? (isAr ? 'إيقاف' : 'Pause') : isAr ? 'تفعيل' : 'Enable'}
                </Button>
              </div>

              <p className="text-xs leading-5 text-subtle">
                {isAr
                  ? 'وظفني يقرأ فقط — لا يرسل ولا يحذف ولا يعلّم الرسائل كمقروءة. السير المعلّقة تُدار من المرشحين.'
                  : 'Wathefni only reads — it never sends, deletes, or marks mail as read. Held CVs are managed from Candidates.'}
              </p>
              <div className="flex flex-wrap gap-2">
                {needsReconnect ? (
                  <Button disabled={busy} onClick={connect} variant="secondary">
                    {isAr ? 'إعادة الربط' : 'Reconnect'}
                  </Button>
                ) : null}
                <Button disabled={busy} onClick={disconnect} variant="ghost">
                  {isAr ? 'قطع الاتصال' : 'Disconnect'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
