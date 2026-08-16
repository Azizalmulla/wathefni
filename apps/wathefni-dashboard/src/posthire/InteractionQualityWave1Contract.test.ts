import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '..')
const buttonSrc = readFileSync(resolve(root, 'components/ui/button.tsx'), 'utf8')
const confirmSrc = readFileSync(resolve(root, 'components/ConfirmDialog.tsx'), 'utf8')
const appSrc = readFileSync(resolve(root, 'App.tsx'), 'utf8')
const hooksSrc = readFileSync(resolve(root, 'lib/query/hooks.ts'), 'utf8')
const activitySrc = readFileSync(resolve(root, 'components/ActivityLog.tsx'), 'utf8')
const leaveSrc = readFileSync(resolve(root, 'posthire/LeaveWorkspace.tsx'), 'utf8')
const postHireSrc = readFileSync(resolve(root, 'posthire/PostHire.tsx'), 'utf8')
const interviewsSrc = readFileSync(resolve(root, 'pages/InterviewsPage.tsx'), 'utf8')
const addToJobSrc = readFileSync(resolve(root, 'components/candidates/AddToJobDialog.tsx'), 'utf8')

describe('Interaction Quality & Loading Integrity Wave 1 contract', () => {
  it('adds shared Button pending and ConfirmDialog async run', () => {
    expect(buttonSrc).toContain('pending?: boolean')
    expect(buttonSrc).toContain('aria-busy={pending || undefined}')
    expect(confirmSrc).toContain('run?: (ctx: { reason?: string }) => Promise<void>')
    expect(confirmSrc).toContain('data-interaction-confirm')
    expect(confirmSrc).toContain('await run(')
  })

  it('shows honest shell busy notice instead of always Refreshing hiring data', () => {
    expect(appSrc).toContain('data-interaction-shell-busy')
    expect(appSrc).toContain('Working…')
    expect(appSrc).not.toMatch(/\{busy \? \(\s*<div[^>]*>\s*\{recruitingLocale === 'ar' \? 'جاري تحديث بيانات التوظيف/)
  })

  it('keeps interviews previous data and sticky drawer while refreshing', () => {
    expect(hooksSrc).toContain('useInterviewsQuery')
    expect(hooksSrc).toMatch(/useInterviewsQuery[\s\S]*placeholderData: keepPreviousData/)
    expect(interviewsSrc).toContain('selectedSnapshot')
    expect(interviewsSrc).toContain('if (busy) return')
    expect(interviewsSrc).toContain('if (!submitting) onClose()')
  })

  it('soft-keeps module and leave data; rematches leave selection', () => {
    expect(postHireSrc).toContain('Soft-keep previous rows while params change')
    expect(postHireSrc).not.toContain('clear stale rows so the\n    // skeleton shows')
    expect(leaveSrc).toContain('Rematch open drawer by leave_id')
    expect(leaveSrc).not.toContain('setSelected(null)\n    setSurfaceError(null)')
  })

  it('soft-refreshes activity and guards add-to-job backdrop', () => {
    expect(activitySrc).toContain('data-activity-refreshing')
    expect(activitySrc).toContain('setRefreshing(true)')
    expect(addToJobSrc).toContain('if (!busy) onClose()')
  })

  it('soft-keeps ranking for the same job; clears only on job switch (Wave 2)', () => {
    expect(appSrc).toContain('rankingLoadedPositionRef')
    expect(appSrc).toMatch(/async function loadCurrentRanking[\s\S]*if \(!sameJob\) setRanking\(null\)/)
  })
})
