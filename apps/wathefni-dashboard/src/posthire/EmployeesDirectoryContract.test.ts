import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHireSrc = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const employeesStart = postHireSrc.indexOf('function EmployeesPage(')
const employeesEnd = postHireSrc.indexOf('// --- Employee 360')
const employeesSrc = postHireSrc.slice(employeesStart, employeesEnd)
const addStart = postHireSrc.indexOf('function AddEmployeeModal(')
const addEnd = postHireSrc.indexOf('function EditEmployeeModal(')
const addSrc = postHireSrc.slice(addStart, addEnd)
const importStart = postHireSrc.indexOf('function ImportEmployeesModal(')
const importSrc = postHireSrc.slice(importStart, employeesStart)
const pageMount = postHireSrc.slice(
  postHireSrc.indexOf('export function PostHirePage('),
  postHireSrc.indexOf('function PostHireModuleBody('),
)

describe('Employees directory Wave 1 contract', () => {
  it('keeps directory as the dominant surface and drops duplicated attention chrome', () => {
    expect(employeesSrc).toContain('data-testid="employees-directory-board"')
    expect(employeesSrc).toContain('data-testid="employees-mobile-cards"')
    expect(employeesSrc).toContain('data-testid="employees-desktop-table"')
    expect(employeesSrc).not.toContain('<NextAction')
    expect(employeesSrc).not.toContain('<StatCard')
    expect(employeesSrc).not.toContain('<ModuleToolbar')
    expect(employeesSrc).toContain("dir={copy.isAr ? 'rtl' : 'ltr'}")
  })

  it('exposes search, status, department, and onboarding under More filters', () => {
    expect(employeesSrc).toContain('statusFilter')
    expect(employeesSrc).toContain('departmentFilter')
    expect(employeesSrc).toContain('onboardingFilter')
    expect(employeesSrc).toContain('showMoreFilters')
    expect(employeesSrc).toContain('copy.moreFilters')
  })

  it('keeps Add/Import roster actions and softens Refresh', () => {
    expect(employeesSrc).toContain('setShowAdd(true)')
    // Import entry moved behind Migration & Sync (ImportEmployeesModal still exists).
    expect(employeesSrc).toContain('setShowMigration(true)')
    expect(employeesSrc).toContain('copy.migrationSync')
    expect(employeesSrc).toContain('variant="ghost"')
    expect(employeesSrc).toContain('aria-label={copy.refresh}')
  })

  it('does not show delivery strip on Employees', () => {
    expect(pageMount).not.toContain('<DeliveryStatusStrip')
    expect(pageMount).toContain('no duplicate DeliveryStatusStrip')
  })

  it('keeps Add Employee small with phone separate from WhatsApp and governed departments', () => {
    expect(addSrc).toContain('getEmployeeOrgUnits')
    expect(addSrc).toContain('copy.phone')
    expect(addSrc).toContain('copy.whatsappNote')
    expect(addSrc).toContain('copy.phoneHint')
    expect(addSrc).toContain('touched')
    expect(addSrc).not.toContain('Phone / WhatsApp')
  })

  it('requires Import preview before confirm and reuses importEmployees authority', () => {
    expect(importSrc).toContain('importEmployees(access, {')
    expect(importSrc).toContain('dryRun')
    expect(importSrc).toContain('batchId')
    expect(importSrc).toContain('disabled={busy || !file || !preview}')
    expect(importSrc).toContain('copy.confirmImport')
    expect(importSrc).toContain('copy.previewFirst')
    expect(importSrc).toContain('downloadEmployeeImportExceptions')
  })
})
