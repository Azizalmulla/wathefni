import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const workspacePath = resolve(process.cwd(), 'src/posthire/intelligence/IntelligenceWorkspace.tsx')
const apiPath = resolve(process.cwd(), 'src/lib/intelligenceApi.ts')
const workspace = readFileSync(workspacePath, 'utf8')
const api = readFileSync(apiPath, 'utf8')

describe('Wave 5 C6 intelligence surface contract', () => {
  it('contains no KPI formula implementation', () => {
    expect(workspace).not.toMatch(/turnover\s*=/i)
    expect(workspace).not.toMatch(/\/\s*headcount/i)
  })

  it('uses governed intelligence evaluate endpoints', () => {
    expect(workspace).toContain('evaluateIntelligenceMetric')
    expect(workspace).toContain('getIntelligenceTrend')
    expect(api).toContain("/evaluate")
    expect(api).toContain("/segment")
    expect(api).toContain("/drill")
  })

  it('keeps Ops Attention separate', () => {
    expect(workspace).toContain('Ops Attention is separate from Intelligence')
    expect(workspace).toContain("onNavigate?.('inbox')")
  })
})

