/**
 * Payroll Authority P4A — Kuwait statutory architecture (counsel-gated, non-legal).
 */
import { Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { DashboardApiError, getPayrollAuthorityStatutoryWorkspace } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type PayrollStatutoryArchitecturePanelProps = {
  access: DashboardAccess
  permissions: string[]
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

function copy(locale: 'en' | 'ar') {
  if (locale === 'ar') {
    return {
      title: 'هيكل الالتزامات النظامية (الكويت)',
      hint: 'بنية PIFSS / العمل الإضافي / الراحة / العطل / المرض / مكافأة نهاية الخدمة — بلا معدلات قانونية غير موثّقة.',
      refresh: 'تحديث',
      packages: 'الحزم',
      rules: 'قواعد الإصدار',
      eos: 'تسويات EOS',
      boundary: 'حدود الاحتساب',
      moneyOff: 'معاينة غير سلطوية · بلا ادّعاء قانوني · الدفع معطّل',
      none: 'لا يوجد',
    }
  }
  return {
    title: 'Kuwait statutory architecture',
    hint: 'PIFSS / OT / rest-day / PH / sick / EOS packaging — no invented legal rates.',
    refresh: 'Refresh',
    packages: 'Packages',
    rules: 'Rule versions',
    eos: 'EOS settlements',
    boundary: 'Calc vs liability vs remittance',
    moneyOff: 'Preview non-authoritative · no legal claim · payment disabled',
    none: 'None',
  }
}

export function PayrollStatutoryArchitecturePanel({
  access,
  permissions,
  onNotice,
  onAccessIssue,
}: PayrollStatutoryArchitecturePanelProps) {
  const locale = useEmployees360Locale()
  const c = copy(locale)
  const isAr = locale === 'ar'
  const [busy, setBusy] = useState(false)
  const [ws, setWs] = useState<Record<string, unknown> | null>(null)

  const reload = useCallback(async () => {
    setBusy(true)
    try {
      const next = await getPayrollAuthorityStatutoryWorkspace(access)
      setWs(next)
    } catch (e) {
      if (e instanceof DashboardApiError && onAccessIssue) {
        const issue = accessIssueFromError(e)
        if (issue) onAccessIssue(issue)
      }
      onNotice(e instanceof Error ? e.message : 'Failed to load statutory architecture', 'error')
    } finally {
      setBusy(false)
    }
  }, [access, onNotice, onAccessIssue])

  useEffect(() => {
    void reload()
  }, [reload])

  const packages = (ws?.packages as Array<Record<string, unknown>> | undefined) || []
  const rules = (ws?.rule_versions as Array<Record<string, unknown>> | undefined) || []
  const eos = (ws?.eos_settlements as Array<Record<string, unknown>> | undefined) || []
  const boundary = (ws?.output_class_boundary as Record<string, unknown> | undefined) || {}

  return (
    <div
      className={cn('space-y-4 rounded-xl border border-[#e8ddd0] bg-white p-4 shadow-sm', isAr && 'text-right')}
      dir={isAr ? 'rtl' : 'ltr'}
      data-testid="payroll-statutory-architecture-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-[#1c1917]">{c.title}</h3>
          <p className="mt-1 max-w-3xl text-sm text-subtle">{c.hint}</p>
          <p className="mt-1 text-xs text-subtle">{c.moneyOff}</p>
        </div>
        <Button type="button" variant="secondary" size="sm" disabled={busy} onClick={() => void reload()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="ms-2">{c.refresh}</span>
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-[#efe6da] bg-[#faf7f2] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{c.packages}</div>
          <div className="mt-1 text-sm font-medium">{packages.length || c.none}</div>
        </div>
        <div className="rounded-lg border border-[#efe6da] bg-[#faf7f2] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{c.rules}</div>
          <div className="mt-1 text-sm font-medium">{rules.length || c.none}</div>
        </div>
        <div className="rounded-lg border border-[#efe6da] bg-[#faf7f2] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{c.eos}</div>
          <div className="mt-1 text-sm font-medium">{eos.length || c.none}</div>
        </div>
      </div>

      <div className="rounded-lg border border-[#efe6da] p-3 text-sm">
        <div className="font-semibold">{c.boundary}</div>
        <ul className="mt-2 list-disc space-y-1 ps-5 text-subtle">
          <li>A — employee net pay</li>
          <li>B — employer liability only</li>
          <li>C — settlement (EOS, not monthly G2N)</li>
          <li>D — remittance/reporting (not payment processing)</li>
        </ul>
        {boundary.never_mix ? <p className="mt-2 text-xs text-subtle">{String(boundary.never_mix)}</p> : null}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-[#efe6da] text-xs uppercase tracking-wide text-subtle">
            <tr>
              <th className="py-2 pe-3">Family</th>
              <th className="py-2 pe-3">Status</th>
              <th className="py-2 pe-3">Legal claim</th>
              <th className="py-2">Fixture</th>
            </tr>
          </thead>
          <tbody>
            {rules.slice(0, 12).map((row) => (
              <tr key={String(row.rule_version_id)} className="border-b border-[#f3ebe0]">
                <td className="py-2 pe-3 font-mono text-xs">{String(row.rule_family)}</td>
                <td className="py-2 pe-3">
                  <StatusPill tone={String(row.approval_status) === 'approved' ? 'warning' : 'neutral'}>
                    {String(row.approval_status)}
                  </StatusPill>
                </td>
                <td className="py-2 pe-3">{row.legal_claim ? 'yes' : 'no'}</td>
                <td className="py-2">{row.is_architecture_fixture ? 'architecture' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rules.length ? <div className="mt-2 text-xs text-subtle">No rule versions yet. Architecture packages are created via qualification / admin API.</div> : null}
      </div>
      <p className="text-xs text-subtle">permissions manage={String(permissions.includes('payroll.manage'))}</p>
    </div>
  )
}

export default PayrollStatutoryArchitecturePanel
