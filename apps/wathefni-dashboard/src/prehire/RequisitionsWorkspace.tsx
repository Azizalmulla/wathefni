/**
 * Requisitions Surface Wave — HR Web (Pre-Hiring).
 * Thin client over frozen requisitions authority + SoD approve/reject.
 */
import { BriefcaseBusiness, CheckCircle2, Loader2, RefreshCw, XCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getPrehireRequisitions,
  getRequisitionDetail,
  postRequisitionCreate,
  postRequisitionTransition,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type RequisitionsWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type ReqRow = {
  requisition_id: string
  title_en?: string
  title_ar?: string
  status: string
  headcount?: number
  department?: string | null
  target_hire_date?: string | null
  decision_required?: boolean
  row_version?: number
  created_by_user_id?: string | null
}

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'طلبات التوظيف',
        subtitle: 'الموافقة على الاحتياج قبل نشر الوظائف — من يمنع التعيين؟',
        attention: 'يحتاج موافقة',
        draft: 'مسودة',
        approved: 'معتمد',
        open: 'مفتوح',
        filled: 'مُشغل',
        cancelled: 'ملغى',
        rejected: 'مرفوض',
        refresh: 'تحديث',
        empty: 'لا توجد طلبات',
        create: 'إنشاء طلب',
        titleField: 'المسمى',
        headcount: 'العدد',
        department: 'القسم',
        submit: 'إرسال للموافقة',
        approve: 'اعتماد',
        reject: 'رفض',
        openReq: 'فتح للتعيين',
        cancel: 'إلغاء',
        sod: 'منشئ الطلب لا يعتمد طلبه بنفسه',
        moduleOff: 'وحدة طلبات التوظيف غير مفعّلة',
        audit: 'السجل',
      }
    : {
        title: 'Requisitions',
        subtitle: 'Approve headcount before jobs publish — who is blocking hire?',
        attention: 'Needs approval',
        draft: 'Draft',
        approved: 'Approved',
        open: 'Open',
        filled: 'Filled',
        cancelled: 'Cancelled',
        rejected: 'Rejected',
        refresh: 'Refresh',
        empty: 'No requisitions',
        create: 'Create requisition',
        titleField: 'Title',
        headcount: 'Headcount',
        department: 'Department',
        submit: 'Submit for approval',
        approve: 'Approve',
        reject: 'Reject',
        openReq: 'Open to fill',
        cancel: 'Cancel',
        sod: 'Creator cannot self-approve',
        moduleOff: 'Requisitions is not enabled for this company',
        audit: 'History',
      }
}

function tone(status: string): 'success' | 'warning' | 'danger' | 'neutral' | 'info' {
  if (status === 'approved' || status === 'open' || status === 'filled') return 'success'
  if (status === 'pending_approval') return 'warning'
  if (status === 'rejected' || status === 'cancelled') return 'danger'
  return 'info'
}

