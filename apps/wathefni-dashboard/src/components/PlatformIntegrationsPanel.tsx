import { useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  connectGoogleEnterprise,
  connectMicrosoftEnterprise,
  disconnectCalendarSync,
  disconnectPlatformIntegration,
  ensureCalendarLegacyOperatorSync,
  getPlatformIntegrationChecklist,
  getPlatformIntegrations,
  healthcheckPlatformIntegration,
  reconnectCalendarSync,
  startPlatformOAuth,
  updateCalendarSyncConnection,
  type PlatformCompanyIntegration,
} from '@/lib/api'
import { useCalendarSyncConnectionsQuery } from '@/lib/query/hooks'
import { qk } from '@/lib/query/keys'
import type { DashboardAccess } from '@/types'

type Props = {
  access: DashboardAccess
  locale?: 'en' | 'ar'
  onNotice?: (text: string, kind?: 'success' | 'error') => void
  /** integrations = HR-facing connect UI; advanced = legacy/diagnostics/projections */
  variant?: 'integrations' | 'advanced'
}

function statusLabel(status: string | undefined, isAr: boolean) {
  const s = String(status || '').toLowerCase()
  if (s === 'connected') return isAr ? 'متصل' : 'Connected'
  if (s === 'reconnect_required') return isAr ? 'يلزم إعادة الربط' : 'Needs reconnect'
  if (s === 'disconnected' || s === 'revoked') return isAr ? 'غير متصل' : 'Disconnected'
  if (s === 'error') return isAr ? 'يحتاج انتباهاً' : 'Needs attention'
  if (!s) return isAr ? '—' : '—'
  return isAr ? 'حالة الاتصال' : 'Connection status'
}

function providerLabel(key: string | undefined, isAr: boolean) {
  if (key === 'microsoft_365') return 'Microsoft 365'
  if (key === 'google_workspace') return 'Google Workspace'
  return key || (isAr ? 'اتصال' : 'Connection')
}

/**
 * Company platform integrations console (Google Workspace / Microsoft 365).
 * Long-term integration authority lives in Settings — not Calendar.
 * Caller must gate with settings.manage AND calendar.sync.
 */
