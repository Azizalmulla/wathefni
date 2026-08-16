import { DashboardApiError } from '@/lib/api'
import type { DashboardAccess } from '@/types'

const BASE = '/dashboard/posthire/intelligence'

export type IntelligenceStatus =
  | 'ok'
  | 'unavailable'
  | 'insufficient_data'
  | 'not_applicable'
  | 'suppressed'
  | 'blocked'
  | 'stale'
  | 'refreshing'

export type IntelligenceDefinition = {
  semantic_key: string
  definition_id: string
  effective_version: number
  family: string
  name_en: string
  name_ar: string
  description_en?: string
  description_ar?: string
  business_meaning?: string
  unit: string
  time_semantics: string
  supported_dimensions: string[]
  permission_class: string
}

export type IntelligenceMetric = {
  ok: boolean
  semantic_key: string
  status: IntelligenceStatus
  status_label: string
  value: number | string | null
  unit?: string | null
  population_count?: number | null
  effective_version?: number
  family?: string
  about_metric?: IntelligenceDefinition
  explain?: Record<string, unknown>
}

export type IntelligenceBootstrap = {
  ok: boolean
  c6_enabled: boolean
  honesty: Record<string, unknown>
  overview: { families: []; evaluated: false }
  published_kpis: IntelligenceDefinition[]
  settings?: {
    manager_analytics_enabled?: boolean
    export_person_level_requires_permission?: boolean
  }
}

export type IntelligenceOverview = {
  ok: boolean
  families: Array<{ family: string; metrics: IntelligenceMetric[] }>
  omitted_count: number
  honesty: Record<string, unknown>
}

export type IntelligenceQuery = {
  semantic_key: string
  time_window?: Record<string, unknown>
  filters?: Record<string, unknown>
  lang?: string
  actor_role?: string | null
}

export type TrendResponse = {
  ok: boolean
  semantic_key: string
  bucket: string
  series: Array<{
    bucket: string
    time_window: Record<string, unknown>
    status: IntelligenceStatus
    status_label: string
    value: number | null
    unit?: string | null
  }>
  about_metric: IntelligenceDefinition
}

export type DrillResponse = {
  ok: boolean
  status: IntelligenceStatus
  rows: Array<{ id: string; label: string }>
  total: number | null
  offset?: number
  limit?: number
  reauthorized: boolean
  explain?: string
}

export type SavedView = {
  view_id: string
  name_en: string
  name_ar?: string | null
  mode: 'live' | 'pinned'
  query_config: Record<string, unknown>
  pinned_definition_versions: Record<string, number>
  layout: Record<string, unknown>
  created_at: string
  updated_at: string
  opened_by_re_evaluation?: boolean
  current_evaluation?: IntelligenceMetric
}

function headers(access: DashboardAccess, input?: HeadersInit) {
  const result = new Headers(input)
  const token = access.token.trim()
  const company = access.companyCode.trim().toUpperCase()
  if (!token) {
    throw new DashboardApiError(401, { error: 'dashboard_auth_failed', message: 'Dashboard token is required.' }, 'Dashboard token is required.')
  }
  if (!company) {
    throw new DashboardApiError(400, { error: 'dashboard_company_required', message: 'Company code is required.' }, 'Company code is required.')
  }
  result.set('Authorization', `Bearer ${token}`)
  result.set('X-Company-Code', company)
  if (access.hrPhone.trim()) result.set('X-HR-Phone', access.hrPhone.trim())
  return result
}

async function request<T>(access: DashboardAccess, path: string, init: RequestInit = {}): Promise<T> {
  const requestHeaders = headers(access, init.headers)
  if (init.body && !requestHeaders.has('Content-Type')) requestHeaders.set('Content-Type', 'application/json')
  const response = await fetch(`${BASE}${path}`, { ...init, headers: requestHeaders })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new DashboardApiError(
      response.status,
      payload?.detail || payload,
      'Could not complete the intelligence request.',
    )
  }
  return payload as T
}

function post<T>(access: DashboardAccess, path: string, body: unknown) {
  return request<T>(access, path, { method: 'POST', body: JSON.stringify(body) })
}

export function getIntelligenceBootstrap(access: DashboardAccess) {
  return request<IntelligenceBootstrap>(access, '/bootstrap')
}

