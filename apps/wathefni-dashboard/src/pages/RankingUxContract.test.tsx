import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

describe('Ranking page UX contract', () => {
  test('uses plain-language counts and eligible helper', () => {
    const src = readFileSync(resolve(__dirname, 'RankingPage.tsx'), 'utf8')
    expect(src).toContain("rankingCopy(locale, 'in_review_order')")
    expect(src).toContain("rankingCopy(locale, 'job_matches')")
    expect(src).toContain("rankingCopy(locale, 'meets_all_requirements')")
    expect(src).toContain("rankingCopy(locale, 'eligible_helper')")
    expect(src).toContain("rankingCopy(locale, 'excluded_note')")
    expect(src).not.toMatch(/Matching\s*\{/)
    expect(src).not.toMatch(/>\s*Rankable\s*</)
    expect(src).not.toContain("'Rankable'")
    expect(src).not.toContain('"Rankable"')
  })

  test('wires on-page states including none rankable', () => {
    const src = readFileSync(resolve(__dirname, 'RankingPage.tsx'), 'utf8')
    expect(src).toContain("state_no_job")
    expect(src).toContain("state_no_run")
    expect(src).toContain("state_running")
    expect(src).toContain("state_stale")
    expect(src).toContain("state_failed")
    expect(src).toContain("state_none_rankable")
  })

  test('keeps CV evidence primary and assessment gated', () => {
    const src = readFileSync(resolve(__dirname, 'RankingPage.tsx'), 'utf8')
    expect(src).toContain('assessmentEnabled')
    expect(src).toContain("rankingCopy(locale, 'cv_evidence')")
    expect(src).toContain('assessmentEnabled && assessmentComponents.length')
    const presentation = readFileSync(resolve(__dirname, '../lib/rankingPresentation.ts'), 'utf8')
    expect(presentation).toContain("group: 'cv'")
    expect(presentation).toContain("group === 'assessment' && !assessmentOn")
  })

  test('wires React Profiler and interaction marks', () => {
    const src = readFileSync(resolve(__dirname, 'RankingPage.tsx'), 'utf8')
    expect(src).toContain('ReactProfiler')
    expect(src).toContain('dashboardPerfMarkProfilerCommit')
    expect(src).toContain('ranking_job_switch')
    expect(src).toContain('ranking_run')
    expect(src).toContain('ranking_expand_evidence')
    expect(src).toContain('ranking_open_candidate')
  })

  test('App returns to Ranking with focus restore; profile uses Escape overlay a11y', () => {
    const app = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(app).toContain("returnPage: 'ranking'")
    expect(app).toContain('Back to Ranking')
    expect(app).toContain('returnFocusEl')
    expect(app).toContain('rankingError')
    const profile = readFileSync(resolve(__dirname, '../components/candidates/CandidateProfilePage.tsx'), 'utf8')
    expect(profile).toContain('useOverlayFocus')
    expect(profile).toContain('aria-modal')
    expect(profile).toContain('returnLabel')
  })

  test('rankingQueueContract module exists for tests', () => {
    const contract = readFileSync(resolve(__dirname, '../lib/rankingQueueContract.ts'), 'utf8')
    expect(contract).toContain('export function isRankable')
    expect(contract).toContain('export function topNRankable')
    expect(contract).toContain('eligible_helper')
  })
})
