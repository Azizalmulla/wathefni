import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'


const source = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8')


describe('dashboard interaction contracts', () => {
  test('post-hire employee deep links survive page navigation and notify observers', () => {
    const start = source.indexOf('onNavigate={(nextPage, opts) => {')
    const end = source.indexOf('}}', start)
    const callback = source.slice(start, end)
    expect(start).toBeGreaterThan(-1)
    expect(callback.indexOf('openPage(nextPage as Page)')).toBeLessThan(
      callback.indexOf("url.searchParams.set('employee', opts.employee)"),
    )
    expect(callback).toContain("window.dispatchEvent(new PopStateEvent('popstate'))")
  })

  test('sidebar and mobile navigation follow the selected locale direction', () => {
    expect(source).not.toContain('data-testid="app-sidebar"\n          dir="ltr"')
    expect(source).not.toContain('data-testid="mobile-prehire-nav" dir="ltr"')
  })
})