export function RequisitionsWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: RequisitionsWorkspaceProps) {
  void role
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const c = copy(isAr)
  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState<ReqRow[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [filter, setFilter] = useState('attention')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<{
    requisition?: ReqRow
    events?: Array<{ event_type?: string; created_at?: string }>
  } | null>(null)
  const [moduleDenied, setModuleDenied] = useState(false)
  const [title, setTitle] = useState('')
  const [headcount, setHeadcount] = useState('1')
  const [department, setDepartment] = useState('')

  const canManage = permissions.includes('requisitions.manage')
  const canApprove = permissions.includes('requisitions.approve')

  const loadQueue = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getPrehireRequisitions(access, { status: filter || undefined, limit: 100 })
      setRows((res.requisitions || []) as ReqRow[])
      setCounts((res.counts || {}) as Record<string, number>)
      setModuleDenied(false)
      if (!selectedId && res.requisitions?.[0]?.requisition_id) {
        setSelectedId(String(res.requisitions[0].requisition_id))
      }
    } catch (error) {
      const issue = accessIssueFromError(error)
      if (issue) onAccessIssue?.(issue)
      if (error instanceof DashboardApiError && String(error.code || '').includes('requisition')) {
        setModuleDenied(true)
      } else {
        onNotice(isAr ? 'تعذر تحميل الطلبات' : 'Could not load requisitions', 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [access, filter, isAr, onAccessIssue, onNotice, selectedId])

  const loadDetail = useCallback(
    async (id: string) => {
      try {
        setDetail((await getRequisitionDetail(access, id)) as typeof detail)
      } catch (error) {
        const issue = accessIssueFromError(error)
        if (issue) onAccessIssue?.(issue)
        onNotice(isAr ? 'تعذر فتح التفاصيل' : 'Could not open detail', 'error')
      }
    },
    [access, isAr, onAccessIssue, onNotice],
  )

  useEffect(() => {
    void loadQueue()
  }, [loadQueue])
  useEffect(() => {
    if (selectedId) void loadDetail(selectedId)
  }, [selectedId, loadDetail])

  async function runSafe(fn: () => Promise<unknown>, okMsg: string) {
    try {
      await fn()
      onNotice(okMsg, 'success')
      await loadQueue()
      if (selectedId) await loadDetail(selectedId)
    } catch (error) {
      const issue = accessIssueFromError(error)
      if (issue) onAccessIssue?.(issue)
      onNotice(error instanceof DashboardApiError ? error.message : 'Error', 'error')
    }
  }

  if (moduleDenied) {
    return (
      <div className="space-y-4 p-6" dir={isAr ? 'rtl' : 'ltr'}>
        <ConfigureInSetupBanner
          title={isAr ? 'طلبات التوظيف غير مفعّلة' : 'Requisitions is not enabled'}
          body={
            isAr
              ? 'فعّل الوحدة واضبط بوابة الوظائف من وحدة التحكم.'
              : 'Enable the module and configure the job-publish gate in Setup Console.'
          }
          anchor="classic-wave1-hire-ready"
          locale={isAr ? 'ar' : 'en'}
        />
        <p className="text-sm text-muted-foreground">{c.moduleOff}</p>
      </div>
    )
  }

  const selected = detail?.requisition

  return (
    <div className="flex h-full min-h-[70vh] flex-col gap-4 p-4 md:p-6" dir={isAr ? 'rtl' : 'ltr'}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BriefcaseBusiness className="h-6 w-6" />
            {c.title}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{c.subtitle}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void loadQueue()}>
          <RefreshCw className="me-2 h-4 w-4" />
          {c.refresh}
        </Button>
      </header>

      <div className="flex flex-wrap gap-2">
        {(
          [
            ['attention', c.attention, counts.attention],
            ['draft', c.draft, counts.draft],
            ['pending_approval', c.attention, counts.pending_approval],
            ['approved', c.approved, counts.approved],
            ['open', c.open, counts.open],
            ['filled', c.filled, counts.filled],
          ] as const
        ).map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={cn(
              'rounded-full border px-3 py-1 text-sm',
              filter === key ? 'border-foreground bg-foreground text-background' : 'border-border',
            )}
          >
            {label}
            {typeof count === 'number' ? ` · ${count}` : ''}
          </button>
        ))}
      </div>

      {canManage ? (
        <div className="grid gap-2 rounded-lg border border-border/60 p-3 md:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">{c.titleField}</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">{c.headcount}</label>
            <Input value={headcount} onChange={(e) => setHeadcount(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">{c.department}</label>
            <Input value={department} onChange={(e) => setDepartment(e.target.value)} />
          </div>
          <div className="flex items-end gap-2">
            <Button
              size="sm"
              disabled={!title.trim()}
              onClick={() =>
                void runSafe(
                  () =>
                    postRequisitionCreate(access, {
                      title_en: title.trim(),
                      title_ar: isAr ? title.trim() : undefined,
                      headcount: Number(headcount) || 1,
                      department: department || undefined,
                      submit: false,
                    }),
                  isAr ? 'أُنشئ كمسودة' : 'Draft created',
                )
              }
            >
              {c.create}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!title.trim()}
              onClick={() =>
                void runSafe(
                  () =>
                    postRequisitionCreate(access, {
                      title_en: title.trim(),
                      headcount: Number(headcount) || 1,
                      department: department || undefined,
                      submit: true,
                    }),
                  isAr ? 'أُرسل للموافقة' : 'Submitted',
                )
              }
            >
              {c.submit}
            </Button>
          </div>
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(280px,1fr)_minmax(360px,1.2fr)]">
        <section className="overflow-auto rounded-xl border border-border/70">
          {loading ? (
            <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> …
            </div>
          ) : rows.length === 0 ? (
            <WorkflowEmpty title={c.empty} />
          ) : (
            <ul className="divide-y divide-border/60">
              {rows.map((row) => (
                <li key={row.requisition_id}>
                  <button
                    type="button"
                    className={cn(
                      'flex w-full flex-col gap-1 px-4 py-3 text-start hover:bg-muted/40',
                      selectedId === row.requisition_id && 'bg-muted/60',
                    )}
                    onClick={() => setSelectedId(row.requisition_id)}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">
                        {isAr ? row.title_ar || row.title_en : row.title_en}
                      </span>
                      <StatusPill tone={tone(row.status)}>{row.status}</StatusPill>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {c.headcount}: {row.headcount}
                      {row.department ? ` · ${row.department}` : ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="overflow-auto rounded-xl border border-border/70 p-4">
          {!selected ? (
            <WorkflowEmpty title={c.empty} />
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-xl font-semibold">
                    {isAr ? selected.title_ar || selected.title_en : selected.title_en}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {c.headcount}: {selected.headcount}
                    {selected.department ? ` · ${selected.department}` : ''}
                  </p>
                </div>
                <StatusPill tone={tone(selected.status)}>{selected.status}</StatusPill>
              </div>
              <p className="text-xs text-muted-foreground">{c.sod}</p>
              <div className="flex flex-wrap gap-2">
                {canManage && selected.status === 'draft' ? (
                  <Button
                    size="sm"
                    onClick={() =>
                      void runSafe(
                        () =>
                          postRequisitionTransition(access, selected.requisition_id, {
                            to_status: 'pending_approval',
                            expected_row_version: selected.row_version,
                          }),
                        c.submit,
                      )
                    }
                  >
                    {c.submit}
                  </Button>
                ) : null}
                {canApprove && selected.status === 'pending_approval' ? (
                  <>
                    <Button
                      size="sm"
                      onClick={() =>
                        void runSafe(
                          () =>
                            postRequisitionTransition(access, selected.requisition_id, {
                              to_status: 'approved',
                              expected_row_version: selected.row_version,
                            }),
                          c.approve,
                        )
                      }
                    >
                      <CheckCircle2 className="me-1 h-4 w-4" /> {c.approve}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() =>
                        void runSafe(
                          () =>
                            postRequisitionTransition(access, selected.requisition_id, {
                              to_status: 'rejected',
                              expected_row_version: selected.row_version,
                            }),
                          c.reject,
                        )
                      }
                    >
                      <XCircle className="me-1 h-4 w-4" /> {c.reject}
                    </Button>
                  </>
                ) : null}
                {canManage && selected.status === 'approved' ? (
                  <Button
                    size="sm"
                    onClick={() =>
                      void runSafe(
                        () =>
                          postRequisitionTransition(access, selected.requisition_id, {
                            to_status: 'open',
                            expected_row_version: selected.row_version,
                          }),
                        c.openReq,
                      )
                    }
                  >
                    {c.openReq}
                  </Button>
                ) : null}
                {canManage && !['filled', 'cancelled'].includes(selected.status) ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void runSafe(
                        () =>
                          postRequisitionTransition(access, selected.requisition_id, {
                            to_status: 'cancelled',
                            expected_row_version: selected.row_version,
                          }),
                        c.cancel,
                      )
                    }
                  >
                    {c.cancel}
                  </Button>
                ) : null}
              </div>
              <div>
                <h3 className="mb-2 font-medium">{c.audit}</h3>
                <ul className="max-h-48 space-y-1 overflow-auto text-xs text-muted-foreground">
                  {(detail?.events || []).map((e, i) => (
                    <li key={`${e.created_at}-${i}`}>
                      {String(e.created_at || '').slice(0, 19)} · {e.event_type}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
