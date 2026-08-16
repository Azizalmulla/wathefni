import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'

export type ClassificationAuthorityFilter =
  | 'confirmed_or_high_ai'
  | 'confirmed_only'
  | 'ai_suggested'
  | 'either'

export type TaxonomyNodeOption = {
  node_id: string
  node_type?: string
  dimension?: string
  label_en?: string
  label_ar?: string
  parent_ids?: string[]
  status?: string
  scope?: 'global' | 'tenant' | string
  broad?: boolean
}

export type TaxonomyDimension = {
  dimension: string
  node_type: string
  nodes: TaxonomyNodeOption[]
}

export type ClassificationFiltersState = {
  dimensionNodes: Record<string, string[]>
  confidence?: string
  authority: ClassificationAuthorityFilter
  includeMediumAi: boolean
}

export const DEFAULT_CLASSIFICATION_FILTERS: ClassificationFiltersState = {
  dimensionNodes: {},
  authority: 'confirmed_or_high_ai',
  includeMediumAi: false,
}

export const CLASSIFICATION_DIMENSIONS = [
  'career_area',
  'likely_role',
  'skill',
  'industry',
  'seniority',
  'experience_band',
] as const

const DIMENSION_LABELS: Record<string, { en: string; ar: string }> = {
  career_area: { en: 'Career area', ar: 'مجال مهني' },
  likely_role: { en: 'Likely role', ar: 'دور محتمل' },
  skill: { en: 'Skill', ar: 'مهارة' },
  industry: { en: 'Industry', ar: 'قطاع' },
  seniority: { en: 'Seniority', ar: 'أقدمية' },
  experience_band: { en: 'Experience band', ar: 'نطاق خبرة' },
}

export function classificationChipLabel(chip?: string | null) {
  return chip?.trim() || null
}

export function ClassificationCompactChip({ chip, confirmed }: { chip?: string | null; confirmed?: boolean }) {
  const label = classificationChipLabel(chip)
  if (!label) return null
  return (
    <div className="mt-1" data-testid="classification-compact-chip">
      <Badge tone={confirmed ? 'success' : 'muted'}>
        {confirmed ? 'Confirmed' : 'Advisory'}: {label}
      </Badge>
    </div>
  )
}

export function classificationFiltersToQuery(value: ClassificationFiltersState): Record<string, string> {
  const out: Record<string, string> = {}
  for (const dimension of CLASSIFICATION_DIMENSIONS) {
    const ids = value.dimensionNodes[dimension] || []
    if (ids.length) out[`classification_${dimension}`] = ids.join(',')
  }
  if (value.authority && value.authority !== 'confirmed_or_high_ai') {
    out.classification_authority = value.authority
  } else if (value.authority === 'confirmed_or_high_ai' && (value.includeMediumAi || value.confidence || Object.keys(value.dimensionNodes).length)) {
    out.classification_authority = value.authority
  }
  if (value.confidence) out.classification_confidence = value.confidence
  if (value.includeMediumAi) out.classification_include_medium_ai = 'true'
  return out
}

export function classificationFiltersForSavedView(value: ClassificationFiltersState) {
  return {
    schema: 'classification-filters-v1',
    dimension_nodes: value.dimensionNodes,
    authority: value.authority,
    confidence: value.confidence || null,
    include_medium_ai: value.includeMediumAi,
    current_only: true,
  }
}

export function classificationFiltersFromSavedView(raw: unknown): ClassificationFiltersState {
  const body = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const nested = (body.classification && typeof body.classification === 'object'
    ? body.classification
    : body) as Record<string, unknown>
  const dimensionNodes: Record<string, string[]> = {}
  const source =
    nested.dimension_nodes && typeof nested.dimension_nodes === 'object'
      ? (nested.dimension_nodes as Record<string, unknown>)
      : nested
  for (const dimension of CLASSIFICATION_DIMENSIONS) {
    const value = source[dimension]
    if (Array.isArray(value)) {
      dimensionNodes[dimension] = value.map(String).filter(Boolean)
    } else if (typeof value === 'string' && value.trim()) {
      dimensionNodes[dimension] = value.split(',').map((part) => part.trim()).filter(Boolean)
    }
  }
  // Legacy single-id fields
  const legacy: Record<string, string | undefined> = {
    career_area: typeof nested.careerArea === 'string' ? nested.careerArea : undefined,
    likely_role: typeof nested.likelyRole === 'string' ? nested.likelyRole : undefined,
  }
  for (const [dimension, nodeId] of Object.entries(legacy)) {
    if (nodeId) dimensionNodes[dimension] = [nodeId]
  }
  return {
    dimensionNodes,
    authority: (String(nested.authority || 'confirmed_or_high_ai') as ClassificationAuthorityFilter),
    confidence: typeof nested.confidence === 'string' ? nested.confidence : undefined,
    includeMediumAi: Boolean(nested.include_medium_ai ?? nested.includeMediumAi),
  }
}

