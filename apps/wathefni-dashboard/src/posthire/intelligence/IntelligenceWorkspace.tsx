import {
  BarChart3,
  Download,
  Inbox,
  Loader2,
  RefreshCw,
  Save,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react'
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { DashboardApiError } from '@/lib/api'
import { useUrlBackedParam } from '@/lib/hrWebUrlTab'
import {
  createIntelligenceExport,
  createIntelligenceSavedView,
  downloadIntelligenceExport,
  drillIntelligenceMetric,
  evaluateIntelligenceMetric,
  getIntelligenceBootstrap,
  getIntelligenceOverview,
  getIntelligenceTrend,
  segmentIntelligenceMetric,
  type DrillResponse,
  type IntelligenceBootstrap,
  type IntelligenceDefinition,
  type IntelligenceMetric,
  type IntelligenceOverview,
  type TrendResponse,
} from '@/lib/intelligenceApi'
import { ResourceState } from '@/pages/shared/dataState'
import { cn } from '@/lib/utils'
import { useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type IntelligenceWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
  onNavigate?: (page: string, opts?: { employee?: string }) => void
  fallback?: ReactNode
}

type DetailState = {
  metric: IntelligenceMetric | null
  trend: TrendResponse | null
  drill: DrillResponse | null
}

const FAMILY_COPY: Record<string, { en: string; ar: string }> = {
  workforce: { en: 'Workforce', ar: 'القوى العاملة' },
  hiring: { en: 'Hiring', ar: 'التوظيف' },
  time_leave: { en: 'Time & leave', ar: 'الوقت والإجازات' },
  pay: { en: 'Pay', ar: 'الأجور' },
  performance: { en: 'Performance', ar: 'الأداء' },
  talent: { en: 'Talent', ar: 'المواهب' },
  hr_ops: { en: 'HR operations', ar: 'عمليات الموارد البشرية' },
}

function copy(isAr: boolean) {
  return isAr
    ? {
        title: 'ذكاء الموارد',
        subtitle: 'مؤشرات محكومة ومنشورة لشركتك — دون صيغ مخفية في الواجهة.',
        attention: 'الاهتمام التشغيلي منفصل عن الذكاء',
        attentionAction: 'فتح صندوق الوارد',
        refresh: 'تحديث',
        loading: 'جارٍ تحميل الذكاء',
        noPublished: 'لا توجد مؤشرات منشورة',
        noPublishedHint: 'هذه حالة مقصودة. تظهر المؤشرات هنا فقط بعد نشر تعريف السجل لشركتك.',
        notEnabled: 'ذكاء الموارد غير مفعّل',
        notEnabledHint: 'تظهر تجربة التحليلات الحالية إلى أن يتم تفعيل الأسطح المحكومة.',
        loadFailed: 'تعذر تحميل ذكاء الموارد',
        about: 'عن المؤشر',
        trend: 'الاتجاه الشهري',
        segment: 'التقسيم',
        segmentBy: 'التقسيم حسب',
        segmentValue: 'قيمة القسم',
        apply: 'تطبيق',
        drill: 'السجلات المشمولة',
        reauthorized: 'أُعيد التحقق من النطاق والصلاحيات لهذا التفصيل.',
        noRows: 'لا توجد سجلات قابلة للعرض',
        previous: 'السابق',
        next: 'التالي',
        export: 'تصدير CSV',
        save: 'حفظ العرض',
        saveName: 'اسم العرض',
        live: 'مباشر',
        pinned: 'لقطة مثبتة',
        close: 'إغلاق',
        version: 'الإصدار',
        state: 'الحالة',
        unavailable: 'لا توجد قيمة متاحة',
        all: 'الكل',
      }
    : {
        title: 'Intelligence',
        subtitle: 'Governed, company-published HR measures — with no hidden formulas in the interface.',
        attention: 'Ops Attention is separate from Intelligence',
        attentionAction: 'Open inbox',
        refresh: 'Refresh',
        loading: 'Loading intelligence',
        noPublished: 'No published KPIs yet',
        noPublishedHint: 'This is intentional. Metrics appear only after a Registry definition is published for your company.',
        notEnabled: 'Intelligence is not enabled',
        notEnabledHint: 'Your current analytics experience remains available until governed surfaces are enabled.',
        loadFailed: 'Could not load HR Intelligence',
        about: 'About this metric',
        trend: 'Monthly trend',
        segment: 'Segment',
        segmentBy: 'Segment by',
        segmentValue: 'Department value',
        apply: 'Apply',
        drill: 'Included records',
        reauthorized: 'Scope and permissions were reauthorized for this drill.',
        noRows: 'No records available to show',
        previous: 'Previous',
        next: 'Next',
        export: 'Export CSV',
        save: 'Save view',
        saveName: 'View name',
        live: 'Live',
        pinned: 'Pinned snapshot',
        close: 'Close',
        version: 'Version',
        state: 'State',
        unavailable: 'No value available',
        all: 'All',
      }
}

function statusTone(status: string): BadgeTone {
  if (status === 'ok') return 'success'
  if (status === 'suppressed' || status === 'insufficient_data') return 'warning'
  if (status === 'blocked' || status === 'unavailable') return 'danger'
  return 'muted'
}

function metricValue(metric: IntelligenceMetric, locale: string) {
  if (metric.status !== 'ok' || metric.value === null || metric.value === undefined) return null
  if (typeof metric.value === 'number') {
    return new Intl.NumberFormat(locale === 'ar' ? 'ar-KW' : 'en-KW', {
      maximumFractionDigits: 2,
    }).format(metric.value)
  }
  return String(metric.value)
}

function DetailPanel({
  selected,
  detail,
  busy,
  isAr,
  drillOffset,
  saveName,
  saveMode,
  segmentDimension,
  segmentValue,
  segmentResult,
  exporting,
  saving,
  onClose,
  onDrillPage,
  onExport,
  onSave,
  onSaveName,
  onSaveMode,
  onSegmentDimension,
  onSegmentValue,
  onSegment,
}: {
  selected: IntelligenceDefinition
  detail: DetailState
  busy: boolean
  isAr: boolean
  drillOffset: number
  saveName: string
  saveMode: 'live' | 'pinned'
  segmentDimension: string
  segmentValue: string
  segmentResult: IntelligenceMetric | null
  exporting: boolean
  saving: boolean
  onClose: () => void
  onDrillPage: (offset: number) => void
  onExport: () => void
  onSave: () => void
  onSaveName: (value: string) => void
  onSaveMode: (value: 'live' | 'pinned') => void
  onSegmentDimension: (value: string) => void
  onSegmentValue: (value: string) => void
  onSegment: () => void
}) {
  const c = copy(isAr)
  const values = (detail.trend?.series || [])
    .map((point) => point.status === 'ok' && typeof point.value === 'number' ? point.value : null)
    .filter((value): value is number => value !== null)
  const maxValue = Math.max(1, ...values)
  const dimensions = selected.supported_dimensions || []
  const metric = detail.metric
  const drill = detail.drill

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-semantic-ink/20 backdrop-blur-[2px]" role="dialog" aria-modal="true">
      <div className="h-full w-full max-w-2xl overflow-y-auto border-s border-semantic-line bg-semantic-surface p-5 shadow-2xl" dir={isAr ? 'rtl' : 'ltr'}>
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-subtle">
              {FAMILY_COPY[selected.family]?.[isAr ? 'ar' : 'en'] || selected.family}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-text">
              {isAr ? selected.name_ar : selected.name_en}
            </h2>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={c.close}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {busy && !metric ? (
          <div className="flex items-center justify-center gap-2 py-20 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin" />
            {c.loading}
          </div>
        ) : null}

        {metric ? (
          <div className="space-y-5">
            <Card tone="quiet">
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle>{c.about}</CardTitle>
                  <Badge tone={statusTone(metric.status)}>{metric.status_label}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {metricValue(metric, isAr ? 'ar' : 'en') !== null ? (
                  <div className="text-4xl font-semibold tracking-tight text-text">
                    {metricValue(metric, isAr ? 'ar' : 'en')}
                    <span className="ms-2 text-sm font-medium text-subtle">{metric.unit}</span>
                  </div>
                ) : (
                  <p className="text-sm text-subtle">{c.unavailable}</p>
                )}
                <p className="text-sm leading-6 text-subtle">
                  {isAr ? selected.description_ar : selected.description_en}
                </p>
                <div className="flex flex-wrap gap-2 text-xs text-subtle">
                  <Badge tone="muted">{c.version} {selected.effective_version}</Badge>
                  <Badge tone="muted">{selected.time_semantics.replaceAll('_', ' ')}</Badge>
                  <Badge tone="muted">{selected.unit}</Badge>
                </div>
              </CardContent>
            </Card>

            <Card tone="quiet">
              <CardHeader>
                <CardTitle>{c.trend}</CardTitle>
              </CardHeader>
              <CardContent>
                {detail.trend?.series?.length ? (
                  <div className="flex h-36 items-end gap-1.5" aria-label={c.trend}>
                    {detail.trend.series.map((point) => {
                      const value = point.status === 'ok' && typeof point.value === 'number' ? point.value : null
                      const width = value === null ? 4 : Math.max(6, (value / maxValue) * 100)
                      return (
                        <div key={point.bucket} className="group flex min-w-0 flex-1 flex-col items-center justify-end gap-1">
                          <span className="invisible text-[10px] text-subtle group-hover:visible">
                            {value ?? point.status_label}
                          </span>
                          <div
                            className={cn(
                              'w-full rounded-t-md',
                              value === null ? 'bg-semantic-line/70' : 'bg-semantic-accent/75',
                            )}
                            style={{ height: `${width}%` }}
                          />
                          <span className="max-w-full truncate text-[9px] text-subtle">
                            {String(point.time_window.period_end || '').slice(5, 10)}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-subtle">{c.noRows}</p>
                )}
              </CardContent>
            </Card>

            {dimensions.length ? (
              <Card tone="quiet">
                <CardHeader>
                  <CardTitle>{c.segment}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="space-y-1 text-xs font-medium text-subtle">
                      <span>{c.segmentBy}</span>
                      <Select className="w-full" value={segmentDimension} onChange={(event) => onSegmentDimension(event.target.value)}>
                        {dimensions.map((dimension) => (
                          <option key={dimension} value={dimension}>{dimension.replaceAll('_', ' ')}</option>
                        ))}
                      </Select>
                    </label>
                    <label className="space-y-1 text-xs font-medium text-subtle">
                      <span>{segmentDimension === 'department' ? c.segmentValue : c.segment}</span>
                      <Input className="w-full" value={segmentValue} onChange={(event) => onSegmentValue(event.target.value)} />
                    </label>
                  </div>
                  <Button size="sm" variant="secondary" disabled={!segmentValue.trim()} onClick={onSegment}>
                    {c.apply}
                  </Button>
                  {segmentResult ? (
                    <div className="flex items-center justify-between rounded-2xl border border-line/60 bg-white/60 px-4 py-3">
                      <span className="text-sm text-subtle">{segmentValue}</span>
                      {metricValue(segmentResult, isAr ? 'ar' : 'en') !== null ? (
                        <strong className="text-lg text-text">{metricValue(segmentResult, isAr ? 'ar' : 'en')}</strong>
                      ) : (
                        <Badge tone={statusTone(segmentResult.status)}>{segmentResult.status_label}</Badge>
                      )}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            <Card tone="quiet">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle>{c.drill}</CardTitle>
                  <Badge tone="muted">{drill?.total ?? '—'}</Badge>
                </div>
                <CardDescription>{c.reauthorized}</CardDescription>
              </CardHeader>
              <CardContent>
                {drill?.rows?.length ? (
                  <div className="overflow-hidden rounded-2xl border border-line/60">
                    {drill.rows.map((row) => (
                      <div key={row.id} className="flex items-center gap-2 border-b border-line/40 px-4 py-3 text-sm last:border-b-0">
                        <Users className="h-4 w-4 text-subtle" />
                        <span className="font-mono text-xs text-text">{row.label}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-subtle">{c.noRows}</p>
                )}
                <div className="mt-3 flex justify-between">
                  <Button variant="ghost" size="sm" disabled={drillOffset === 0} onClick={() => onDrillPage(Math.max(0, drillOffset - 25))}>
                    {c.previous}
                  </Button>
                  <Button variant="ghost" size="sm" disabled={!drill?.total || drillOffset + 25 >= drill.total} onClick={() => onDrillPage(drillOffset + 25)}>
                    {c.next}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card tone="quiet">
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Button pending={exporting} onClick={onExport}>
                    <Download className="h-4 w-4" />
                    {c.export}
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
                  <Input value={saveName} placeholder={c.saveName} onChange={(event) => onSaveName(event.target.value)} />
                  <Select value={saveMode} onChange={(event) => onSaveMode(event.target.value as 'live' | 'pinned')}>
                    <option value="live">{c.live}</option>
                    <option value="pinned">{c.pinned}</option>
                  </Select>
                  <Button variant="secondary" pending={saving} disabled={!saveName.trim()} onClick={onSave}>
                    <Save className="h-4 w-4" />
                    {c.save}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function IntelligenceWorkspace({
  access,
  role,
  onNotice,
  onAccessIssue,
  onNavigate,
  fallback,
}: IntelligenceWorkspaceProps) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const c = copy(isAr)
  const [bootstrap, setBootstrap] = useState<IntelligenceBootstrap | null>(null)
  const bootstrapRef = useRef(bootstrap)
  bootstrapRef.current = bootstrap
  const [overview, setOverview] = useState<IntelligenceOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [gateOff, setGateOff] = useState(false)
  const [error, setError] = useState(false)
  const [metricKey, setMetricKey] = useUrlBackedParam('analytics', 'q', '', 'replace')
  const [selected, setSelected] = useState<IntelligenceDefinition | null>(null)
  const [detail, setDetail] = useState<DetailState>({ metric: null, trend: null, drill: null })
  const [detailBusy, setDetailBusy] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const [drillOffset, setDrillOffset] = useState(0)
  const [segmentDimension, setSegmentDimension] = useState('department')
  const [segmentValue, setSegmentValue] = useState('')
  const [segmentResult, setSegmentResult] = useState<IntelligenceMetric | null>(null)
  const [saveName, setSaveName] = useState('')
  const [saveMode, setSaveMode] = useState<'live' | 'pinned'>('live')
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)

  const reportError = useCallback((caught: unknown, message: string) => {
    const issue = accessIssueFromError(caught)
    if (issue) onAccessIssue?.(issue)
    onNotice(message, 'error')
  }, [onAccessIssue, onNotice])

  const load = useCallback(async (soft = false) => {
    if (soft || bootstrapRef.current) setRefreshing(true)
    else setLoading(true)
    setError(false)
    try {
      const boot = await getIntelligenceBootstrap(access)
      setBootstrap(boot)
      setGateOff(!boot.c6_enabled)
      if (boot.c6_enabled) {
        const nextOverview = await getIntelligenceOverview(access, { lang: locale })
        setOverview(nextOverview)
      }
    } catch (caught) {
      const code = caught instanceof DashboardApiError ? caught.code : ''
      if (
        code.includes('intelligence_surfaces') ||
        code === 'c1_registry_required' ||
        code === 'c1_company_entitlement_required'
      ) {
        setGateOff(true)
      } else if (!bootstrapRef.current) {
        setError(true)
        reportError(caught, c.loadFailed)
      } else {
        reportError(caught, c.loadFailed)
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [access, c.loadFailed, locale, reportError])

  useEffect(() => {
    // Initial remote bootstrap is the external synchronization owned by this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  const definitions = useMemo(() => {
    const map = new Map<string, IntelligenceDefinition>()
    for (const definition of bootstrap?.published_kpis || []) map.set(definition.semantic_key, definition)
    return map
  }, [bootstrap])

  const loadDetail = useCallback(async (definition: IntelligenceDefinition, offset = 0) => {
    setDetailBusy(true)
    setDetailError(false)
    try {
      const query = { semantic_key: definition.semantic_key, lang: locale, actor_role: role, time_window: {} }
      const [metric, trend, drill] = await Promise.all([
        evaluateIntelligenceMetric(access, query),
        getIntelligenceTrend(access, { ...query, bucket: 'monthly' }),
        drillIntelligenceMetric(access, { ...query, offset, limit: 25 }),
      ])
      setDetail({ metric, trend, drill })
      setDrillOffset(offset)
    } catch (caught) {
      setDetailError(true)
      reportError(caught, c.loadFailed)
    } finally {
      setDetailBusy(false)
    }
  }, [access, c.loadFailed, locale, reportError, role])

  useEffect(() => {
    if (!metricKey || selected?.semantic_key === metricKey) return
    const definition = definitions.get(metricKey)
    if (!definition) return
    setSelected(definition)
    setSaveName(isAr ? definition.name_ar : definition.name_en)
    setSegmentDimension(
      definition.supported_dimensions.includes('department')
        ? 'department'
        : definition.supported_dimensions[0] || '',
    )
    void loadDetail(definition)
  }, [metricKey, definitions, selected, isAr, loadDetail])

  const openMetric = (metric: IntelligenceMetric) => {
    const definition = metric.about_metric || definitions.get(metric.semantic_key)
    if (!definition) return
    setMetricKey(definition.semantic_key, 'push')
    setSelected(definition)
    setDetail({ metric, trend: null, drill: null })
    setSegmentDimension(definition.supported_dimensions.includes('department') ? 'department' : definition.supported_dimensions[0] || '')
    setSegmentValue('')
    setSegmentResult(null)
    setSaveName(isAr ? definition.name_ar : definition.name_en)
    void loadDetail(definition)
  }

  const runSegment = async () => {
    if (!selected || !segmentDimension || !segmentValue.trim()) return
    try {
      const response = await segmentIntelligenceMetric(access, {
        semantic_key: selected.semantic_key,
        dimension: segmentDimension,
        dimension_value: segmentValue.trim(),
        lang: locale,
      })
      setSegmentResult(response.metric)
    } catch (caught) {
      reportError(caught, c.loadFailed)
    }
  }

  const runExport = async () => {
    if (!selected) return
    setExporting(true)
    try {
      const response = await createIntelligenceExport(access, {
        semantic_key: selected.semantic_key,
        lang: locale,
      })
      await downloadIntelligenceExport(access, response.export.export_id)
      onNotice(isAr ? 'تم إنشاء التصدير' : 'Export generated', 'success')
    } catch (caught) {
      reportError(caught, isAr ? 'تعذر إنشاء التصدير' : 'Could not create export')
    } finally {
      setExporting(false)
    }
  }

  const saveView = async () => {
    if (!selected || !saveName.trim()) return
    setSaving(true)
    try {
      await createIntelligenceSavedView(access, {
        name_en: saveName.trim(),
        name_ar: isAr ? saveName.trim() : undefined,
        mode: saveMode,
        query_config: { semantic_key: selected.semantic_key, time_window: {}, filters: {} },
      })
      onNotice(isAr ? 'تم حفظ العرض' : 'View saved', 'success')
    } catch (caught) {
      reportError(caught, isAr ? 'تعذر حفظ العرض' : 'Could not save view')
    } finally {
      setSaving(false)
    }
  }

  if (gateOff) {
    if (fallback) return <>{fallback}</>
    return <WorkflowEmpty title={c.notEnabled} hint={c.notEnabledHint} icon={<ShieldCheck className="h-7 w-7" />} />
  }

  if (loading && !bootstrap) {
    return (
      <div className="flex min-h-64 items-center justify-center gap-2 text-sm text-subtle">
        <Loader2 className="h-4 w-4 animate-spin" />
        {c.loading}
      </div>
    )
  }

  if (error) {
    return (
      <ResourceState
        kind="error"
        locale={isAr ? 'ar' : 'en'}
        title={c.loadFailed}
        onRetry={() => void load()}
        retrying={refreshing}
        testId="intelligence-workspace-state"
      />
    )
  }

  return (
    <div className="space-y-6" dir={isAr ? 'rtl' : 'ltr'}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="max-w-2xl text-sm leading-6 text-subtle">{c.subtitle}</p>
          <button
            type="button"
            className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-subtle underline-offset-4 transition-colors duration-150 hover:text-text hover:underline"
            onClick={() => onNavigate?.('inbox')}
          >
            <Inbox className="h-3.5 w-3.5" />
            {c.attention} · {c.attentionAction}
          </button>
        </div>
        <Button variant="ghost" size="sm" pending={refreshing} onClick={() => void load(true)} aria-label={c.refresh}>
          <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
        </Button>
      </div>

      {!bootstrap?.published_kpis?.length ? (
        <WorkflowEmpty
          title={c.noPublished}
          hint={c.noPublishedHint}
          icon={<BarChart3 className="h-7 w-7" />}
        />
      ) : null}

      {(overview?.families || []).map((family) => (
        <section key={family.family} className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-[0.13em] text-subtle">
            {FAMILY_COPY[family.family]?.[isAr ? 'ar' : 'en'] || family.family}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {family.metrics.map((metric) => {
              const value = metricValue(metric, locale)
              const definition = metric.about_metric || definitions.get(metric.semantic_key)
              return (
                <Card
                  key={metric.semantic_key}
                  tone="quiet"
                  className="cursor-pointer transition-colors duration-150 hover:border-semantic-accent/35"
                  role="button"
                  tabIndex={0}
                  onClick={() => openMetric(metric)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') openMetric(metric)
                  }}
                >
                  <CardContent className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm font-medium leading-5 text-text">
                        {isAr ? definition?.name_ar : definition?.name_en}
                      </p>
                      {metric.status !== 'ok' ? <Badge tone={statusTone(metric.status)}>{metric.status_label}</Badge> : null}
                    </div>
                    {value !== null ? (
                      <div className="text-3xl font-semibold tracking-tight text-text">
                        {value}
                        <span className="ms-2 text-xs font-medium text-subtle">{metric.unit}</span>
                      </div>
                    ) : (
                      <div className="flex min-h-9 items-center">
                        <Badge tone={statusTone(metric.status)}>{metric.status_label}</Badge>
                      </div>
                    )}
                    <p className="line-clamp-2 text-xs leading-5 text-subtle">
                      {isAr ? definition?.description_ar : definition?.description_en}
                    </p>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </section>
      ))}

      {selected && detailError ? (
        <ResourceState
          kind="error"
          locale={isAr ? 'ar' : 'en'}
          title={c.loadFailed}
          onRetry={() => void loadDetail(selected)}
          retrying={detailBusy}
          testId="intelligence-detail-state"
        />
      ) : selected ? (
        <DetailPanel
          selected={selected}
          detail={detail}
          busy={detailBusy}
          isAr={isAr}
          drillOffset={drillOffset}
          saveName={saveName}
          saveMode={saveMode}
          segmentDimension={segmentDimension}
          segmentValue={segmentValue}
          segmentResult={segmentResult}
          exporting={exporting}
          saving={saving}
          onClose={() => {
            setSelected(null)
            setMetricKey('')
          }}
          onDrillPage={(offset) => void loadDetail(selected, offset)}
          onExport={() => void runExport()}
          onSave={() => void saveView()}
          onSaveName={setSaveName}
          onSaveMode={setSaveMode}
          onSegmentDimension={setSegmentDimension}
          onSegmentValue={setSegmentValue}
          onSegment={() => void runSegment()}
        />
      ) : null}
    </div>
  )
}

