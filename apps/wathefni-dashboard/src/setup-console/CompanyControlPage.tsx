import { useCallback, useEffect, useState } from 'react'
import { Loader2, Pause, Play, RefreshCw, ShieldAlert } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import {
  getCompanyControl,
  moduleLifecycleAction,
  previewImpact,
  previewOffboarding,
  runCompanyReadiness,
} from './api'
import { EmailAdminPanel } from './EmailAdminPanel'
import type { SetupCredentials } from './types'

type Section =
  | 'overview'
  | 'modules'
  | 'integrations'
  | 'roles'
  | 'policies'
  | 'data'
  | 'readiness'
  | 'health'
  | 'audit'

const SECTIONS: Array<{ id: Section; en: string; ar: string }> = [
  { id: 'overview', en: 'Overview', ar: 'نظرة عامة' },
  { id: 'modules', en: 'Modules', ar: 'الوحدات' },
  { id: 'integrations', en: 'Integrations', ar: 'التكاملات' },
  { id: 'roles', en: 'Roles and permissions', ar: 'الأدوار والصلاحيات' },
  { id: 'policies', en: 'Policies', ar: 'السياسات' },
  { id: 'data', en: 'Data and imports', ar: 'البيانات والاستيراد' },
  { id: 'readiness', en: 'Readiness', ar: 'الجاهزية' },
  { id: 'health', en: 'Health', ar: 'الصحة' },
  { id: 'audit', en: 'Audit history', ar: 'سجل التدقيق' },
]

function stateTone(flags: Record<string, unknown>) {
  if (flags.blocked) return 'danger' as const
  if (flags.degraded || flags.paused) return 'warning' as const
  if (flags.live) return 'success' as const
  if (flags.ready) return 'success' as const
  if (flags.setup_required) return 'warning' as const
  return 'muted' as const
}

