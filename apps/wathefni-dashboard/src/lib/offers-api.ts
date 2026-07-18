import type { DashboardAccess } from '@/types'

async function request<T>(path: string, access: DashboardAccess, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${access.token.trim()}`)
  headers.set('X-Company-Code', access.companyCode.trim().toUpperCase())
  if (access.hrPhone?.trim()) headers.set('X-HR-Phone', access.hrPhone.trim())
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload?.detail || payload
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || detail?.error || 'Offer request failed.'
    throw new Error(message)
  }
  return payload as T
}

export type EmploymentOffer = {
  offer_id: string
  app_key: string
  status: string
  status_label?: string
  current_version?: number
  accepted_version?: number | null
  position_code?: string | null
  position_title?: string | null
  currency?: string
  base_salary?: string | null
  candidate_name_snapshot?: string | null
  candidate_phone_snapshot?: string | null
  allowed_actions?: string[]
  respond_url?: string
  delivery?: {
    status?: string
    channel?: string
    offer_version?: number
    document_sha256?: string
    sent_at?: string
    failed_at?: string
  } | null
}

export function listApplicationOffers(access: DashboardAccess, appKey: string) {
  return request<{ ok: boolean; items: EmploymentOffer[] }>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/offers`,
    access,
  )
}

export function createOfferDraft(
  access: DashboardAccess,
  appKey: string,
  body: Record<string, unknown>,
) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/applications/${encodeURIComponent(appKey)}/offers`,
    access,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function updateOfferDraft(
  access: DashboardAccess,
  offerId: string,
  body: Record<string, unknown>,
) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/offers/${encodeURIComponent(offerId)}`,
    access,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function submitOfferApproval(access: DashboardAccess, offerId: string) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/offers/${encodeURIComponent(offerId)}/submit-approval`,
    access,
    { method: 'POST' },
  )
}

export function approveOffer(access: DashboardAccess, offerId: string) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/offers/${encodeURIComponent(offerId)}/approve`,
    access,
    { method: 'POST' },
  )
}

export function returnOffer(access: DashboardAccess, offerId: string, reason?: string) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/offers/${encodeURIComponent(offerId)}/return`,
    access,
    { method: 'POST', body: JSON.stringify({ reason: reason || null }) },
  )
}

export function sendOffer(access: DashboardAccess, offerId: string) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/offers/${encodeURIComponent(offerId)}/send`,
    access,
    { method: 'POST' },
  )
}

export function withdrawOffer(access: DashboardAccess, offerId: string, reason: string) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/offers/${encodeURIComponent(offerId)}/withdraw`,
    access,
    { method: 'POST', body: JSON.stringify({ reason }) },
  )
}

export function recordOfferResponse(
  access: DashboardAccess,
  offerId: string,
  decision: 'accepted' | 'declined',
  evidenceNote?: string,
) {
  return request<{ ok: boolean; offer: EmploymentOffer }>(
    `/dashboard/prehire/offers/${encodeURIComponent(offerId)}/record-response`,
    access,
    { method: 'POST', body: JSON.stringify({ decision, evidence_note: evidenceNote || null }) },
  )
}
