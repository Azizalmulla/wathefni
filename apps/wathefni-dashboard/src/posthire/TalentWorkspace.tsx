/**
 * R5C Talent workspace — thin client over frozen Wave 4 C5–C6.
 * Distinct from Performance and from recruiting talent_pool.
 * No master talent score. 9-box is a derived visualization only.
 */
import { Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'
import { useUrlBackedTab, URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getTalentEvidenceIndex,
  getTalentMap,
  getTalentModels,
  getTalentNineBox,
  getTalentProfile,
  getTalentProfiles,
  getTalentReviews,
  getTalentRoleFitSets,
  getTalentSlate,
  getTalentSuccession,
  getTalentWorkspace,
  postTalentJson,
  type TalentWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type TalentWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'people' | 'reviews' | 'succession' | 'mobility' | 'ninebox' | 'models' | 'rolefit' | 'map'

const WORKSPACE_TABS = URL_BACKED_WORKSPACE_TABS.talent as readonly Tab[]

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'المواهب',
        subtitle: 'الملفات والإشارات والإمكانات والتعاقب — منفصلة عن الأداء وعن مجمع المرشحين.',
        overview: 'نظرة عامة',
        people: 'الأشخاص',
        reviews: 'مراجعات المواهب',
        succession: 'التعاقب',
        mobility: 'التنقل الداخلي',
        ninebox: 'شبكة التسعة (عرض مشتق)',
        models: 'نماذج المشتق',
        map: 'خريطة المواهب',
        lens: 'العدسة',
        unknownStay: 'المجهول يبقى مجهولاً.',
        rolefit: 'ملاءمة الدور',
        fitNotReady: 'الملاءمة ليست جاهزية وليست أهلية ترقية.',
        jaOffFit: 'الهندسة الوظيفية غير متاحة — الملاءمة غير متاحة بصدق.',
        derivedNotHipo: 'الإشارة المشتقة ليست تعيين إمكانات عالية.',
        publishModel: 'نشر النموذج الافتراضي',
        evaluate: 'تشغيل النموذج',
        why: 'لماذا',
        refresh: 'تحديث',
        profiles: 'ملفات المواهب',
        openReviews: 'مراجعات مفتوحة',
        uncovered: 'أدوار بلا خلفاء',
        hipo: 'إمكانات عالية (صريح)',
        emptyPeople: 'لا توجد ملفات مواهب بعد',
        emptyReviews: 'لا توجد مراجعات مواهب بعد',
        emptySuccession: 'لا توجد خطط تعاقب بعد',
        emptyNine: 'العرض غير متاح — المدخلات أو الإعداد ناقصة.',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'المواهب غير متاحة لهذه الشركة.',
        noScore: 'لا توجد درجة مواهب عامة.',
        perfOff: 'الأداء اختياري. التقييم العالي لا يعني إمكانات عالية.',
        recruitingOff: 'التوظيف اختياري. الاهتمام بالتنقل ليس طلباً ولا يُنشئ مرشحاً.',
        config: 'السياسات في الإعداد',
        createProfile: 'ملف جديد',
        addEvidence: 'إضافة دليل',
        potential: 'قرار الإمكانات',
        designateHipo: 'تعيين إمكانات عالية',
        createReview: 'مراجعة جديدة',
        prepare: 'تجهيز وتجميد',
        start: 'بدء',
        lock: 'إقفال',
        criticalRole: 'دور مستهدف',
        nominate: 'ترشيح خلف',
        readiness: 'الجاهزية لهذا الدور',
        employeeKey: 'مفتاح الموظف',
        titleEn: 'العنوان',
        rationale: 'المبرر',
        project: 'عرض مشتق',
        evidenceIndex: 'فهرس الأدلة (مؤشرات — ليست حقيقة ثانية)',
        claimedNotVerified: 'مُدّعى — غير موثّق',
      }
    : {
        title: 'Talent',
        subtitle: 'Profiles, signals, potential, and succession — not Performance, not the recruiting pool.',
        overview: 'Overview',
        people: 'People',
        reviews: 'Talent reviews',
        succession: 'Succession',
        mobility: 'Mobility',
        ninebox: '9-box (derived)',
        models: 'Derived models',
        map: 'Talent map',
        lens: 'Lens',
        unknownStay: 'Unknown stays unknown.',
        rolefit: 'Role fit',
        fitNotReady: 'Fit is not readiness and not promotion eligibility.',
        jaOffFit: 'Job Architecture is off — role fit is honestly unavailable.',
        derivedNotHipo: 'A derived signal is not a HiPo designation.',
        publishModel: 'Publish default model',
        evaluate: 'Run model',
        why: 'WHY',
        refresh: 'Refresh',
        profiles: 'Talent profiles',
        openReviews: 'Open talent reviews',
        uncovered: 'Roles without successors',
        hipo: 'HiPo (explicit)',
        emptyPeople: 'No Talent profiles yet',
        emptyReviews: 'No Talent reviews yet',
        emptySuccession: 'No succession plans yet',
        emptyNine: 'Visualization unavailable — required inputs or config are missing.',
        emptyHint: 'This is a true empty result — not a load failure.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Talent is not available for this company.',
        noScore: 'There is no universal Talent score.',
        perfOff: 'Performance is optional. A high rating is not HiPo.',
        recruitingOff: 'Recruiting is optional. Mobility interest is not an application and creates no candidate.',
        config: 'Policies live in Setup',
        createProfile: 'New profile',
        addEvidence: 'Add evidence',
        potential: 'Potential decision',
        designateHipo: 'Designate HiPo',
        createReview: 'New review',
        prepare: 'Prepare and freeze',
        start: 'Start',
        lock: 'Lock',
        criticalRole: 'Target role',
        nominate: 'Nominate successor',
        readiness: 'Readiness for this role',
        employeeKey: 'Employee key',
        titleEn: 'Title',
        rationale: 'Rationale',
        project: 'Derived view',
        evidenceIndex: 'Evidence index (pointers — not a second truth)',
        claimedNotVerified: 'Claimed — not verified',
      }
}