function nodeLabel(node: TaxonomyNodeOption, locale: 'en' | 'ar') {
  const label = locale === 'ar' ? node.label_ar || node.label_en : node.label_en || node.label_ar
  return label || node.node_id
}

function DimensionSelector({
  dimension,
  locale,
  nodes,
  selected,
  onChange,
}: {
  dimension: string
  locale: 'en' | 'ar'
  nodes: TaxonomyNodeOption[]
  selected: string[]
  onChange: (nodeIds: string[]) => void
}) {
  const [query, setQuery] = useState('')
  const labels = DIMENSION_LABELS[dimension] || { en: dimension, ar: dimension }
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return nodes.slice(0, 40)
    return nodes
      .filter((node) => {
        const blob = `${node.label_en || ''} ${node.label_ar || ''} ${node.node_id}`.toLowerCase()
        return blob.includes(q)
      })
      .slice(0, 40)
  }, [nodes, query])

  return (
    <div className="min-w-[12rem] flex-1" data-testid={`classification-filter-${dimension}`}>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-subtle">
        {locale === 'ar' ? labels.ar : labels.en}
      </div>
      <Input
        className="mb-2 h-9"
        onChange={(event) => setQuery(event.target.value)}
        placeholder={locale === 'ar' ? 'بحث…' : 'Search…'}
        value={query}
      />
      <select
        className="h-10 w-full rounded-full border border-line/60 bg-white/80 px-3 text-sm"
        multiple={false}
        onChange={(event) => {
          const nodeId = event.target.value
          if (!nodeId) return
          if (selected.includes(nodeId)) return
          onChange([...selected, nodeId])
          event.target.value = ''
        }}
        value=""
      >
        <option value="">{locale === 'ar' ? 'إضافة…' : 'Add…'}</option>
        {filtered.map((node) => (
          <option key={node.node_id} value={node.node_id}>
            {nodeLabel(node, locale)}
          </option>
        ))}
      </select>
    </div>
  )
}

