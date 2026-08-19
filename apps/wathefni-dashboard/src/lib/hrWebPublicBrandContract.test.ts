import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

const SRC_ROOT = resolve(__dirname, '..')
const NATURAL_BRAND = /(?<![A-Za-z0-9_])Wathefni(?![A-Za-z0-9_])|واثقني|وظفني|وظّفني|وثفني|وثّفني|وطّفني/
const FORBIDDEN_PHRASES = [/WATHEFNI canary/i, /Wathefni Calendar/, /WATHEFNI-PYW1/]

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return walk(full)
    return [full]
  })
}

function isCommentLine(line: string) {
  const stripped = line.trim()
  return (
    stripped.startsWith('//')
    || stripped.startsWith('*')
    || stripped.startsWith('/*')
    || stripped.startsWith('{/*')
  )
}

describe('HR Web customer-visible branding', () => {
  test('production UI source does not leak legacy product names', () => {
    const files = walk(SRC_ROOT).filter((file) => {
      if (!file.endsWith('.tsx') && !file.endsWith('.ts') && !file.endsWith('.html')) return false
      if (file.includes('.test.') || file.endsWith('.test.ts') || file.endsWith('.test.tsx')) return false
      if (file.endsWith('publicBrand.ts')) return false
      return true
    })

    const defects: string[] = []
    for (const file of files) {
      const rel = relative(SRC_ROOT, file)
      const lines = readFileSync(file, 'utf8').split('\n')
      lines.forEach((line, index) => {
        if (isCommentLine(line)) return
        if (NATURAL_BRAND.test(line) || FORBIDDEN_PHRASES.some((pattern) => pattern.test(line))) {
          defects.push(`${rel}:${index + 1}: ${line.trim().slice(0, 200)}`)
        }
      })
    }

    expect(defects).toEqual([])
  })

  test('document title stays OctoHR', () => {
    const html = readFileSync(resolve(__dirname, '../../index.html'), 'utf8')
    expect(html).toContain('<title>OctoHR</title>')
    expect(html).not.toMatch(/Wathefni|واثقني|وظفني/)
  })
})
