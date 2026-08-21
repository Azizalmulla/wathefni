import { Loader2, RefreshCw, Radio, ShieldAlert, CheckCircle2, XCircle, RotateCcw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { useConfirm } from '@/components/ConfirmDialog'
import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'
import {
  approveCaptureMapping,
  getCaptureOpsOverview,
  rejectCaptureRemediation,
  seedCaptureOpsSynthetic,
  updateCaptureConnectorHealth,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { DashboardApiError } from '@/lib/api'
import type { DashboardAccess } from '@/types'
import { useEmployees360Locale, type Locale } from '@/posthire/employees360/chrome'

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof DashboardApiError) return error.message || fallback
  if (error instanceof Error && error.message) return error.message
  return fallback
}

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

type CaptureOpsOverview = {
  ok?: boolean
  company_code?: string
  capture_ops_enabled?: boolean
  ingest_enabled?: boolean
  sites?: Array<{ site_id: string; name: string; timezone?: string }>
  connectors?: Array<{
    connector_id: string
    status: string
    site_name?: string | null
    terminal_sn?: string | null
    row_version?: number
    health?: {
      status?: string
      lag_seconds?: number | null
      last_sync_at?: string | null
      last_error?: string | null
      alerts?: string[]
      failure_count?: number
    }
  }>
  remediation_open?: RemediationItem[]
  payroll_excluded?: RemediationItem[]
  counts?: {
    open_remediation?: number
    payroll_excluded?: number
    online?: number
    offline?: number
    degraded?: number
    by_kind?: Record<string, number>
  }
  flags?: Record<string, boolean>
}

type RemediationItem = {
  item_id: string
  kind: string
  status: string
  employee_key?: string | null
  device_user_id?: string | null
  device_id?: string | null
  work_date?: string | null
  payroll_excluded?: boolean
  row_version: number
  connector_id?: string | null
}

const copy = {
  en: {
    title: 'Connector health',
    subtitle: 'Site connectors, mapping issues, and capture exceptions — punch ingest stays off.',
    refresh: 'Refresh',
    seed: 'Seed lab data',
    connectors: 'Connectors',
    mapping: 'Unknown mapping',
    missing: 'Missing / ambiguous',
    conflicts: 'Conflicts',
    emptyConnectors: 'No connectors registered yet.',
    emptyQueue: 'Queue is empty.',
    payrollExcluded: 'Payroll excluded',
    approve: 'Approve mapping',
    reject: 'Reject',
    recover: 'Mark recovered',
    offline: 'Simulate offline',
    lag: 'Simulate lag',
    employeeKey: 'Employee key',
    loading: 'Loading connector health…',
    permission: 'You need attendance manage permission to work connector remediation.',
    ingestOff: 'Live punch ingest is off. Mapping can be approved; replay stays blocked.',
    stale: 'Someone else updated this item. Refresh and try again.',
    online: 'Online',
    degraded: 'Degraded',
    revoked: 'Revoked',
    statusOffline: 'Offline',
  },
  ar: {
    title: 'صحة الموصلات',
    subtitle: 'موصلات المواقع ومشاكل الربط واستثناءات الالتقاط — استيراد البصمات متوقف.',
    refresh: 'تحديث',
    seed: 'بيانات مختبر',
    connectors: 'الموصلات',
    mapping: 'ربط غير معروف',
    missing: 'دخول/خروج ناقص أو غامض',
    conflicts: 'تعارضات',
    emptyConnectors: 'لا توجد موصلات بعد.',
    emptyQueue: 'الطابور فارغ.',
    payrollExcluded: 'مستبعد من الرواتب',
    approve: 'اعتماد الربط',
    reject: 'رفض',
    recover: 'تعافٍ',
    offline: 'محاكاة انقطاع',
    lag: 'محاكاة تأخير',
    employeeKey: 'مفتاح الموظف',
    loading: 'جاري تحميل صحة الموصلات…',
    permission: 'تحتاج صلاحية إدارة الحضور لمعالجة الموصلات.',
    ingestOff: 'استيراد البصمات الحي متوقف. يمكن اعتماد الربط؛ إعادة التشغيل محظورة.',
    stale: 'حدّث شخص آخر هذا العنصر. حدّث الصفحة وحاول مجدداً.',
    online: 'متصل',
    degraded: 'متدهور',
    revoked: 'ملغى',
    statusOffline: 'غير متصل',
  },
} as const

