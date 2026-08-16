import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const shiftsSrc = readFileSync(resolve(__dirname, './ShiftsWorkspace.tsx'), 'utf8')
const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const uxSrc = readFileSync(resolve(__dirname, './shiftsUx.ts'), 'utf8')

describe('Shifts Wave 1 IA refinement contract', () => {
  it('uses Schedule / Requests / Planning surfaces instead of eight peer tabs', () => {
    expect(shiftsSrc).toContain("SurfaceTab = 'schedule' | 'requests' | 'planning'")
    expect(shiftsSrc).toContain('data-shifts-surfaces')
    expect(shiftsSrc).toContain('surfaceSchedule')
    expect(shiftsSrc).toContain('surfaceRequests')
    expect(shiftsSrc).toContain('surfacePlanning')
    expect(shiftsSrc).toContain("useState<SurfaceTab>('schedule')")
    // Old peer tablist of board+swaps+availability+… should not drive first paint
    expect(shiftsSrc).not.toMatch(/\[\s*\['board',\s*c\.board\],\s*\['swaps'/)
  })

  it('makes Schedule the dominant surface with one primary Schedule a shift action', () => {
    expect(shiftsSrc).toContain('data-testid="shifts-board"')
    expect(shiftsSrc).toContain('data-primary-action="schedule"')
    expect(shiftsSrc).toContain('data-testid="shifts-add"')
    expect(shiftsSrc).toContain('data-shifts-attention')
    expect(shiftsSrc).toContain('data-shifts-date-chrome')
  })

  it('removes duplicated inner Shifts heading and main-view honesty/lab banner', () => {
    expect(shiftsSrc).not.toMatch(/<h1[^>]*>[\s\S]*\{c\.title\}/)
    expect(shiftsSrc).not.toMatch(/uppercase tracking-\[0\.18em\][\s\S]*Shifts/)
    // Honesty banner only under collapsed planning readiness
    expect(shiftsSrc).toContain('data-shifts-operations')
    expect(shiftsSrc).toContain('readinessOpen')
    expect(shiftsSrc).toMatch(/readinessOpen && wave3\?\.enabled/)
  })

  it('excludes delivery-failure strip from Shifts mounts', () => {
    expect(postHire).toMatch(/page === 'employees' \|\| page === 'inbox' \|\| page === 'onboarding' \|\| page === 'shifts'/)
  })

  it('uses governed compact org filters and quieter Refresh', () => {
    expect(shiftsSrc).toContain('getEmployeeOrgUnits')
    expect(shiftsSrc).toContain('data-shifts-filters')
    expect(shiftsSrc).toContain('allBranches')
    expect(shiftsSrc).toContain('allSites')
    expect(shiftsSrc).toContain('allTeams')
    expect(shiftsSrc).toContain('aria-label={c.refresh}')
    const filtersIdx = shiftsSrc.indexOf('data-shifts-filters')
    const boardIdx = shiftsSrc.indexOf('data-testid="shifts-board"', filtersIdx)
    const filtersBlock = shiftsSrc.slice(filtersIdx, boardIdx > filtersIdx ? boardIdx : filtersIdx + 1200)
    expect(filtersBlock).toContain('<select')
    expect(filtersBlock).toContain('allBranches')
    expect(filtersBlock).not.toContain('placeholder={c.branch}')
    expect(filtersBlock).not.toContain('placeholder={c.site}')
  })

  it('uses governed org selectors in create/edit composer with Unmapped legacy state', () => {
    expect(shiftsSrc).toContain('data-shifts-composer-org')
    expect(shiftsSrc).toContain('data-shifts-edit-org')
    expect(shiftsSrc).toContain('ORG_UNMAPPED')
    expect(shiftsSrc).toContain('unmappedOrg')
    expect(shiftsSrc).toContain('data-org-field="branch_key"')
    expect(shiftsSrc).toContain('data-org-field="site_key"')
    expect(shiftsSrc).toContain('data-org-field="team_key"')
    expect(shiftsSrc).toContain('data-org-field="location"')
    expect(shiftsSrc).toContain('childrenOfParent')
    expect(shiftsSrc).toContain('expected_updated_at')
    const createIdx = shiftsSrc.indexOf('data-shifts-composer-org')
    const createBlock = shiftsSrc.slice(createIdx, createIdx + 3500)
    expect(createBlock).not.toContain('placeholder={c.branch}')
    expect(createBlock).not.toContain('placeholder={c.site}')
    expect(createBlock).not.toContain('placeholder={c.team}')
  })

  it('moves advanced tools under Planning and keeps mutation contracts', () => {
    expect(shiftsSrc).toContain('data-shifts-planning')
    expect(shiftsSrc).toContain('createShift')
    expect(shiftsSrc).toContain('cancelShift')
    expect(shiftsSrc).toContain('rescheduleShift')
    expect(shiftsSrc).toContain('expected_updated_at')
    expect(shiftsSrc).toContain('approve_shift_swap')
    expect(shiftsSrc).toContain('resolveShiftReconciliation')
  })

  it('shows useful empty states with a clear next action', () => {
    expect(shiftsSrc).toContain('data-shifts-empty')
    expect(uxSrc).toContain('emptyBoardHint')
    expect(uxSrc).toContain('emptyRequestsHint')
  })
})
