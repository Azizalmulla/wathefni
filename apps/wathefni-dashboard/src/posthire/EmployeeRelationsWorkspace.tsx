/**
 * R5G Employee Relations workspace — thin client over frozen Wave 6 C4.
 * Sealed need-to-know. Intake ≠ finding. Investigation ≠ outcome. Outcome ≠ employment mutation.
 */
import { RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'
import { useUrlBackedParam, useUrlBackedTab, URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getEmployeeRelationsCase,
  getEmployeeRelationsCases,
  getEmployeeRelationsHistory,
  getEmployeeRelationsMyWork,
  getEmployeeRelationsWorkspace,
  postEmployeeRelationsJson,
  type EmployeeRelationsWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type EmployeeRelationsWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'cases' | 'detail' | 'my-work' | 'history'

const WORKSPACE_TABS = URL_BACKED_WORKSPACE_TABS['employee-relations'] as readonly Tab[]

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'علاقات الموظفين',
        subtitle: 'مساحة سرية حسب الحاجة للمعرفة — ليست قائمة مهام موارد بشرية عامة.',
        overview: 'نظرة عامة',
        cases: 'القضايا',
        detail: 'تفاصيل القضية',
        myWork: 'عملي',
        history: 'السجل والتدقيق',
        refresh: 'تحديث',
        mine: 'قضايا تتطلب إجرائي',
        assigned: 'قضايا مفتوحة مسندة',
        overdue: 'تحقيق متأخر',
        emptyCases: 'لا توجد قضايا مسندة إليك',
        emptyHint: 'النطاق الفارغ يعني صفراً — وليس كل قضايا الشركة.',
        emptyHistory: 'لا يوجد سجل ظاهر لهذه القضية',
        loadError: 'تعذر تحميل هذا القسم. هذه ليست نتيجة فارغة.',
        forbidden: 'ليست لديك صلاحية علاقات الموظفين.',
        unavailable: 'علاقات الموظفين غير متاحة لهذه الشركة.',
        boundaries:
          'التقديم ليس ثبوتاً. التحقيق ليس نتيجة. النتيجة ليست تغييراً في التوظيف. المدير ليس دوراً في علاقات الموظفين.',
        intake: 'استلام (ليس نتيجة)',
        triage: 'فرز',
        assign: 'إسناد محقق',
        note: 'ملاحظة تحقيق',
        evidence: 'مرجع دليل',
        finding: 'استنتاج',
        outcome: 'نتيجة',
        close: 'إغلاق',
        handoff: 'تسليم تغيير التوظيف (ليس تنفيذاً)',
        caseId: 'معرّف القضية',
        subject: 'مفتاح الموظف المعني',
        caseType: 'معرّف نوع القضية',
        investigator: 'مفتاح المحقق',
        reason: 'السبب',
        noCompanyWide: 'لا يوجد تجميع على مستوى الشركة لمن لا يملك صلاحية القضية.',
      }
    : {
        title: 'Employee Relations',
        subtitle: 'A sealed need-to-know workspace — not a generic HR task list.',
        overview: 'Overview',
        cases: 'Cases',
        detail: 'Case detail',
        myWork: 'My work',
        history: 'History / Audit',
        refresh: 'Refresh',
        mine: 'Cases requiring my action',
        assigned: 'Assigned open cases',
        overdue: 'Overdue investigation work',
        emptyCases: 'No cases are assigned to you',
        emptyHint: 'Empty assignment means zero cases — never the company-wide caseload.',
        emptyHistory: 'No visible history for this case',
        loadError: 'This section could not be loaded. This is not an empty result.',
        forbidden: 'You do not have Employee Relations authority.',
        unavailable: 'Employee Relations is not available for this company.',
        boundaries:
          'Submission is not proof. Investigation is not a finding. Outcome is not an employment mutation. Manager is not an ER role.',
        intake: 'Intake (not a finding)',
        triage: 'Triage',
        assign: 'Assign investigator',
        note: 'Investigation note',
        evidence: 'Evidence reference',
        finding: 'Finding',
        outcome: 'Outcome',
        close: 'Close',
        handoff: 'Employment-change handoff (not execution)',
        caseId: 'Case id',
        subject: 'Subject employee key',
        caseType: 'Case type id',
        investigator: 'Investigator key',
        reason: 'Reason',
        noCompanyWide: 'No company-wide aggregate is shown without case-level authority.',
      }
}

