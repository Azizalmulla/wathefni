import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const inboxStart = postHire.indexOf('function ActionInboxPage(')
const inboxEnd = postHire.indexOf('function AnalyticsPage(', inboxStart)
const inboxSrc = postHire.slice(inboxStart, inboxEnd)
const onboardingStart = postHire.indexOf('function OnboardingPage(')
const onboardingSrc = postHire.slice(onboardingStart, postHire.indexOf('function AttendancePage(', onboardingStart))
const appSrc = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
const capSrc = readFileSync(resolve(__dirname, '../lib/workspaceCapability.ts'), 'utf8')

describe('Needs Attention Wave 1 contract', () => {
  it('renames user-facing labels while keeping page id inbox', () => {
    expect(appSrc).toMatch(/inbox: 'Needs Attention'/)
    expect(appSrc).toMatch(/inbox: 'يحتاج متابعة'/)
    expect(appSrc).toMatch(/الأمور التي تحتاج متابعتك|Ranked follow-ups/)
    expect(capSrc).toMatch(/label: 'Needs Attention'/)
    expect(inboxSrc).toContain("data-testid=\"needs-attention-page\"")
    expect(inboxSrc).not.toContain('Action Inbox')
    expect(inboxSrc).not.toContain('صندوق الإجراءات')
  })

  it('keeps ranked list dominant with presentation filters and slim rows', () => {
    expect(inboxSrc).toContain('needs-attention-board')
    expect(inboxSrc).toContain('needs-attention-filters')
    expect(inboxSrc).toContain('needs_action')
    expect(inboxSrc).toContain('due_soon')
    expect(inboxSrc).toContain('blocked')
    expect(inboxSrc).toContain('urgencyMeta')
    expect(inboxSrc).not.toContain('System of action')
    expect(inboxSrc).not.toContain('Employees 360')
    expect(inboxSrc).toContain('expandedId')
  })

  it('routes to owning modules and honors onboarding employee focus', () => {
    expect(inboxSrc).toContain('honorsEmployee')
    expect(inboxSrc).toContain("page === 'onboarding'")
    expect(onboardingSrc).toContain("get('employee')")
    expect(onboardingSrc).toContain('focusEmployee')
    expect(onboardingSrc).toContain('loadDetail')
  })

  it('does not duplicate shell heading or host delivery strip', () => {
    expect(inboxSrc).not.toMatch(/<h2[^>]*>[\s\S]*Needs Attention/)
    expect(postHire).toContain('no duplicate DeliveryStatusStrip')
    expect(postHire).not.toMatch(/<DeliveryStatusStrip[\s>]/)
  })

  it('surfaces backend-grouped document cases without client-side regrouping', () => {
    expect(inboxSrc).toContain('grouped_document_types')
    expect(inboxSrc).toContain('needs-attention-grouped-docs')
    expect(inboxSrc).not.toContain('groupByEmployee')
  })
})
