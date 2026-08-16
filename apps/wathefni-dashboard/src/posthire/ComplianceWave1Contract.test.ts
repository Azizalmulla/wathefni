import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const start = postHire.indexOf('function CompliancePage(')
const end = postHire.indexOf('// --- dispatcher', start)
const complianceSrc = postHire.slice(start, end > 0 ? end : start + 20000)

const reviewStart = postHire.indexOf('function DocumentHrReviewButtons(')
const reviewEnd = postHire.indexOf('\nfunction ', reviewStart + 10)
const reviewSrc = postHire.slice(reviewStart, reviewEnd > 0 ? reviewEnd : reviewStart + 8000)

describe('Compliance Page Refinement Wave 1 contract', () => {
  it('is findings-first with All documents demoted behind a surface tab', () => {
    expect(complianceSrc).toContain("useState<'findings' | 'register'>('findings')")
    expect(complianceSrc).toContain('data-compliance-findings')
    expect(complianceSrc).toContain('data-compliance-findings-list')
    expect(complianceSrc).toContain('data-compliance-register')
    expect(complianceSrc).toContain('data-compliance-surfaces')
    expect(complianceSrc).toContain("['register', isAr ? 'كل المستندات' : 'All documents']")
    expect(complianceSrc).not.toMatch(/NextAction/)
    expect(complianceSrc).not.toMatch(/StatCard/)
    expect(complianceSrc).not.toMatch(/Remind all/i)
    expect(complianceSrc).not.toMatch(/setBulkBusy|bulkBusy/)
  })

  it('exposes ordered simple filters without a metrics banner stack', () => {
    expect(complianceSrc).toContain('data-compliance-filters')
    expect(complianceSrc).toContain('data-compliance-summary')
    const labelsStart = complianceSrc.indexOf('const filterLabels')
    expect(labelsStart).toBeGreaterThan(0)
    const labelsBlock = complianceSrc.slice(labelsStart, labelsStart + 600)
    expect(labelsBlock).toMatch(
      /needs_review[\s\S]*missing[\s\S]*expiring_soon[\s\S]*expired[\s\S]*all/,
    )
  })

  it('keeps a single reminder path on Findings only', () => {
    expect(complianceSrc).toContain('data-compliance-remind')
    expect(complianceSrc).toContain('compliance_send_reminder')
    expect(complianceSrc).toContain('sendFindingReminder')
    // Register routes follow-up into Findings instead of a second Remind button
    expect(complianceSrc).toContain('Open in Findings')
    const registerStart = complianceSrc.indexOf('data-compliance-register')
    const registerBlock = complianceSrc.slice(registerStart)
    expect(registerBlock).not.toContain('data-compliance-remind')
    expect(registerBlock).not.toContain("action.run('compliance_send_reminder'")
  })

  it('demotes methodology and hides delivery strip on Compliance', () => {
    expect(complianceSrc).toContain('data-compliance-methodology')
    expect(complianceSrc).toContain('showMethodology')
    expect(postHire).toContain('no duplicate DeliveryStatusStrip')
    expect(postHire).not.toMatch(/<DeliveryStatusStrip[\s>]/)
  })

  it('replaces D3–D6 native prompts with governed review modals', () => {
    expect(reviewSrc).toContain('confirm.withReason')
    expect(reviewSrc).toContain('minReasonLength: 3')
    expect(reviewSrc).toContain('datesOpen')
    expect(reviewSrc).toContain('useBodyScrollLock')
    expect(reviewSrc).toContain('useOverlayFocus')
    expect(reviewSrc).toContain('Correct dates')
    expect(reviewSrc).not.toContain('window.prompt')
    expect(reviewSrc).not.toContain('window.confirm')
  })

  it('keeps bilingual RTL shell and HR-reviewed honesty language', () => {
    expect(complianceSrc).toContain("lang={locale}")
    expect(complianceSrc).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(complianceSrc).toContain('not government verification')
    expect(complianceSrc).toContain('compliance.manage')
    expect(reviewSrc).toContain('HR reviewed')
    expect(reviewSrc).toContain('not PACI')
  })

  it('routes Employees 360 compliance actions into Compliance', () => {
    expect(postHire).toContain("onNavigate?.('compliance'")
    expect(postHire).toContain('Review and reminders happen in Compliance.')
    expect(postHire).not.toMatch(/emp360-section-compliance[\s\S]{0,1200}DocumentHrReviewButtons/)
    expect(postHire).not.toMatch(/emp360-section-compliance[\s\S]{0,1200}compliance_send_reminder/)
  })
})
