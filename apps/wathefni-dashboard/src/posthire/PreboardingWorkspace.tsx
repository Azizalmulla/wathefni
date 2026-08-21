/**
 * Preboarding Surface Wave — HR Web primary operator workspace.
 * Thin client over frozen preboarding authority (no business-logic rewrite).
 */
import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, UserPlus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/field'
import { StatusPill } from '@/components/ui/page-chrome'
import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'
import { SoftKeepSurface } from '@/components/ui/SoftKeepSurface'
import { URL_BACKED_WORKSPACE_TABS, useUrlBackedParam, useUrlBackedTab } from '@/lib/hrWebUrlTab'
import { ResourceState } from '@/pages/shared/dataState'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getPosthirePreboarding,
  getPosthirePreboardingConfig,
  getPreboardingDetail,
  patchPreboardingSettings,
  postPreboardingCancel,
  postPreboardingCreate,
  postPreboardingItem,
  postPreboardingJoiningDate,
  postPreboardingRemind,
  postPreboardingStart,
  postPreboardingWaive,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type PreboardingWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type AssignmentRow = {
  assignment_id: string
  employee_key: string
  employee_name?: string
  status: string
  joining_date?: string | null
  readiness?: { ready?: boolean; percent?: number; blockers?: Array<{ code?: string; item_key?: string }> }
  items_summary?: { required_open?: number; overdue?: number; blocked?: number }
  is_joining?: boolean
  is_active_employee?: boolean
  employment_lifecycle?: string
  blocker_reasons?: unknown[]
}

type ItemRow = {
  item_id: string
  item_key: string
  title_en?: string
  title_ar?: string
  owner_role?: string
  required?: boolean
  status?: string
  due_at?: string | null
  overdue?: boolean
  blocker_reason?: string | null
  evidence_document_id?: string | null
  row_version?: number
}

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'التهيئة قبل الالتحاق',
        subtitle: 'جاهزية المنضمين الجدد — منفصلون عن الموظفين النشطين',
        joiningBadge: 'ينضم',
        activeBadge: 'نشط',
        filterAll: 'الكل',
        filterBlocked: 'معطّل',
        filterReady: 'جاهز',
        filterProgress: 'قيد التنفيذ',
        refresh: 'تحديث',
        empty: 'لا توجد برامج تهيئة مفتوحة',
        emptyHint: 'أنشئ برنامجاً لموظف بحالة pending_start أو منضم قريباً',
        detail: 'التفاصيل',
        items: 'العناصر',
        audit: 'السجل',
        config: 'القالب والإعدادات',
        joiningDate: 'تاريخ الالتحاق',
        waive: 'استثناء',
        markDone: 'تم',
        block: 'تعطيل',
        start: 'بدء',
        cancel: 'إلغاء / لم يحضر',
        remind: 'تذكير',
        overdue: 'متأخر',
        required: 'مطلوب',
        owner: 'المسؤول',
        readiness: 'الجاهزية',
        blockers: 'العوائق',
        moduleOff: 'وحدة التهيئة غير مفعّلة لهذه الشركة',
        saveJoining: 'حفظ التاريخ',
        create: 'إنشاء تهيئة',
        employeeKey: 'مفتاح الموظف',
        permissionDenied: 'لا تملك صلاحية هذا الإجراء',
      }
    : {
        title: 'Preboarding',
        subtitle: 'Future-joiner readiness — distinct from active employees',
        joiningBadge: 'Joining',
        activeBadge: 'Active',
        filterAll: 'All open',
        filterBlocked: 'Blocked',
        filterReady: 'Ready',
        filterProgress: 'In progress',
        refresh: 'Refresh',
        empty: 'No open preboarding programs',
        emptyHint: 'Create one for a pending_start / joining employee',
        detail: 'Detail',
        items: 'Items',
        audit: 'History',
        config: 'Template & settings',
        joiningDate: 'Joining date',
        waive: 'Waive',
        markDone: 'Done',
        block: 'Block',
        start: 'Start',
        cancel: 'Cancel / no-show',
        remind: 'Remind',
        overdue: 'Overdue',
        required: 'Required',
        owner: 'Owner',
        readiness: 'Readiness',
        blockers: 'Blockers',
        moduleOff: 'Preboarding is not enabled for this company',
        saveJoining: 'Save date',
        create: 'Create preboarding',
        employeeKey: 'Employee key',
        permissionDenied: 'You do not have permission for this action',
      }
}

