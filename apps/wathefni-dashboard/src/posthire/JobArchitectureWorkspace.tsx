/**
 * R5D Job Architecture workspace — thin client over frozen Wave 6 C1.
 * JA Job Profile ≠ Recruiting Job ≠ Requisition.
 * Career edges are not eligibility. No career score. No salary bands.
 */
import { Layers3, Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { useUrlBackedTab, URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getJobArchitectureAssignments,
  getJobArchitectureCatalog,
  getJobArchitectureHistory,
  getJobArchitectureMappings,
  getJobArchitectureRefs,
  getJobArchitectureWorkspace,
  postJobArchitectureJson,
  type JobArchitectureCatalogPayload,
  type JobArchitectureWorkspacePayload,
} from '@/lib/api'
import { ResourceState, resolveListDataState } from '@/pages/shared/dataState'
import { hasActorPermission } from '@/pages/shared/access'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type JobArchitectureWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'overview' | 'catalog' | 'grades' | 'paths' | 'mappings'

const WORKSPACE_TABS = URL_BACKED_WORKSPACE_TABS['job-architecture'] as readonly Tab[]

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'هيكل الوظائف',
        subtitle: 'العائلة ← الوظيفة ← الملف الوظيفي ← الدرجة ← المستوى ← المسارات. قدرة منصّة مشتركة وليست وظيفة توظيف.',
        overview: 'نظرة عامة',
        catalog: 'الكتالوج',
        grades: 'الدرجات والمستويات',
        paths: 'المسارات المهنية',
        mappings: 'الربط والترحيل',
        refresh: 'تحديث',
        families: 'العائلات',
        functions: 'الوظائف',
        profiles: 'الملفات الوظيفية',
        published: 'منشور',
        gradesCount: 'الدرجات',
        levels: 'المستويات',
        edges: 'مسارات التقدّم',
        mapped: 'مربوط',
        unmapped: 'غير مربوط',
        ambiguous: 'ملتبس',
        emptyCatalog: 'لا توجد ملفات وظيفية بعد',
        emptyMappings: 'لا توجد عناصر ترحيل بعد',
        emptyHint: 'هذه نتيجة فارغة صادقة — ليست خطأ تحميل.',
        forbidden: 'ليست لديك صلاحية هذا السطح.',
        unavailable: 'هيكل الوظائف غير متاح لهذه الشركة.',
        noScore: 'لا توجد درجة مسار مهني عامة.',
        edgeNotEligible: 'المسار المهني ليس أهلية للموظف ولا توصية ترقية.',
        recruitingBoundary: 'الملف الوظيفي لهيكل الوظائف ليس وظيفة التوظيف وليس طلب توظيف.',
        rawPreserved: 'العنوان والدرجة القديمان يبقيان كما هما. الربط يضيف بنية ولا يمحو المصدر.',
        config: 'التهيئة في الإعداد',
        familyCode: 'رمز العائلة',
        functionCode: 'رمز الوظيفة',
        profileCode: 'رمز الملف الوظيفي',
        gradeCode: 'رمز الدرجة',
        levelCode: 'رمز المستوى',
        nameEn: 'الاسم إنجليزي',
        nameAr: 'الاسم عربي',
        description: 'الوصف',
        status: 'الحالة',
        reason: 'سبب التدقيق',
        saveFamily: 'حفظ عائلة',
        saveFunction: 'حفظ وظيفة',
        saveProfile: 'حفظ ملف وظيفي',
        saveGrade: 'حفظ درجة',
        saveLevel: 'حفظ مستوى',
        saveEdge: 'إضافة مسار',
        edgeType: 'نوع المسار',
        fromProfile: 'من ملف وظيفي',
        toProfile: 'إلى ملف وظيفي',
        resolve: 'حل بشري',
        mappingId: 'معرّف الربط',
        entityType: 'نوع الكيان',
        entityId: 'معرّف الكيان',
        history: 'السجل والإصدارات',
        assignments: 'تعيينات التوظيف',
        refs: 'مراجع اختيارية (مواهب / توظيف)',
        version: 'الإصدار',
      }
    : {
        title: 'Job Architecture',
        subtitle: 'Family → function → job profile → grade → level → career paths. A shared platform foundation — not a Recruiting Job.',
        overview: 'Overview',
        catalog: 'Catalog',
        grades: 'Grades & levels',
        paths: 'Career paths',
        mappings: 'Mappings',
        refresh: 'Refresh',
        families: 'Families',
        functions: 'Functions',
        profiles: 'Job profiles',
        published: 'Published',
        gradesCount: 'Grades',
        levels: 'Levels',
        edges: 'Career edges',
        mapped: 'Mapped',
        unmapped: 'Unmapped',
        ambiguous: 'Ambiguous',
        emptyCatalog: 'No job profiles yet',
        emptyMappings: 'No migration items yet',
        emptyHint: 'This is a true empty result — not a load failure.',
        forbidden: 'You do not have access to this surface.',
        unavailable: 'Job Architecture is not available for this company.',
        noScore: 'There is no universal career score.',
        edgeNotEligible: 'A career path is not employee eligibility and not a promotion recommendation.',
        recruitingBoundary: 'A Job Architecture job profile is not a Recruiting Job and not a requisition.',
        rawPreserved: 'Raw title and grade stay preserved. Mapping adds structure; it does not erase source truth.',
        config: 'Configuration lives in Setup',
        familyCode: 'Family code',
        functionCode: 'Function code',
        profileCode: 'Job profile code',
        gradeCode: 'Grade code',
        levelCode: 'Level code',
        nameEn: 'Name (EN)',
        nameAr: 'Name (AR)',
        description: 'Description',
        status: 'Status',
        reason: 'Audit reason',
        saveFamily: 'Save family',
        saveFunction: 'Save function',
        saveProfile: 'Save job profile',
        saveGrade: 'Save grade',
        saveLevel: 'Save level',
        saveEdge: 'Add career edge',
        edgeType: 'Edge type',
        fromProfile: 'From job profile',
        toProfile: 'To job profile',
        resolve: 'Human resolve',
        mappingId: 'Mapping id',
        entityType: 'Entity type',
        entityId: 'Entity id',
        history: 'Version / history',
        assignments: 'Employment mappings',
        refs: 'Optional Talent / Recruiting refs',
        version: 'Version',
      }
}

