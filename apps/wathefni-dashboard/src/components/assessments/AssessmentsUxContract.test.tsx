import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

describe('Assessments page UX contract', () => {
  test('removes MetricGrid and Average score from ops header', () => {
    const src = readFileSync(resolve(__dirname, '../../pages/AssessmentsPage.tsx'), 'utf8')
    expect(src).not.toContain('MetricGrid')
    expect(src).not.toContain('Average score')
    expect(src).not.toContain('averagePercent')
    expect(src).toContain('assessmentCohortChipLabel')
    expect(src).toContain("dir={isAr ? 'rtl' : 'ltr'}")
  })

  test('wires React Profiler and interaction marks', () => {
    const src = readFileSync(resolve(__dirname, '../../pages/AssessmentsPage.tsx'), 'utf8')
    expect(src).toContain('ReactProfiler')
    expect(src).toContain('dashboardPerfMarkProfilerCommit')
    expect(src).toContain('assessments_tab')
    expect(src).toContain('assessments_cohort')
    expect(src).toContain('assessments_pagination')
    expect(src).toContain('assessments_open_report')
    expect(src).toContain('assessments_row_action')
  })

  test('AttemptRow respects backend allowed_actions including cancelled resend', () => {
    const src = readFileSync(resolve(__dirname, 'AssessmentRows.tsx'), 'utf8')
    expect(src).toContain('allowed_actions')
    expect(src).toContain("allowed.has('resend_assessment')")
    expect(src).not.toMatch(/\['pending', 'in_progress', 'expired'\]/)
  })

  test('overlays use aria-modal and scroll lock helpers', () => {
    const report = readFileSync(resolve(__dirname, 'AssessmentReportPage.tsx'), 'utf8')
    expect(report).toContain('aria-modal')
    expect(report).toContain('useBodyScrollLock')
    expect(report).toContain('useOverlayFocus')
    expect(report).toContain('role="dialog"')
  })

  test('Assessment configuration is collapsed admin summary with technical expand', () => {
    const src = readFileSync(resolve(__dirname, '../../pages/AssessmentsPage.tsx'), 'utf8')
    expect(src).toContain('Assessment configuration')
    expect(src).toContain('إعداد التقييم')
    expect(src).toContain('data-testid="assessment-configuration"')
    expect(src).toContain('data-testid="assessment-configuration-summary"')
    expect(src).toContain('data-testid="assessment-configuration-details"')
    expect(src).toContain('Setup ready')
    expect(src).toContain('Needs attention')
    expect(src).toContain('evidence indicators')
    expect(src).toContain('assessmentSetupLastRefreshedLabel')
    expect(src).toContain('canSeeSetup')
    expect(src).toContain('Refresh setup')
    expect(src).toContain('Content source')
    expect(src).toContain('Setup version')
    expect(src).toContain('Battery')
    expect(src).not.toContain('Assessment setup details')
    // Collapsed by default: no open attribute on the configuration details element
    expect(src).not.toMatch(/data-testid="assessment-configuration"[^>]*\sopen[\s>]/)
    // Product2 authoring stays on page, not moved
    expect(src).toContain('Product2AuthoringPanel')
  })
})
