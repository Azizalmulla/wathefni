import { screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { BenefitsWorkspace } from '@/posthire/BenefitsWorkspace'
import { CompensationPlanningWorkspace } from '@/posthire/CompensationPlanningWorkspace'
import { IntelligenceWorkspace } from '@/posthire/intelligence/IntelligenceWorkspace'
import { LearningWorkspace } from '@/posthire/LearningWorkspace'
import { PerformanceWorkspace } from '@/posthire/PerformanceWorkspace'
import { renderWithProviders } from '@/test/render'
import type { DashboardAccess } from '@/types'

const access = {
  token: 'test-token',
  companyCode: 'WATHEFNI',
  baseUrl: 'http://localhost',
  hrPhone: '+96500000000',
} as DashboardAccess

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('HR Web workspace request failures', () => {
  test('Benefits workspace failure renders error, not an empty enrollment list', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)))
    renderWithProviders(
      <BenefitsWorkspace access={access} permissions={['benefits.manage']} role="owner" onNotice={vi.fn()} />,
    )
    const state = await screen.findByTestId('benefits-workspace-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No enrollments/i)).not.toBeInTheDocument()
  })

  test('Learning workspace failure renders error, not an empty assignment list', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)))
    renderWithProviders(
      <LearningWorkspace access={access} permissions={['learning.manage']} role="owner" onNotice={vi.fn()} />,
    )
    const state = await screen.findByTestId('learning-workspace-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No learning assigned/i)).not.toBeInTheDocument()
  })

  test('Compensation Planning workspace failure renders error, not no compensation changes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)))
    renderWithProviders(
      <CompensationPlanningWorkspace
        access={access}
        permissions={['comp_planning.manage']}
        role="owner"
        onNotice={vi.fn()}
      />,
    )
    const state = await screen.findByTestId('compensation-planning-workspace-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No compensation/i)).not.toBeInTheDocument()
  })

  test('Performance workspace failure renders error, not an empty goals list', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)))
    renderWithProviders(
      <PerformanceWorkspace
        access={access}
        permissions={['performance.manage']}
        role="owner"
        onNotice={vi.fn()}
      />,
    )
    const state = await screen.findByTestId('performance-workspace-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
  })

  test('Intelligence bootstrap failure renders error, not a no-KPIs empty state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)))
    renderWithProviders(
      <IntelligenceWorkspace access={access} permissions={[]} role="owner" onNotice={vi.fn()} />,
    )
    const state = await screen.findByTestId('intelligence-workspace-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
  })
})
