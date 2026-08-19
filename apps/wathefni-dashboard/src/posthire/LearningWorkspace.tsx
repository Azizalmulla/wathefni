/**
 * R5E Learning workspace — thin client over frozen Wave 6 C2.
 * Assignment ≠ enrollment ≠ attendance ≠ completion ≠ certification.
 * Performance / Talent / Job Architecture are optional enrichments.
 */
import { RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getLearningAssignments,
  getLearningCatalog,
  getLearningCertificates,
  getLearningHistory,
  getLearningRequests,
  getLearningSessions,
  getLearningWorkspace,
  postLearningJson,
  type LearningWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type LearningWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'catalog' | 'assignments' | 'sessions' | 'certifications' | 'requests' | 'history'

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'التعلم والتطوير',
        subtitle: 'الكتالوج والإسناد والجلسات والإكمال بدليل والشهادات — ليست خطط التطوير.',
        overview: 'نظرة عامة',
        catalog: 'الكتالوج',
        assignments: 'الإسنادات',
        sessions: 'الجلسات',
        certifications: 'الشهادات',
        requests: 'الطلبات والموافقات',
        history: 'السجل',
        refresh: 'تحديث',
        active: 'تعلم نشط',
        overdue: 'إلزامي متأخر',
        upcoming: 'جلسات قادمة',
        expiring: 'شهادات قاربت الانتهاء',
        pending: 'طلبات تحتاج قراراً',
        emptyCatalog: 'لا توجد عناصر كتالوج بعد',
        emptyAssignments: 'لا توجد إسنادات تعلم',
        emptySessions: 'لا توجد جلسات مجدولة',
        emptyCerts: 'لا توجد شهادات',
        emptyRequests: 'لا توجد طلبات تعلم',
        emptyHistory: 'لا يوجد سجل تعلم بعد',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        loadError: 'تعذر تحميل هذا القسم. هذه ليست نتيجة فارغة.',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'التعلم غير متاح لهذه الشركة.',
        config: 'السياسات في الإعداد',
        boundaries: 'الإسناد ليس تسجيلاً. التسجيل ليس حضوراً. الحضور ليس إكمالاً. الإكمال ليس شهادة.',
        overdueNotFail: 'التأخر لا يعني رسوباً تلقائياً.',
        createItem: 'عنصر كتالوج',
        assign: 'إسناد',
        session: 'جلسة',
        enroll: 'تسجيل',
        attendance: 'حضور',
        complete: 'إكمال بدليل',
        certify: 'إصدار شهادة',
        approve: 'موافقة',
        reject: 'رفض',
        employeeKey: 'مفتاح الموظف',
        titleEn: 'العنوان (إنجليزي)',
        titleAr: 'العنوان (عربي)',
        code: 'الرمز',
        reason: 'السبب',
        evidence: 'مرجع الدليل',
      }
    : {
        title: 'Learning & Development',
        subtitle: 'Catalog, assignments, sessions, evidence-backed completion, and certificates — not development plans.',
        overview: 'Overview',
        catalog: 'Catalog',
        assignments: 'Assignments',
        sessions: 'Sessions',
        certifications: 'Certifications',
        requests: 'Requests & approvals',
        history: 'History',
        refresh: 'Refresh',
        active: 'Active learning',
        overdue: 'Overdue mandatory',
        upcoming: 'Upcoming sessions',
        expiring: 'Expiring certificates',
        pending: 'Requests needing a decision',
        emptyCatalog: 'No catalog items yet',
        emptyAssignments: 'No learning assigned',
        emptySessions: 'No scheduled sessions',
        emptyCerts: 'No certificates',
        emptyRequests: 'No learning requests',
        emptyHistory: 'No learning history yet',
        emptyHint: 'This is a true empty result — not a load failure.',
        loadError: 'This section could not be loaded. This is not an empty result.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Learning is not available for this company.',
        config: 'Policies live in Setup',
        boundaries: 'Assigned is not enrolled. Enrolled is not attended. Attended is not completed. Completed is not certified.',
        overdueNotFail: 'Past due is not automatic failure.',
        createItem: 'Catalog item',
        assign: 'Assign',
        session: 'Session',
        enroll: 'Enroll',
        attendance: 'Attendance',
        complete: 'Evidence-backed completion',
        certify: 'Issue certificate',
        approve: 'Approve',
        reject: 'Reject',
        employeeKey: 'Employee key',
        titleEn: 'Title (EN)',
        titleAr: 'Title (AR)',
        code: 'Code',
        reason: 'Reason',
        evidence: 'Evidence reference',
      }
}

