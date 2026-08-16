/**
 * Payroll Wave 5 — PIFSS + EOS review worksheet workspace (staging).
 * Non-authoritative review only. No remittance / payable / filing.
 */
import { useCallback, useEffect, useState } from 'react'

import {
  DashboardApiError,
  getPayrollStatutoryWorkspace,
  postPayrollStatutoryApprove,
  postPayrollStatutoryEos,
  postPayrollStatutoryOverrideConfirm,
  postPayrollStatutoryOverrideInitiate,
  postPayrollStatutoryPifss,
  postPayrollStatutorySubmit,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { BlockedReason, useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import { payrollStatutoryCopy, statutoryStatusTone } from '@/posthire/payrollStatutoryUx'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type StatutoryWorksheetWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

function can(permissions: string[], permission: string): boolean {
  return permissions.includes(permission)
}

type WsRow = {
  worksheet_id: string
  employee_key?: string
  employee_category?: string
  status: string
  period_start?: string
  period_end?: string
  termination_date?: string
  row_version?: number
}

type Workspace = {
  pifss_worksheets?: WsRow[]
  eos_worksheets?: WsRow[]
  rule_tables?: Array<Record<string, unknown>>
  can_manage?: boolean
  can_approve?: boolean
}

export function StatutoryWorksheetWorkspace({
  access,
  permissions,
  onNotice,
  onAccessIssue,
}: StatutoryWorksheetWorkspaceProps) {
  const locale = useEmployees360Locale()
  const c = payrollStatutoryCopy(locale)
  const isAr = locale === 'ar'
  const canManage = can(permissions, 'payroll.manage')
  const canApprove = can(permissions, 'payroll.approve')
  const [data, setData] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'pifss' | 'eos' | 'rules'>('pifss')
  const [reason, setReason] = useState('')
  const [employeeKey, setEmployeeKey] = useState('')
  const [category, setCategory] = useState('kuwaiti_national')
  const [selected, setSelected] = useState<{ kind: 'pifss' | 'eos'; row: WsRow } | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const ws = (await getPayrollStatutoryWorkspace(access)) as Workspace
      setData(ws)
    } catch (err) {
      if (err instanceof DashboardApiError && err.status === 404) {
        setError('disabled')
      } else {
        const issue = accessIssueFromError(err)
        if (issue && onAccessIssue) onAccessIssue(issue)
        setError(err instanceof Error ? err.message : 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(fn: () => Promise<unknown>, okMsg: string) {
    if (!reason.trim()) {
      onNotice(c.reasonRequired, 'error')
      return
    }
    setBusy(true)
    try {
      await fn()
      onNotice(okMsg, 'success')
      setReason('')
      await reload()
    } catch (err) {
      const detail =
        err instanceof DashboardApiError
          ? String((err.body as { detail?: { error?: string } })?.detail?.error || err.message)
          : err instanceof Error
            ? err.message
            : 'error'
      onNotice(detail, 'error')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <p className="text-sm text-subtle">{c.loading}</p>
  if (error === 'disabled') {
    return <BlockedReason title={c.disabled} detail={c.disabledHint} onRetry={() => void reload()} retryLabel={c.retry} />
  }
  if (error) return <BlockedReason title={error} onRetry={() => void reload()} retryLabel={c.retry} />

  const rows = tab === 'pifss' ? data?.pifss_worksheets || [] : tab === 'eos' ? data?.eos_worksheets || [] : []

  return (
    <div className="space-y-4" data-testid="statutory-worksheet-workspace" dir={isAr ? 'rtl' : 'ltr'}>
      <div>
        <h2 className="text-lg font-semibold text-text">{c.title}</h2>
        <p className="mt-1 text-sm text-subtle">{c.subtitle}</p>
        <p className="mt-2 rounded-md bg-black/[0.03] px-3 py-2 text-[13px] text-text">{c.honesty}</p>
        <p className="mt-1 text-[12px] text-subtle">
          {c.paymentDisabled} · {c.noRemittance} · {c.noAutoPayable} · {c.reviewOnly}
        </p>
        <p className="mt-1 text-[12px] text-subtle">{c.counselHint}</p>
        <p className="mt-1 text-[12px] text-subtle md:hidden">{c.mobileHint}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {(['pifss', 'eos', 'rules'] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={`rounded-lg px-3 py-1.5 text-[13px] font-medium ${
              tab === t ? 'bg-wf-ink/10 text-text' : 'text-subtle hover:bg-black/[0.03]'
            }`}
            onClick={() => setTab(t)}
          >
            {t === 'pifss' ? c.tabPifss : t === 'eos' ? c.tabEos : c.tabRules}
          </button>
        ))}
        <button
          type="button"
          className="ms-auto rounded-lg px-3 py-1.5 text-[13px] text-subtle hover:bg-black/[0.03]"
          onClick={() => void reload()}
        >
          {c.refresh}
        </button>
      </div>

      <label className="block text-[13px] text-subtle">
        {c.reasonPlaceholder}
        <input
          className="mt-1 w-full rounded-md border border-black/10 bg-white px-3 py-2 text-sm"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>

      {tab !== 'rules' && canManage ? (
        <div className="flex flex-wrap gap-2">
          <input
            className="min-w-[12rem] flex-1 rounded-md border border-black/10 px-3 py-2 text-sm"
            placeholder="employee_key"
            value={employeeKey}
            onChange={(e) => setEmployeeKey(e.target.value)}
          />
          <select
            className="rounded-md border border-black/10 px-3 py-2 text-sm"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="kuwaiti_national">kuwaiti_national</option>
            <option value="gcc_national">gcc_national</option>
            <option value="expatriate">expatriate</option>
          </select>
          {tab === 'pifss' ? (
            <button
              type="button"
              disabled={busy || !employeeKey}
              className="rounded-lg bg-wf-ink px-3 py-2 text-[13px] text-white disabled:opacity-40"
              onClick={() =>
                void runAction(
                  () =>
                    postPayrollStatutoryPifss(access, {
                      employee_key: employeeKey,
                      employee_category: category,
                      period_start: '2033-05-01',
                      period_end: '2033-05-31',
                      contributory_salary: 1000,
                      reason,
                    }),
                  c.generatePifss,
                )
              }
            >
              {c.generatePifss}
            </button>
          ) : (
            <button
              type="button"
              disabled={busy || !employeeKey}
              className="rounded-lg bg-wf-ink px-3 py-2 text-[13px] text-white disabled:opacity-40"
              onClick={() =>
                void runAction(
                  () =>
                    postPayrollStatutoryEos(access, {
                      employee_key: employeeKey,
                      employee_category: category,
                      termination_date: '2033-05-15',
                      termination_reason: 'employer_termination',
                      service_start: '2018-01-01',
                      service_end: '2033-05-15',
                      monthly_wage: 800,
                      pay_type: 'monthly',
                      art_51_53_status: 'resolved',
                      law_17_2018_status: category === 'kuwaiti_national' ? 'resolved' : 'not_applicable',
                      reason,
                    }),
                  c.generateEos,
                )
              }
            >
              {c.generateEos}
            </button>
          )}
        </div>
      ) : null}

      {tab === 'rules' ? (
        <div className="overflow-x-auto">
          {(data?.rule_tables || []).length === 0 ? (
            <WorkflowEmpty title={c.empty} detail={c.counselHint} />
          ) : (
            <table className="min-w-full text-left text-[13px]">
              <thead className="text-subtle">
                <tr>
                  <th className="px-2 py-1">Domain</th>
                  <th className="px-2 py-1">{c.category}</th>
                  <th className="px-2 py-1">Version</th>
                  <th className="px-2 py-1">Counsel</th>
                </tr>
              </thead>
              <tbody>
                {(data?.rule_tables || []).map((r) => (
                  <tr key={String(r.rule_table_id)} className="border-t border-black/5">
                    <td className="px-2 py-2">{String(r.rule_domain)}</td>
                    <td className="px-2 py-2">{String(r.employee_category)}</td>
                    <td className="px-2 py-2">{String(r.version_label)}</td>
                    <td className="px-2 py-2">{String(r.counsel_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : rows.length === 0 ? (
        <WorkflowEmpty title={c.empty} detail={c.emptyHint} />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-[13px]">
            <thead className="text-subtle">
              <tr>
                <th className="px-2 py-1">Employee</th>
                <th className="px-2 py-1">{c.category}</th>
                <th className="px-2 py-1">{c.status}</th>
                <th className="px-2 py-1">ID</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.worksheet_id}
                  className={`cursor-pointer border-t border-black/5 ${
                    selected?.row.worksheet_id === r.worksheet_id ? 'bg-wf-ink/5' : ''
                  }`}
                  onClick={() => setSelected({ kind: tab === 'eos' ? 'eos' : 'pifss', row: r })}
                >
                  <td className="px-2 py-2">{r.employee_key}</td>
                  <td className="px-2 py-2">{r.employee_category}</td>
                  <td className={`px-2 py-2 ${statutoryStatusTone(r.status)}`}>
                    {r.status}
                    {r.status === 'approved' ? ` · ${c.immutable}` : ''}
                  </td>
                  <td className="px-2 py-2 font-mono text-[11px]">{r.worksheet_id.slice(0, 8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <div className="flex flex-wrap gap-2 rounded-md border border-black/10 p-3">
          {canManage && selected.row.status === 'draft' ? (
            <button
              type="button"
              disabled={busy}
              className="rounded-lg bg-wf-ink/90 px-3 py-2 text-[13px] text-white disabled:opacity-40"
              onClick={() =>
                void runAction(
                  () =>
                    postPayrollStatutorySubmit(access, selected.kind, selected.row.worksheet_id, {
                      reason,
                      expected_row_version: selected.row.row_version ?? 1,
                    }),
                  c.submitReview,
                )
              }
            >
              {c.submitReview}
            </button>
          ) : null}
          {canApprove && selected.row.status === 'in_review' ? (
            <button
              type="button"
              disabled={busy}
              className="rounded-lg bg-wf-ink px-3 py-2 text-[13px] text-white disabled:opacity-40"
              onClick={() =>
                void runAction(
                  () =>
                    postPayrollStatutoryApprove(access, selected.kind, selected.row.worksheet_id, {
                      reason,
                      expected_row_version: selected.row.row_version ?? 1,
                    }),
                  c.approve,
                )
              }
            >
              {c.approve}
            </button>
          ) : null}
          {canApprove && ['draft', 'in_review', 'counsel_required', 'unsupported'].includes(selected.row.status) ? (
            <>
              <button
                type="button"
                disabled={busy}
                className="rounded-lg border border-black/10 px-3 py-2 text-[13px] disabled:opacity-40"
                onClick={() =>
                  void runAction(
                    () =>
                      postPayrollStatutoryOverrideInitiate(access, selected.kind, selected.row.worksheet_id, {
                        reason,
                        evidence: { note: reason },
                      }),
                    c.override,
                  )
                }
              >
                {c.override}
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded-lg border border-black/10 px-3 py-2 text-[13px] disabled:opacity-40"
                onClick={() =>
                  void runAction(
                    () =>
                      postPayrollStatutoryOverrideConfirm(access, selected.kind, selected.row.worksheet_id, {
                        reason,
                      }),
                    c.confirmOverride,
                  )
                }
              >
                {c.confirmOverride}
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
