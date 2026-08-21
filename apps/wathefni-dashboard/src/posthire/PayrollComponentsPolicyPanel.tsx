/**
 * Payroll Authority P3 — components, company policy, Mode A preview (non-authoritative).
 */
import { Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getPayrollComponentsWorkspace,
  getPayrollInputReadiness,
  postPayrollCalcPreview,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type PayrollComponentsPolicyPanelProps = {
  access: DashboardAccess
  permissions: string[]
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
  periodStart?: string
  periodEnd?: string
}

function canManage(permissions: string[]) {
  return permissions.includes('payroll.manage')
}

function money(n: unknown): string {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return v.toFixed(3)
}

function copy(locale: 'en' | 'ar') {
  if (locale === 'ar') {
    return {
      title: 'مكونات الرواتب والسياسة',
      hint: 'تحويل المدخلات المقفلة والتعويض إلى بنود معاينة — بلا سلطة مالية بعد.',
      refresh: 'تحديث',
      policy: 'السياسة النشطة',
      catalog: 'الكتالوج',
      preview: 'معاينة الحساب',
      createPolicy: 'إنشاء نسخة سياسة',
      calculate: 'احتساب المعاينة',
      snapshotId: 'معرّف لقطة المدخلات المقفلة',
      attMode: 'وضع الحضور',
      lateness: 'التأخير يؤثر على الأجر',
      otMoney: 'أجر العمل الإضافي (يتطلب جداول مستشار)',
      moneyOff: 'معاينة غير سلطوية · معالجة الدفع معطّلة',
      none: 'لا يوجد',
      blockers: 'عوائق',
    }
  }
  return {
    title: 'Payroll components & policy',
    hint: 'Turn locked inputs + compensation into preview component lines — not money authority yet.',
    refresh: 'Refresh',
    policy: 'Active policy',
    catalog: 'Catalog',
    preview: 'Calculation preview',
    createPolicy: 'Create policy version',
    calculate: 'Calculate preview',
    snapshotId: 'Locked input snapshot ID',
    attMode: 'Attendance mode',
    lateness: 'Lateness affects pay',
    otMoney: 'OT money (needs counsel rates)',
    moneyOff: 'Preview non-authoritative · payment processing disabled',
    none: 'None',
    blockers: 'Blockers',
  }
}

export function PayrollComponentsPolicyPanel({
  access,
  permissions,
  onNotice,
  onAccessIssue,
  periodStart,
  periodEnd,
}: PayrollComponentsPolicyPanelProps) {
  const locale = useEmployees360Locale()
  const c = copy(locale)
  const isAr = locale === 'ar'
  const manage = canManage(permissions)
  const [busy, setBusy] = useState(false)
  const [ws, setWs] = useState<Record<string, unknown> | null>(null)
  const [start, setStart] = useState(periodStart || '')
  const [end, setEnd] = useState(periodEnd || '')
  const [inputSnapshotId, setInputSnapshotId] = useState('')
  const [lastCalc, setLastCalc] = useState<Record<string, unknown> | null>(null)

  const activePolicy = useMemo(() => {
    const policies = (ws?.policies as Array<Record<string, unknown>> | undefined) || []
    return policies.find((p) => String(p.status) === 'approved') || policies[0] || null
  }, [ws])

  const recent = useMemo(() => {
    const runs = (ws?.recent_calc_runs as Array<Record<string, unknown>> | undefined) || []
    return runs[0] || null
  }, [ws])

  const catalog = (ws?.catalog as Array<Record<string, unknown>> | undefined) || []

  const reload = useCallback(async () => {
    setBusy(true)
    try {
      const next = await getPayrollComponentsWorkspace(access)
      setWs(next)
      if (start && end) {
        const readiness = await getPayrollInputReadiness(access, {
          period_start: start,
          period_end: end,
        })
        const snap = readiness?.input_snapshot as Record<string, unknown> | undefined
        const sid = snap?.input_snapshot_id
        if (sid && String(snap?.status || readiness?.status || '') === 'locked') {
          setInputSnapshotId(String(sid))
        }
      }
    } catch (e) {
      if (e instanceof DashboardApiError && onAccessIssue) {
        const issue = accessIssueFromError(e)
        if (issue) onAccessIssue(issue)
      }
      onNotice(e instanceof Error ? e.message : 'Failed to load payroll components', 'error')
    } finally {
      setBusy(false)
    }
  }, [access, start, end, onNotice, onAccessIssue])

  useEffect(() => {
    void reload()
  }, [reload])

  async function onCalculate() {
    if (!manage || !inputSnapshotId.trim()) {
      onNotice('Need a locked payroll input snapshot ID', 'error')
      return
    }
    setBusy(true)
    try {
      const result = await postPayrollCalcPreview(access, {
        input_snapshot_id: inputSnapshotId.trim(),
        reason: 'HR Mode A preview calculation from components panel',
      })
      const run = (result.calc_run as Record<string, unknown>) || result
      setLastCalc(run)
      const status = String(run.status || '')
      onNotice(
        status === 'blocked' || Number(run.blocker_count || 0) > 0
          ? `Preview needs review (${run.blocker_count || 0} blockers)`
          : `Preview calculated · net ${money(run.totals_net)}`,
        status === 'blocked' ? 'error' : 'success',
      )
      await reload()
    } catch (e) {
      onNotice(e instanceof Error ? e.message : 'Preview calculation failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className={cn('space-y-4 rounded-xl border border-semantic-line bg-semantic-surface-raised p-4 shadow-sm', isAr && 'text-end')}
      dir={isAr ? 'rtl' : 'ltr'}
      data-testid="payroll-components-policy-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-semantic-ink">{c.title}</h3>
          <p className="mt-1 max-w-3xl text-sm text-subtle">{c.hint}</p>
          <p className="mt-1 text-xs text-subtle">{c.moneyOff}</p>
        </div>
        <Button type="button" variant="secondary" size="sm" disabled={busy} onClick={() => void reload()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="ms-2">{c.refresh}</span>
        </Button>
      </div>

      <ConfigureInSetupBanner
        locale={locale}
        title={isAr ? 'إعداد الرواتب للشركة' : 'Company payroll setup'}
        body={
          isAr
            ? 'وحدة الإعداد تملك سياسة الشركة. هذا اللوح للمعاينة التشغيلية فقط.'
            : 'Setup Console owns company payroll policy. This panel is for operational previews only.'
        }
        anchor="classic-payroll-setup"
      />

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-xs text-subtle">
          Period start
          <Input className="mt-1" value={start} onChange={(e) => setStart(e.target.value)} placeholder="YYYY-MM-DD" />
        </label>
        <label className="text-xs text-subtle">
          Period end
          <Input className="mt-1" value={end} onChange={(e) => setEnd(e.target.value)} placeholder="YYYY-MM-DD" />
        </label>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-[#efe6da] bg-[#faf7f2] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{c.policy}</div>
          <div className="mt-1 flex items-center gap-2 text-sm font-medium">
            {activePolicy ? `v${activePolicy.version_number}` : c.none}
            {activePolicy ? (
              <StatusPill tone={String(activePolicy.status) === 'approved' ? 'success' : 'warning'}>
                {String(activePolicy.status)}
              </StatusPill>
            ) : null}
          </div>
          <div className="mt-1 text-xs text-subtle">
            {activePolicy
              ? `${activePolicy.attendance_payroll_mode} · lateness ${activePolicy.lateness_money_enabled ? 'on' : 'off'}`
              : isAr
                ? 'اضبط السياسة من وحدة الإعداد قبل المعاينة.'
                : 'Configure policy in Setup Console before preview.'}
          </div>
        </div>
        <div className="rounded-lg border border-[#efe6da] bg-[#faf7f2] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{c.catalog}</div>
          <div className="mt-1 text-sm font-medium">{catalog.length} components</div>
          <div className="mt-1 text-xs text-subtle">Basic · allowances · deductions · time-pay · custom</div>
        </div>
        <div className="rounded-lg border border-[#efe6da] bg-[#faf7f2] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">{c.preview}</div>
          <div className="mt-1 text-sm font-medium">{recent ? String(recent.status) : c.none}</div>
          <div className="mt-1 text-xs text-subtle">
            {recent ? `Net ${money(recent.totals_net)} · blockers ${recent.blocker_count ?? 0}` : 'Run against a locked input snapshot.'}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-[#efe6da] p-3">
        <div className="text-sm font-semibold">{c.preview}</div>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="min-w-[280px] flex-1 text-xs text-subtle">
            {c.snapshotId}
            <Input
              className="mt-1 font-mono text-sm"
              value={inputSnapshotId}
              onChange={(e) => setInputSnapshotId(e.target.value)}
              placeholder="uuid"
            />
          </label>
          {manage ? (
            <Button type="button" disabled={busy} onClick={() => void onCalculate()}>
              {c.calculate}
            </Button>
          ) : null}
        </div>
        {lastCalc ? (
          <div className="mt-3 space-y-1 rounded-lg bg-[#faf7f2] p-3 text-sm">
            <div>
              Status <strong>{String(lastCalc.status)}</strong> · employees {String(lastCalc.employee_count ?? '—')} ·
              gross {money(lastCalc.totals_gross)} · deductions {money(lastCalc.totals_deductions)} · net{' '}
              {money(lastCalc.totals_net)}
            </div>
            {Number(lastCalc.blocker_count || 0) > 0 ? (
              <div className="text-amber-800">
                {c.blockers}: {String(lastCalc.blocker_count)}
              </div>
            ) : null}
            <div className="font-mono text-xs text-subtle">calc_run_id={String(lastCalc.calc_run_id || '')}</div>
          </div>
        ) : null}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-[#efe6da] text-xs uppercase tracking-wide text-subtle">
            <tr>
              <th className="py-2 pe-3">Code</th>
              <th className="py-2 pe-3">EN</th>
              <th className="py-2 pe-3">AR</th>
              <th className="py-2 pe-3">Category</th>
              <th className="py-2">Side</th>
            </tr>
          </thead>
          <tbody>
            {catalog.slice(0, 24).map((row) => (
              <tr key={String(row.component_code)} className="border-b border-semantic-line">
                <td className="py-2 pe-3 font-mono text-xs">{String(row.component_code)}</td>
                <td className="py-2 pe-3">{String(row.label_en)}</td>
                <td className="py-2 pe-3" dir="rtl">
                  {String(row.label_ar || '—')}
                </td>
                <td className="py-2 pe-3">{String(row.category)}</td>
                <td className="py-2">{String(row.line_kind)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {catalog.length > 24 ? (
          <div className="mt-2 text-xs text-subtle">Showing first 24 of {catalog.length}</div>
        ) : null}
      </div>
    </div>
  )
}

export default PayrollComponentsPolicyPanel