export function LearningWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: LearningWorkspaceProps) {
  const isAr = useEmployees360Locale() === 'ar'
  const t = copy(isAr)
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<LearningWorkspacePayload | null>(null)
  const [catalog, setCatalog] = useState<Array<Record<string, unknown>>>([])
  const [assignments, setAssignments] = useState<Array<Record<string, unknown>>>([])
  const [sessions, setSessions] = useState<Array<Record<string, unknown>>>([])
  const [certs, setCerts] = useState<Array<Record<string, unknown>>>([])
  const [requests, setRequests] = useState<Array<Record<string, unknown>>>([])
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([])
  const [tabError, setTabError] = useState(false)
  const [tabReady, setTabReady] = useState(false)
  const [code, setCode] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [titleAr, setTitleAr] = useState('')
  const [empKey, setEmpKey] = useState('')
  const [itemId, setItemId] = useState('')
  const [reason, setReason] = useState('')
  const [evidence, setEvidence] = useState('')

  const canManage = hasActorPermission(permissions, 'learning.manage')
  const canAssign = hasActorPermission(permissions, 'learning.assign') || canManage
  const canApprove = hasActorPermission(permissions, 'learning.approve') || canManage
  const managerOnly = String(role || '').toLowerCase() === 'manager'

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      const data = await getLearningWorkspace(access)
      setPayload(data)
      if (data.resource_state === 'unavailable' || data.enabled === false) {
        setUnavailable(true)
      }
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      if (err instanceof DashboardApiError) {
        if (err.status === 403) {
          const codeErr = String((err.body as { error?: string } | undefined)?.error || '')
          if (codeErr.includes('permission') || codeErr.includes('forbidden') || codeErr.includes('scope')) {
            setForbidden(true)
          } else {
            setUnavailable(true)
          }
        } else if (err.status === 404) {
          setUnavailable(true)
        } else {
          setError(true)
        }
      } else {
        setError(true)
      }
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void load()
  }, [load])

  const loadTab = useCallback(async () => {
    setTabError(false)
    setTabReady(false)
    try {
      if (tab === 'catalog') {
        const data = await getLearningCatalog(access)
        setCatalog(data.items || [])
      } else if (tab === 'assignments') {
        const data = await getLearningAssignments(access)
        setAssignments(data.assignments || [])
      } else if (tab === 'sessions') {
        const data = await getLearningSessions(access)
        setSessions(data.sessions || [])
      } else if (tab === 'certifications') {
        const data = await getLearningCertificates(access)
        setCerts(data.certificates || [])
      } else if (tab === 'requests') {
        const data = await getLearningRequests(access)
        setRequests(data.requests || [])
      } else if (tab === 'history') {
        const data = await getLearningHistory(access)
        setHistory(data.events || data.completions || [])
      }
      setTabReady(true)
    } catch (err) {
      setTabError(true)
      setTabReady(false)
      onNotice(t.loadError, 'error')
      if (err instanceof DashboardApiError && err.status === 403) {
        setForbidden(true)
      }
    }
  }, [access, onNotice, t.loadError, tab])

  useEffect(() => {
    if (tab !== 'overview') void loadTab()
  }, [loadTab, tab])

  const counts = payload?.counts
  const state = resolveListDataState({
    forbidden,
    unavailable,
    loading,
    error,
    itemCount: counts ? 1 : 0,
  })

  function tabEmpty(label: string, count: number) {
    if (tabError) {
      return (
        <ResourceState
          kind="error"
          locale={isAr ? 'ar' : 'en'}
          title={t.loadError}
          onRetry={() => void loadTab()}
          testId="learning-tab-state"
        />
      )
    }
    if (tabReady && count === 0) return <p className="text-sm text-muted-foreground">{label}</p>
    return null
  }

  const tabs = useMemo(() => {
    const all: Array<{ id: Tab; label: string }> = [
      { id: 'overview', label: t.overview },
      { id: 'catalog', label: t.catalog },
      { id: 'assignments', label: t.assignments },
      { id: 'sessions', label: t.sessions },
      { id: 'certifications', label: t.certifications },
      { id: 'requests', label: t.requests },
      { id: 'history', label: t.history },
    ]
    return managerOnly ? all.filter((item) => item.id !== 'catalog') : all
  }, [managerOnly, t])

  async function author(path: string, body: Record<string, unknown>) {
    try {
      await postLearningJson(access, path, body)
      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
      await load()
      await loadTab()
    } catch (err) {
      onNotice(err instanceof Error ? err.message : 'Error', 'error')
    }
  }

  return (
    <div className="space-y-6" dir={isAr ? 'rtl' : 'ltr'}>
      <ConfigureInSetupBanner anchor="classic-wave6-learning" />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t.title}</h1>
          <p className="text-sm text-muted-foreground">{t.subtitle}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t.boundaries}</p>
        </div>
        <Button type="button" variant="outline" onClick={() => void load()}>
          <RefreshCw className="h-4 w-4" />
          {t.refresh}
        </Button>
      </div>

      {state !== 'ready' ? (
        <ResourceState
          kind={state}
          locale={isAr ? 'ar' : 'en'}
          title={
            state === 'forbidden'
              ? t.forbidden
              : state === 'unavailable'
                ? t.unavailable
                : state === 'empty'
                  ? t.emptyAssignments
                  : state === 'error'
                    ? isAr
                      ? 'تعذر تحميل التعلم'
                      : 'Could not load Learning'
                    : undefined
          }
          detail={state === 'empty' ? t.emptyHint : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="learning-workspace-state"
        />
      ) : (
        <>
        <div className="flex flex-wrap gap-2">
          {tabs.map((item) => (
            <Button key={item.id} type="button" variant={tab === item.id ? 'default' : 'outline'} onClick={() => setTab(item.id)}>
              {item.label}
            </Button>
          ))}
        </div>

        {tab === 'overview' ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              [t.active, counts?.active_assignments],
              [t.overdue, counts?.overdue_mandatory],
              [t.upcoming, counts?.upcoming_sessions],
              [t.expiring, counts?.expiring_certificates],
              [t.pending, counts?.pending_requests],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-lg border border-border/70 p-3">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="text-2xl font-semibold">{value ?? '—'}</div>
              </div>
            ))}
            <p className="sm:col-span-2 lg:col-span-5 text-xs text-muted-foreground">{t.overdueNotFail}</p>
          </div>
        ) : null}

        {tab === 'catalog' ? (
          <section className="space-y-3">
            {canManage ? (
              <div className="grid gap-2 sm:grid-cols-4">
                <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.code} />
                <Input value={titleEn} onChange={(e) => setTitleEn(e.target.value)} placeholder={t.titleEn} />
                <Input value={titleAr} onChange={(e) => setTitleAr(e.target.value)} placeholder={t.titleAr} />
                <Button
                  type="button"
                  onClick={() =>
                    void author('/dashboard/learning/catalog', {
                      code,
                      item_type: 'self_paced',
                      title_en: titleEn,
                      title_ar: titleAr,
                      status: 'published',
                      reason: reason || 'catalog',
                    })
                  }
                >
                  {t.createItem}
                </Button>
              </div>
            ) : null}
            {tabEmpty(t.emptyCatalog, catalog.length)}
            <ul className="space-y-2">
              {catalog.map((item) => (
                <li key={String(item.item_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(item.title_en || item.code)} · {String(item.item_type)} · {String(item.status)}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'assignments' ? (
          <section className="space-y-3">
            {canAssign ? (
              <div className="grid gap-2 sm:grid-cols-4">
                <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
                <Input value={itemId} onChange={(e) => setItemId(e.target.value)} placeholder="item_id" />
                <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.reason} />
                <Button
                  type="button"
                  onClick={() =>
                    void author('/dashboard/learning/assignments', {
                      employee_key: empKey,
                      item_id: itemId,
                      source: managerOnly ? 'manager_assigned' : 'hr_assigned',
                      reason: reason || 'assign',
                    })
                  }
                >
                  {t.assign}
                </Button>
              </div>
            ) : null}
            {tabEmpty(t.emptyAssignments, assignments.length)}
            <ul className="space-y-2">
              {assignments.map((row) => (
                <li key={String(row.assignment_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.employee_key)} · {String(row.title_en || row.item_id)} · {String(row.status)} ·{' '}
                  {row.required ? (isAr ? 'إلزامي' : 'mandatory') : isAr ? 'اختياري' : 'optional'}
                  {row.enrolled ? ` · ${isAr ? 'مسجّل' : 'enrolled'}` : ''}
                  {row.attended ? ` · ${isAr ? 'حضر' : 'attended'}` : ''}
                  {row.completed ? ` · ${isAr ? 'مكتمل' : 'completed'}` : ''}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'sessions' ? (
          <section className="space-y-3">
            {canManage ? (
              <div className="grid gap-2 sm:grid-cols-3">
                <Input value={itemId} onChange={(e) => setItemId(e.target.value)} placeholder="item_id" />
                <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
                <Button type="button" onClick={() => void author('/dashboard/learning/sessions', { item_id: itemId, capacity: 20 })}>
                  {t.session}
                </Button>
              </div>
            ) : null}
            {tabEmpty(t.emptySessions, sessions.length)}
            <ul className="space-y-2">
              {sessions.map((row) => (
                <li key={String(row.offering_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.title_en || row.item_id)} · {isAr ? 'السعة' : 'capacity'} {String(row.capacity ?? '—')} ·{' '}
                  {isAr ? 'مسجّلون' : 'enrolled'} {String(row.enrolled_count ?? 0)}
                  {canAssign ? (
                    <Button
                      type="button"
                      variant="ghost"
                      className="ms-2 h-7 px-2"
                      onClick={() =>
                        void author(`/dashboard/learning/sessions/${row.offering_id}/enroll`, {
                          employee_key: empKey,
                          reason: 'enroll',
                        })
                      }
                    >
                      {t.enroll}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'certifications' ? (
          <section className="space-y-3">
            {canManage ? (
              <div className="grid gap-2 sm:grid-cols-4">
                <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
                <Input value={titleEn} onChange={(e) => setTitleEn(e.target.value)} placeholder={t.titleEn} />
                <Input value={titleAr} onChange={(e) => setTitleAr(e.target.value)} placeholder={t.titleAr} />
                <Button
                  type="button"
                  onClick={() =>
                    void author('/dashboard/learning/certificates', {
                      employee_key: empKey,
                      cert_type: 'internal',
                      title_en: titleEn,
                      title_ar: titleAr,
                      issued_on: new Date().toISOString().slice(0, 10),
                      evidence_ref: evidence,
                    })
                  }
                >
                  {t.certify}
                </Button>
              </div>
            ) : null}
            {tabEmpty(t.emptyCerts, certs.length)}
            <ul className="space-y-2">
              {certs.map((row) => (
                <li key={String(row.certification_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.title_en)} · {String(row.employee_key)} · {String((row.derived as { status?: string } | undefined)?.status || row.status)}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'requests' ? (
          <section className="space-y-3">
            {tabEmpty(t.emptyRequests, requests.length)}
            <ul className="space-y-2">
              {requests.map((row) => (
                <li key={String(row.request_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.employee_key)} · {String(row.title_en || row.item_id)} · {String(row.status)}
                  {canApprove && row.status === 'requested' ? (
                    <span className="ms-2 inline-flex gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        className="h-7 px-2"
                        onClick={() =>
                          void author(`/dashboard/learning/requests/${row.request_id}/decide`, {
                            approve: true,
                            reason: reason || 'approve',
                          })
                        }
                      >
                        {t.approve}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        className="h-7 px-2"
                        onClick={() =>
                          void author(`/dashboard/learning/requests/${row.request_id}/decide`, {
                            approve: false,
                            reason: reason || 'rejected',
                          })
                        }
                      >
                        {t.reject}
                      </Button>
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
            {canApprove ? (
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.reason} />
            ) : null}
          </section>
        ) : null}

        {tab === 'history' ? (
          <section className="space-y-3">
            {tabEmpty(t.emptyHistory, history.length)}
            <ul className="space-y-2">
              {history.map((row, index) => (
                <li key={String(row.event_id || row.completion_id || index)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(row.action || row.evidence_source || row.title_en || 'event')}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {canManage ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <Input value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder={t.evidence} />
            <p className="text-xs text-muted-foreground">{t.config}</p>
          </div>
        ) : null}
        </>
      )}
    </div>
  )
}
