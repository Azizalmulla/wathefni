import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const payrollStart = postHire.indexOf('function PayrollPage(')
const payrollEnd = postHire.indexOf('function PayrollTimesheetsPage(', payrollStart)
const payrollSrc = postHire.slice(payrollStart, payrollEnd > 0 ? payrollEnd : payrollStart + 4000)
const externalSrc = readFileSync(resolve(__dirname, './ExternalPayrollWorkspace.tsx'), 'utf8')

describe('Payroll Wave 1 IA refinement contract', () => {
  it('collapses peer tabs to Run / Hours / Records', () => {
    expect(payrollSrc).toContain("useState<'run' | 'hours' | 'records'>('run')")
    expect(payrollSrc).toContain('data-payroll-surfaces')
    expect(payrollSrc).toContain('surfaceRun')
    expect(payrollSrc).toContain('surfaceHours')
    expect(payrollSrc).toContain('surfaceRecords')
    expect(payrollSrc).toContain('data-payroll-records-panels')
    expect(payrollSrc).not.toMatch(/useState<'timesheets' \| 'external'/)
  })

  it('defaults to Run (external money path) and keeps hours + records mounts', () => {
    expect(payrollSrc).toContain('ExternalPayrollWorkspace')
    expect(payrollSrc).toContain('PayrollTimesheetsPage')
    expect(payrollSrc).toContain('PayslipWorkspace')
    expect(payrollSrc).toContain('CloseExportWorkspace')
    expect(payrollSrc).toContain('StatutoryWorksheetWorkspace')
    expect(payrollSrc).toContain("surface === 'run'")
  })

  it('excludes delivery strip from Payroll mounts', () => {
    expect(postHire).toContain('no duplicate DeliveryStatusStrip')
    expect(postHire).not.toMatch(/<DeliveryStatusStrip[\s>]/)
  })

  it('demotes External honesty off first paint and removes duplicate Run h2', () => {
    expect(externalSrc).toContain('honestyOpen')
    expect(externalSrc).toContain('data-payroll-honesty-toggle')
    expect(externalSrc).toMatch(/honestyOpen \? \(/)
    expect(externalSrc).not.toMatch(/<h2[^>]*>[\s\S]*\{c\.title\}/)
  })

  it('demotes Records workspace honesty and removes duplicate h2s', () => {
    const payslip = readFileSync(resolve(__dirname, './PayslipWorkspace.tsx'), 'utf8')
    const close = readFileSync(resolve(__dirname, './CloseExportWorkspace.tsx'), 'utf8')
    const statutory = readFileSync(resolve(__dirname, './StatutoryWorksheetWorkspace.tsx'), 'utf8')
    for (const src of [payslip, close, statutory]) {
      expect(src).toContain('honestyOpen')
      expect(src).toContain('data-payroll-honesty-toggle')
      expect(src).not.toMatch(/<h2[^>]*>[\s\S]*\{c\.title\}/)
    }
  })

  it('softens Hours export primary so Approve remains the row primary', () => {
    expect(postHire).toContain('data-payroll-hours-export')
    expect(postHire).toMatch(/variant="secondary"[\s\S]{0,120}data-payroll-hours-export/)
  })
})