export function TalentWorkspace({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
}: TalentWorkspaceProps) {
  const { isAr } = useEmployees360Locale()
  const t = copy(isAr)
  const [tab, setTab] = useUrlBackedTab<Tab>('talent', WORKSPACE_TABS, 'overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<TalentWorkspacePayload | null>(null)
  const payloadRef = useRef(payload)
  payloadRef.current = payload
  const [people, setPeople] = useState<Array<Record<string, unknown>>>([])
  const [peopleLoading, setPeopleLoading] = useState(false)
  const [peopleError, setPeopleError] = useState(false)
  const [reviews, setReviews] = useState<Array<Record<string, unknown>>>([])
  const [reviewsLoading, setReviewsLoading] = useState(false)
  const [reviewsError, setReviewsError] = useState(false)
  const [succession, setSuccession] = useState<{
    critical_roles?: Array<Record<string, unknown>>
    plans?: Array<Record<string, unknown>>
    uncovered?: Array<Record<string, unknown>>
  } | null>(null)
  const [successionLoading, setSuccessionLoading] = useState(false)
  const [successionError, setSuccessionError] = useState(false)
  const [nine, setNine] = useState<{ enabled?: boolean; configs?: Array<Record<string, unknown>> } | null>(null)
  const [nineLoading, setNineLoading] = useState(false)
  const [nineError, setNineError] = useState(false)
  const [empKey, setEmpKey] = useState('')
  const [title, setTitle] = useState('')
  const [rationale, setRationale] = useState('')

  const canManage = hasActorPermission(permissions, 'talent.manage')
  const canSensitive = hasActorPermission(permissions, 'talent.sensitive')
  const canReview = hasActorPermission(permissions, 'talent.review')
  const canSuccession = hasActorPermission(permissions, 'talent.succession')
  const managerOnly = String(role || '').toLowerCase() === 'manager'

  const load = useCallback(async () => {
    if (!payloadRef.current) setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      const data = await getTalentWorkspace(access)
      setPayload(data)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      if (err instanceof DashboardApiError) {
        if (err.status === 403) {
          const code = String((err.body as { error?: string } | undefined)?.error || '')
          if (code.includes('permission') || code.includes('forbidden')) setForbidden(true)
          else setUnavailable(true)
        } else if (err.status === 404) {
          setUnavailable(true)
        } else {
          setError(true)
        }
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

  const counts = payload?.counts
  const state = resolveListDataState({
    forbidden,
    unavailable,
    loading,
    error,
    itemCount: counts ? 1 : 0,
  })

  const tabs = useMemo(() => {
    const items: Array<{ id: Tab; label: string }> = [
      { id: 'overview', label: t.overview },
      { id: 'people', label: t.people },
      { id: 'mobility', label: t.mobility },
    ]
    if (canReview) items.splice(2, 0, { id: 'reviews', label: t.reviews })
    if (canSuccession) items.splice(canReview ? 3 : 2, 0, { id: 'succession', label: t.succession })
    if (!managerOnly) items.push({ id: 'models', label: t.models })
    if (!managerOnly) items.push({ id: 'rolefit', label: t.rolefit })
    if (!managerOnly) items.push({ id: 'map', label: t.map })
    if (!managerOnly) items.push({ id: 'ninebox', label: t.ninebox })
    return items
  }, [canReview, canSuccession, managerOnly, t])

  const loadPeople = useCallback(async () => {
    setPeopleLoading(true)
    setPeopleError(false)
    try {
      const data = await getTalentProfiles(access)
      setPeople(data.profiles || [])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      setPeopleError(true)
    } finally {
      setPeopleLoading(false)
    }
  }, [access, onAccessIssue])

  const loadReviews = useCallback(async () => {
    setReviewsLoading(true)
    setReviewsError(false)
    try {
      const data = await getTalentReviews(access)
      setReviews(data.reviews || [])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      setReviewsError(true)
    } finally {
      setReviewsLoading(false)
    }
  }, [access, onAccessIssue])

  const loadSuccession = useCallback(async () => {
    setSuccessionLoading(true)
    setSuccessionError(false)
    try {
      const data = await getTalentSuccession(access)
      setSuccession(data)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      setSuccessionError(true)
    } finally {
      setSuccessionLoading(false)
    }
  }, [access, onAccessIssue])

  const loadNine = useCallback(async () => {
    setNineLoading(true)
    setNineError(false)
    try {
      const data = await getTalentNineBox(access)
      setNine(data)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      setNineError(true)
    } finally {
      setNineLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    if (tab === 'people') void loadPeople()
    if (tab === 'reviews' && canReview) void loadReviews()
    if (tab === 'succession' && canSuccession) void loadSuccession()
    if (tab === 'ninebox') void loadNine()
  }, [tab, canReview, canSuccession, loadPeople, loadReviews, loadSuccession, loadNine])

  return (
    <div dir={isAr ? 'rtl' : 'ltr'} lang={isAr ? 'ar' : 'en'} className="space-y-5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => void load()} disabled={loading} aria-label={t.refresh}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>

      <ConfigureInSetupBanner anchor="classic-wave4-talent" />

      {state !== 'ready' ? (
        <ResourceState
          kind={state === 'empty' ? 'empty' : state}
          locale={isAr ? 'ar' : 'en'}
          title={forbidden ? t.forbidden : unavailable ? t.unavailable : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="talent-workspace-state"
        />
      ) : (
        <>
          <HrSurfaceTabs value={tab} onChange={setTab} ariaLabel={t.title} items={tabs} />

          {tab === 'overview' ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{t.noScore}</p>
              <p className="text-sm text-muted-foreground">{t.perfOff}</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  [t.profiles, counts?.profiles],
                  [t.openReviews, counts?.open_reviews],
                  [t.uncovered, counts?.uncovered_roles ?? '—'],
                  [t.hipo, canSensitive ? counts?.hipo_designated ?? '—' : '—'],
                ].map(([label, value]) => (
                  <div key={String(label)} className="rounded-xl border border-border/70 p-3">
                    <div className="text-xs text-muted-foreground">{label}</div>
                    <div className="text-2xl font-semibold">{String(value ?? 0)}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {tab === 'people' ? (
            <PeoplePanel
              t={t}
              isAr={isAr}
              canManage={canManage}
              canSensitive={canSensitive}
              empKey={empKey}
              setEmpKey={setEmpKey}
              title={title}
              setTitle={setTitle}
              rationale={rationale}
              setRationale={setRationale}
              people={people}
              peopleLoading={peopleLoading}
              peopleError={peopleError}
              access={access}
              onNotice={onNotice}
              onAccessIssue={onAccessIssue}
              onReload={() => void loadPeople()}
            />
          ) : null}

          {tab === 'reviews' && canReview ? (
            <ReviewsPanel
              t={t}
              isAr={isAr}
              canManage={canManage}
              reviews={reviews}
              reviewsLoading={reviewsLoading}
              reviewsError={reviewsError}
              empKey={empKey}
              setEmpKey={setEmpKey}
              title={title}
              setTitle={setTitle}
              access={access}
              onNotice={onNotice}
              onRetry={() => void loadReviews()}
            />
          ) : null}

          {tab === 'succession' && canSuccession ? (
            <SuccessionPanel
              t={t}
              isAr={isAr}
              succession={succession}
              successionLoading={successionLoading}
              successionError={successionError}
              empKey={empKey}
              setEmpKey={setEmpKey}
              title={title}
              setTitle={setTitle}
              rationale={rationale}
              setRationale={setRationale}
              access={access}
              onNotice={onNotice}
              onRetry={() => void loadSuccession()}
            />
          ) : null}

          {tab === 'mobility' ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{t.recruitingOff}</p>
              <ResourceState kind="empty" locale={isAr ? 'ar' : 'en'} title={t.emptyHint} />
            </div>
          ) : null}

          {tab === 'models' && !managerOnly ? (
            <ModelsPane access={access} isAr={isAr} t={t} empKey={empKey} setEmpKey={setEmpKey} onNotice={onNotice} canManage={canManage} />
          ) : null}

          {tab === 'rolefit' && !managerOnly ? (
            <RoleFitPane access={access} isAr={isAr} t={t} empKey={empKey} setEmpKey={setEmpKey} onNotice={onNotice} canManage={canManage} />
          ) : null}

          {tab === 'map' && !managerOnly ? <MapPane access={access} isAr={isAr} t={t} /> : null}

          {tab === 'ninebox' ? (
            <div className="space-y-3">
              {(() => {
                const nineState = resolveListDataState({
                  loading: nineLoading,
                  error: nineError,
                  itemCount: nine?.configs?.length || 0,
                })
                if (nineState !== 'ready') {
                  return (
                    <ResourceState
                      kind={nineState === 'empty' ? 'empty' : nineState}
                      locale={isAr ? 'ar' : 'en'}
                      title={nineState === 'empty' ? t.emptyNine : undefined}
                      detail={nineState === 'empty' ? t.emptyHint : undefined}
                      onRetry={() => void loadNine()}
                      retrying={nineLoading}
                      testId="talent-ninebox-state"
                    />
                  )
                }
                return (
                  <ul className="space-y-2">
                    {nine!.configs!.map((cfg) => (
                      <li key={String(cfg.config_id)} className="rounded-xl border border-border/70 p-3 text-sm">
                        {String(cfg.name_en || cfg.config_id)} · {t.project}
                      </li>
                    ))}
                  </ul>
                )
              })()}
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}

function PeoplePanel({
  t,
  isAr,
  canManage,
  canSensitive,
  empKey,
  setEmpKey,
  title,
  setTitle,
  rationale,
  setRationale,
  people,
  peopleLoading,
  peopleError,
  access,
  onNotice,
  onAccessIssue,
  onReload,
}: {
  t: ReturnType<typeof copy>
  isAr: boolean
  canManage: boolean
  canSensitive: boolean
  empKey: string
  setEmpKey: (v: string) => void
  title: string
  setTitle: (v: string) => void
  rationale: string
  setRationale: (v: string) => void
  people: Array<Record<string, unknown>>
  peopleLoading: boolean
  peopleError: boolean
  access: DashboardAccess
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
  onReload: () => void
}) {
  const [open, setOpen] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [evidence, setEvidence] = useState<Array<Record<string, unknown>>>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const peopleState = resolveListDataState({
    loading: peopleLoading,
    error: peopleError,
    itemCount: people.length,
  })

  return (
    <div className="space-y-3">
      {canManage ? (
        <div className="flex flex-wrap gap-2">
          <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t.titleEn} />
          <Button
            type="button"
            size="sm"
            onClick={() => {
              void postTalentJson(access, '/dashboard/posthire/talent/profiles', {
                employee_key: empKey,
                reason: 'create talent profile',
              })
                .then(() => {
                  onNotice(isAr ? 'تم إنشاء الملف' : 'Profile created', 'success')
                  onReload()
                })
                .catch(() => onNotice(isAr ? 'تعذّر الإنشاء' : 'Could not create', 'error'))
            }}
          >
            {t.createProfile}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              void postTalentJson(access, '/dashboard/posthire/talent/evidence', {
                employee_key: empKey,
                dimension_kind: 'strength',
                title_en: title || 'Evidence',
                source: 'hr_assessed',
                reason: 'add talent evidence',
              })
                .then(() => onNotice(isAr ? 'أُضيف الدليل' : 'Evidence added', 'success'))
                .catch(() => onNotice(isAr ? 'تعذّر الإضافة' : 'Could not add', 'error'))
            }}
          >
            {t.addEvidence}
          </Button>
          {canSensitive ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                void postTalentJson(access, '/dashboard/posthire/talent/hipo', {
                  employee_key: empKey,
                  status: 'designated',
                  rationale: rationale || 'Explicit HiPo decision',
                  reason: 'explicit HiPo decision',
                })
                  .then(() => onNotice(isAr ? 'تم التعيين' : 'HiPo designated', 'success'))
                  .catch(() => onNotice(isAr ? 'تعذّر التعيين' : 'Could not designate', 'error'))
              }}
            >
              {t.designateHipo}
            </Button>
          ) : null}
        </div>
      ) : null}
      {canSensitive ? (
        <Textarea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder={t.rationale} />
      ) : null}
      {peopleState !== 'ready' ? (
        <ResourceState
          kind={peopleState === 'empty' ? 'empty' : peopleState}
          locale={isAr ? 'ar' : 'en'}
          title={peopleState === 'empty' ? t.emptyPeople : undefined}
          detail={peopleState === 'empty' ? t.emptyHint : undefined}
          onRetry={onReload}
          retrying={peopleLoading}
          testId="talent-people-state"
        />
      ) : (
        <ul className="space-y-2">
          {people.map((row) => {
            const key = String(row.employee_key || '')
            return (
              <li key={key} className="rounded-xl border border-border/70 p-3">
                <button
                  type="button"
                  className="text-start font-medium"
                  onClick={() => {
                    setOpen(key)
                    setDetail(null)
                    setEvidence([])
                    setDetailError(false)
                    setDetailLoading(true)
                    void Promise.all([
                      getTalentProfile(access, key),
                      getTalentEvidenceIndex(access, key),
                    ])
                      .then(([profile, index]) => {
                        setDetail(profile)
                        setEvidence(index.evidence || [])
                      })
                      .catch((err) => {
                        const issue = accessIssueFromError(err)
                        if (issue) onAccessIssue?.(issue)
                        setDetailError(true)
                      })
                      .finally(() => setDetailLoading(false))
                  }}
                >
                  {key}
                </button>
                {open === key ? (
                  detailLoading ? (
                    <ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} testId="talent-profile-detail-state" />
                  ) : detailError ? (
                    <div className="mt-2">
                      <ResourceState
                        kind="error"
                        locale={isAr ? 'ar' : 'en'}
                        testId="talent-profile-detail-state"
                      />
                    </div>
                  ) : detail ? (
                  <div className="mt-2 space-y-2">
                    <pre className="overflow-auto text-xs text-muted-foreground">
                      {JSON.stringify(
                        {
                          facts: detail.facts,
                          skills: detail.skills,
                          potential: detail.potential,
                          hipo: detail.hipo,
                          master_talent_score: detail.master_talent_score,
                          evidence_index: detail.evidence_index || evidence,
                        },
                        null,
                        2,
                      )}
                    </pre>
                    {evidence.length > 0 ? (
                      <div className="text-xs text-muted-foreground">
                        <div className="font-medium text-foreground">{t.evidenceIndex}</div>
                        {evidence.map((item) => (
                          <div key={String(item.evidence_id)}>
                            {String(item.provenance_class || '')} · {String(item.evidence_kind || '')}
                            {item.claimed_not_verified ? ` · ${t.claimedNotVerified}` : ''}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  ) : null
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function ReviewsPanel({
  t,
  isAr,
  canManage,
  reviews,
  reviewsLoading,
  reviewsError,
  empKey,
  setEmpKey,
  title,
  setTitle,
  access,
  onNotice,
  onRetry,
}: {
  t: ReturnType<typeof copy>
  isAr: boolean
  canManage: boolean
  reviews: Array<Record<string, unknown>>
  reviewsLoading: boolean
  reviewsError: boolean
  empKey: string
  setEmpKey: (v: string) => void
  title: string
  setTitle: (v: string) => void
  access: DashboardAccess
  onNotice: NoticeFn
  onRetry: () => void
}) {
  const reviewsState = resolveListDataState({
    loading: reviewsLoading,
    error: reviewsError,
    itemCount: reviews.length,
  })
  return (
    <div className="space-y-3">
      {canManage ? (
        <div className="flex flex-wrap gap-2">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t.titleEn} />
          <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
          <Button
            type="button"
            size="sm"
            onClick={() => {
              void postTalentJson<{ review?: { review_id?: string } }>(access, '/dashboard/posthire/talent/reviews', {
                name_en: title || 'Talent review',
                reason: 'create talent review',
              })
                .then(async (created) => {
                  const id = created.review?.review_id
                  if (id && empKey) {
                    await postTalentJson(access, `/dashboard/posthire/talent/reviews/${id}/prepare`, {
                      population: [{ employee_key: empKey }],
                      reason: 'prepare talent review',
                    })
                  }
                  onNotice('ok', 'success')
                })
                .catch(() => onNotice('error', 'error'))
            }}
          >
            {t.createReview}
          </Button>
        </div>
      ) : null}
      {reviewsState !== 'ready' ? (
        <ResourceState
          kind={reviewsState === 'empty' ? 'empty' : reviewsState}
          locale={isAr ? 'ar' : 'en'}
          title={reviewsState === 'empty' ? t.emptyReviews : undefined}
          detail={reviewsState === 'empty' ? t.emptyHint : undefined}
          onRetry={onRetry}
          retrying={reviewsLoading}
          testId="talent-reviews-state"
        />
      ) : (
        <ul className="space-y-2">
          {reviews.map((row) => (
            <li key={String(row.review_id)} className="rounded-xl border border-border/70 p-3 text-sm">
              {String(row.name_en || row.review_id)} · {String(row.status)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SuccessionPanel({
  t,
  isAr,
  succession,
  successionLoading,
  successionError,
  empKey,
  setEmpKey,
  title,
  setTitle,
  rationale,
  setRationale,
  access,
  onNotice,
  onRetry,
}: {
  t: ReturnType<typeof copy>
  isAr: boolean
  succession: {
    critical_roles?: Array<Record<string, unknown>>
    plans?: Array<Record<string, unknown>>
    uncovered?: Array<Record<string, unknown>>
  } | null
  successionLoading: boolean
  successionError: boolean
  empKey: string
  setEmpKey: (v: string) => void
  title: string
  setTitle: (v: string) => void
  rationale: string
  setRationale: (v: string) => void
  access: DashboardAccess
  onNotice: NoticeFn
  onRetry: () => void
}) {
  const successionState = resolveListDataState({
    loading: successionLoading,
    error: successionError,
    itemCount: succession?.plans?.length || 0,
  })
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t.criticalRole} />
        <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
        <Textarea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder={t.rationale} />
        <Button
          type="button"
          size="sm"
          onClick={() => {
            void postTalentJson<{ critical_role?: { critical_role_id?: string } }>(
              access,
              '/dashboard/posthire/talent/critical-roles',
              {
                canonical_role_key: title || 'role-1',
                title_en: title || 'Target role',
                reason: 'designate critical role',
              },
            )
              .then(async (role) => {
                const id = role.critical_role?.critical_role_id
                if (!id) return
                const plan = await postTalentJson<{ plan?: { plan_id?: string } }>(
                  access,
                  '/dashboard/posthire/talent/plans',
                  { critical_role_id: id, reason: 'create succession plan' },
                )
                const planId = plan.plan?.plan_id
                if (planId && empKey) {
                  await postTalentJson(access, `/dashboard/posthire/talent/plans/${planId}/nominations`, {
                    employee_key: empKey,
                    rationale: rationale || 'Nomination',
                    readiness: 'ready_now',
                    reason: 'nominate successor',
                  })
                }
                onNotice('ok', 'success')
              })
              .catch(() => onNotice('error', 'error'))
          }}
        >
          {t.nominate}
        </Button>
      </div>
      {successionState !== 'ready' ? (
        <ResourceState
          kind={successionState === 'empty' ? 'empty' : successionState}
          locale={isAr ? 'ar' : 'en'}
          title={successionState === 'empty' ? t.emptySuccession : undefined}
          detail={successionState === 'empty' ? t.emptyHint : undefined}
          onRetry={onRetry}
          retrying={successionLoading}
          testId="talent-succession-state"
        />
      ) : (
        <ul className="space-y-2">
          {(succession?.plans || []).map((plan) => (
            <li key={String(plan.plan_id)} className="rounded-xl border border-border/70 p-3 text-sm">
              {String(plan.title_en || plan.canonical_role_key || plan.plan_id)}
              <button
                type="button"
                className="ms-2 underline"
                onClick={() => {
                  void getTalentSlate(access, String(plan.plan_id)).then((slate) => {
                    onNotice(String((slate.nominations || []).length), 'info')
                  })
                }}
              >
                {t.readiness}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ModelsPane({
  access,
  isAr,
  t,
  empKey,
  setEmpKey,
  onNotice,
  canManage,
}: {
  access: DashboardAccess
  isAr: boolean
  t: ReturnType<typeof copy>
  empKey: string
  setEmpKey: (v: string) => void
  onNotice: NoticeFn
  canManage: boolean
}) {
  const [models, setModels] = useState<Array<Record<string, unknown>>>([])
  const [why, setWhy] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const reload = useCallback(() => {
    setLoading(true)
    setError(false)
    void getTalentModels(access)
      .then((data) => setModels(data.models || []))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [access])

  useEffect(() => {
    reload()
  }, [reload])

  const modelsState = resolveListDataState({ loading, error, itemCount: models.length })

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t.derivedNotHipo}</p>
      {canManage ? (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => {
              void postTalentJson<{ model?: { model_id?: string } }>(access, '/dashboard/posthire/talent/models', {
                name_en: 'High Potential signal',
                name_ar: 'إشارة الإمكانات العالية',
                reason: 'create default talent model',
              })
                .then(async (created) => {
                  const id = created.model?.model_id
                  if (!id) return
                  const version = await postTalentJson<{ version?: { version_id?: string } }>(
                    access,
                    '/dashboard/posthire/talent/models/versions',
                    {
                      model_id: id,
                      use_default_high_potential_signal: true,
                      reason: 'draft default rules',
                    },
                  )
                  const vid = version.version?.version_id
                  if (vid) {
                    await postTalentJson(access, `/dashboard/posthire/talent/models/versions/${vid}/publish`, {
                      reason: 'publish default model',
                    })
                  }
                  onNotice(isAr ? 'تم نشر النموذج' : 'Model published', 'success')
                  reload()
                })
                .catch(() => onNotice(isAr ? 'تعذّر النشر' : 'Could not publish', 'error'))
            }}
          >
            {t.publishModel}
          </Button>
          <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!empKey.trim() || !models[0]}
            onClick={() => {
              void postTalentJson<Record<string, unknown>>(access, '/dashboard/posthire/talent/models/evaluate', {
                employee_key: empKey.trim(),
                model_id: String(models[0]?.model_id || ''),
                reason: 'evaluate derived signal',
              })
                .then((result) => {
                  setWhy((result.why as Record<string, unknown>) || null)
                  onNotice(isAr ? 'تم التشغيل' : 'Evaluated', 'success')
                })
                .catch(() => onNotice(isAr ? 'تعذّر التشغيل' : 'Could not evaluate', 'error'))
            }}
          >
            {t.evaluate}
          </Button>
        </div>
      ) : null}
      {modelsState !== 'ready' ? (
        <ResourceState
          kind={modelsState === 'empty' ? 'empty' : modelsState}
          locale={isAr ? 'ar' : 'en'}
          title={modelsState === 'empty' ? t.emptyHint : undefined}
          onRetry={reload}
          retrying={loading}
          testId="talent-models-state"
        />
      ) : (
        <ul className="space-y-2">
          {models.map((model) => (
            <li key={String(model.model_id)} className="rounded-xl border border-border/70 p-3 text-sm">
              {isAr ? String(model.name_ar || model.name_en || '') : String(model.name_en || '')} · {String(model.status || '')}
            </li>
          ))}
        </ul>
      )}
      {why ? (
        <pre className="overflow-auto text-xs text-muted-foreground">
          {t.why}
          {'\n'}
          {JSON.stringify(why, null, 2)}
        </pre>
      ) : null}
    </div>
  )
}

function RoleFitPane({
  access,
  isAr,
  t,
  empKey,
  setEmpKey,
  onNotice,
  canManage,
}: {
  access: DashboardAccess
  isAr: boolean
  t: ReturnType<typeof copy>
  empKey: string
  setEmpKey: (v: string) => void
  onNotice: NoticeFn
  canManage: boolean
}) {
  const [sets, setSets] = useState<Array<Record<string, unknown>>>([])
  const [why, setWhy] = useState<Record<string, unknown> | null>(null)
  const [roleKey, setRoleKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const reload = useCallback(() => {
    setLoading(true)
    setError(false)
    void getTalentRoleFitSets(access)
      .then((data) => setSets(data.sets || []))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [access])

  useEffect(() => {
    reload()
  }, [reload])

  const setsState = resolveListDataState({ loading, error, itemCount: sets.length })

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t.fitNotReady}</p>
      <p className="text-sm text-muted-foreground">{t.jaOffFit}</p>
      {canManage ? (
        <div className="flex flex-wrap gap-2">
          <Input value={roleKey} onChange={(e) => setRoleKey(e.target.value)} placeholder={t.criticalRole} />
          <Button
            type="button"
            size="sm"
            disabled={!roleKey.trim()}
            onClick={() => {
              void postTalentJson<{ set?: { set_id?: string } }>(access, '/dashboard/posthire/talent/role-fit/sets', {
                name_en: 'Target role requirements',
                name_ar: 'متطلبات الدور المستهدف',
                critical_role_id: roleKey.trim(),
                reason: 'create requirement set',
              })
                .then(async (created) => {
                  const id = created.set?.set_id
                  if (!id) return
                  const version = await postTalentJson<{ version?: { version_id?: string } }>(
                    access,
                    '/dashboard/posthire/talent/role-fit/sets/versions',
                    {
                      set_id: id,
                      requirements: [
                        { id: 'skill-core', kind: 'skill', code: 'CORE', priority: 'required' },
                      ],
                      reason: 'draft requirements',
                    },
                  )
                  const vid = version.version?.version_id
                  if (vid) {
                    await postTalentJson(access, `/dashboard/posthire/talent/role-fit/sets/versions/${vid}/publish`, {
                      reason: 'publish requirement set',
                    })
                  }
                  onNotice(isAr ? 'تم النشر' : 'Published', 'success')
                  reload()
                })
                .catch(() => onNotice(isAr ? 'تعذّر النشر' : 'Could not publish', 'error'))
            }}
          >
            {t.publishModel}
          </Button>
          <Input value={empKey} onChange={(e) => setEmpKey(e.target.value)} placeholder={t.employeeKey} />
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!empKey.trim() || !sets[0]}
            onClick={() => {
              void postTalentJson<Record<string, unknown>>(access, '/dashboard/posthire/talent/role-fit/evaluate', {
                employee_key: empKey.trim(),
                set_id: String(sets[0]?.set_id || ''),
                reason: 'evaluate role fit',
              })
                .then((result) => {
                  setWhy((result.why as Record<string, unknown>) || null)
                  onNotice(isAr ? 'تم التقييم' : 'Evaluated', 'success')
                })
                .catch(() => onNotice(isAr ? 'تعذّر التقييم' : 'Could not evaluate', 'error'))
            }}
          >
            {t.evaluate}
          </Button>
        </div>
      ) : null}
      {setsState !== 'ready' ? (
        <ResourceState
          kind={setsState === 'empty' ? 'empty' : setsState}
          locale={isAr ? 'ar' : 'en'}
          title={setsState === 'empty' ? t.emptyHint : undefined}
          onRetry={reload}
          retrying={loading}
          testId="talent-rolefit-state"
        />
      ) : (
        <ul className="space-y-2">
          {sets.map((item) => (
            <li key={String(item.set_id)} className="rounded-xl border border-border/70 p-3 text-sm">
              {isAr ? String(item.name_ar || item.name_en || '') : String(item.name_en || '')} · {String(item.status || '')}
            </li>
          ))}
        </ul>
      )}
      {why ? (
        <pre className="overflow-auto text-xs text-muted-foreground">
          {t.why}
          {'\n'}
          {JSON.stringify(why, null, 2)}
        </pre>
      ) : null}
    </div>
  )
}

function MapPane({
  access,
  isAr,
  t,
}: {
  access: DashboardAccess
  isAr: boolean
  t: ReturnType<typeof copy>
}) {
  const [lens, setLens] = useState('perf_x_potential')
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null)
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    setLoading(true)
    setError(false)
    void getTalentMap(access, lens)
      .then((data) => setPayload(data))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [access, lens, reloadToken])

  const placements = (payload?.placements as Array<Record<string, unknown>>) || []
  const lenses = (payload?.lenses as Array<Record<string, unknown>>) || []
  const mapState = resolveListDataState({ loading, error, itemCount: placements.length })

  return (
    <div className="space-y-3" dir={isAr ? 'rtl' : 'ltr'}>
      <p className="text-sm text-muted-foreground">{t.unknownStay}</p>
      <label className="text-sm">
        {t.lens}
        <select
          className="ms-2 rounded-md border border-border bg-background px-2 py-1"
          value={lens}
          onChange={(e) => {
            setLens(e.target.value)
            setSelected(null)
          }}
        >
          {(lenses.length
            ? lenses
            : error
              ? []
              : [{ id: 'perf_x_potential', label_en: 'Performance × Potential', label_ar: 'الأداء × الإمكانات' }]
          ).map((item) => (
            <option key={String(item.id)} value={String(item.id)}>
              {isAr ? String(item.label_ar || item.label_en || '') : String(item.label_en || item.id)}
            </option>
          ))}
        </select>
      </label>
      {mapState !== 'ready' ? (
        <ResourceState
          kind={mapState === 'empty' ? 'empty' : mapState}
          locale={isAr ? 'ar' : 'en'}
          title={mapState === 'empty' ? t.emptyHint : undefined}
          onRetry={() => setReloadToken((n) => n + 1)}
          retrying={loading}
          testId="talent-map-state"
        />
      ) : (
        <ul className="space-y-2">
          {placements.map((place) => (
            <li key={String(place.employee_key)}>
              <button
                type="button"
                className="w-full rounded-xl border border-border/70 p-3 text-start text-sm"
                onClick={() => setSelected(place)}
              >
                {String(place.employee_key)} · {place.unknown ? t.unknownStay : String(place.cell || '')}
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected ? (
        <pre className="overflow-auto text-xs text-muted-foreground">
          {t.why}
          {'\n'}
          {JSON.stringify(selected.why || selected.canonical_facts, null, 2)}
        </pre>
      ) : null}
    </div>
  )
}
