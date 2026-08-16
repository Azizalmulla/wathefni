/** Candidate decision presentation helpers — no invented business meaning. */

import type { StatusTone } from '@/components/ui'
import { canonicalStage } from '@hr/features/recruiting/lifecycle'

export type CandidateDecideAction = 'shortlist' | 'reject' | 'hire'

export type CandidateOfferCurrent = {
  offer_id?: string | null
  status?: string | null
  status_label?: string | null
  position_title?: string | null
  position_code?: string | null
  currency?: string | null
  base_salary?: string | number | null
  proposed_start_date?: string | null
  compensation_redacted?: boolean | null
  candidate_name_snapshot?: string | null
}

export type CandidateOfferPayload = {
  current?: CandidateOfferCurrent | null
  items?: unknown[]
  allowed_actions?: string[]
}

export function candidateStageTone(status: string | null | undefined): StatusTone {
  const stage = canonicalStage(status) || String(status || '').toLowerCase()
  if (stage === 'hired') return 'success'
  if (stage === 'rejected' || stage === 'withdrawn' || stage === 'import_archived') return 'danger'
  if (stage === 'ready_for_review' || stage === 'shortlisted' || stage === 'interview') return 'warning'
  if (stage === 'awaiting_cv' || stage === 'cv_processing') return 'neutral'
  return 'neutral'
}

export function candidateIsTerminal(status: string | null | undefined): boolean {
  const raw = String(status || '').toLowerCase()
  const stage = canonicalStage(status) || raw
  return (
    stage === 'hired' ||
    stage === 'rejected' ||
    stage === 'withdrawn' ||
    raw === 'import_archived' ||
    raw === 'archived'
  )
}

export function parseCandidateOffer(offer: unknown): CandidateOfferPayload | null {
  if (!offer || typeof offer !== 'object') return null
  return offer as CandidateOfferPayload
}

export function hasRenderableOffer(offer: unknown): boolean {
  const parsed = parseCandidateOffer(offer)
  return Boolean(parsed?.current && typeof parsed.current === 'object')
}

/**
 * Map known English prepare consequences to mobile i18n templates.
 * Unknown server text is returned unchanged (no invented meaning).
 */
export function localizeCandidateConsequence(
  consequence: string | null | undefined,
  action: CandidateDecideAction,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const raw = String(consequence || '').trim()
  if (!raw) {
    if (action === 'shortlist') return t('hrCandidate.consequenceShortlistGeneric')
    if (action === 'reject') return t('hrCandidate.consequenceRejectGeneric')
    return t('hrCandidate.consequenceHireGeneric')
  }
  const shortlist = /^Move (.+) to the shortlist for (.+)\.?$/i.exec(raw)
  if (shortlist) {
    return t('hrCandidate.consequenceShortlist', { name: shortlist[1], role: shortlist[2] })
  }
  const reject = /^Reject (.+) for (.+)\. This removes them from the active pipeline\.?$/i.exec(raw)
  if (reject) {
    return t('hrCandidate.consequenceReject', { name: reject[1], role: reject[2] })
  }
  const hire = /^Hire (.+) for (.+)\. This creates the employee and starts post-hire setup\.?$/i.exec(raw)
  if (hire) {
    return t('hrCandidate.consequenceHire', { name: hire[1], role: hire[2] })
  }
  return raw
}

export function localizeCandidateCurrentState(
  status: string | null | undefined,
  locale: 'en' | 'ar',
  stageLabel: (value: string | null | undefined, locale: 'en' | 'ar') => string,
): string {
  return stageLabel(status, locale)
}

export function formatOfferSalary(
  currency: string | null | undefined,
  baseSalary: string | number | null | undefined,
  redacted: boolean | null | undefined,
): string | null {
  if (redacted) return null
  if (baseSalary == null || baseSalary === '') return null
  const amount = String(baseSalary).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
  const cur = String(currency || '').trim()
  return cur ? `${cur} ${amount}` : amount
}
