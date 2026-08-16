/**
 * Contract: Employee App ↔ HR Dashboard sync hardening.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '../../../..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

describe('Employee↔HR sync hardening contracts', () => {
  it('mobile soft-refreshes /app/me on foreground and unlock', () => {
    const refresh = read('apps/wathefni-employee-mobile/src/lib/refresh.tsx')
    const soft = read('apps/wathefni-employee-mobile/src/lib/employeeSoftRefresh.ts')
    const unlock = read('apps/wathefni-employee-mobile/src/features/pin/LocalUnlockShell.tsx')
    const profile = read('apps/wathefni-employee-mobile/app/(tabs)/profile.tsx')
    expect(soft).toContain('softRefreshEmployeeSurfaces')
    expect(soft).toContain('refreshMe')
    expect(refresh).toContain('softRefreshEmployeeSurfaces')
    expect(unlock).toContain('softRefreshEmployeeSurfaces')
    expect(profile).toContain('refreshMe')
    expect(profile).toContain('onRefresh')
  })

  it('documents renew invalidates onboarding', () => {
    const docs = read('apps/wathefni-employee-mobile/app/documents.tsx')
    expect(docs).toContain("queryKey: ['documents']")
    expect(docs).toContain("queryKey: ['onboarding']")
  })

  it('high-churn mobile screens use HIGH_CHURN_STALE_MS', () => {
    expect(read('apps/wathefni-employee-mobile/app/(tabs)/index.tsx')).toContain('HIGH_CHURN_STALE_MS')
    expect(read('apps/wathefni-employee-mobile/app/(tabs)/leave.tsx')).toContain('HIGH_CHURN_STALE_MS')
    expect(read('apps/wathefni-employee-mobile/app/(tabs)/schedule.tsx')).toContain('HIGH_CHURN_STALE_MS')
  })

  it('HR inbound soft poll wired for leave/onboarding/compliance/ess/app-access', () => {
    const freshness = read('apps/wathefni-dashboard/src/lib/query/freshness.ts')
    const leave = read('apps/wathefni-dashboard/src/posthire/LeaveWorkspace.tsx')
    const postHire = read('apps/wathefni-dashboard/src/posthire/PostHire.tsx')
    const workforce = read('apps/wathefni-dashboard/src/posthire/employees360/WorkforcePage.tsx')
    const bank = read('apps/wathefni-dashboard/src/posthire/employees360/BankReviewPanel.tsx')
    expect(freshness).toContain('inboundQueue')
    expect(leave).toContain('useVisibilitySoftPoll')
    expect(leave).toContain('FRESHNESS_MS.inboundQueue')
    expect(postHire).toContain('FRESHNESS_MS.inboundQueue')
    expect(postHire).toContain('reloadAppAccess')
    expect(workforce).toContain("action: 'reject'")
    expect(workforce).toContain('employees.ess.approve.payroll')
    expect(bank).toContain('useVisibilityRefetchInterval')
  })

  it('inbox API localizes catalog titles', () => {
    const app = read('wathefni-orchestrator/app.py')
    const outbound = read('wathefni-orchestrator/outbound_delivery.py')
    expect(outbound).toContain('def catalog_label')
    expect(outbound).toContain('label_ar')
    expect(app).toContain('catalog_label')
    expect(app).toContain('locale: str | None = Query')
  })
})
