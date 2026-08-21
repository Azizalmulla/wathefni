import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

describe('Pre-hire semantic color contract', () => {
  test('shared soft/ink tokens remain in theme', () => {
    const css = read('index.css')
    for (const token of [
      'wf-accent-priority-soft',
      'wf-accent-priority-ink',
      'wf-accent-review-soft',
      'wf-accent-review-ink',
      'wf-accent-assess-soft',
      'wf-accent-assess-ink',
      'wf-accent-follow-soft',
      'wf-accent-follow-ink',
      'wf-accent-paused-soft',
      'wf-accent-paused-ink',
      'wf-accent-active-soft',
      'wf-accent-active-ink',
    ]) {
      expect(css).toContain(`--color-${token}`)
    }
  })

  test('Jobs status tiles use soft+ink pastel pairs', () => {
    const src = read('pages/JobsPage.tsx')
    expect(src).toContain('bg-wf-accent-priority-soft')
    expect(src).toContain('text-wf-accent-priority-ink')
    expect(src).toContain('bg-wf-accent-review-soft')
    expect(src).toContain('text-wf-accent-review-ink')
    expect(src).toContain('bg-wf-accent-paused-soft')
    expect(src).toContain('text-wf-accent-paused-ink')
    expect(src).toContain('bg-wf-accent-follow-soft')
    expect(src).toContain('text-wf-accent-follow-ink')
  })

  test('Candidates stay quiet cream with muted stages except outcomes', () => {
    const page = read('pages/CandidatesPage.tsx')
    const table = read('components/candidates/CandidatesTable.tsx')
    const tones = read('lib/candidatesListPresentation.ts')
    expect(page).toContain('tone="board"')
    expect(page).not.toContain('people-band')
    expect(table).toContain('bg-semantic-accent-soft')
    expect(table).toContain('bg-wf-accent-review')
    expect(table).toContain('text-semantic-ink')
    expect(tones).toContain("if (key === STAGE_BUCKET_HIRED) return 'priority'")
    expect(tones).toContain("if (key === STAGE_BUCKET_READY) return 'review'")
    expect(tones).toContain('return \'muted\'')
  })

  test('Interviews summary tiles use schedule/attention/complete fills', () => {
    const src = read('pages/InterviewsPage.tsx')
    expect(src).toContain('bg-wf-accent-follow')
    expect(src).toContain('text-wf-accent-follow-ink')
    expect(src).toContain('bg-wf-accent-review')
    expect(src).toContain('text-wf-accent-review-ink')
    expect(src).toContain('bg-wf-accent-priority')
    expect(src).toContain('text-wf-accent-priority-ink')
  })

  test('Assessments use assess/review soft panels', () => {
    const src = read('pages/AssessmentsPage.tsx')
    expect(src).toContain('bg-wf-accent-assess-soft')
    expect(src).toContain('text-wf-accent-assess-ink')
    expect(src).toContain('bg-wf-accent-review-soft')
    expect(src).toContain('text-wf-accent-review-ink')
  })

  test('Ranking top-3 use priority / follow / assess-soft washes', () => {
    const src = read('pages/RankingPage.tsx')
    expect(src).toContain('bg-wf-accent-priority')
    expect(src).toContain('text-wf-accent-priority-ink')
    expect(src).toContain('bg-wf-accent-follow')
    expect(src).toContain('text-wf-accent-follow-ink')
    expect(src).toContain('bg-wf-accent-assess-soft')
    expect(src).toContain('text-wf-accent-assess-ink')
  })

  test('Reports stay quiet cream with tiny dots and black count pills', () => {
    const src = read('pages/ReportsPage.tsx')
    expect(src).toContain('bg-wf-accent-priority')
    expect(src).toContain('bg-wf-accent-review')
    expect(src).toContain('bg-wf-accent-assess')
    expect(src).toContain('bg-wf-accent-follow')
    expect(src).toContain('h-2 w-2 shrink-0 rounded-full')
    expect(src).toContain('bg-semantic-ink px-2 text-[11px] font-semibold text-white')
    expect(src).not.toContain('Badge tone="muted"')
  })

  test('Assistant suggestion chips stay neutral (no capability tint)', () => {
    const src = read('pages/AdminAIPage.tsx')
    expect(src).toContain('bg-semantic-surface/45')
    expect(src).toContain('assistant-empty-chips')
    expect(src).not.toMatch(/assistant-empty-chips[\s\S]{0,800}wf-accent-/)
  })
})

describe('HR Web semantic token layer (palette is not frozen)', () => {
  test('semantic aliases exist and only reference other tokens', () => {
    const css = read('index.css')
    const tokens = [
      'semantic-canvas',
      'semantic-frame',
      'semantic-sidebar',
      'semantic-surface',
      'semantic-surface-raised',
      'semantic-ink',
      'semantic-ink-muted',
      'semantic-text',
      'semantic-subtle',
      'semantic-mist',
      'semantic-line',
      'semantic-accent',
      'semantic-accent-soft',
      'semantic-danger',
      'semantic-success',
      'semantic-warning',
      'semantic-info',
    ]
    for (const token of tokens) {
      const match = css.match(new RegExp(`--color-${token}:\\s*([^;]+);`))
      expect(match, token).toBeTruthy()
      expect(match![1].trim().startsWith('var('), `${token} must alias, not freeze a hex`).toBe(true)
      expect(match![1]).not.toMatch(/#[0-9a-fA-F]{3,8}/)
    }
  })
})