export function getIntelligenceOverview(
  access: DashboardAccess,
  body: { time_window?: Record<string, unknown>; filters?: Record<string, unknown>; lang?: string } = {},
) {
  return post<IntelligenceOverview>(access, '/overview', body)
}

export function evaluateIntelligenceMetric(access: DashboardAccess, body: IntelligenceQuery) {
  return post<IntelligenceMetric>(access, '/evaluate', body)
}

export function getIntelligenceMetricAbout(access: DashboardAccess, semanticKey: string) {
  return request<{ ok: true; about_metric: IntelligenceDefinition }>(
    access,
    `/about/${encodeURIComponent(semanticKey)}`,
  )
}

export function getIntelligenceTrend(
  access: DashboardAccess,
  body: IntelligenceQuery & { bucket?: string; time_buckets?: Array<Record<string, unknown>> },
) {
  return post<TrendResponse>(access, '/trend', body)
}

export function compareIntelligenceMetric(
  access: DashboardAccess,
  body: {
    semantic_key: string
    current_time_window?: Record<string, unknown>
    prior_time_window?: Record<string, unknown>
    current_filters?: Record<string, unknown>
    comparison_filters?: Record<string, unknown>
    mode?: 'prior' | 'segment_vs_company'
    lang?: string
  },
) {
  return post<{
    ok: boolean
    comparable: boolean
    current: IntelligenceMetric
    comparison: IntelligenceMetric
  }>(access, '/compare', body)
}

export function segmentIntelligenceMetric(
  access: DashboardAccess,
  body: IntelligenceQuery & { dimension: string; dimension_value: unknown },
) {
  return post<{ ok: boolean; dimension: string; dimension_value: unknown; metric: IntelligenceMetric }>(
    access,
    '/segment',
    body,
  )
}

export function drillIntelligenceMetric(
  access: DashboardAccess,
  body: IntelligenceQuery & { offset?: number; limit?: number },
) {
  return post<DrillResponse>(access, '/drill', body)
}

export function listIntelligenceSavedViews(access: DashboardAccess) {
  return request<{ ok: true; saved_views: SavedView[] }>(access, '/saved-views')
}

export function createIntelligenceSavedView(
  access: DashboardAccess,
  body: {
    name_en: string
    name_ar?: string
    mode?: 'live' | 'pinned'
    query_config: Record<string, unknown>
    layout?: Record<string, unknown>
  },
) {
  return post<{ ok: true; saved_view: SavedView }>(access, '/saved-views', body)
}

export function getIntelligenceSavedView(access: DashboardAccess, viewId: string) {
  return request<{ ok: true; saved_view: SavedView }>(
    access,
    `/saved-views/${encodeURIComponent(viewId)}`,
  )
}

export function deleteIntelligenceSavedView(access: DashboardAccess, viewId: string) {
  return request<{ ok: true; deleted: true; view_id: string }>(
    access,
    `/saved-views/${encodeURIComponent(viewId)}`,
    { method: 'DELETE' },
  )
}

export function createIntelligenceExport(
  access: DashboardAccess,
  body: IntelligenceQuery & { person_level?: boolean },
) {
  return post<{
    ok: true
    export: {
      export_id: string
      status: 'generated' | 'failed'
      row_count: number
      csv_sha256: string
      metadata: Record<string, unknown>
    }
  }>(access, '/exports', body)
}

export function getIntelligenceExport(access: DashboardAccess, exportId: string) {
  return request<{ ok: true; export: Record<string, unknown> }>(
    access,
    `/exports/${encodeURIComponent(exportId)}`,
  )
}

export async function downloadIntelligenceExport(access: DashboardAccess, exportId: string) {
  const response = await fetch(`${BASE}/exports/${encodeURIComponent(exportId)}/download`, {
    headers: headers(access),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new DashboardApiError(response.status, payload?.detail || payload, 'Could not download the intelligence export.')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] || `hr-intelligence-${exportId}.csv`
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function queryIntelligenceAssistant(access: DashboardAccess, semanticKey: string) {
  return post<Record<string, unknown>>(access, '/assistant/query', { semantic_key: semanticKey })
}

