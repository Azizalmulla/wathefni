import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const start = postHire.indexOf('function AnalyticsPage(')
const end = postHire.indexOf('// --- Compliance', start)
const analyticsSrc = postHire.slice(start, end > 0 ? end : start + 8000)

describe('Analytics Page Refinement Wave 1 contract', () => {
  it('is insight-first and removes the duplicate Needs Attention inbox', () => {
    expect(analyticsSrc).toContain('data-analytics-insights')
    expect(analyticsSrc).toContain('data-analytics-snapshot')
    expect(analyticsSrc).toContain('data-analytics-narrative')
    expect(analyticsSrc).toContain('data-analytics-patterns')
    expect(analyticsSrc).toContain('data-analytics-triage-link')
    expect(analyticsSrc).toContain("onNavigate?.('inbox')")
    expect(analyticsSrc).not.toContain('attentionTitle')
    expect(analyticsSrc).not.toContain('openDeepLink')
    expect(analyticsSrc).not.toMatch(/CardTitle>\s*\{copy\.attentionTitle\}/)
    expect(analyticsSrc).not.toMatch(/attention\.map\(/)
  })

  it('shows period and comparison chrome without inventing a new backend window', () => {
    expect(analyticsSrc).toContain('data-analytics-period')
    expect(analyticsSrc).toContain('data-analytics-comparison')
    expect(analyticsSrc).toContain('compareNote')
    expect(analyticsSrc).toContain('Kuwait month-to-date')
  })

  it('demotes methodology and source honesty off first paint', () => {
    expect(analyticsSrc).toContain('data-analytics-methodology')
    expect(analyticsSrc).toContain('showMethodology')
    expect(analyticsSrc).toContain('data-analytics-partial')
    expect(analyticsSrc).not.toContain('sourcesOk')
    expect(analyticsSrc).not.toMatch(/NextAction/)
  })

  it('excludes delivery strip from Analytics mounts', () => {
    expect(postHire).toMatch(
      /page === 'shifts' \|\| page === 'payroll' \|\| page === 'analytics'/,
    )
  })

  it('keeps bilingual RTL shell and preserves read-only contract language behind methodology', () => {
    expect(analyticsSrc).toContain("lang={locale}")
    expect(analyticsSrc).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(analyticsSrc).toContain('readOnlyShort')
    expect(analyticsSrc).toContain('definitions')
  })
})