export function ClassificationFilterBar({
  value,
  onChange,
  enabled,
  dimensions = [],
  locale = 'en',
  deprecatedNodes = [],
}: {
  value: ClassificationFiltersState
  onChange: (next: ClassificationFiltersState) => void
  enabled: boolean
  dimensions?: TaxonomyDimension[]
  locale?: 'en' | 'ar'
  deprecatedNodes?: Array<{ node_id: string; message?: string }>
}) {
  if (!enabled) return null

  const selectedChips = Object.entries(value.dimensionNodes).flatMap(([dimension, ids]) =>
    ids.map((nodeId) => ({ dimension, nodeId })),
  )

  const dimensionMap = Object.fromEntries(dimensions.map((item) => [item.dimension, item.nodes]))

  return (
    <div className="mt-3 space-y-3 rounded-[1.25rem] border border-line/50 bg-white/40 p-3" data-testid="classification-filter-bar">
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">
        {locale === 'ar' ? 'مرشحات الخبرة' : 'Expertise filters'}
      </div>
      <div className="flex flex-wrap gap-3">
        {CLASSIFICATION_DIMENSIONS.map((dimension) => (
          <DimensionSelector
            dimension={dimension}
            key={dimension}
            locale={locale}
            nodes={dimensionMap[dimension] || []}
            onChange={(nodeIds) =>
              onChange({
                ...value,
                dimensionNodes: { ...value.dimensionNodes, [dimension]: nodeIds },
              })
            }
            selected={value.dimensionNodes[dimension] || []}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <select
          className="h-10 rounded-full border border-line/60 bg-white/80 px-3 text-sm"
          data-testid="classification-authority-filter"
          onChange={(event) => onChange({ ...value, authority: event.target.value as ClassificationAuthorityFilter })}
          value={value.authority}
        >
          <option value="confirmed_or_high_ai">{locale === 'ar' ? 'مؤكد أو اقتراح قوي' : 'Confirmed or strong suggestion'}</option>
          <option value="confirmed_only">{locale === 'ar' ? 'مؤكد من الموارد البشرية فقط' : 'HR confirmed only'}</option>
          <option value="ai_suggested">{locale === 'ar' ? 'اقتراح فقط' : 'Suggested only'}</option>
          <option value="either">{locale === 'ar' ? 'أي تصنيف متاح' : 'Any available classification'}</option>
        </select>
        <select
          className="h-10 rounded-full border border-line/60 bg-white/80 px-3 text-sm"
          data-testid="classification-confidence-filter"
          onChange={(event) => onChange({ ...value, confidence: event.target.value || undefined })}
          value={value.confidence || ''}
        >
          <option value="">{locale === 'ar' ? 'أي حالة' : 'Any state'}</option>
          <option value="High">{locale === 'ar' ? 'واضح' : 'Clear'}</option>
          <option value="Medium">{locale === 'ar' ? 'متوسط' : 'Medium'}</option>
          <option value="Needs review">{locale === 'ar' ? 'يحتاج مراجعة' : 'Needs review'}</option>
          <option value="Unclassified">{locale === 'ar' ? 'غير مصنف' : 'Not identified'}</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-subtle">
          <input
            checked={value.includeMediumAi}
            onChange={(event) => onChange({ ...value, includeMediumAi: event.target.checked })}
            type="checkbox"
          />
          {locale === 'ar' ? 'تضمين الاقتراحات المتوسطة' : 'Include medium suggestions'}
        </label>
        <Button onClick={() => onChange(DEFAULT_CLASSIFICATION_FILTERS)} size="sm" type="button" variant="secondary">
          {locale === 'ar' ? 'مسح خبرة' : 'Clear expertise filters'}
        </Button>
      </div>
      {selectedChips.length ? (
        <div className="flex flex-wrap gap-2" data-testid="classification-selected-chips">
          {selectedChips.map((item) => {
            const node = (dimensionMap[item.dimension] || []).find((entry) => entry.node_id === item.nodeId)
            return (
              <button
                className="rounded-full border border-line/60 bg-white/80 px-3 py-1 text-xs"
                key={`${item.dimension}:${item.nodeId}`}
                onClick={() => {
                  const next = (value.dimensionNodes[item.dimension] || []).filter((id) => id !== item.nodeId)
                  const dimensionNodes = { ...value.dimensionNodes }
                  if (next.length) dimensionNodes[item.dimension] = next
                  else delete dimensionNodes[item.dimension]
                  onChange({ ...value, dimensionNodes })
                }}
                type="button"
              >
                {(locale === 'ar' ? node?.label_ar : node?.label_en) || item.nodeId} ×
              </button>
            )
          })}
        </div>
      ) : null}
      {deprecatedNodes.length ? (
        <p className="text-xs text-amber-800" data-testid="classification-deprecated-nodes">
          {locale === 'ar'
            ? 'بعض التصنيفات المحفوظة لم تعد متاحة. أزلها أو اختر بديلاً.'
            : 'Some saved expertise filters are no longer available. Clear them or choose a replacement.'}
        </p>
      ) : null}
    </div>
  )
}

export function useTaxonomyDimensionsLoader(
  enabled: boolean,
  loader: () => Promise<{ dimensions?: TaxonomyDimension[] }>,
) {
  const [dimensions, setDimensions] = useState<TaxonomyDimension[]>([])
  useEffect(() => {
    if (!enabled) {
      setDimensions([])
      return
    }
    let cancelled = false
    void loader()
      .then((payload) => {
        if (!cancelled) setDimensions(payload.dimensions || [])
      })
      .catch(() => {
        if (!cancelled) setDimensions([])
      })
    return () => {
      cancelled = true
    }
  }, [enabled, loader])
  return dimensions
}
