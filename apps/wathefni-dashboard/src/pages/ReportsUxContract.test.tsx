import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

import { metricValue } from '@/pages/ReportsPage'

describe('Reports page UX contract', () => {
  test('uses overview contract labels and not interviews needing action', () => {
    const src = readFileSync(resolve(__dirname, 'ReportsPage.tsx'), 'utf8')
    expect(src).toContain('interview_debt')
    expect(src).toContain('Candidates needing interview scheduling')
    expect(src).not.toContain('Interviews needing action')
    expect(src).toContain('Active applications by role')
    expect(src).toContain("dir={isAr ? 'rtl' : 'ltr'}")
  })

  test('wires React Profiler and interaction marks', () => {
    const src = readFileSync(resolve(__dirname, 'ReportsPage.tsx'), 'utf8')
    expect(src).toContain('ReactProfiler')
    expect(src).toContain('dashboardPerfMarkProfilerCommit')
    expect(src).toContain('reports_page_load')
    expect(src).toContain('reports_refresh')
    expect(src).toContain('reports_export')
  })

  test('export cards use role_rows and interview module gate', () => {
    const src = readFileSync(resolve(__dirname, 'ReportsPage.tsx'), 'utf8')
    expect(src).toContain('exports?.role_rows')
    expect(src).toContain('interviewsEnabled')
    expect(src).toContain('followup_delivery_history_rows')
    expect(src).not.toContain('interviewTotal')
  })

  test('export and breakdown counts use black pills (not muted badges)', () => {
    const src = readFileSync(resolve(__dirname, 'ReportsPage.tsx'), 'utf8')
    expect(src).toContain('bg-semantic-ink px-2 text-[11px] font-semibold text-white')
    expect(src).not.toContain('Badge tone="muted"')
    expect(src).toContain('h-2 w-2 shrink-0 rounded-full')
  })

  test('metricValue reads numeric overview metrics', () => {
    expect(
      metricValue(
        {
          metrics: [{ key: 'active_applications', label: 'Active applications', value: 7 }],
        },
        'active_applications',
      ),
    ).toBe(7)
  })
})