function statusTone(status: string): 'success' | 'warning' | 'danger' | 'neutral' | 'info' {
  if (status === 'ready') return 'success'
  if (status === 'blocked') return 'danger'
  if (status === 'in_progress') return 'info'
  if (status === 'cancelled') return 'neutral'
  return 'warning'
}

export function PreboardingWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: PreboardingWorkspaceProps) {
  void role
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const c = copy(isAr)
  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState<AssignmentRow[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [tab, setTab] = useUrlBackedTab('preboarding', URL_BACKED_WORKSPACE_TABS.preboarding, 'all')
  const filter = tab === 'all' ? '' : tab
  const [employeeKey, setEmployeeKey] = useUrlBackedParam('preboarding', 'employee', '')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const rowsRef = useRef(rows)
  const selectedIdRef = useRef(selectedId)
  rowsRef.current = rows
  selectedIdRef.current = selectedId
  const [detail, setDetail] = useState<{
    assignment?: AssignmentRow
    items?: ItemRow[]
    events?: Array<{ event_type?: string; created_at?: string; payload?: Record<string, unknown> }>
    permissions?: { manage?: boolean; waive_item?: boolean; configure_template?: boolean }
  } | null>(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [templateItems, setTemplateItems] = useState<Array<Record<string, unknown>>>([])
  const [settings, setSettings] = useState<Record<string, unknown>>({})
  const [joiningDraft, setJoiningDraft] = useState('')
  const [waiveKey, setWaiveKey] = useState<string | null>(null)
  const [waiveReason, setWaiveReason] = useState('')
  const [createKey, setCreateKey] = useState('')
  const [moduleDenied, setModuleDenied] = useState(false)

  const canManage = permissions.includes('preboarding.manage')
  const canWaive = permissions.includes('preboarding.waive_item')

  const loadQueue = useCallback(async () => {
    const cold = rowsRef.current.length === 0
    if (cold) setLoading(true)
    else setRefreshing(true)
    try {
      const res = await getPosthirePreboarding(access, {
        status: filter || undefined,
        limit: 100,
      })
      const next = (res.assignments || []) as AssignmentRow[]
      setRows(next)
      setCounts((res.counts || {}) as Record<string, number>)
      setModuleDenied(false)
      const focused = employeeKey ? next.find((row) => row.employee_key === employeeKey) : null
      if (focused) setSelectedId(focused.assignment_id)
      else if (!selectedIdRef.current && next[0]?.assignment_id) {
        setSelectedId(String(next[0].assignment_id))
      }
    } catch (error) {
      const issue = accessIssueFromError(error)
      if (issue) onAccessIssue?.(issue)
      if (error instanceof DashboardApiError && String(error.code || '').includes('preboarding')) {
        setModuleDenied(true)
      } else {
        onNotice(isAr ? 'تعذر تحميل التهيئة' : 'Could not load preboarding', 'error')
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [access, employeeKey, filter, isAr, onAccessIssue, onNotice])

  const loadDetail = useCallback(
    async (assignmentId: string) => {
      try {
        const res = await getPreboardingDetail(access, assignmentId)
        setDetail(res as typeof detail)
        setJoiningDraft(String(res.assignment?.joining_date || ''))
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

  const filtered = useMemo(() => rows, [rows])

  async function runSafe(fn: () => Promise<unknown>, okMsg: string) {
    try {
      await fn()
      onNotice(okMsg, 'success')
      await loadQueue()
      if (selectedId) await loadDetail(selectedId)
    } catch (error) {
      const issue = accessIssueFromError(error)
      if (issue) onAccessIssue?.(issue)
      onNotice(error instanceof DashboardApiError ? error.message : c.permissionDenied, 'error')
    }
  }

  if (moduleDenied) {
    return (
      <div className="space-y-4 p-6" dir={isAr ? 'rtl' : 'ltr'}>
        <ConfigureInSetupBanner
          title={isAr ? 'التهيئة قبل الالتحاق غير مفعّلة' : 'Preboarding is not enabled'}
          body={
            isAr
              ? 'فعّل الوحدة واضبط قالب ما قبل الالتحاق من وحدة التحكم.'
              : 'Enable the module and configure the preboarding template in Setup Console.'
          }
          anchor="classic-wave1-hire-ready"
          locale={isAr ? 'ar' : 'en'}
        />
        <WorkflowEmpty title={c.moduleOff} />
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-[70vh] flex-col gap-4" dir={isAr ? 'rtl' : 'ltr'}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <HrSurfaceTabs
          value={tab}
          onChange={setTab}
          ariaLabel={isAr ? 'تصفية التهيئة قبل الالتحاق' : 'Preboarding status'}
          items={[
            { id: 'all', label: c.filterAll, count: counts.open_total },
            { id: 'blocked', label: c.filterBlocked, count: counts.blocked },
            { id: 'ready', label: c.filterReady, count: counts.ready },
            { id: 'in_progress', label: c.filterProgress, count: counts.in_progress },
            { id: 'not_started', label: 'Not started', count: counts.not_started },
          ]}
        />
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={() => void loadQueue()} disabled={refreshing}>
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} /> {c.refresh}
          </Button>
          {canManage ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                setConfigOpen(true)
                try {
                  const cfg = await getPosthirePreboardingConfig(access)
                  setTemplateItems(cfg.items || [])
                  setSettings(cfg.settings || {})
                } catch {
                  onNotice(c.permissionDenied, 'error')
                }
              }}
            >
              {c.config}
            </Button>
          ) : null}
        </div>
      </div>

      {canManage ? (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border p-3">
          <div className="min-w-[220px] flex-1">
            <label className="text-xs text-muted-foreground">{c.employeeKey}</label>
            <Input value={createKey} onChange={(e) => setCreateKey(e.target.value)} placeholder="COMPANY-KEY" />
          </div>
          <Button
            size="sm"
            disabled={!createKey.trim()}
            onClick={() =>
              void runSafe(
                () => postPreboardingCreate(access, { employee_key: createKey.trim() }),
                isAr ? 'تم إنشاء التهيئة' : 'Preboarding created',
              )
            }
          >
            <UserPlus className="h-4 w-4" /> {c.create}
          </Button>
        </div>
      ) : null}

      <SoftKeepSurface
        cold={loading && rows.length === 0}
        coldFallback={<ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} />}
        refreshing={refreshing}
        refreshingLabel={isAr ? 'جاري التحديث…' : 'Updating…'}
      >
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(280px,360px)_1fr]">
        <section className="overflow-auto rounded-xl border border-semantic-line/80 bg-semantic-surface">
          {filtered.length === 0 ? (
            <div className="p-6">
              <WorkflowEmpty title={c.empty} hint={c.emptyHint} />
            </div>
          ) : null}
          <ul className="divide-y">
            {filtered.map((row) => (
              <li key={row.assignment_id}>
                <button
                  type="button"
                  className={cn(
                    'flex w-full flex-col gap-1 px-4 py-3 text-start hover:bg-muted/50',
                    selectedId === row.assignment_id && 'bg-muted',
                  )}
                  onClick={() => {
                    setSelectedId(row.assignment_id)
                    setEmployeeKey(row.employee_key)
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{row.employee_name || row.employee_key}</span>
                    <StatusPill tone={statusTone(row.status)}>{row.status}</StatusPill>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <StatusPill tone={row.is_active_employee ? 'success' : 'warning'}>
                      {row.is_active_employee ? c.activeBadge : c.joiningBadge}
                    </StatusPill>
                    <span>{row.joining_date || '—'}</span>
                    {(row.items_summary?.overdue || 0) > 0 ? (
                      <span className="inline-flex items-center gap-1 text-amber-700">
                        <Clock3 className="h-3 w-3" /> {row.items_summary?.overdue} {c.overdue}
                      </span>
                    ) : null}
                    {row.status === 'blocked' ? (
                      <span className="inline-flex items-center gap-1 text-red-700">
                        <AlertTriangle className="h-3 w-3" /> {c.blockers}
                      </span>
                    ) : null}
                    {row.status === 'ready' ? (
                      <span className="inline-flex items-center gap-1 text-emerald-700">
                        <CheckCircle2 className="h-3 w-3" /> {c.readiness} {row.readiness?.percent ?? 100}%
                      </span>
                    ) : (
                      <span>
                        {c.readiness} {row.readiness?.percent ?? 0}%
                      </span>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="overflow-auto rounded-xl border bg-background p-4">
          {!selectedId || !detail?.assignment ? (
            <WorkflowEmpty title={c.detail} description={c.emptyHint} />
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold">
                    {detail.assignment.employee_name || detail.assignment.employee_key}
                  </h2>
                  <div className="mt-1 flex flex-wrap gap-2 text-sm">
                    <StatusPill tone={statusTone(detail.assignment.status)}>{detail.assignment.status}</StatusPill>
                    <StatusPill tone={detail.assignment.is_active_employee ? 'success' : 'warning'}>
                      {detail.assignment.is_active_employee ? c.activeBadge : c.joiningBadge}
                    </StatusPill>
                    <span className="text-muted-foreground">
                      {c.readiness}: {detail.assignment.readiness?.percent ?? 0}%
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {canManage && detail.assignment.status === 'not_started' ? (
                    <Button size="sm" onClick={() => void runSafe(() => postPreboardingStart(access, selectedId), 'Started')}>
                      {c.start}
                    </Button>
                  ) : null}
                  {canManage ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void runSafe(() => postPreboardingRemind(access, selectedId, {}), 'Reminded')}
                    >
                      {c.remind}
                    </Button>
                  ) : null}
                  {canManage ? (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() =>
                        void runSafe(
                          () => postPreboardingCancel(access, selectedId, { cancel_reason: 'no_show' }),
                          'Cancelled',
                        )
                      }
                    >
                      {c.cancel}
                    </Button>
                  ) : null}
                </div>
              </div>

              <div className="flex flex-wrap items-end gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">{c.joiningDate}</label>
                  <Input
                    type="date"
                    value={joiningDraft?.slice?.(0, 10) || ''}
                    disabled={!canManage}
                    onChange={(e) => setJoiningDraft(e.target.value)}
                  />
                </div>
                {canManage ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void runSafe(
                        () => postPreboardingJoiningDate(access, selectedId, { joining_date: joiningDraft }),
                        isAr ? 'تم حفظ التاريخ' : 'Joining date saved',
                      )
                    }
                  >
                    {c.saveJoining}
                  </Button>
                ) : null}
              </div>

              {(detail.assignment.readiness?.blockers || []).length > 0 ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                  <div className="mb-1 font-medium">{c.blockers}</div>
                  <ul className="list-disc ps-5">
                    {(detail.assignment.readiness?.blockers || []).map((b, idx) => (
                      <li key={`${b.item_key}-${idx}`}>
                        {b.item_key}: {b.code}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div>
                <h3 className="mb-2 font-medium">{c.items}</h3>
                <ul className="divide-y rounded-lg border">
                  {(detail.items || []).map((item) => (
                    <li key={item.item_id} className="flex flex-col gap-2 px-3 py-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="font-medium">{isAr ? item.title_ar || item.title_en : item.title_en || item.item_key}</div>
                        <div className="text-xs text-muted-foreground">
                          {c.owner}: {item.owner_role}
                          {item.required ? ` · ${c.required}` : ''}
                          {item.overdue ? ` · ${c.overdue}` : ''}
                          {item.evidence_document_id ? ` · doc:${item.evidence_document_id}` : ''}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusPill tone={statusTone(item.status || 'pending')}>{item.status}</StatusPill>
                        {canManage && item.status !== 'done' && item.status !== 'waived' ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void runSafe(
                                  () =>
                                    postPreboardingItem(access, selectedId, item.item_key, {
                                      to_status: 'done',
                                      expected_row_version: item.row_version,
                                    }),
                                  'Updated',
                                )
                              }
                            >
                              {c.markDone}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void runSafe(
                                  () =>
                                    postPreboardingItem(access, selectedId, item.item_key, {
                                      to_status: 'blocked',
                                      blocker_reason: 'hr_blocked',
                                      expected_row_version: item.row_version,
                                    }),
                                  'Blocked',
                                )
                              }
                            >
                              {c.block}
                            </Button>
                          </>
                        ) : null}
                        {canWaive && item.status !== 'done' && item.status !== 'waived' ? (
                          <Button size="sm" variant="ghost" onClick={() => setWaiveKey(item.item_key)}>
                            {c.waive}
                          </Button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              {waiveKey ? (
                <div className="rounded-lg border p-3 space-y-2">
                  <div className="text-sm font-medium">
                    {c.waive}: {waiveKey}
                  </div>
                  <Textarea value={waiveReason} onChange={(e) => setWaiveReason(e.target.value)} rows={3} />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={waiveReason.trim().length < 2}
                      onClick={() =>
                        void runSafe(async () => {
                          await postPreboardingWaive(access, selectedId, waiveKey, { waive_reason: waiveReason })
                          setWaiveKey(null)
                          setWaiveReason('')
                        }, 'Waived')
                      }
                    >
                      {c.waive}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setWaiveKey(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : null}

              <div>
                <h3 className="mb-2 font-medium">{c.audit}</h3>
                <ul className="max-h-48 space-y-1 overflow-auto text-xs text-muted-foreground">
                  {(detail.events || []).map((ev, idx) => (
                    <li key={`${ev.event_type}-${idx}`}>
                      {String(ev.created_at || '')} · {ev.event_type}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </section>
      </div>
      </SoftKeepSurface>

      {configOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[85vh] w-full max-w-2xl overflow-auto rounded-xl bg-background p-5 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{c.config}</h3>
              <Button size="sm" variant="ghost" onClick={() => setConfigOpen(false)}>
                Close
              </Button>
            </div>
            <div className="mb-4 space-y-2 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={Boolean(settings.auto_create_on_offer_accept)}
                  onChange={(e) =>
                    void runSafe(
                      () =>
                        patchPreboardingSettings(access, {
                          auto_create_on_offer_accept: e.target.checked,
                        }).then((r) => setSettings(r.settings || {})),
                      'Saved',
                    )
                  }
                />
                auto_create_on_offer_accept
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={Boolean(settings.required_for_ready_mark)}
                  onChange={(e) =>
                    void runSafe(
                      () =>
                        patchPreboardingSettings(access, {
                          required_for_ready_mark: e.target.checked,
                        }).then((r) => setSettings(r.settings || {})),
                      'Saved',
                    )
                  }
                />
                required_for_ready_mark
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={Boolean(settings.handoff_onboarding_enabled)}
                  onChange={(e) =>
                    void runSafe(
                      () =>
                        patchPreboardingSettings(access, {
                          handoff_onboarding_enabled: e.target.checked,
                        }).then((r) => setSettings(r.settings || {})),
                      'Saved',
                    )
                  }
                />
                handoff_onboarding_enabled
              </label>
            </div>
            <ul className="divide-y rounded-lg border text-sm">
              {templateItems.map((t) => (
                <li key={String(t.item_key)} className="px-3 py-2">
                  <div className="font-medium">{String(isAr ? t.title_ar || t.title_en : t.title_en)}</div>
                  <div className="text-xs text-muted-foreground">
                    {String(t.item_key)} · {String(t.owner_role)} · {t.required ? c.required : 'optional'}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  )
}