function kindLabel(kind: string, locale: Locale) {
  const map: Record<string, { en: string; ar: string }> = {
    unknown_employee: { en: 'Unknown employee', ar: 'موظف غير معروف' },
    unknown_device: { en: 'Unknown device', ar: 'جهاز غير معروف' },
    missing_check_in: { en: 'Missing check-in', ar: 'دخول ناقص' },
    missing_check_out: { en: 'Missing check-out', ar: 'خروج ناقص' },
    ambiguous_punch_order: { en: 'Ambiguous order', ar: 'ترتيب غامض' },
    duplicate_conflict: { en: 'Duplicate / conflict', ar: 'تكرار / تعارض' },
    connector_lag: { en: 'Connector lag', ar: 'تأخير الموصل' },
    connector_offline: { en: 'Connector offline', ar: 'موصل غير متصل' },
  }
  return map[kind]?.[locale] || kind
}

function statusTone(status?: string): 'success' | 'warning' | 'danger' | 'muted' {
  if (status === 'online' || status === 'active' || status === 'ok') return 'success'
  if (status === 'degraded' || status === 'rotated') return 'warning'
  if (status === 'revoked') return 'danger'
  return 'muted'
}

export function AttendanceCaptureOpsPanel({
  access,
  canManage,
  onNotice,
  onAccessIssue,
}: {
  access: DashboardAccess
  canManage: boolean
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const locale = useEmployees360Locale()
  const t = copy[locale]
  const isAr = locale === 'ar'
  const confirm = useConfirm()
  const [tab, setTab] = useState<'connectors' | 'mapping' | 'missing' | 'conflicts'>('connectors')
  const [data, setData] = useState<CaptureOpsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [employeeKeyDraft, setEmployeeKeyDraft] = useState<Record<string, string>>({})

  const load = useCallback(
    async (soft = false) => {
      if (!canManage) {
        setLoading(false)
        return
      }
      if (soft) setRefreshing(true)
      else setLoading(true)
      setError(null)
      try {
        const res = await getCaptureOpsOverview(access)
        setData(res as CaptureOpsOverview)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return
        }
        // 404 when dark flag off — treat as disabled empty
        const msg = friendlyError(err, t.loading)
        if (String(msg).toLowerCase().includes('not found') || (err instanceof DashboardApiError && err.status === 404)) {
          setData(null)
          setError(null)
        } else {
          setError(msg)
        }
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [access, canManage, onAccessIssue, t.loading],
  )

  useEffect(() => {
    void load()
  }, [load])

  const mappingItems = useMemo(
    () => (data?.remediation_open || []).filter((i) => i.kind === 'unknown_employee' || i.kind === 'unknown_device'),
    [data],
  )
  const missingItems = useMemo(
    () =>
      (data?.remediation_open || []).filter((i) =>
        ['missing_check_in', 'missing_check_out', 'ambiguous_punch_order', 'connector_lag', 'connector_offline'].includes(i.kind),
      ),
    [data],
  )
  const conflictItems = useMemo(
    () => (data?.remediation_open || []).filter((i) => i.kind === 'duplicate_conflict'),
    [data],
  )

  async function runSeed() {
    const ok = await confirm({
      title: isAr ? 'بذر بيانات مختبر؟' : 'Seed lab capture data?',
      body: isAr ? 'ينشئ موقعاً وموصلاً وطابور استثناءات اصطناعية فقط.' : 'Creates a synthetic site, connector, and exception queue only.',
      confirmLabel: t.seed,
    })
    if (!ok) return
    setBusyId('seed')
    try {
      await seedCaptureOpsSynthetic(access)
      onNotice(isAr ? 'تم بذر بيانات المختبر' : 'Lab capture data seeded', 'success')
      await load(true)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) return onAccessIssue?.(issue)
      onNotice(friendlyError(err, isAr ? 'تعذر البذر' : 'Could not seed'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function onApprove(item: RemediationItem) {
    const key = (employeeKeyDraft[item.item_id] || '').trim()
    if (!key) {
      onNotice(isAr ? 'أدخل مفتاح الموظف' : 'Enter an employee key', 'error')
      return
    }
    setBusyId(item.item_id)
    try {
      await approveCaptureMapping(access, item.item_id, {
        employee_key: key,
        expected_row_version: item.row_version,
        replay: false,
      })
      onNotice(isAr ? 'تم اعتماد الربط' : 'Mapping approved', 'success')
      await load(true)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) return onAccessIssue?.(issue)
      const detail = (err as { detail?: { error?: string } })?.detail?.error
      onNotice(detail === 'stale_row_version' ? t.stale : friendlyError(err, isAr ? 'تعذر الاعتماد' : 'Approve failed'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function onReject(item: RemediationItem) {
    setBusyId(item.item_id)
    try {
      await rejectCaptureRemediation(access, item.item_id, { expected_row_version: item.row_version })
      onNotice(isAr ? 'تم الرفض' : 'Rejected', 'success')
      await load(true)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) return onAccessIssue?.(issue)
      const detail = (err as { detail?: { error?: string } })?.detail?.error
      onNotice(detail === 'stale_row_version' ? t.stale : friendlyError(err, isAr ? 'تعذر الرفض' : 'Reject failed'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function setHealth(connectorId: string, mode: 'recover' | 'offline' | 'lag') {
    setBusyId(connectorId)
    try {
      const body =
        mode === 'recover'
          ? { status: 'ok', lag_seconds: 5, error_count: 0, last_sync_at: new Date().toISOString() }
          : mode === 'offline'
            ? { status: 'offline', lag_seconds: 0, error_count: 1, last_error: 'lab_offline' }
            : { status: 'ok', lag_seconds: 2400, error_count: 0, last_sync_at: new Date().toISOString() }
      await updateCaptureConnectorHealth(access, connectorId, body)
      await load(true)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) return onAccessIssue?.(issue)
      onNotice(friendlyError(err, 'Health update failed'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  if (!canManage) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t.title}</CardTitle>
          <CardDescription>{t.permission}</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[13px] text-subtle" dir={isAr ? 'rtl' : 'ltr'}>
        <Loader2 className="h-4 w-4 animate-spin" />
        {t.loading}
      </div>
    )
  }

  if (error) {
    return (
      <Card dir={isAr ? 'rtl' : 'ltr'}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-danger">
            <ShieldAlert className="h-4 w-4" /> {error}
          </CardTitle>
          <Button size="sm" variant="secondary" onClick={() => void load()}>
            {t.refresh}
          </Button>
        </CardHeader>
      </Card>
    )
  }

  if (!data) {
    return (
      <Card dir={isAr ? 'rtl' : 'ltr'}>
        <CardHeader>
          <CardTitle>{t.title}</CardTitle>
          <CardDescription>{isAr ? 'عمليات الالتقاط غير مفعّلة لهذه الشركة.' : 'Capture operations are not enabled for this company.'}</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const tabs = [
    { id: 'connectors' as const, label: t.connectors, count: data.connectors?.length || 0 },
    { id: 'mapping' as const, label: t.mapping, count: mappingItems.length },
    { id: 'missing' as const, label: t.missing, count: missingItems.length },
    { id: 'conflicts' as const, label: t.conflicts, count: conflictItems.length },
  ]

  return (
    <div className="space-y-4" data-testid="attendance-capture-ops" dir={isAr ? 'rtl' : 'ltr'}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[16px] font-semibold tracking-[-0.02em] text-text">{t.title}</h3>
          <p className="mt-0.5 max-w-2xl text-[13px] text-subtle/90">{t.subtitle}</p>
          <p className="mt-1 text-[12px] text-mist">{t.ingestOff}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={() => void load(true)} disabled={refreshing}>
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {t.refresh}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void runSeed()} disabled={busyId === 'seed'}>
            {busyId === 'seed' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radio className="h-4 w-4" />}
            {t.seed}
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label={t.online} value={data.counts?.online ?? 0} />
        <Stat label={t.statusOffline} value={data.counts?.offline ?? 0} />
        <Stat label={t.degraded} value={data.counts?.degraded ?? 0} />
        <Stat label={t.payrollExcluded} value={data.counts?.payroll_excluded ?? 0} />
      </div>

      <HrSurfaceTabs
        value={tab}
        onChange={setTab}
        items={tabs.map((tabItem) => ({
          id: tabItem.id,
          label: tabItem.label,
          count: tabItem.count,
        }))}
      />

      {tab === 'connectors' ? (
        <div className="space-y-2">
          {(data.connectors || []).length === 0 ? (
            <Empty text={t.emptyConnectors} />
          ) : (
            (data.connectors || []).map((c) => {
              const h = c.health || {}
              const st = h.status || c.status
              return (
                <Card key={c.connector_id} className="p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[13px] text-text">{c.connector_id}</span>
                        <Badge tone={statusTone(st)}>{st}</Badge>
                        {c.status === 'revoked' ? <Badge tone="danger">{t.revoked}</Badge> : null}
                      </div>
                      <p className="text-[12px] text-subtle">
                        {c.site_name || '—'} · {c.terminal_sn || '—'}
                      </p>
                      <p className="text-[12px] text-mist">
                        lag {h.lag_seconds ?? '—'}s · sync {h.last_sync_at || '—'}
                        {h.last_error ? ` · ${h.last_error}` : ''}
                      </p>
                      {(h.alerts || []).length ? (
                        <p className="text-[11px] text-danger">{(h.alerts || []).join(' · ')}</p>
                      ) : null}
                    </div>
                    {c.status !== 'revoked' ? (
                      <div className="flex flex-wrap gap-1">
                        <Button size="sm" variant="ghost" disabled={busyId === c.connector_id} onClick={() => void setHealth(c.connector_id, 'recover')}>
                          <CheckCircle2 className="h-3.5 w-3.5" /> {t.recover}
                        </Button>
                        <Button size="sm" variant="ghost" disabled={busyId === c.connector_id} onClick={() => void setHealth(c.connector_id, 'offline')}>
                          {t.offline}
                        </Button>
                        <Button size="sm" variant="ghost" disabled={busyId === c.connector_id} onClick={() => void setHealth(c.connector_id, 'lag')}>
                          <RotateCcw className="h-3.5 w-3.5" /> {t.lag}
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </Card>
              )
            })
          )}
        </div>
      ) : null}

      {tab === 'mapping' ? (
        <QueueList
          items={mappingItems}
          empty={t.emptyQueue}
          locale={locale}
          renderActions={(item) => (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input
                value={employeeKeyDraft[item.item_id] || ''}
                onChange={(e) => setEmployeeKeyDraft((prev) => ({ ...prev, [item.item_id]: e.target.value }))}
                placeholder={t.employeeKey}
                className="min-w-[180px]"
              />
              <Button size="sm" disabled={busyId === item.item_id} onClick={() => void onApprove(item)}>
                {busyId === item.item_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                {t.approve}
              </Button>
              <Button size="sm" variant="ghost" disabled={busyId === item.item_id} onClick={() => void onReject(item)}>
                <XCircle className="h-3.5 w-3.5" /> {t.reject}
              </Button>
            </div>
          )}
        />
      ) : null}

      {tab === 'missing' ? (
        <QueueList
          items={missingItems}
          empty={t.emptyQueue}
          locale={locale}
          renderActions={(item) => (
            <Button size="sm" variant="ghost" disabled={busyId === item.item_id} onClick={() => void onReject(item)}>
              <XCircle className="h-3.5 w-3.5" /> {t.reject}
            </Button>
          )}
        />
      ) : null}

      {tab === 'conflicts' ? (
        <QueueList
          items={conflictItems}
          empty={t.emptyQueue}
          locale={locale}
          renderActions={(item) => (
            <Button size="sm" variant="ghost" disabled={busyId === item.item_id} onClick={() => void onReject(item)}>
              <XCircle className="h-3.5 w-3.5" /> {t.reject}
            </Button>
          )}
        />
      ) : null}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border/70 bg-surface/40 px-3 py-2">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mist">{label}</div>
      <div className="mt-1 text-[20px] font-semibold tabular-nums text-text">{value}</div>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <p className="rounded-lg border border-dashed border-border/70 px-4 py-8 text-center text-[13px] text-subtle">{text}</p>
}

function QueueList({
  items,
  empty,
  locale,
  renderActions,
}: {
  items: RemediationItem[]
  empty: string
  locale: Locale
  renderActions: (item: RemediationItem) => React.ReactNode
}) {
  if (!items.length) return <Empty text={empty} />
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <Card key={item.item_id} className="p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-medium text-text">{kindLabel(item.kind, locale)}</span>
                {item.payroll_excluded ? (
                  <Badge tone="warning">{locale === 'ar' ? 'مستبعد من الرواتب' : 'Payroll excluded'}</Badge>
                ) : null}
              </div>
              <p className="font-mono text-[11px] text-mist">{item.item_id}</p>
              <p className="text-[12px] text-subtle">
                {item.device_user_id || item.employee_key || '—'}
                {item.work_date ? ` · ${item.work_date}` : ''}
                {item.device_id ? ` · ${item.device_id}` : ''}
              </p>
            </div>
            {renderActions(item)}
          </div>
        </Card>
      ))}
    </div>
  )
}
