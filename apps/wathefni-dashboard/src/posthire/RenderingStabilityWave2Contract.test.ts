import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '..')
const buttonSrc = readFileSync(resolve(root, 'components/ui/button.tsx'), 'utf8')
const clientSrc = readFileSync(resolve(root, 'lib/query/client.ts'), 'utf8')
const hooksSrc = readFileSync(resolve(root, 'lib/query/hooks.ts'), 'utf8')
const softKeepSrc = readFileSync(resolve(root, 'components/ui/SoftKeepSurface.tsx'), 'utf8')
const loaderSrc = readFileSync(resolve(root, 'lib/query/useSoftKeepLoader.ts'), 'utf8')
const contractSrc = readFileSync(resolve(root, 'lib/renderingStability.ts'), 'utf8')
const calendarSrc = readFileSync(resolve(root, 'components/CalendarShell.tsx'), 'utf8')
const overviewCalSrc = readFileSync(resolve(root, 'components/OverviewCalendarPanel.tsx'), 'utf8')
const appSrc = readFileSync(resolve(root, 'App.tsx'), 'utf8')
const alertsSrc = readFileSync(resolve(root, 'pages/NotificationsPage.tsx'), 'utf8')
const closeSrc = readFileSync(resolve(root, 'posthire/CloseExportWorkspace.tsx'), 'utf8')
const statutorySrc = readFileSync(resolve(root, 'posthire/StatutoryWorksheetWorkspace.tsx'), 'utf8')
const iqSrc = readFileSync(resolve(root, 'posthire/InteractionQualityWave1Contract.test.ts'), 'utf8')

describe('Rendering Stability Wave 2 contract', () => {
  it('documents shared soft-keep QueryClient default and work-queue opt-out', () => {
    expect(clientSrc).toContain('placeholderData: keepPreviousData')
    expect(clientSrc).toContain('Rendering Stability Wave 2')
    expect(hooksSrc).toMatch(/useWorkQueueQuery[\s\S]*placeholderData: undefined/)
  })

  it('ships SoftKeepSurface and useSoftKeepLoader with latest-request wins', () => {
    expect(softKeepSrc).toContain('data-rendering-soft-keep')
    expect(softKeepSrc).toContain('data-rendering-updating-rail')
    expect(softKeepSrc).not.toContain('opacity-')
    expect(loaderSrc).toContain('requestIdRef')
    expect(loaderSrc).toContain('loading = refreshing && data === null')
    expect(contractSrc).toContain('Keep previous content visible')
  })

  it('keeps Button pending width stable via overlay spinner', () => {
    expect(buttonSrc).toContain('data-button-pending-slot')
    expect(buttonSrc).toContain('opacity-0')
    expect(buttonSrc).toContain('absolute')
  })

  it('removes Calendar and Overview calendar opacity flashes', () => {
    expect(calendarSrc).toContain('data-rendering-updating')
    expect(calendarSrc).not.toMatch(/opacity-95/)
    expect(overviewCalSrc).not.toMatch(/opacity-90/)
  })

  it('soft-keeps Ranking same-job refresh without shell busy', () => {
    expect(appSrc).toContain('rankingBusy')
    expect(appSrc).toContain('rankingLoadedPositionRef')
    expect(appSrc).toContain('const sameJob = rankingLoadedPositionRef.current === position')
    expect(appSrc).toContain('if (!sameJob) setRanking(null)')
    expect(appSrc).toContain('setRankingBusy(true)')
  })

  it('soft-keeps Alerts and payroll worksheet refreshes', () => {
    expect(alertsSrc).toContain('alertsPaintedRef')
    expect(alertsSrc).toContain('setRefreshing(true)')
    expect(alertsSrc).toContain('data-alerts-refreshing')
    expect(closeSrc).toContain('paintedRef')
    expect(closeSrc).toContain('if (loading && !data)')
    expect(statutorySrc).toContain('if (loading && !data)')
  })

  it('does not weaken Interaction Quality Wave 1 contract file', () => {
    expect(iqSrc).toContain('Interaction Quality & Loading Integrity Wave 1 contract')
  })
})
