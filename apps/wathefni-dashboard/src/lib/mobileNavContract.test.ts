import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

describe('mobile pre-hiring navigation contract', () => {
  const src = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')

  test('mobile uses PRE-HIRING-only rail with sticky active chip and More overflow', () => {
    expect(src).toContain('data-testid="mobile-prehire-nav"')
    expect(src).toContain('data-testid="mobile-active-route-chip"')
    expect(src).toContain('data-testid="mobile-prehire-rail"')
    expect(src).toContain('data-testid="mobile-nav-more"')
    expect(src).toContain('prehireNavItems')
    expect(src).toContain('otherNavItems')
    expect(src).toContain('.filter((item) => item.id !== activePage)')
  })

  test('desktop/mobile nav are mutually exclusive via matchMedia; prehire rail scoped', () => {
    expect(src).toContain("matchMedia('(min-width: 1024px)')")
    expect(src).toContain('useFramedShell && !isLgUp')
    expect(src).toContain('(!useFramedShell || isLgUp)')
    expect(src).toContain("'desktop-workspace-nav'")
    expect(src).toContain("item.group === 'prehire'")
  })
})
