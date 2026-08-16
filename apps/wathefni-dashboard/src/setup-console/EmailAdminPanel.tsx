import { useCallback, useEffect, useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'

import {
  createCompanyEmailDomain,
  forceCompanyEmailWathefni,
  getCompanyEmailAdmin,
  patchCompanyEmailMailbox,
  probeCompanyEmailMailbox,
  refreshCompanyEmailDomain,
  seedCompanyEmailMailboxes,
} from './api'
import type { SetupCredentials } from './types'

export function EmailAdminPanel({
  credentials,
  companyCode,
}: {
  credentials: SetupCredentials
  companyCode: string
}) {
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null)
  const [domain, setDomain] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setError('')
    setSnapshot(await getCompanyEmailAdmin(credentials, companyCode))
  }, [companyCode, credentials])

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : 'Could not load email admin'))
  }, [load])

  const mailboxes = Array.isArray(snapshot?.mailboxes) ? (snapshot?.mailboxes as Array<Record<string, unknown>>) : []
  const domains = Array.isArray(snapshot?.domains) ? (snapshot?.domains as Array<Record<string, unknown>>) : []
  const settings = (snapshot?.settings as Record<string, unknown>) || {}

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await fn()
      await load()
      setNotice(label)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-line/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">Email sending (admin)</p>
          <p className="text-xs text-subtle">
            Mode: {String(settings.outbound_mode || 'wathefni') === 'wathefni' ? 'OctoHR' : String(settings.outbound_mode)} · MS configured:{' '}
            {String(Boolean(snapshot?.microsoft_mail_configured))} · Postmark account:{' '}
            {String(Boolean(snapshot?.postmark_account_configured))}
          </p>
        </div>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void load()}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {error ? <p className="text-xs text-rose-600">{error}</p> : null}
      {notice ? <p className="text-xs text-emerald-700">{notice}</p> : null}

      <div className="flex flex-wrap items-end gap-2">
        <label className="space-y-1 text-xs text-subtle">
          <span>Company domain</span>
          <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="company.com" />
        </label>
        <Button
          size="sm"
          disabled={busy || !domain.trim()}
          onClick={() => void run('Mailboxes seeded', () => seedCompanyEmailMailboxes(credentials, companyCode, domain.trim()))}
        >
          Seed careers/hr/…
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy || !domain.trim()}
          onClick={() => void run('Domain linked', () => createCompanyEmailDomain(credentials, companyCode, domain.trim()))}
        >
          Start domain verify
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => void run('Forced OctoHR fallback', () => forceCompanyEmailWathefni(credentials, companyCode))}
        >
          Force OctoHR
        </Button>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-subtle">Operational mailboxes</p>
        {mailboxes.length ? (
          mailboxes.map((mb) => (
            <div key={String(mb.mailbox_id)} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/60 p-2 text-xs">
              <div>
                <p className="font-medium">{String(mb.address)}</p>
                <p className="text-subtle">
                  status={String(mb.status)} · allow_send={String(mb.allow_send)} · probe={String(mb.last_probe_ok ?? '—')}
                </p>
                {mb.last_error ? <p className="text-rose-600">{String(mb.last_error)}</p> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={mb.status === 'approved' ? 'success' : mb.status === 'error' ? 'danger' : 'muted'}>{String(mb.status)}</Badge>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    void run('Mailbox approved', () =>
                      patchCompanyEmailMailbox(credentials, companyCode, String(mb.mailbox_id), {
                        status: 'approved',
                        allow_send: true,
                      }),
                    )
                  }
                >
                  Approve send
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    void run('Mailbox disabled', () =>
                      patchCompanyEmailMailbox(credentials, companyCode, String(mb.mailbox_id), {
                        status: 'disabled',
                        allow_send: false,
                      }),
                    )
                  }
                >
                  Disable
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void run('Probe done', () => probeCompanyEmailMailbox(credentials, companyCode, String(mb.mailbox_id)))}
                >
                  Probe
                </Button>
              </div>
            </div>
          ))
        ) : (
          <p className="text-xs text-subtle">No operational mailboxes yet.</p>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-subtle">Domains</p>
        {domains.length ? (
          domains.map((d) => (
            <div key={String(d.domain_id)} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/60 p-2 text-xs">
              <div>
                <p className="font-medium">{String(d.domain)}</p>
                <p className="text-subtle">{String(d.verification_status)}</p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => void run('Domain refreshed', () => refreshCompanyEmailDomain(credentials, companyCode, String(d.domain_id)))}
              >
                {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                Refresh
              </Button>
            </div>
          ))
        ) : (
          <p className="text-xs text-subtle">No company domains linked.</p>
        )}
      </div>
    </div>
  )
}
