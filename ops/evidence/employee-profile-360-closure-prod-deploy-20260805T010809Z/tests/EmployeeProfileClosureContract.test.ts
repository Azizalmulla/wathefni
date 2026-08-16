import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHireSrc = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const profileStart = postHireSrc.indexOf('function EmployeeProfile(')
const profileEnd = postHireSrc.indexOf('// --- Onboarding')
const profileSrc = postHireSrc.slice(profileStart, profileEnd)
const panelsSrc = readFileSync(resolve(__dirname, './employees360/ProfilePanels.tsx'), 'utf8')
const editStart = postHireSrc.indexOf('function EditEmployeeModal(')
const editEnd = postHireSrc.indexOf('type ActivationHandoff')
const editSrc = postHireSrc.slice(editStart, editEnd)

describe('Employee Profile / 360 closure contract', () => {
  it('locks body scroll on roster overlays and edit', () => {
    expect(postHireSrc).toContain('function AddEmployeeModal(')
    expect(postHireSrc.indexOf('useBodyScrollLock(true)', postHireSrc.indexOf('function AddEmployeeModal('))).toBeGreaterThan(0)
    expect(editSrc).toContain('useBodyScrollLock(true)')
    expect(editSrc).toContain('useOverlayFocus(true, onClose, panelRef)')
    expect(editSrc).not.toContain('Phone / WhatsApp')
    expect(editSrc).toContain("dir={copy.isAr ? 'rtl' : 'ltr'}")
  })

  it('keeps profile RTL, deep-link sync, and section anchors for next actions', () => {
    expect(profileSrc).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(profileSrc).toContain('data-testid="employee-profile"')
    expect(profileSrc).toContain('id="emp360-section-documents"')
    expect(profileSrc).toContain('id="emp360-section-onboarding"')
    expect(profileSrc).toContain("onNavigate?.('shifts'")
    expect(profileSrc).toContain("onNavigate?.('attendance'")
    expect(profileSrc).toContain("onNavigate?.('payroll'")
    expect(postHireSrc).toContain("window.addEventListener('popstate', syncFromUrl)")
  })

  it('replaces window.prompt status/activation flows with calm dialogs', () => {
    expect(profileSrc).not.toContain('window.prompt')
    expect(profileSrc).toContain('ApproverPickModal')
    expect(profileSrc).toContain('confirm.withReason')
    expect(profileSrc).toContain('Approve without a second person?')
  })

  it('keeps assignment history soft-keep and HR language (no Wave 4 jargon)', () => {
    expect(panelsSrc).toContain('hasRowsRef')
    expect(panelsSrc).not.toContain('Wave 4')
    expect(panelsSrc).toContain('read-only here')
    expect(panelsSrc).toContain('Manager')
  })

  it('does not invent payroll/shift mutations beyond existing timesheet approve gate', () => {
    expect(profileSrc).toContain("action.run('approve_timesheet'")
    expect(profileSrc).toContain('Open in Payroll')
    expect(profileSrc).toContain('Open in Shifts')
    expect(profileSrc).not.toContain('run_payroll')
  })
})
