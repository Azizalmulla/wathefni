import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

describe('global dashboard shell contract', () => {
  const appSrc = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
  const cssSrc = readFileSync(resolve(__dirname, '../index.css'), 'utf8')
  const authSrc = readFileSync(resolve(__dirname, '../pages/ShellStates.tsx'), 'utf8')
  const htmlSrc = readFileSync(resolve(__dirname, '../../index.html'), 'utf8')
  const mainSrc = readFileSync(resolve(__dirname, '../main.tsx'), 'utf8')
  const localeSrc = readFileSync(resolve(__dirname, './dashboardLocale.ts'), 'utf8')

  test('app shell fills viewport, locks outer scroll, and scrolls main only', () => {
    expect(appSrc).toContain('data-testid="app-shell"')
    expect(appSrc).toContain('data-testid="app-sidebar"')
    expect(appSrc).toContain('data-testid="app-main"')
    expect(appSrc).toContain('app-shell flex h-dvh w-full flex-col overflow-hidden')
    expect(appSrc).toContain('lg:h-dvh lg:w-[210px]')
    expect(appSrc).toContain('min-h-0 overflow-y-auto lg:h-dvh')
    // No floating outer frame
    expect(appSrc).not.toContain('rounded-[2rem]')
    expect(appSrc).not.toContain('bg-wf-canvas p-3')
    expect(appSrc).not.toContain('shadow-[0_30px_80px_rgba(35,33,29,0.16)]')
    expect(appSrc).not.toContain('h-[calc(100dvh-1.5rem)]')
  })

  test('html/body/root are non-scrolling viewport containers', () => {
    expect(cssSrc).toContain('html,')
    expect(cssSrc).toContain('body,')
    expect(cssSrc).toContain('#root {')
    expect(cssSrc).toMatch(/html,\s*body,\s*#root\s*\{[^}]*overflow:\s*hidden/s)
    expect(cssSrc).toContain('height: 100dvh')
    expect(cssSrc).toContain('.wf-sidebar-scroll')
  })

  test('unauthenticated auth returns a dedicated surface before the signed-in sidebar', () => {
    const unauthIdx = appSrc.indexOf('if (showingInviteAcceptance || resolvedAccessIssue)')
    const unauthReturn = appSrc.indexOf('<AccessVerificationPage', unauthIdx)
    const resolvingIdx = appSrc.indexOf('if (!sessionValidated)')
    const resolvingReturn = appSrc.indexOf('<AuthSessionResolvingPage', resolvingIdx)
    const sidebarIdx = appSrc.indexOf('data-testid="app-sidebar"')
    expect(unauthIdx).toBeGreaterThan(-1)
    expect(unauthReturn).toBeGreaterThan(unauthIdx)
    expect(resolvingIdx).toBeGreaterThan(unauthIdx)
    expect(resolvingReturn).toBeGreaterThan(resolvingIdx)
    expect(unauthReturn).toBeLessThan(sidebarIdx)
    expect(resolvingReturn).toBeLessThan(sidebarIdx)
    expect(appSrc).not.toContain('أكمل دعوة واثقني')
    expect(appSrc).not.toContain('تحقق من وصولك إلى واثقني')
    expect(authSrc).toContain('testId="octohr-auth-surface"')
    expect(authSrc).toContain('testId="octohr-auth-resolving"')
    expect(authSrc).not.toContain('Backup access')
    expect(authSrc).not.toContain('Workspace Access')
    expect(authSrc).not.toContain('Wathefni')
    expect(authSrc).not.toContain('واثقني')
    expect(authSrc).toContain('data-testid="octohr-auth-locale"')
    expect(authSrc).toContain('documentDirection(locale)')
    expect(authSrc).not.toContain('dir="ltr"')
  })

  test('document locale uses the canonical recruiting store and Arabic type stack', () => {
    expect(localeSrc).toContain("RECRUITING_LOCALE_STORAGE_KEY = 'wathefni_recruiting_locale'")
    expect(appSrc).toContain('readStoredRecruitingLocale')
    expect(appSrc).toContain('changeRecruitingLocale')
    expect(appSrc).toContain('applyDocumentLocale')
    expect(appSrc).not.toContain("localStorage.setItem('wathefni_recruiting_locale'")
    expect(mainSrc).toContain('applyDocumentLocale(readStoredRecruitingLocale())')
    expect(htmlSrc).toContain("localStorage.getItem('wathefni_recruiting_locale')")
    expect(htmlSrc).toContain('IBM+Plex+Sans+Arabic')
    expect(htmlSrc).toContain('family=Inter')
    expect(cssSrc).toContain('IBM Plex Sans Arabic')
    expect(cssSrc).toContain('html[lang="ar"]')
    expect(appSrc).toContain('text-start')
    expect(appSrc).toContain('border-e')
    expect(appSrc).toContain('end-6')
    expect(appSrc).not.toContain('text-left')
    expect(appSrc).not.toContain('border-r ')
    expect(appSrc).not.toContain('right-6')
  })

  test('non-overview pages mount after bootstrap and do not wait for hiring summary', () => {
    expect(appSrc).toContain("activePage === 'overview' ? overviewBootstrapped : workspaceBootstrapped")
    expect(appSrc).not.toContain('const dashboardLoaded = Boolean(moduleState && (!prehireEnabled || (summary && notifications)))')
  })
})