export function CompanyControlPage({
  credentials,
  companyCode,
  locale = 'en',
}: {
  credentials: SetupCredentials
  companyCode: string
  locale?: 'en' | 'ar'
}) {
  const [section, setSection] = useState<Section>('overview')
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [impact, setImpact] = useState<Record<string, unknown> | null>(null)
  const dir = locale === 'ar' ? 'rtl' : 'ltr'
  const isAr = locale === 'ar'

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setSnapshot(await getCompanyControl(credentials, companyCode))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load company control')
    } finally {
      setLoading(false)
    }
  }, [companyCode, credentials])

  useEffect(() => {
    void load()
  }, [load])

  const modules = Array.isArray(snapshot?.modules) ? (snapshot?.modules as Array<Record<string, unknown>>) : []
  const integrations = Array.isArray(snapshot?.integrations) ? (snapshot?.integrations as Array<Record<string, unknown>>) : []
  const audit = Array.isArray(snapshot?.audit_history) ? (snapshot?.audit_history as Array<Record<string, unknown>>) : []
  const readiness = (snapshot?.readiness as Record<string, unknown>) || {}

  async function runModuleAction(moduleKey: string, action: 'pause' | 'resume' | 'activate') {
    const preview = await previewImpact(credentials, companyCode, { action, module_key: moduleKey })
    setImpact(preview)
    await moduleLifecycleAction(credentials, companyCode, moduleKey, { action, reason: `control_page_${action}` })
    await load()
  }

  return (
    <div dir={dir} className="space-y-4" data-control-page={companyCode}>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>{companyCode} control</CardTitle>
            <CardDescription>
              See what works, what is incomplete, what is broken, and what a draft publish would change.
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {SECTIONS.map((item) => (
              <Button
                key={item.id}
                size="sm"
                variant={section === item.id ? 'default' : 'ghost'}
                onClick={() => setSection(item.id)}
              >
                {locale === 'ar' ? item.ar : item.en}
              </Button>
            ))}
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}

          {section === 'overview' ? (
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-line/70 p-3 text-sm">
                <p className="text-subtle">Lifecycle</p>
                <p className="font-medium">{String((snapshot?.overview as Record<string, unknown> | undefined)?.lifecycle_status || '—')}</p>
              </div>
              <div className="rounded-2xl border border-line/70 p-3 text-sm">
                <p className="text-subtle">Activation epoch</p>
                <p className="font-medium">{String((snapshot?.overview as Record<string, unknown> | undefined)?.activation_epoch || '—')}</p>
              </div>
              <div className="rounded-2xl border border-line/70 p-3 text-sm">
                <p className="text-subtle">Externally usable</p>
                <p className="font-medium">{String(Boolean((snapshot?.overview as Record<string, unknown> | undefined)?.externally_usable))}</p>
              </div>
            </div>
          ) : null}

          {section === 'modules' ? (
            <div className="space-y-2">
              {modules.map((mod) => (
                <div key={String(mod.module_key)} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line/70 p-3">
                  <div>
                    <p className="font-medium">{String(mod.module_key)}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {mod.purchased ? <Badge tone="muted">purchased</Badge> : null}
                      {mod.setup_required ? <Badge tone="warning">setup required</Badge> : null}
                      {mod.configured ? <Badge tone="muted">configured</Badge> : null}
                      {mod.testing ? <Badge tone="muted">testing</Badge> : null}
                      {mod.ready ? <Badge tone="success">ready</Badge> : null}
                      {mod.live ? <Badge tone="success">live</Badge> : null}
                      {mod.paused ? <Badge tone="warning">paused</Badge> : null}
                      {mod.degraded ? <Badge tone="warning">degraded</Badge> : null}
                      {mod.blocked ? <Badge tone="danger">blocked</Badge> : null}
                      <Badge tone={stateTone(mod)}>epoch {String(mod.activation_epoch || 1)}</Badge>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => void runModuleAction(String(mod.module_key), 'pause')}>
                      <Pause className="h-4 w-4" /> Pause
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void runModuleAction(String(mod.module_key), 'resume')}>
                      <Play className="h-4 w-4" /> Resume
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {section === 'integrations' ? (
            <div className="space-y-2">
              <p className="text-sm text-subtle">
                {isAr
                  ? 'حالة التكاملات للمنصة. الكتالوج الموجّه للعميل في '
                  : 'Platform integration status. Customer catalog lives in '}
                <a href="/setup-console#classic-integrations" className="font-medium text-accent hover:underline">
                  {isAr ? 'التكاملات' : 'Integrations'}
                </a>
                {isAr ? '. تشغيل المزامنة في ' : '. Sync operations live in '}
                <a href="/dashboard?page=employees&view=migration" className="font-medium text-accent hover:underline">
                  {isAr ? 'الأنظمة المتصلة' : 'Connected Systems'}
                </a>
                .
              </p>
              {integrations.map((item) => {
                const key = String(item.provider_key || '')
                const label =
                  (
                    {
                      octopus_whatsapp: isAr ? 'واتساب الأعمال' : 'WhatsApp Business',
                      postmark_inbound: isAr ? 'بريد وارد' : 'Inbound email',
                      postmark_outbound: isAr ? 'بريد صادر' : 'Outbound email',
                      gmail_gog: isAr ? 'صندوق Gmail' : 'Gmail mailbox',
                      google_calendar: isAr ? 'تقويم Google' : 'Google Calendar',
                      microsoft_365: 'Microsoft 365',
                      microsoft_teams: 'Microsoft Teams',
                      mistral_ocr: isAr ? 'استخراج المستندات' : 'Document extraction',
                      candidate_indexing: isAr ? 'فهرسة المرشحين' : 'Candidate indexing',
                      push: isAr ? 'إشعارات الدفع' : 'Push notifications',
                    } as Record<string, string>
                  )[key] || key.replace(/_/g, ' ')
                // Hide unsupported/future stubs from Control customer-facing list
                if (key === 'imap' || key === 'sms') return null
                return (
                  <div key={key} className="rounded-2xl border border-line/70 p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-medium">{label}</p>
                      <Badge tone={item.kill_switch ? 'danger' : item.state === 'live' ? 'success' : 'muted'}>
                        {item.kill_switch
                          ? isAr
                            ? 'متوقف'
                            : 'Paused'
                          : item.state === 'live'
                            ? isAr
                              ? 'يعمل'
                              : 'Live'
                            : String(item.state || '—')}
                      </Badge>
                    </div>
                  </div>
                )
              })}
              <EmailAdminPanel credentials={credentials} companyCode={companyCode} />
            </div>
          ) : null}

          {section === 'roles' ? (
            <p className="text-sm text-subtle">
              {isAr
                ? 'أدوار الشركة الجاهزة تُدار من الإعدادات ← الفريق. نظرة الإعداد في '
                : 'Company role presets are managed in Settings → Team. Setup overview lives in '}
              <a href="/setup-console#classic-team-access" className="font-medium text-accent hover:underline">
                {isAr ? 'الفريق والوصول' : 'Team & access'}
              </a>
              .
            </p>
          ) : null}

          {section === 'policies' ? (
            <pre className="overflow-auto rounded-2xl border border-line/70 bg-panel/40 p-3 text-xs">
              {JSON.stringify(snapshot?.policies || {}, null, 2)}
            </pre>
          ) : null}

          {section === 'data' ? (
            <div className="space-y-3">
              <p className="text-sm text-subtle">Dry-run imports only. No external company import.</p>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void previewOffboarding(credentials, companyCode).then((r) => setImpact(r))}
              >
                <ShieldAlert className="h-4 w-4" /> Preview offboarding
              </Button>
            </div>
          ) : null}

          {section === 'readiness' ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge tone={readiness.ready ? 'success' : 'warning'}>{readiness.ready ? 'Ready' : 'Not ready'}</Badge>
                <Button size="sm" onClick={() => void runCompanyReadiness(credentials, companyCode).then(load)}>
                  Retest
                </Button>
              </div>
              <pre className="overflow-auto rounded-2xl border border-line/70 bg-panel/40 p-3 text-xs">
                {JSON.stringify(readiness.results || readiness, null, 2)}
              </pre>
            </div>
          ) : null}

          {section === 'health' ? (
            <p className="text-sm text-subtle">Orchestrator health and delivery-sweep status are verified by platform monitoring. Control-plane gates block side effects when paused, degraded, or epoch-mismatched.</p>
          ) : null}

          {section === 'audit' ? (
            <div className="space-y-2">
              {audit.slice(0, 20).map((row, idx) => (
                <div key={idx} className="rounded-2xl border border-line/70 p-3 text-xs">
                  <p className="font-medium">{String(row.event_type)} · {String(row.actor || 'system')}</p>
                  <p className="text-subtle">{String(row.created_at)}</p>
                </div>
              ))}
            </div>
          ) : null}

          {impact ? (
            <div className="rounded-2xl border border-line/70 p-3">
              <p className="mb-2 text-sm font-medium">Impact preview</p>
              <pre className="overflow-auto text-xs">{JSON.stringify(impact, null, 2)}</pre>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
