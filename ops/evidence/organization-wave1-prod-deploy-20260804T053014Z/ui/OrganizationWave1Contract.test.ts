import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const src = readFileSync(resolve(__dirname, './WorkforcePage.tsx'), 'utf8')
const appSrc = readFileSync(resolve(__dirname, '../../App.tsx'), 'utf8')
const capSrc = readFileSync(resolve(__dirname, '../../lib/workspaceCapability.ts'), 'utf8')

describe('Organization (Workforce) Wave 1 contract', () => {
  it('renames the product surface to Organization while keeping page id workforce', () => {
    expect(appSrc).toMatch(/id: 'workforce', label: 'Organization'/)
    expect(appSrc).toMatch(/workforce: 'Organization'/)
    expect(appSrc).toMatch(/workforce: 'الهيكل التنظيمي'/)
    expect(capSrc).toMatch(/label: 'Organization'/)
    expect(src).toContain("data-page=\"organization\"")
    expect(src).toContain("data-testid=\"workforce-hub\"")
  })

  it('lands on structure and keeps admin queues behind Advanced', () => {
    expect(src).toContain('organization-structure-board')
    expect(src).toContain('organization-advanced-toggle')
    expect(src).toContain('organization-advanced-rail')
    expect(src).toContain('ADVANCED_SECTIONS')
    expect(src).toContain("PRIMARY_SECTION = 'organization'")
    expect(src).not.toContain('Employees 360')
    expect(src).not.toContain('عمليات القوى العاملة')
  })

    it('shows overview, hierarchy, mobile cards, and coverage without inventing planning', () => {
    expect(src).toContain('organization-overview')
    expect(src).toContain('organization-mobile-cards')
    expect(src).toContain('organization-desktop-table')
    expect(src).toContain('Parent unit')
    expect(src).toContain('Unit hierarchy')
    expect(src).toContain('not manager lines')
    expect(src).not.toContain('Reports under')
    expect(src).toContain('organization-coverage')
    expect(src).toContain('missing_wave4_as_of_assignment')
    expect(src).not.toMatch(/forecast|headcount plan|vacanc|budget/i)
  })

  it('opens employees in the existing profile path and gates view vs manage honestly', () => {
    expect(src).toContain("onNavigate('employees'")
    expect(src).toContain('canViewStructure')
    expect(src).toContain("employees.read")
    expect(src).toContain("section === 'lifecycle'")
    expect(src).toContain('Requires status approval or employees.manage')
    expect(src).toContain('Technical IDs')
  })
})
