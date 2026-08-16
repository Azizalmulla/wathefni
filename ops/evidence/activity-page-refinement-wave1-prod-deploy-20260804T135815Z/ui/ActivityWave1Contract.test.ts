import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const activitySrc = readFileSync(resolve(__dirname, '../components/ActivityLog.tsx'), 'utf8')
const appSrc = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')

describe('Activity Page Refinement Wave 1 contract', () => {
  it('is timeline-first with compact purpose and no duplicate card heading', () => {
    expect(activitySrc).toContain('data-activity-timeline')
    expect(activitySrc).toContain('data-activity-summary')
    expect(activitySrc).toContain('data-activity-list')
    expect(activitySrc).toContain('data-activity-event')
    expect(activitySrc).not.toContain('Company activity')
    expect(activitySrc).not.toContain('CardTitle')
    expect(activitySrc).not.toContain('CATEGORY_META')
  })

  it('exposes date, actor, category, action, result filters plus search and export', () => {
    expect(activitySrc).toContain('data-activity-filters')
    expect(activitySrc).toContain('data-activity-export')
    expect(activitySrc).toContain('action_type')
    expect(activitySrc).toContain("status: 'all'")
    expect(activitySrc).toContain('downloadCompanyActivityCsv')
    expect(activitySrc).toMatch(/From|من/)
    expect(activitySrc).toMatch(/Actor|المنفّذ/)
  })

  it('shows who / what / affected / when / outcome and hides technical evidence behind Details', () => {
    expect(activitySrc).toContain('data-activity-details')
    expect(activitySrc).toContain('data-activity-details-toggle')
    expect(activitySrc).toContain('humanizeActionType')
    expect(activitySrc).toContain('Affected')
    expect(activitySrc).toContain('action_type')
    expect(activitySrc).toContain('Event id')
    expect(activitySrc).toContain('Read-only audit record')
  })

  it('uses semantic status tokens and corrects RBAC copy to HR Admins', () => {
    expect(activitySrc).toContain("tone: 'success'")
    expect(activitySrc).toContain("tone: 'danger'")
    expect(activitySrc).toContain('Owners and HR Admins')
    expect(activitySrc).not.toContain('HR Managers')
    expect(activitySrc).toContain('data-activity-denied')
  })

  it('is bilingual RTL and remains read-only with ownership honesty', () => {
    expect(activitySrc).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(activitySrc).toContain("lang={locale}")
    expect(activitySrc).toContain('data-activity-ownership')
    expect(activitySrc).not.toMatch(/method:\s*'POST'/)
    expect(activitySrc).not.toMatch(/resolveHrTask|runPosthireAction/)
    expect(appSrc).toContain('trustworthy, read-only timeline')
  })
})
