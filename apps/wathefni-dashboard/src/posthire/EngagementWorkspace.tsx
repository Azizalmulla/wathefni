/**
 * R5H Engagement workspace — thin client over frozen Wave 6 C5.
 * Anonymous ≠ identified. Below threshold → suppress, never guess. Result ≠ action plan ≠ ER.
 */
import { Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getEngagementActionPlans,
  getEngagementCampaigns,
  getEngagementHistory,
  getEngagementManager,
  getEngagementResults,
  getEngagementWorkspace,
  postEngagementJson,
  type EngagementWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type EngagementWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'surveys' | 'results' | 'actions' | 'history'

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'المشاركة والارتباط',
        subtitle: 'استبيانات مع إخفاء هوية. النتيجة المحجوبة ليست صفراً. النتيجة ليست خطة عمل وليست قضية علاقات موظفين.',
        overview: 'نظرة عامة',
        surveys: 'الاستبيانات',
        results: 'النتائج',
        actions: 'خطط العمل',
        history: 'السجل',
        refresh: 'تحديث',
        live: 'استبيانات مباشرة',
        closed: 'استبيانات مغلقة',
        drafts: 'مسودات',
        plans: 'خطط عمل مفتوحة',
        emptySurveys: 'لا توجد استبيانات بعد',
        emptyResults: 'لا توجد نتائج بعد — أو أنها محجوبة دون الحد.',
        emptyActions: 'لا توجد خطط عمل',
        emptyHistory: 'لا يوجد سجل بعد',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        loadError: 'تعذر تحميل هذا القسم. هذه ليست نتيجة فارغة.',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'المشاركة والارتباط غير متاحة لهذه الشركة.',
        suppressed: 'محجوب — لم يُبلَغ حد إخفاء الهوية. هذا ليس صفراً.',
        boundaries: 'الاستجابة المجهولة ليست استجابة معرّفة. المشاركة ليست ربطاً بالإجابات. النتيجة ليست خطة عمل.',
        createSurvey: 'استبيان',
        launch: 'إطلاق (تجميد الجمهور)',
        close: 'إغلاق',
        actionPlan: 'خطة عمل (ليست قضية)',
        code: 'الرمز',
        titleEn: 'العنوان (إنجليزي)',
        titleAr: 'العنوان (عربي)',
        audience: 'مفاتيح الجمهور (مفصولة بفاصلة)',
        notGenericBi: 'ليست تحليلات مشاعر وهمية.',
      }
    : {
        title: 'Engagement',
        subtitle: 'Surveys with anonymity. A suppressed result is not zero. A result is not an action plan and not an ER case.',
        overview: 'Overview',
        surveys: 'Surveys',
        results: 'Results',
        actions: 'Action plans',
        history: 'History',
        refresh: 'Refresh',
        live: 'Live surveys',
        closed: 'Closed surveys',
        drafts: 'Drafts',
        plans: 'Open action plans',
        emptySurveys: 'No surveys yet',
        emptyResults: 'No results yet — or they are suppressed below the threshold.',
        emptyActions: 'No action plans',
        emptyHistory: 'No engagement history yet',
        emptyHint: 'This is a true empty result — not a load failure.',
        loadError: 'This section could not be loaded. This is not an empty result.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Engagement is not available for this company.',
        suppressed: 'Suppressed — the anonymity threshold was not met. This is not zero.',
        boundaries: 'Anonymous is not identified. Participation is not an answer map. A survey result is not an action plan.',
        createSurvey: 'Survey',
        launch: 'Launch (freeze audience)',
        close: 'Close',
        actionPlan: 'Action plan (not an ER case)',
        code: 'Code',
        titleEn: 'Title (EN)',
        titleAr: 'Title (AR)',
        audience: 'Audience keys (comma-separated)',
        notGenericBi: 'Not fake sentiment analytics.',
      }
}

