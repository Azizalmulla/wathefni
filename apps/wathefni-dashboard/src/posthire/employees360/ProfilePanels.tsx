import { useCallback, useEffect, useRef, useState } from 'react'
import { History } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { getEmployeeOrgHistory } from '@/lib/api'
import type { DashboardAccess, OrgHistoryRow } from '@/types'

import { RecordEpoch, useEmployees360Locale, WorkflowEmpty } from './chrome'
import { ResourceState } from '@/pages/shared/dataState'

function epochForRow(row: OrgHistoryRow, today = new Date().toISOString().slice(0, 10)): 'current' | 'scheduled' | 'historical' {
  const from = String(row.effective_from || '').slice(0, 10)
  const to = row.effective_to ? String(row.effective_to).slice(0, 10) : null
  if (from && from > today) return 'scheduled'
  if (to && to < today) return 'historical'
  return 'current'
}

export function AssignmentHistoryPanel({
  access,
  employeeKey,
  onAccessIssue,
}: {
  access: DashboardAccess
  employeeKey: string
  onAccessIssue: (issue: AccessIssue) => void
}) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const [rows, setRows] = useState<OrgHistoryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)
  const [error, setError] = useState(false)
  const hasRowsRef = useRef(false)

  const load = useCallback(async () => {
    // Soft-keep prior rows — only cold-load shows a spinner.
    if (!hasRowsRef.current) setLoading(true)
    try {
      const res = await getEmployeeOrgHistory(access, employeeKey)
      const next = Array.isArray(res.history) ? res.history : []
      setRows(next)
      hasRowsRef.current = next.length > 0
      setUnavailable(false)
      setError(false)
    } catch (err) {
      const anyErr = err as { detail?: { error?: string }; status?: number }
      if (anyErr?.detail?.error === 'org_v4_disabled' || anyErr?.status === 403) {
        setUnavailable(true)
      } else {
        const issue = accessIssueFromError(err)
        if (issue) onAccessIssue(issue)
        setError(true)
      }
    } finally {
      setLoading(false)
    }
  }, [access, employeeKey, onAccessIssue])

  useEffect(() => {
    hasRowsRef.current = false
    setRows([])
    void load()
  }, [load])

  if (unavailable) return null

  return (
    <Card tone="board" className="p-5" data-testid="assignment-history">
      <CardHeader className="mb-3 border-0 pb-0">
        <CardTitle className="flex items-center gap-2 text-[15px]">
          <History className="h-4 w-4 text-mist" />
          {isAr ? 'تاريخ التعيين' : 'Assignment history'}
        </CardTitle>
        <CardDescription>
          {isAr
            ? 'التعيين الحالي والمجدول والسابق — للقراءة فقط. التعديل من التنظيم.'
            : 'Current, scheduled, and past assignments — read-only here. Change them in Organization.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading && rows.length === 0 ? (
          <ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} testId="assignment-history-state" />
        ) : error ? (
          <ResourceState kind="error" locale={isAr ? 'ar' : 'en'} onRetry={() => void load()} retrying={loading} testId="assignment-history-state" />
        ) : rows.length === 0 ? (
          <WorkflowEmpty
            className="py-8"
            title={isAr ? 'لا يوجد تاريخ تعيين' : 'No assignment history yet'}
            hint={isAr ? 'التغييرات عبر النقل أو الترحيل تظهر هنا.' : 'Transfers and org changes appear here.'}
          />
        ) : (
          <ol className="space-y-2">
            {rows.map((row, idx) => {
              const epoch = epochForRow(row)
              return (
                <li
                  key={row.history_id || `${row.effective_from}-${idx}`}
                  className="flex flex-wrap items-start justify-between gap-2 rounded-[1rem] border border-[#e8dfd0]/80 bg-[#fffdf8] px-3 py-2.5"
                >
                  <div>
                    <p className="text-[13px] font-semibold text-text">{String(row.change_type || 'change').replace(/_/g, ' ')}</p>
                    <p className="text-[12px] text-subtle/90">
                      {String(row.effective_from || '').slice(0, 10)}
                      {row.effective_to ? ` → ${String(row.effective_to).slice(0, 10)}` : ''}
                      {row.manager_employee_key
                        ? ` · ${isAr ? 'المدير' : 'Manager'} ${row.manager_employee_key}`
                        : ''}
                    </p>
                    {row.reason ? <p className="mt-0.5 text-[12px] text-subtle/80">{row.reason}</p> : null}
                  </div>
                  <RecordEpoch epoch={epoch} locale={locale} />
                </li>
              )
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}