function labelOf(row: Record<string, unknown>, isAr: boolean): string {
  const name = isAr ? row.name_ar || row.name_en : row.name_en || row.name_ar
  return String(name || row.code || row.profile_id || row.family_id || '')
}

export function JobArchitectureWorkspace({
  access,
  permissions,
  onNotice,
  onAccessIssue,
}: JobArchitectureWorkspaceProps) {
  const { isAr } = useEmployees360Locale()
  const t = copy(isAr)
  const [tab, setTab] = useUrlBackedTab<Tab>('job-architecture', WORKSPACE_TABS, 'overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [payload, setPayload] = useState<JobArchitectureWorkspacePayload | null>(null)
  const [catalog, setCatalog] = useState<JobArchitectureCatalogPayload | null>(null)
  const [mappings, setMappings] = useState<Array<Record<string, unknown>>>([])
  const [assignments, setAssignments] = useState<Array<Record<string, unknown>>>([])
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([])
  const [refs, setRefs] = useState<Array<Record<string, unknown>>>([])
  const [code, setCode] = useState('')
  const [nameEn, setNameEn] = useState('')
  const [nameAr, setNameAr] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState('draft')
  const [reason, setReason] = useState('job architecture authoring')
  const [familyId, setFamilyId] = useState('')
  const [functionId, setFunctionId] = useState('')
  const [gradeId, setGradeId] = useState('')
  const [fromProfile, setFromProfile] = useState('')
  const [toProfile, setToProfile] = useState('')
  const [edgeType, setEdgeType] = useState('promotion')
  const [mappingId, setMappingId] = useState('')
  const [mappedType, setMappedType] = useState('job_profile')
  const [mappedId, setMappedId] = useState('')

  const canManage = hasActorPermission(permissions, 'job_architecture.manage')
  const canMap = hasActorPermission(permissions, 'job_architecture.mapping') || canManage
  const canPublish = hasActorPermission(permissions, 'job_architecture.publish') || canManage

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    setForbidden(false)
    setUnavailable(false)
    try {
      const data = await getJobArchitectureWorkspace(access)
      setPayload(data)
      if (data.resource_state === 'unavailable' || data.enabled === false) {
        setUnavailable(true)
        setCatalog(null)
        setMappings([])
        return
      }
      const nextCatalog = await getJobArchitectureCatalog(access)
      setCatalog(nextCatalog)
      if (nextCatalog.resource_state === 'unavailable') setUnavailable(true)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      if (err instanceof DashboardApiError) {
        if (err.status === 403) {
          const codeErr = String((err.body as { error?: string } | undefined)?.error || '')
          if (codeErr.includes('permission') || codeErr.includes('forbidden')) setForbidden(true)
          else setUnavailable(true)
        } else if (err.status === 404) {
          setUnavailable(true)
        } else {
          setError(true)
        }
      } else {
        setError(true)
      }
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (unavailable || forbidden || error) return
    if (tab === 'mappings') {
      void Promise.all([
        getJobArchitectureMappings(access),
        getJobArchitectureAssignments(access),
        getJobArchitectureRefs(access),
      ])
        .then(([mapPayload, assignPayload, refPayload]) => {
          setMappings(mapPayload.mappings || [])
          setAssignments(assignPayload.assignments || [])
          setRefs(refPayload.refs || [])
        })
        .catch(() => setError(true))
    }
    if (tab === 'grades' || tab === 'paths') {
      void getJobArchitectureHistory(access)
        .then((hist) => setHistory(hist.events || []))
        .catch(() => setError(true))
    }
  }, [access, error, forbidden, tab, unavailable])

  const counts = payload?.counts
  const enabledReady = Boolean(payload?.ok) && !unavailable && !forbidden && !error && !loading
  const state = resolveListDataState({
    forbidden,
    unavailable,
    loading,
    error,
    itemCount: enabledReady ? 1 : 0,
  })

  const tabs = useMemo(
    () =>
      [
        { id: 'overview' as const, label: t.overview },
        { id: 'catalog' as const, label: t.catalog },
        { id: 'grades' as const, label: t.grades },
        { id: 'paths' as const, label: t.paths },
        { id: 'mappings' as const, label: t.mappings },
      ],
    [t],
  )

  async function author(path: string, body: Record<string, unknown>) {
    if (!canManage && path !== '/dashboard/job-architecture/mappings/migrate') {
      onNotice(t.forbidden, 'error')
      return
    }
    try {
      await postJobArchitectureJson(access, path, { ...body, reason, status })
      onNotice(isAr ? 'تم الحفظ' : 'Saved', 'success')
      await load()
    } catch (err) {
      onNotice(err instanceof Error ? err.message : 'Error', 'error')
    }
  }

  return (
    <div dir={isAr ? 'rtl' : 'ltr'} lang={isAr ? 'ar' : 'en'} className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Layers3 className="h-5 w-5 text-primary" />
            <h2 className="text-xl font-semibold">{t.title}</h2>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t.subtitle}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="ms-2">{t.refresh}</span>
        </Button>
      </div>

      <ConfigureInSetupBanner anchor="classic-wave6-job-architecture" />

      {state !== 'ready' ? (
        <ResourceState
          kind={state === 'empty' ? 'empty' : state}
          locale={isAr ? 'ar' : 'en'}
          title={forbidden ? t.forbidden : unavailable ? t.unavailable : state === 'empty' ? t.emptyCatalog : undefined}
          detail={state === 'empty' ? t.emptyHint : undefined}
          onRetry={() => void load()}
          retrying={loading}
          testId="job-architecture-workspace-state"
        />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {tabs.map((item) => (
              <Button
                key={item.id}
                type="button"
                size="sm"
                variant={tab === item.id ? 'default' : 'outline'}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </Button>
            ))}
          </div>

          {tab === 'overview' ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{t.noScore}</p>
              <p className="text-sm text-muted-foreground">{t.edgeNotEligible}</p>
              <p className="text-sm text-muted-foreground">{t.recruitingBoundary}</p>
              <p className="text-sm text-muted-foreground">{t.rawPreserved}</p>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  [t.families, counts?.families],
                  [t.functions, counts?.functions],
                  [t.profiles, counts?.profiles],
                  [t.published, counts?.published_profiles],
                  [t.gradesCount, counts?.grades],
                  [t.levels, counts?.levels],
                  [t.edges, counts?.career_edges],
                  [t.mapped, counts?.mapped],
                  [t.unmapped, counts?.unmapped],
                  [t.ambiguous, counts?.ambiguous],
                ].map(([label, value]) => (
                  <div key={String(label)} className="rounded-lg border border-border/70 px-3 py-3">
                    <div className="text-xs text-muted-foreground">{label}</div>
                    <div className="text-lg font-semibold">{value ?? '—'}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {tab === 'catalog' ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">{t.recruitingBoundary}</p>
              {canManage ? (
                <div className="grid gap-2 md:grid-cols-2">
                  <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.profileCode} />
                  <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} placeholder={t.nameEn} />
                  <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} placeholder={t.nameAr} />
                  <Input value={familyId} onChange={(e) => setFamilyId(e.target.value)} placeholder={t.familyCode} />
                  <Input value={functionId} onChange={(e) => setFunctionId(e.target.value)} placeholder={t.functionCode} />
                  <Input value={status} onChange={(e) => setStatus(e.target.value)} placeholder={t.status} />
                  <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t.description} />
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.reason} />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      disabled={!canPublish && status === 'published'}
                      onClick={() =>
                        void author('/dashboard/job-architecture/families', {
                          code,
                          name_en: nameEn,
                          name_ar: nameAr,
                          description_en: description,
                          description_ar: description,
                        })
                      }
                    >
                      {t.saveFamily}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void author('/dashboard/job-architecture/functions', {
                          family_id: familyId,
                          code,
                          name_en: nameEn,
                          name_ar: nameAr,
                        })
                      }
                    >
                      {t.saveFunction}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void author('/dashboard/job-architecture/profiles', {
                          function_id: functionId,
                          code,
                          name_en: nameEn,
                          name_ar: nameAr,
                          description_en: description,
                          description_ar: description,
                          default_grade_id: gradeId || null,
                        })
                      }
                    >
                      {t.saveProfile}
                    </Button>
                  </div>
                </div>
              ) : null}
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.families}</h3>
                <ul className="space-y-1 text-sm">
                  {(catalog?.families || []).map((row) => (
                    <li key={String(row.family_id)}>
                      {labelOf(row, isAr)} · {String(row.code)} · {t.version} {String(row.effective_version)}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.functions}</h3>
                <ul className="space-y-1 text-sm">
                  {(catalog?.functions || []).map((row) => (
                    <li key={String(row.function_id)}>
                      {labelOf(row, isAr)} · {String(row.code)}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.profiles}</h3>
                {(catalog?.profiles || []).length ? (
                  <ul className="space-y-1 text-sm">
                    {(catalog?.profiles || []).map((row) => (
                      <li key={String(row.profile_id)}>
                        {labelOf(row, isAr)} · {String(row.code)} · {String(row.status)} · {t.version}{' '}
                        {String(row.effective_version)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">{t.emptyCatalog}</p>
                )}
              </section>
            </div>
          ) : null}

          {tab === 'grades' ? (
            <div className="space-y-4">
              {canManage ? (
                <div className="grid gap-2 md:grid-cols-2">
                  <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t.gradeCode} />
                  <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} placeholder={t.nameEn} />
                  <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} placeholder={t.nameAr} />
                  <Input value={gradeId} onChange={(e) => setGradeId(e.target.value)} placeholder={t.gradeCode} />
                  <Button
                    type="button"
                    size="sm"
                    onClick={() =>
                      void author('/dashboard/job-architecture/grades', {
                        code,
                        name_en: nameEn,
                        name_ar: nameAr,
                        rank_order: 0,
                      })
                    }
                  >
                    {t.saveGrade}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void author('/dashboard/job-architecture/levels', {
                        code,
                        name_en: nameEn,
                        name_ar: nameAr,
                        grade_id: gradeId || null,
                        rank_order: 0,
                      })
                    }
                  >
                    {t.saveLevel}
                  </Button>
                </div>
              ) : null}
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.gradesCount}</h3>
                <ul className="space-y-1 text-sm">
                  {(catalog?.grades || []).map((row) => (
                    <li key={String(row.grade_id)}>
                      {labelOf(row, isAr)} · {String(row.code)} · {t.version} {String(row.effective_version)}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.levels}</h3>
                <ul className="space-y-1 text-sm">
                  {(catalog?.levels || []).map((row) => (
                    <li key={String(row.level_id)}>
                      {labelOf(row, isAr)} · {String(row.code)}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.history}</h3>
                <ul className="space-y-1 text-sm">
                  {history.slice(0, 12).map((row) => (
                    <li key={String(row.event_id || `${row.action}-${row.created_at}`)}>
                      {String(row.action)} · {String(row.entity_type)} · {String(row.entity_id)}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          ) : null}

          {tab === 'paths' ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">{t.edgeNotEligible}</p>
              {canManage ? (
                <div className="grid gap-2 md:grid-cols-2">
                  <Input value={edgeType} onChange={(e) => setEdgeType(e.target.value)} placeholder={t.edgeType} />
                  <Input value={fromProfile} onChange={(e) => setFromProfile(e.target.value)} placeholder={t.fromProfile} />
                  <Input value={toProfile} onChange={(e) => setToProfile(e.target.value)} placeholder={t.toProfile} />
                  <Button
                    type="button"
                    size="sm"
                    onClick={() =>
                      void author('/dashboard/job-architecture/career-edges', {
                        edge_type: edgeType,
                        from_profile_id: fromProfile,
                        to_profile_id: toProfile,
                      })
                    }
                  >
                    {t.saveEdge}
                  </Button>
                </div>
              ) : null}
              <ul className="space-y-1 text-sm">
                {(catalog?.career_edges || []).map((row) => (
                  <li key={String(row.edge_id)}>
                    {String(row.edge_type)} · {String(row.from_profile_id || row.from_grade_id)} →{' '}
                    {String(row.to_profile_id || row.to_grade_id)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {tab === 'mappings' ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">{t.rawPreserved}</p>
              {canMap ? (
                <div className="grid gap-2 md:grid-cols-2">
                  <Input value={mappingId} onChange={(e) => setMappingId(e.target.value)} placeholder={t.mappingId} />
                  <Input value={mappedType} onChange={(e) => setMappedType(e.target.value)} placeholder={t.entityType} />
                  <Input value={mappedId} onChange={(e) => setMappedId(e.target.value)} placeholder={t.entityId} />
                  <Button
                    type="button"
                    size="sm"
                    onClick={() =>
                      void postJobArchitectureJson(
                        access,
                        `/dashboard/job-architecture/mappings/${encodeURIComponent(mappingId)}/resolve`,
                        { mapped_entity_type: mappedType, mapped_entity_id: mappedId, reason },
                      ).then(() => load())
                    }
                  >
                    {t.resolve}
                  </Button>
                </div>
              ) : null}
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.mappings}</h3>
                {mappings.length ? (
                  <ul className="space-y-1 text-sm">
                    {mappings.map((row) => (
                      <li key={String(row.mapping_id)}>
                        {String(row.raw_field)} = {String(row.raw_value)} · {String(row.match_kind)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">{t.emptyMappings}</p>
                )}
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.assignments}</h3>
                <ul className="space-y-1 text-sm">
                  {assignments.map((row) => (
                    <li key={String(row.assignment_id)}>
                      {String(row.employee_key)} · {String(row.profile_id || '')} · {String(row.effective_start)}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">{t.refs}</h3>
                <ul className="space-y-1 text-sm">
                  {refs.map((row) => (
                    <li key={String(row.ref_id)}>
                      {String(row.domain)} · {String(row.external_key)}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
