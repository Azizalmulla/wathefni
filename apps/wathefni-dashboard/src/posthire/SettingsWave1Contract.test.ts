import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const settingsSrc = readFileSync(resolve(__dirname, '../pages/SettingsPage.tsx'), 'utf8')
const panelSrc = readFileSync(resolve(__dirname, '../components/PlatformIntegrationsPanel.tsx'), 'utf8')
const appSrc = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')

describe('Settings Wave 1 IA Closure contract', () => {
  it('exposes secondary navigation and section panels', () => {
    expect(settingsSrc).toContain('data-settings')
    expect(settingsSrc).toContain('data-settings-ia-closure')
    expect(settingsSrc).toContain('data-settings-nav')
    expect(settingsSrc).toContain("data-settings-nav-item={item.id}")
    expect(settingsSrc).toContain('data-settings-section="account"')
    expect(settingsSrc).toContain('data-settings-section="team"')
    expect(settingsSrc).toContain('data-settings-section="company"')
    expect(settingsSrc).toContain('data-settings-section="communications"')
    expect(settingsSrc).toContain('data-settings-section="integrations"')
    expect(settingsSrc).toContain('data-settings-section="advanced"')
    expect(settingsSrc).toContain('My account')
    expect(settingsSrc).toContain('Team & access')
    expect(settingsSrc).toContain('Communications')
    expect(settingsSrc).toContain('Integrations')
    expect(settingsSrc).toContain('Advanced')
  })

  it('separates personal, company, communications, and advanced surfaces', () => {
    expect(settingsSrc).toContain('data-settings-account')
    expect(settingsSrc).toContain('data-settings-team')
    expect(settingsSrc).toContain('data-settings-company')
    expect(settingsSrc).toContain('data-settings-communications')
    expect(settingsSrc).toContain('data-settings-intake')
    expect(settingsSrc).toContain('data-settings-advanced')
    expect(settingsSrc).toContain('IntakeSettingsCard')
    expect(settingsSrc).toContain('EmailSendingCard')
    expect(settingsSrc).toContain('EmailDocumentIntakeCard')
    expect(settingsSrc).toContain('variant="integrations"')
    expect(settingsSrc).toContain('variant="advanced"')
    expect(settingsSrc).not.toContain('data-settings-purpose')
    expect(settingsSrc).toContain('Setup guide')
  })

  it('keeps bilingual RTL shell and demotes capability dump', () => {
    expect(settingsSrc).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(settingsSrc).toContain('lang={locale}')
    expect(settingsSrc).toContain('useEmployees360Locale')
    expect(settingsSrc).toMatch(/<details[\s\S]*What you can do/)
  })

  it('uses governed role and deactivate confirms with audit context', () => {
    expect(settingsSrc).toContain('Change role?')
    expect(settingsSrc).toContain('Deactivate user?')
    expect(settingsSrc).toContain('recorded in Activity')
    expect(settingsSrc).toContain('destructive: true')
  })

  it('keeps plain language outside Advanced and technical tools inside', () => {
    expect(panelSrc).toContain("variant?: 'integrations' | 'advanced'")
    expect(panelSrc).toContain('Prepare backup calendar connection')
    expect(panelSrc).toContain('Company connection removed')
    expect(panelSrc).toContain('Setup guide')
    expect(panelSrc).toContain('Learn how')
    expect(panelSrc).toContain('data-settings-legacy-operator')
    expect(panelSrc).not.toContain('Ensure legacy operator')
    expect(settingsSrc).not.toContain('Ensure legacy operator')
    expect(settingsSrc).not.toContain('Platform Integrations')
    expect(settingsSrc).not.toContain('platform_integration_disconnected')
    expect(settingsSrc).not.toContain('C6B')
  })

  it('preserves permission gates, APIs, and delivery ownership honesty', () => {
    expect(settingsSrc).toContain('users.manage')
    expect(settingsSrc).toContain('settings.manage')
    expect(settingsSrc).toContain('calendar.sync')
    expect(settingsSrc).toContain('candidate.import')
    expect(settingsSrc).toContain('putPrehireVisibilityPolicy')
    expect(settingsSrc).toContain('onInvite')
    expect(settingsSrc).toContain('onUpdateUser')
    expect(settingsSrc).toContain('data-settings-ownership')
    expect(settingsSrc).toContain('Setup Console')
    expect(settingsSrc).toContain('Alerts & Delivery')
    expect(settingsSrc).toContain('without changing role permissions or delivery ownership')
    expect(appSrc).toContain('how OctoHR connects company tools')
  })
})