export function PlatformIntegrationsPanel({ access, locale = 'en', onNotice, variant = 'integrations' }: Props) {
  const queryClient = useQueryClient()
  const isAr = locale === 'ar'
  const advanced = variant === 'advanced'
  const [platformIntegrations, setPlatformIntegrations] = useState<PlatformCompanyIntegration[]>([])
  const [hideCandidateNames, setHideCandidateNames] = useState(true)
  const [connectProvider, setConnectProvider] = useState<'google_workspace' | 'microsoft_365' | null>(null)
  const [connectMode, setConnectMode] = useState<'enterprise_app' | 'enterprise_dwd' | 'oauth_delegated' | null>(null)
  const [checklist, setChecklist] = useState<Record<string, unknown> | null>(null)
  const [connectBusy, setConnectBusy] = useState(false)
  const [m365Tenant, setM365Tenant] = useState('')
  const [m365ClientId, setM365ClientId] = useState('')
  const [m365Secret, setM365Secret] = useState('')
  const [m365Identity, setM365Identity] = useState('')
  const [googleImpersonate, setGoogleImpersonate] = useState('')
  const [googleSaJson, setGoogleSaJson] = useState('')
  const [localNotice, setLocalNotice] = useState<{ text: string; kind: 'success' | 'error' } | null>(null)

  const syncConnectionsQuery = useCalendarSyncConnectionsQuery(access, advanced)
  const syncConnections = syncConnectionsQuery.data?.connections || []

  const notify = (text: string, kind: 'success' | 'error' = 'success') => {
    onNotice?.(text, kind)
    if (!onNotice) setLocalNotice({ text, kind })
  }

  useEffect(() => {
    let cancelled = false
    void getPlatformIntegrations(access)
      .then((res) => {
        if (!cancelled) setPlatformIntegrations(res.integrations || [])
      })
      .catch(() => {
        if (!cancelled) setPlatformIntegrations([])
      })
    return () => {
      cancelled = true
    }
  }, [access])

  if (advanced) {
    return (
      <div className="space-y-4" dir={isAr ? 'rtl' : 'ltr'} data-settings-advanced-integrations>
        {localNotice ? (
          <p className={`text-sm ${localNotice.kind === 'error' ? 'text-[#9a3412]' : 'text-[#3f6b3a]'}`}>{localNotice.text}</p>
        ) : null}

        <div className="rounded-[1.25rem] border border-line/55 bg-white p-4">
          <p className="text-[13px] font-semibold text-ink">{isAr ? 'أدوات المشغّل القديمة' : 'Legacy operator tools'}</p>
          <p className="mt-1 text-[12.5px] text-muted">
            {isAr
              ? 'للمسؤولين فقط — تمثيل اتصال التقويم القديم عند الهجرة أو الاسترداد.'
              : 'Admin only — restore the older calendar operator link during migration or recovery.'}
          </p>
          <Button
            type="button"
            variant="secondary"
            className="mt-3"
            data-settings-legacy-operator
            onClick={() => {
              void ensureCalendarLegacyOperatorSync(access)
                .then(() => {
                  notify(isAr ? 'تم تجهيز اتصال التقويم الاحتياطي' : 'Backup calendar connection is ready', 'success')
                  void queryClient.invalidateQueries({ queryKey: qk.calendarSyncConnections(access) })
                })
                .catch((err) => notify(err instanceof Error ? err.message : (isAr ? 'تعذر تجهيز الاتصال الاحتياطي' : 'Could not prepare backup connection'), 'error'))
            }}
          >
            {isAr ? 'تجهيز اتصال التقويم الاحتياطي' : 'Prepare backup calendar connection'}
          </Button>
        </div>

        <div className="rounded-[1.25rem] border border-line/55 bg-white p-4">
          <p className="text-[13px] font-semibold text-ink">{isAr ? 'تشخيص اتصالات المنصة' : 'Connection diagnostics'}</p>
          <p className="mt-1 text-[12.5px] text-muted">
            {isAr ? 'معرّفات داخلية وحالات خام للمساعدة في الدعم.' : 'Internal identifiers and raw states for support troubleshooting.'}
          </p>
          {platformIntegrations.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{isAr ? 'لا اتصالات منصة بعد.' : 'No platform connections yet.'}</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {platformIntegrations.map((integ) => (
                <li key={integ.integration_id} className="rounded-xl border border-line/50 bg-[#fbf7f1] px-3 py-2 text-sm">
                  <div className="font-medium text-ink">
                    {providerLabel(integ.provider_key, isAr)} · {integ.connection_mode || '—'} · {integ.status}
                  </div>
                  <div className="text-xs text-muted">
                    id: {integ.integration_id}
                    {integ.last_error ? ` · ${integ.last_error}` : ''}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <button
                      type="button"
                      className="underline"
                      onClick={() => {
                        void healthcheckPlatformIntegration(access, integ.integration_id)
                          .then((res) => {
                            notify(isAr ? 'تم فحص الاتصال' : 'Health checked', res.ok ? 'success' : 'error')
                            setPlatformIntegrations((prev) =>
                              prev.map((x) => (x.integration_id === res.integration.integration_id ? res.integration : x)),
                            )
                          })
                          .catch((err) => notify(err instanceof Error ? err.message : 'Health failed', 'error'))
                      }}
                    >
                      {isAr ? 'فحص الصحة' : 'Health check'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-[1.25rem] border border-line/55 bg-white p-4">
          <p className="text-[13px] font-semibold text-ink">{isAr ? 'مزامنة التقويم (تفصيلي)' : 'Calendar sync detail'}</p>
          <p className="mt-1 text-[12.5px] text-muted">
            {isAr ? 'حالات المزامنة الخام ومعرّفات الربط.' : 'Raw sync states and link identifiers.'}
          </p>
          {syncConnectionsQuery.isPending ? (
            <p className="mt-3 flex items-center gap-2 text-sm text-muted">
              <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جاري التحميل…' : 'Loading…'}
            </p>
          ) : syncConnections.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{isAr ? 'لا توجد اتصالات مزامنة بعد.' : 'No calendar sync connections yet.'}</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {syncConnections.map((c) => (
                <li key={c.connection_id} className="rounded-xl border border-line/50 bg-[#fbf7f1] px-3 py-2 text-sm">
                  <div className="font-medium text-ink">
                    {c.display_name || c.account_email || c.provider_key} · {c.mode} · {c.status}
                  </div>
                  <div className="text-xs text-muted">
                    connection_id: {c.connection_id}
                    {c.platform_integration_id ? ` · platform_integration_id: ${c.platform_integration_id}` : ''}
                    {c.last_error ? ` · ${c.last_error}` : ''}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <button
                      type="button"
                      className="underline"
                      onClick={() => {
                        void updateCalendarSyncConnection(access, c.connection_id, {
                          sync_include_candidate_name: !hideCandidateNames,
                        })
                          .then((res) => {
                            setHideCandidateNames(!res.connection.sync_include_candidate_name)
                            notify(isAr ? 'تم تحديث سياسة الخصوصية' : 'Privacy policy updated', 'success')
                            void queryClient.invalidateQueries({ queryKey: qk.calendarSyncConnections(access) })
                          })
                          .catch((err) => notify(err instanceof Error ? err.message : 'Update failed', 'error'))
                      }}
                    >
                      {hideCandidateNames ? (isAr ? 'الأسماء مخفية' : 'Names hidden') : isAr ? 'الأسماء ظاهرة' : 'Names visible'}
                    </button>
                    {c.status === 'connected' ? (
                      <button
                        type="button"
                        className="underline"
                        onClick={() => {
                          void disconnectCalendarSync(access, c.connection_id)
                            .then(() => {
                              notify(isAr ? 'تم قطع الاتصال' : 'Disconnected', 'success')
                              void queryClient.invalidateQueries({ queryKey: qk.calendarSyncConnections(access) })
                            })
                            .catch((err) => notify(err instanceof Error ? err.message : 'Disconnect failed', 'error'))
                        }}
                      >
                        {isAr ? 'قطع' : 'Disconnect'}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="underline"
                        onClick={() => {
                          void reconnectCalendarSync(access, c.connection_id)
                            .then(() => {
                              notify(isAr ? 'تمت إعادة الاتصال' : 'Reconnected', 'success')
                              void queryClient.invalidateQueries({ queryKey: qk.calendarSyncConnections(access) })
                            })
                            .catch((err) => notify(err instanceof Error ? err.message : 'Reconnect failed', 'error'))
                        }}
                      >
                        {isAr ? 'إعادة' : 'Reconnect'}
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-[1.55rem] border border-line/55 bg-white p-4 shadow-[0_12px_28px_rgba(35,33,29,0.06)]" dir={isAr ? 'rtl' : 'ltr'} data-settings-integrations-panel>
      <div className="mb-3">
        <p className="text-[13px] font-semibold text-ink">{isAr ? 'Google و Microsoft' : 'Google and Microsoft'}</p>
        <p className="text-[12.5px] text-muted">
          {isAr
            ? 'اربط مساحة عمل Google أو Microsoft 365 للتقويم والاجتماعات.'
            : 'Connect Google Workspace or Microsoft 365 for calendar and meetings.'}
        </p>
      </div>

      {localNotice ? (
        <p className={`mb-3 text-sm ${localNotice.kind === 'error' ? 'text-[#9a3412]' : 'text-[#3f6b3a]'}`}>{localNotice.text}</p>
      ) : null}

      <div className="mb-4 space-y-3 rounded-xl border border-line/45 bg-[#fbf7f1] p-3">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={connectProvider === 'microsoft_365' ? 'default' : 'secondary'}
            onClick={() => {
              setConnectProvider('microsoft_365')
              setConnectMode(null)
              setChecklist(null)
            }}
          >
            {isAr ? 'ربط Microsoft 365' : 'Connect Microsoft 365'}
          </Button>
          <Button
            type="button"
            variant={connectProvider === 'google_workspace' ? 'default' : 'secondary'}
            onClick={() => {
              setConnectProvider('google_workspace')
              setConnectMode(null)
              setChecklist(null)
            }}
          >
            {isAr ? 'ربط Google Workspace' : 'Connect Google Workspace'}
          </Button>
        </div>

        {connectProvider ? (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant={connectMode === (connectProvider === 'microsoft_365' ? 'enterprise_app' : 'enterprise_dwd') ? 'default' : 'secondary'}
              onClick={() => {
                const mode = connectProvider === 'microsoft_365' ? 'enterprise_app' : 'enterprise_dwd'
                setConnectMode(mode)
                void getPlatformIntegrationChecklist(access, connectProvider, mode)
                  .then((res) => setChecklist(res.checklist || null))
                  .catch(() => setChecklist(null))
              }}
            >
              {isAr ? 'اتصال مُدار من تقنية المعلومات' : 'IT-managed company connection'}
            </Button>
            <Button
              type="button"
              variant={connectMode === 'oauth_delegated' ? 'default' : 'secondary'}
              onClick={() => {
                setConnectMode('oauth_delegated')
                void getPlatformIntegrationChecklist(access, connectProvider, 'oauth_delegated')
                  .then((res) => setChecklist(res.checklist || null))
                  .catch(() => setChecklist(null))
              }}
            >
              {isAr ? 'اتصال سريع بحسابك' : 'Quick account connection'}
            </Button>
          </div>
        ) : null}

        {checklist ? (
          <details className="rounded-lg border border-line/40 bg-white/80 p-3 text-sm">
            <summary className="cursor-pointer font-medium text-ink">{isAr ? 'دليل الإعداد' : 'Setup guide'}</summary>
            <p className="mb-2 mt-2 text-xs text-muted">{(checklist.required_admin_role as string) || ''}</p>
            <ol className="list-decimal space-y-1 ps-4 text-xs text-muted">
              {((checklist.steps as Array<Record<string, unknown>>) || []).map((step) => (
                <li key={String(step.id)}>
                  <span className="text-ink">{String(step.title || '')}</span>
                  {step.detail ? <span> — {String(step.detail)}</span> : null}
                </li>
              ))}
            </ol>
          </details>
        ) : null}

        {connectProvider === 'microsoft_365' && connectMode === 'enterprise_app' ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="rounded-lg border border-line/50 bg-white px-3 py-2 text-sm" placeholder={isAr ? 'معرّف المستأجر' : 'Organization ID (Tenant)'} value={m365Tenant} onChange={(e) => setM365Tenant(e.target.value)} />
            <input className="rounded-lg border border-line/50 bg-white px-3 py-2 text-sm" placeholder={isAr ? 'معرّف التطبيق' : 'Application ID'} value={m365ClientId} onChange={(e) => setM365ClientId(e.target.value)} />
            <input className="rounded-lg border border-line/50 bg-white px-3 py-2 text-sm" placeholder={isAr ? 'هوية التقويم (UPN)' : 'Calendar identity (UPN)'} value={m365Identity} onChange={(e) => setM365Identity(e.target.value)} />
            <input className="rounded-lg border border-line/50 bg-white px-3 py-2 text-sm" placeholder={isAr ? 'سر التطبيق' : 'Client secret'} type="password" value={m365Secret} onChange={(e) => setM365Secret(e.target.value)} />
            <Button
              type="button"
              className="sm:col-span-2"
              disabled={connectBusy || !m365Tenant || !m365ClientId || !m365Identity || !m365Secret}
              onClick={() => {
                setConnectBusy(true)
                void connectMicrosoftEnterprise(access, {
                  tenant_id: m365Tenant.trim(),
                  client_id: m365ClientId.trim(),
                  calendar_identity: m365Identity.trim(),
                  client_secret: m365Secret.trim(),
                  dry_run_accept: true,
                  validate: false,
                })
                  .then((res) => {
                    notify(isAr ? 'تم ربط Microsoft 365' : 'Microsoft 365 connected', 'success')
                    setM365Secret('')
                    if (res.integration) {
                      setPlatformIntegrations((prev) => [...prev.filter((i) => i.integration_id !== res.integration.integration_id), res.integration])
                    }
                    if (res.connection) void queryClient.invalidateQueries({ queryKey: qk.calendarSyncConnections(access) })
                  })
                  .catch((err) => notify(err instanceof Error ? err.message : 'Connect failed', 'error'))
                  .finally(() => setConnectBusy(false))
              }}
            >
              {connectBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : isAr ? 'حفظ الاتصال' : 'Save connection'}
            </Button>
          </div>
        ) : null}

        {connectProvider === 'google_workspace' && connectMode === 'enterprise_dwd' ? (
          <div className="grid gap-2">
            <input
              className="rounded-lg border border-line/50 bg-white px-3 py-2 text-sm"
              placeholder={isAr ? 'بريد التقويم المعتمد (مثل hr@company.com)' : 'Approved calendar email (e.g. hr@company.com)'}
              value={googleImpersonate}
              onChange={(e) => setGoogleImpersonate(e.target.value)}
            />
            <textarea
              className="min-h-[96px] rounded-lg border border-line/50 bg-white px-3 py-2 font-mono text-xs"
              placeholder={isAr ? 'الصق ملف حساب الخدمة من تقنية المعلومات' : 'Paste the service-account file from IT'}
              value={googleSaJson}
              onChange={(e) => setGoogleSaJson(e.target.value)}
            />
            <details className="text-xs text-muted">
              <summary className="cursor-pointer font-medium text-ink">{isAr ? 'تعرّف كيف' : 'Learn how'}</summary>
              <p className="mt-2">
                {isAr
                  ? 'حساب الخدمة لا يملك بيانات التقويم — يستخدم تفويض النطاق لانتحال الهوية المعتمدة فقط. اطلب من تقنية المعلومات ملف JSON والتفويض.'
                  : 'The service account does not own calendar data — it uses company-approved domain delegation. Ask IT for the JSON file and delegation setup.'}
              </p>
            </details>
            <Button
              type="button"
              disabled={connectBusy || !googleImpersonate || googleSaJson.trim().length < 20}
              onClick={() => {
                setConnectBusy(true)
                void connectGoogleEnterprise(access, {
                  impersonation_email: googleImpersonate.trim(),
                  service_account_json: googleSaJson.trim(),
                  dry_run_accept: true,
                  validate: false,
                })
                  .then((res) => {
                    notify(isAr ? 'تم ربط Google Workspace' : 'Google Workspace connected', 'success')
                    setGoogleSaJson('')
                    if (res.integration) {
                      setPlatformIntegrations((prev) => [...prev.filter((i) => i.integration_id !== res.integration.integration_id), res.integration])
                    }
                    if (res.connection) void queryClient.invalidateQueries({ queryKey: qk.calendarSyncConnections(access) })
                  })
                  .catch((err) => notify(err instanceof Error ? err.message : 'Connect failed', 'error'))
                  .finally(() => setConnectBusy(false))
              }}
            >
              {connectBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : isAr ? 'حفظ الاتصال' : 'Save connection'}
            </Button>
          </div>
        ) : null}

        {connectProvider && connectMode === 'oauth_delegated' ? (
          <Button
            type="button"
            disabled={connectBusy}
            onClick={() => {
              setConnectBusy(true)
              void startPlatformOAuth(access, { provider_key: connectProvider, attach_calendar: true })
                .then((res) => {
                  if (res.authorize_url) window.open(res.authorize_url, '_blank', 'noopener,width=520,height=720')
                  notify(isAr ? 'أكمل الموافقة في النافذة الجديدة' : 'Complete consent in the new window', 'success')
                })
                .catch((err) => notify(err instanceof Error ? err.message : (isAr ? 'الاتصال غير مُعدّ' : 'Connection is not configured'), 'error'))
                .finally(() => setConnectBusy(false))
            }}
          >
            {connectBusy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : connectProvider === 'microsoft_365' ? (
              isAr ? 'الاتصال عبر Microsoft' : 'Connect with Microsoft'
            ) : isAr ? (
              'الاتصال عبر Google'
            ) : (
              'Connect with Google'
            )}
          </Button>
        ) : null}
      </div>

      {platformIntegrations.length > 0 ? (
        <ul className="space-y-2">
          {platformIntegrations.map((integ) => (
            <li key={integ.integration_id} className="rounded-xl border border-line/50 bg-white px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-medium text-ink">
                    {integ.display_name || integ.account_email || providerLabel(integ.provider_key, isAr)}
                  </div>
                  <div className="text-xs text-muted">
                    {statusLabel(integ.status, isAr)}
                    {integ.reconnect_required ? (isAr ? ' · يلزم إعادة الربط' : ' · reconnect required') : ''}
                    {integ.expiry_warning ? ` · ${integ.expiry_warning}` : ''}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {integ.status === 'connected' || integ.status === 'reconnect_required' ? (
                    <button
                      type="button"
                      className="text-xs underline"
                      onClick={() => {
                        void disconnectPlatformIntegration(access, integ.integration_id)
                          .then((res) => {
                            notify(isAr ? 'تم قطع اتصال الشركة' : 'Company connection removed', 'success')
                            setPlatformIntegrations((prev) =>
                              prev.map((x) => (x.integration_id === res.integration.integration_id ? res.integration : x)),
                            )
                            void queryClient.invalidateQueries({ queryKey: qk.calendarSyncConnections(access) })
                          })
                          .catch((err) => notify(err instanceof Error ? err.message : 'Disconnect failed', 'error'))
                      }}
                    >
                      {isAr ? 'قطع الاتصال' : 'Disconnect'}
                    </button>
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">{isAr ? 'لا اتصالات بعد — ابدأ بالربط أعلاه.' : 'No connections yet — start with Connect above.'}</p>
      )}
    </div>
  )
}
