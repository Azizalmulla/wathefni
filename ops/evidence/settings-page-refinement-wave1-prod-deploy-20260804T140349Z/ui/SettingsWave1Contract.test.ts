import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const settingsSrc = readFileSync(resolve(__dirname, '../pages/SettingsPage.tsx'), 'utf8')
const appSrc = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')

describe('Settings Page Refinement Wave 1 contract', () => {
  it('has compact purpose and clear ownership honesty', () => {
    expect(settingsSrc).toContain('data-settings')
    expect(settingsSrc).toContain('data-settings-purpose')
    expect(settingsSrc).toContain('data-settings-ownership')
    expect(settingsSrc).toContain('without changing role permissions or delivery ownership')
    expect(settingsSrc).toContain('Setup Console')
    expect(settingsSrc).toContain('Alerts & Delivery')
  })

  it('keeps bilingual RTL shell and demotes capability dump', () => {
    expect(settingsSrc).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(settingsSrc).toContain("lang={locale}")
    expect(settingsSrc).toContain('useEmployees360Locale')
    expect(settingsSrc).toMatch(/<details[\s\S]*What you can do/)
  })

  it('renames sections to HR language and softens integrations copy', () => {
    expect(settingsSrc).toContain('data-settings-account')
    expect(settingsSrc).toContain('data-settings-access')
    expect(settingsSrc).toContain('data-settings-team')
    expect(settingsSrc).toContain('data-settings-communications')
    expect(settingsSrc).toContain('Company connections')
    expect(settingsSrc).not.toContain('Requires settings and calendar sync authority')
    expect(settingsSrc).not.toContain('Platform Integrations')
  })

  it('preserves permission gates and existing mutation APIs', () => {
    expect(settingsSrc).toContain('users.manage')
    expect(settingsSrc).toContain('settings.manage')
    expect(settingsSrc).toContain('calendar.sync')
    expect(settingsSrc).toContain('candidate.import')
    expect(settingsSrc).toContain('putPrehireVisibilityPolicy')
    expect(settingsSrc).toContain('onInvite')
    expect(settingsSrc).toContain('onUpdateUser')
    expect(appSrc).toContain('how Wathefni connects company tools')
  })
})
