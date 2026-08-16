import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const notifications = readFileSync(resolve(__dirname, '../pages/NotificationsPage.tsx'), 'utf8')
const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const appSrc = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')

describe('Alerts & Delivery Page Refinement Wave 1 contract', () => {
  it('renders a findings-style live issues list with filters and summary', () => {
    expect(notifications).toContain('data-alerts-delivery')
    expect(notifications).toContain('data-alerts-summary')
    expect(notifications).toContain('data-alerts-filters')
    expect(notifications).toContain('data-alerts-issues')
    expect(notifications).toMatch(
      /needs_follow_up[\s\S]*failed[\s\S]*retrying[\s\S]*resolved[\s\S]*all/,
    )
    expect(notifications).not.toContain('Urgent HR alerts')
    expect(notifications).not.toContain('void issues')
  })

  it('fixes the discarded scoped-notification-row path by rendering prehire rows', () => {
    expect(notifications).toContain('moduleScopedNotificationRows')
    expect(notifications).toContain('issueFromPrehireRow')
    expect(notifications).toContain('scopedRows.map')
    expect(notifications).not.toMatch(/void issues/)
  })

  it('keeps one follow-up resolve path and never mounts silent fake CTAs', () => {
    expect(notifications).toContain("resolveHrTask(access, taskId, 'done')")
    expect(notifications).toContain("kind: 'status'")
    expect(notifications).toContain('data-alerts-status-cta')
    expect(notifications).toContain("kind: 'navigate'")
    expect(notifications).toContain('data-alerts-issue-detail')
  })

  it('is bilingual RTL and owns delivery without specialist-module strips', () => {
    expect(notifications).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(notifications).toContain("lang={locale}")
    expect(notifications).toContain('data-alerts-ownership')
    expect(postHire).toContain('no duplicate DeliveryStatusStrip')
    expect(postHire).not.toMatch(/<DeliveryStatusStrip[\s>]/)
    expect(postHire).toMatch(/export function PostHireDeliveryCenter[\s\S]*return null/)
  })

  it('wires App props for access and post-hire enablement without nested deliveryCenter cards', () => {
    expect(appSrc).toContain('posthireEnabled={anyPosthireModuleEnabled(moduleState)}')
    expect(appSrc).toContain('<LazyNotificationsPage')
    expect(appSrc).not.toContain('LazyPostHireDeliveryCenter')
    expect(appSrc).not.toContain('deliveryCenter=')
    expect(appSrc).toContain('safest next action')
  })
})
