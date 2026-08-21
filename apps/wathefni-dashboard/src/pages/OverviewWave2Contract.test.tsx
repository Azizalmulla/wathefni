import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

const overviewSrc = readFileSync(resolve(__dirname, 'OverviewPage.tsx'), 'utf8')

describe('Wave 2 Overview work-queue contract', () => {
  test('no top-level View all beside My Work / Company Attention opens follow-up', () => {
    // Miswired control was: onClick={onOpenFollowUps} labeled View all.
    // Follow-up attention cards may still call onOpenFollowUps — that is fine.
    expect(overviewSrc).not.toMatch(
      /onClick=\{onOpenFollowUps\}[\s\S]{0,120}\{isAr \? 'عرض الكل' : 'View all'\}/,
    )
    expect(overviewSrc).not.toMatch(
      /\{isAr \? 'عرض الكل' : 'View all'\}[\s\S]{0,80}onOpenFollowUps/,
    )
  })

  test('roles View all remains contextual (jobs destination)', () => {
    expect(overviewSrc).toContain("onOpenDestination({ page: 'jobs' })")
    expect(overviewSrc).toMatch(/onOpenDestination\(\{ page: 'jobs' \}[\s\S]{0,200}View all/)
  })

  test('attention cards distinguish people from applications', () => {
    expect(overviewSrc).toContain('formatOverviewPeopleMetric')
    expect(overviewSrc).toContain('card.metric.unitLabel')
    expect(overviewSrc).toContain('card.metric.applicationsHint')
    expect(overviewSrc).toContain('formatWorkQueueShownTotal')
  })

  test('row actions still open per-item destinations', () => {
    expect(overviewSrc).toContain('onOpenDestination(item.destination)')
  })

  test('work queue and role priority honour capability flags and distinguish error from empty', () => {
    expect(overviewSrc).toContain('showWorkQueue')
    expect(overviewSrc).toContain('showRolePriority')
    expect(overviewSrc).toContain('data-overview-work-queue')
    expect(overviewSrc).toContain('data-overview-role-priority')
    expect(overviewSrc).toContain('overview-work-error')
    expect(overviewSrc).toContain('overview-work-empty')
    expect(overviewSrc).toContain('workQueueError')
  })
})