export function EmployeeRelationsWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: EmployeeRelationsWorkspaceProps) {
  const isAr = useEmployees360Locale() === 'ar'
  const t = copy(isAr)
  const [tab, setTab] = useUrlBackedTab<Tab>('employee-relations', WORKSPACE_TABS, 'overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<EmployeeRelationsWorkspacePayload | null>(null)
  const payloadRef = useRef(payload)
  payloadRef.current = payload
  const [cases, setCases] = useState<Array<Record<string, unknown>>>([])
  const [myWork, setMyWork] = useState<Array<Record<string, unknown>>>([])
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([])
  const [tabError, setTabError] = useState(false)
  const [tabReady, setTabReady] = useState(false)
  const [caseId, setCaseId] = useUrlBackedParam('employee-relations', 'q', '', 'replace')
  const [caseTypeId, setCaseTypeId] = useState('')
  const [subjectKey, setSubjectKey] = useState('')
  const [investigatorKey, setInvestigatorKey] = useState('')
  const [reason, setReason] = useState('')

  const canManage = hasActorPermission(permissions, 'er.manage')
  const canInvestigate = hasActorPermission(permissions, 'er.investigate') || canManage
  const canDecide = hasActorPermission(permissions, 'er.decide') || canManage
  const managerOnly = String(role || '').toLowerCase() === 'manager'
  const hasErAuthority =
    hasActorPermission(permissions, 'er.read') || canManage || canInvestigate || canDecide

  const load = useCallback(async () => {
    if (!payloadRef.current) setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      const data = await getEmployeeRelationsWorkspace(access)
      setPayload(data)
      if (data.resource_state === 'unavailable' || data.enabled === false) {
        setUnavailable(true)
      }
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      if (err instanceof DashboardApiError) {
        if (err.status === 403) setForbidden(true)
        else if (err.status === 404) setUnavailable(true)
        else setError(true)
      } else {
        setError(true)
      }
      if (!payloadRef.current) setPayload(null)
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
      if (tab === 'cases') {
        const data = await getEmployeeRelationsCases(access)
        setCases(data.cases || [])
      } else if (tab === 'my-work') {
        const data = await getEmployeeRelationsMyWork(access)
        setMyWork(data.cases || [])
      } else if (tab === 'detail' && caseId) {
        const data = await getEmployeeRelationsCase(access, caseId)
        setDetail(data)
      } else if (tab === 'history' && caseId) {
        const data = await getEmployeeRelationsHistory(access, caseId)
        setHistory(data.events || [])
      }
      setTabReady(true)
    } catch (err) {
      setTabError(true)
      setTabReady(false)
      if (err instanceof DashboardApiError && err.status === 403) {
        onNotice(t.forbidden, 'error')
      } else {
        onNotice(t.loadError, 'error')
      }
    }
  }, [access, caseId, onNotice, t.forbidden, t.loadError, tab])

  useEffect(() => {
    if (tab !== 'overview') void loadTab()
  }, [loadTab, tab])

  const counts = payload?.counts
  const state = resolveListDataState({
    forbidden: forbidden || managerOnly || !hasErAuthority,
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
          testId="employee-relations-tab-state"
        />
      )
    }
    if (tabReady && count === 0) return <p className="text-sm text-muted-foreground">{label}</p>
    return null
  }

  const tabs = useMemo(() => {
    const all: Array<{ id: Tab; label: string }> = [
      { id: 'overview', label: t.overview },
      { id: 'cases', label: t.cases },
      { id: 'detail', label: t.detail },
      { id: 'my-work', label: t.myWork },
      { id: 'history', label: t.history },
    ]
    return all
  }, [t])

  async function author(path: string, body: Record<string, unknown>) {
    try {
      await postEmployeeRelationsJson(access, path, body)
      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
      await load()
      await loadTab()
    } catch (err) {
      onNotice(err instanceof Error ? err.message : 'Error', 'error')
    }
  }

  return (
    <div className="space-y-6" dir={isAr ? 'rtl' : 'ltr'} data-testid="employee-relations-workspace">
      <ConfigureInSetupBanner anchor="classic-wave6-employee-relations" />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-semantic-subtle">{t.boundaries}</p>
        <Button type="button" variant="ghost" size="sm" onClick={() => void load()} disabled={loading} aria-label={t.refresh}>
          <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
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
                  ? t.emptyCases
                  : state === 'error'
                    ? isAr
                      ? 'تعذر تحميل علاقات الموظفين'
                      : 'Could not load Employee Relations'
                    : undefined
          }
          detail={state === 'empty' ? t.emptyHint : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="employee-relations-workspace-state"
        />
      ) : (
        <>
        <HrSurfaceTabs value={tab} onChange={setTab} ariaLabel={t.title} items={tabs} />

        {tab === 'overview' ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">{t.noCompanyWide}</p>
            <div className="grid gap-3 sm:grid-cols-3">
              {[
                [t.mine, counts?.requiring_my_action],
                [t.assigned, counts?.assigned_open],
                [t.overdue, counts?.overdue_investigation],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg border border-border/70 p-3">
                  <div className="text-xs text-muted-foreground">{label}</div>
                  <div className="text-2xl font-semibold">{value ?? '—'}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {tab === 'cases' ? (
          <section className="space-y-3">
            {canManage ? (
              <div className="grid gap-2 sm:grid-cols-4">
                <Input value={caseTypeId} onChange={(e) => setCaseTypeId(e.target.value)} placeholder={t.caseType} />
                <Input value={subjectKey} onChange={(e) => setSubjectKey(e.target.value)} placeholder={t.subject} />
                <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.reason} />
                <Button
                  type="button"
                  onClick={() =>
                    void author('/dashboard/employee-relations/cases', {
                      case_type_id: caseTypeId,
                      subject_employee_key: subjectKey,
                      intake_source: 'hr_created',
                      summary_en: reason,
                    })
                  }
                >
                  {t.intake}
                </Button>
              </div>
            ) : null}
            {tabEmpty(t.emptyCases, cases.length)}
            {tabReady && cases.length === 0 ? <p className="text-xs text-muted-foreground">{t.emptyHint}</p> : null}
            <ul className="space-y-2">
              {cases.map((item) => (
                <li key={String(item.case_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(item.case_type_code || item.case_id)} · {String(item.status_label_en || item.status)}
                  <Button
                    type="button"
                    variant="ghost"
                    className="ms-2 h-7 px-2"
                    onClick={() => {
                      setCaseId(String(item.case_id || ''), 'push')
                      setTab('detail')
                    }}
                  >
                    {t.detail}
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'detail' ? (
          <section className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-3">
              <Input value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder={t.caseId} />
              <Input value={investigatorKey} onChange={(e) => setInvestigatorKey(e.target.value)} placeholder={t.investigator} />
              <Button type="button" variant="outline" onClick={() => void loadTab()}>
                {t.refresh}
              </Button>
            </div>
            {canManage ? (
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={() => void author(`/dashboard/employee-relations/cases/${caseId}/triage`, { reason: reason || 'triage' })}>
                  {t.triage}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author(`/dashboard/employee-relations/cases/${caseId}/assign`, {
                      investigator_key: investigatorKey,
                    })
                  }
                >
                  {t.assign}
                </Button>
                <Button type="button" variant="outline" onClick={() => void author(`/dashboard/employee-relations/cases/${caseId}/closure`, { reason: reason || 'closure' })}>
                  {t.close}
                </Button>
              </div>
            ) : null}
            {canInvestigate ? (
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author(`/dashboard/employee-relations/cases/${caseId}/notes`, {
                      body_en: reason || 'note',
                      body_ar: '',
                    })
                  }
                >
                  {t.note}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author(`/dashboard/employee-relations/cases/${caseId}/evidence`, {
                      shared_document_ref: `doc://${caseId}`,
                      label_en: 'Evidence',
                      label_ar: 'دليل',
                      sensitive: true,
                    })
                  }
                >
                  {t.evidence}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author(`/dashboard/employee-relations/cases/${caseId}/findings`, {
                      findings_en: reason || 'finding',
                      findings_ar: '',
                    })
                  }
                >
                  {t.finding}
                </Button>
              </div>
            ) : null}
            {canDecide ? (
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author(`/dashboard/employee-relations/cases/${caseId}/outcomes`, {
                      outcome_code: 'no_action',
                      summary_en: reason || 'outcome',
                    })
                  }
                >
                  {t.outcome}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    void author(`/dashboard/employee-relations/cases/${caseId}/handoffs`, {
                      outcome_id: String((detail?.outcomes as Array<Record<string, unknown>> | undefined)?.[0]?.outcome_id || ''),
                    })
                  }
                >
                  {t.handoff}
                </Button>
              </div>
            ) : null}
            {tabError ? (
              <ResourceState
                kind="error"
                locale={isAr ? 'ar' : 'en'}
                title={t.loadError}
                onRetry={() => void loadTab()}
                testId="employee-relations-tab-state"
              />
            ) : null}
            {detail ? (
              <div className="space-y-2 rounded-lg border border-border/70 p-3 text-sm">
                <div>{t.intake}: {String((detail.intake as Record<string, unknown> | undefined)?.source || '')}</div>
                <div>{String((detail.case as Record<string, unknown> | undefined)?.status || '')}</div>
                <div>{isAr ? 'الأدلة' : 'Evidence'}: {Array.isArray(detail.evidence) ? detail.evidence.length : 0}</div>
                <div>{isAr ? 'الاستنتاجات' : 'Findings'}: {Array.isArray(detail.findings) ? detail.findings.length : 0}</div>
              </div>
            ) : null}
          </section>
        ) : null}

        {tab === 'my-work' ? (
          <section className="space-y-3">
            {tabEmpty(t.emptyCases, myWork.length)}
            <ul className="space-y-2">
              {myWork.map((item) => (
                <li key={String(item.case_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(item.case_type_code || item.case_id)} · {String(item.status_label_en || item.status)}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {tab === 'history' ? (
          <section className="space-y-3">
            <Input value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder={t.caseId} />
            {tabEmpty(t.emptyHistory, history.length)}
            <ul className="space-y-2">
              {history.map((item) => (
                <li key={String(item.audit_id)} className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  {String(item.action)} · {String(item.created_at || '')}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        </>
      )}
    </div>
  )
}
