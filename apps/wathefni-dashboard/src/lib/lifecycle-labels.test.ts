import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

/**
 * Web/mobile consistency proof for Canonical Recruiting Lifecycle stage labels.
 * Both clients must render the same human labels for canonical + legacy statuses.
 */
const SHARED_LABELS: Record<string, string> = {
  awaiting_cv: 'Waiting for CV',
  cv_processing: 'Processing CV',
  cv_received: 'Processing CV',
  screening: 'Processing CV',
  ready_for_review: 'Ready for review',
  screening_complete: 'Ready for review',
  review_pending: 'Ready for review',
  shortlisted: 'Shortlisted',
  interview: 'Interview',
  hired: 'Hired',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  offered: 'Shortlisted',
  offer_sent: 'Shortlisted',
}

describe('canonical recruiting lifecycle labels', () => {
  test('dashboard STAGE_LABELS match the shared contract', () => {
    const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    for (const [status, label] of Object.entries(SHARED_LABELS)) {
      expect(source).toContain(`${status}: '${label}'`)
    }
    // Formal offer lifecycle is out of scope — do not show "Offer sent" as a stage.
    expect(source).not.toMatch(/offered:\s*'Offer sent'/)
  })

  test('HR mobile STAGE_LABELS match the shared contract', () => {
    const source = readFileSync(
      resolve(__dirname, '../../../wathefni-hr-mobile/src/features/recruiting/CandidateReviewView.tsx'),
      'utf8',
    )
    for (const [status, label] of Object.entries(SHARED_LABELS)) {
      expect(source).toContain(`${status}: '${label}'`)
    }
  })

  test('reject requires candidate.decide on web (not manage)', () => {
    const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(source).toMatch(/canDecideCandidates[\s\S]{0,120}runReject/)
    expect(source).toMatch(/disabled=\{busy \|\| !canDecideCandidates\} onClick=\{\(\) => void runReject\(\)\}/)
  })

  test('shortlist requires explicit confirmation on web', () => {
    const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(source).toContain("title: 'Shortlist this candidate?'")
    expect(source).toContain('runShortlist')
  })
})