export function EngagementWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: EngagementWorkspaceProps) {
  const isAr = useEmployees360Locale() === 'ar'
  const t = copy(isAr)
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<EngagementWorkspacePayload | null>(null)
  const [campaigns, setCampaigns] = useState<Array<Record<string, unknown>>>([])
  const [results, setResults] = useState<Record<string, unknown> | null>(null)
  const [plans, setPlans] = useState<Array<Record<string, unknown>>>([])
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([])
  const [tabError, setTabError] = useState(false)
  const [tabReady, setTabReady] = useState(false)
  const [code, setCode] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [titleAr, setTitleAr] = useState('')
  const [audience, setAudience] = useState('')
  const [selectedCampaign, setSelectedCampaign] = useState('')

  const canManage = hasActorPermission(permissions, 'engagement.manage')
  const canLaunch = hasActorPermission(permissions, 'engagement.launch') || canManage
  const canActions = hasActorPermission(permissions, 'engagement.actions') || canManage
  const managerOnly = String(role || '').toLowerCase() === 'manager'

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      if (managerOnly) {
        const data = await getEngagementManager(access)
        setPayload({
          ok: data.ok,
          enabled: data.enabled,
          resource_state: data.resource_state,
          counts: null,
        })
        setCampaigns(data.campaigns || [])
        if (data.resource_state === 'unavailable' || data.enabled === false) setUnavailable(true)
      } else {
        const data = await getEngagementWorkspace(access)
        setPayload(data)
        if (data.resource_state === 'unavailable' || data.enabled === false) setUnavailable(true)
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
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [access, managerOnly, onAccessIssue])

  useEffect(() => {
    void load()
  }, [load])

  const loadTab = useCallback(async () => {
    if (forbidden || unavailable || managerOnly) return
    setTabError(false)
    setTabReady(false)
    try {
      if (tab === 'surveys' || tab === 'overview') {
        const data = await getEngagementCampaigns(access)
        setCampaigns(data.campaigns || [])
      }
      if (tab === 'results' && selectedCampaign) {
        const data = await getEngagementResults(access, selectedCampaign)
        setResults(data)
      }
      if (tab === 'actions') {
        const data = await getEngagementActionPlans(access)
        setPlans(data.action_plans || [])
      }
      if (tab === 'history') {
        const data = await getEngagementHistory(access)
        setHistory(data.history || [])
      }
      setTabReady(true)
    } catch (err) {
      if (err instanceof DashboardApiError && err.status === 403) setForbidden(true)
      else setTabError(true)
    }
  }, [access, forbidden, managerOnly, selectedCampaign, tab, unavailable])

  useEffect(() => {
    void loadTab()
  }, [loadTab])

  const counts = payload?.counts
  const itemCount = useMemo(() => {
    if (tab === 'surveys') return campaigns.length
    if (tab === 'results') return results ? 1 : 0
    if (tab === 'actions') return plans.length
    if (tab === 'history') return history.length
    return counts ? 1 : 0
  }, [campaigns.length, counts, history.length, plans.length, results, tab])

  const state = resolveListDataState({
    forbidden,
    unavailable,
    loading,
    error,
    itemCount: loading ? 0 : itemCount,
  })

  async function author(path: string, body: Record<string, unknown>) {
    try {
      await postEngagementJson(access, path, body)
      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
      await load()
      await loadTab()
    } catch (err) {
      onNotice(err instanceof Error ? err.message : isAr ? 'فشل الحفظ' : 'Save failed', 'error')
    }
  }

  const tabs: Tab[] = managerOnly ? ['overview', 'results'] : ['overview', 'surveys', 'results', 'actions', 'history']

  return (
    <div className="space-y-6" dir={isAr ? 'rtl' : 'ltr'} data-testid="engagement-workspace">
      <ConfigureInSetupBanner anchor="classic-wave6-engagement" />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t.title}</h1>
          <p className="text-sm text-muted-foreground">{t.subtitle}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t.boundaries}</p>
          <p className="text-xs text-muted-foreground">{t.notGenericBi}</p>
        </div>
        <Button type="button" variant="outline" onClick={() => void load()}>
          <RefreshCw className="me-2 h-4 w-4" />
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
                  ? t.emptySurveys
                  : state === 'error'
                    ? t.loadError
                    : undefined
          }
          detail={state === 'empty' ? t.emptyHint : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="engagement-workspace-state"
        />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {tabs.map((id) => (
              <Button key={id} type="button" variant={tab === id ? 'default' : 'outline'} onClick={() => setTab(id)}>
                {t[id]}
              </Button>
            ))}
          </div>
          {tab === 'overview' && counts && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                [t.live, counts.live_surveys],
                [t.closed, counts.closed_surveys],
                [t.drafts, counts.draft_surveys],
                [t.plans, counts.open_action_plans],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">{label}</div>
                  <div className="text-2xl font-semibold">{value ?? '—'}</div>
                </div>
              ))}
            </div>
          )}
          {managerOnly && tab === 'overview' && (
            <div className="space-y-2">
              {campaigns.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyResults}</p> : null}
              {campaigns.map((row) => {
                const res = (row.results || {}) as Record<string, unknown>
                return (
                  <div key={String(row.campaign_id)} className="rounded-lg border p-3 text-sm">
                    <div className="font-medium">{isAr ? String(row.title_ar || row.title_en) : String(row.title_en || row.title_ar)}</div>
                    <div className="text-muted-foreground">
                      {res.suppressed ? t.suppressed : `${isAr ? 'النتيجة' : 'Result'} · n=${String(res.n ?? '—')}`}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
          {tab === 'surveys' && !managerOnly && (
            <div className="space-y-4">
              {canManage && (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.code} />
                  <Input value={titleEn} onChange={(e) => setTitleEn(e.target.value)} placeholder={t.titleEn} />
                  <Input value={titleAr} onChange={(e) => setTitleAr(e.target.value)} placeholder={t.titleAr} />
                  <Input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder={t.audience} />
                  <Button
                    type="button"
                    onClick={() =>
                      void author('/dashboard/engagement/surveys', {
                        code,
                        title_en: titleEn,
                        title_ar: titleAr,
                      })
                    }
                  >
                    {t.createSurvey}
                  </Button>
                </div>
              )}
              {tabError ? (
                <ResourceState
                  kind="error"
                  locale={isAr ? 'ar' : 'en'}
                  title={t.loadError}
                  onRetry={() => void loadTab()}
                  testId="engagement-tab-state"
                />
              ) : null}
              {tabReady && campaigns.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptySurveys}</p> : null}
              {campaigns.map((row) => (
                <div key={String(row.campaign_id)} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
                  <div>
                    <div className="font-medium">{isAr ? String(row.title_ar || row.title_en) : String(row.title_en || row.title_ar)}</div>
                    <div className="text-xs text-muted-foreground">
                      {String(isAr ? row.status_label_ar : row.status_label_en)} · {String(isAr ? row.privacy_mode_label_ar : row.privacy_mode_label_en)}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" onClick={() => { setSelectedCampaign(String(row.campaign_id)); setTab('results') }}>
                      {t.results}
                    </Button>
                    {canLaunch && row.status === 'draft' ? (
                      <Button type="button" onClick={() => void author(`/dashboard/engagement/campaigns/${row.campaign_id}/launch`, {})}>
                        {t.launch}
                      </Button>
                    ) : null}
                    {canLaunch && row.status === 'launched' ? (
                      <Button type="button" variant="outline" onClick={() => void author(`/dashboard/engagement/campaigns/${row.campaign_id}/close`, {})}>
                        {t.close}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === 'results' && (
            <div className="space-y-3">
              {results?.suppressed ? <p className="rounded-lg border p-3 text-sm">{t.suppressed}</p> : null}
              {!results && tabReady ? <p className="text-sm text-muted-foreground">{t.emptyResults}</p> : null}
              {results && !results.suppressed ? (
                <pre className="overflow-auto rounded-lg border p-3 text-xs">{JSON.stringify(results.scores || results, null, 2)}</pre>
              ) : null}
              {canActions && selectedCampaign ? (
                <Button
                  type="button"
                  onClick={() =>
                    void author('/dashboard/engagement/action-plans', {
                      campaign_id: selectedCampaign,
                      title_en: 'Follow-up',
                      title_ar: 'متابعة',
                      source_result_ref: `campaign:${selectedCampaign}`,
                      owner_key: 'HR',
                      actions: [{ title_en: 'Follow up', title_ar: 'متابعة' }],
                    })
                  }
                >
                  {t.actionPlan}
                </Button>
              ) : null}
            </div>
          )}
          {tab === 'actions' && !managerOnly && (
            <div className="space-y-2">
              {tabReady && plans.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyActions}</p> : null}
              {plans.map((row) => (
                <div key={String(row.action_plan_id)} className="rounded-lg border p-3 text-sm">
                  <div className="font-medium">{isAr ? String(row.title_ar || row.title_en) : String(row.title_en || row.title_ar)}</div>
                  <div className="text-muted-foreground">{String(row.status)} · {t.actionPlan}</div>
                </div>
              ))}
            </div>
          )}
          {tab === 'history' && !managerOnly && (
            <div className="space-y-2">
              {tabReady && history.length === 0 ? <p className="text-sm text-muted-foreground">{t.emptyHistory}</p> : null}
              {history.map((row) => (
                <div key={String(row.audit_id)} className="rounded-lg border p-3 text-sm">
                  {String(row.action)} · {String(row.entity_type)} · {String(row.created_at || '')}
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
    </div>
  )
}
