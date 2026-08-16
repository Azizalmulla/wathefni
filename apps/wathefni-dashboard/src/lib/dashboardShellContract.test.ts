import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

describe('global dashboard shell contract', () => {
  const appSrc = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
  const cssSrc = readFileSync(resolve(__dirname, '../index.css'), 'utf8')

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
})
