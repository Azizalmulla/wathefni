import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

const overviewSrc = readFileSync(resolve(__dirname, 'OverviewPage.tsx'), 'utf8')
const headerSrc = readFileSync(resolve(__dirname, '../components/hr/HrPageHeader.tsx'), 'utf8')
const sectionSrc = readFileSync(resolve(__dirname, '../components/hr/HrSection.tsx'), 'utf8')
const tileSrc = readFileSync(resolve(__dirname, '../components/hr/HrMetricTile.tsx'), 'utf8')
const rowSrc = readFileSync(resolve(__dirname, '../components/hr/HrAttentionRow.tsx'), 'utf8')
const destSrc = readFileSync(resolve(__dirname, '../components/hr/HrDestinationButton.tsx'), 'utf8')

describe('Phase 3 Overview reference experience', () => {
  test('ships the approved shared primitives', () => {
    expect(headerSrc).toContain('export function HrPageHeader')
    expect(sectionSrc).toContain('SoftKeepSurface')
    expect(tileSrc).toContain('current')
    expect(rowSrc).toContain('HrDestinationButton')
    expect(destSrc).not.toContain('translate-y')
    expect(destSrc).not.toMatch(/shadow-/)
  })

  test('does not invent a frontend attention total', () => {
    expect(overviewSrc).not.toContain('totalAttention')
    expect(overviewSrc).not.toMatch(/reviewCount\s*\+\s*followUpCount/)
  })

  test('recruiting bands are capability-gated and can disappear', () => {
    expect(overviewSrc).toContain('showWorkQueue')
    expect(overviewSrc).toContain('showRolePriority')
    expect(overviewSrc).toContain('showHiringMetrics')
    expect(overviewSrc).toContain('showApprovals')
    expect(overviewSrc).toContain('showSignals')
  })

  test('inbox peek and C1 signals stay backend-owned', () => {
    expect(overviewSrc).toContain('useWorkQueueQuery')
    expect(overviewSrc).toContain('useIntelligenceOverviewQuery')
    expect(overviewSrc).toContain('intelligenceIsCurrent')
    expect(overviewSrc).toContain("CURRENT_INTELLIGENCE = new Set(['ok'])")
    expect(overviewSrc).toContain('onOpenDestination(item.destination)')
    expect(overviewSrc).not.toContain('useActionInboxQuery')
  })

  test('uses semantic tokens rather than Overview hex palettes', () => {
    expect(overviewSrc).not.toMatch(/bg-\[#f1d96f\]/)
    expect(overviewSrc).not.toMatch(/hover:-translate-y/)
    expect(overviewSrc).toContain('bg-semantic-surface')
    expect(overviewSrc).toContain('dir={isAr ? \'rtl\' : \'ltr\'}')
  })

  test('soft-keep wraps Overview bands', () => {
    expect(sectionSrc).toContain('SoftKeepSurface')
    expect(overviewSrc).toContain('HrSection')
    expect(overviewSrc).toContain('cold={workQueueLoading}')
    expect(overviewSrc).not.toContain('cold={inboxLoading}')
    expect(overviewSrc).toContain('cold={intelligenceLoading}')
  })
})
