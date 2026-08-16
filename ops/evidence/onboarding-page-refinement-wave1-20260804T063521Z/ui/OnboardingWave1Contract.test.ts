import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const onboardingStart = postHire.indexOf('function OnboardingPage(')
const onboardingEnd = postHire.indexOf('function AttendanceCorrectionRow(', onboardingStart)
const onboardingSrc = postHire.slice(onboardingStart, onboardingEnd)
const inboxStart = postHire.indexOf('function ActionInboxPage(')
const inboxSrc = postHire.slice(inboxStart, postHire.indexOf('function AnalyticsPage(', inboxStart))
const profileSection = postHire.slice(
  postHire.indexOf('id="emp360-section-onboarding"'),
  postHire.indexOf('id="emp360-section-compliance"'),
)

describe('Onboarding Wave 1 refinement contract', () => {
  it('is queue-first with filters and no oversized still-onboarding banner', () => {
    expect(onboardingSrc).toContain('onboarding-queue')
    expect(onboardingSrc).toContain('onboarding-filters')
    expect(onboardingSrc).toContain('needs_attention')
    expect(onboardingSrc).toContain('not_started')
    expect(onboardingSrc).not.toContain('still onboarding')
    expect(onboardingSrc).not.toContain('<NextAction')
    expect(onboardingSrc).not.toContain('BlockedReason')
  })

  it('uses one primary action and secondary More menu', () => {
    expect(onboardingSrc).toContain('MoreHorizontal')
    expect(onboardingSrc).toContain('send_onboarding_reminder')
    expect(onboardingSrc).toContain('reschedule_onboarding')
    expect(onboardingSrc).toContain('cancel_onboarding')
    expect(onboardingSrc).toMatch(/confirm:\s*\{[\s\S]*Cancel onboarding/)
  })

  it('honors employee deep-link with expand, URL sync, and pin/scroll', () => {
    expect(onboardingSrc).toContain("get('employee')")
    expect(onboardingSrc).toContain('focusEmployee')
    expect(onboardingSrc).toContain('scrollIntoView')
    expect(onboardingSrc).toContain('syncEmployeeParam')
    expect(onboardingSrc).toContain('focusPin')
  })

  it('keeps mutation integrity confirm handshake', () => {
    expect(onboardingSrc).toContain('usePosthireAction')
    expect(onboardingSrc).toMatch(/confirm:\s*\{/)
    expect(onboardingSrc).toContain('onSuccess')
  })
})

describe('Needs Attention polish in Onboarding wave', () => {
  it('removes duplicated inner Needs Attention heading', () => {
    expect(inboxSrc).not.toMatch(/<h2[^>]*>[\s\S]*Needs Attention/)
    expect(inboxSrc).not.toContain('ما بعد التوظيف')
    expect(inboxSrc).toContain('needs-attention-board')
  })

  it('excludes delivery strip from inbox and onboarding mounts', () => {
    expect(postHire).toMatch(/page === 'employees' \|\| page === 'inbox' \|\| page === 'onboarding'/)
  })
})

describe('Profile onboarding ownership', () => {
  it('demotes profile checklist mutates to Open in Onboarding', () => {
    expect(profileSection).toContain('Open in Onboarding')
    expect(profileSection).not.toContain('onboarding_mark_item')
    expect(profileSection).not.toContain('send_onboarding_reminder')
  })
})
