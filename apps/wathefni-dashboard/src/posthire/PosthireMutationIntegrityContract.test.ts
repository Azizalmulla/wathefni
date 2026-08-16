import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const start = postHire.indexOf('function usePosthireAction(')
const end = postHire.indexOf('function employeeRef(', start)
const src = postHire.slice(start, end)

describe('Post-hire mutation integrity (client)', () => {
  it('returns a Promise from run and toasts on confirm dismiss', () => {
    expect(src).toContain('): Promise<boolean> =>')
    expect(src).toContain("Action cancelled — nothing changed.")
    expect(src).toContain('dashboardActionError')
    expect(src).toContain('mutations_disabled')
  })

  it('Onboarding Cancel/Reschedule/Mark use options.confirm preconfirm path', () => {
    expect(postHire).toMatch(/cancel_onboarding[\s\S]*confirm:\s*\{/)
    expect(postHire).toMatch(/reschedule_onboarding[\s\S]*onSuccess:\s*\(\)\s*=>\s*setRescheduleFor\(null\)/)
    expect(postHire).toMatch(/item_status: status[\s\S]*confirm:\s*[\s\S]*Mark this item complete/)
  })
})
