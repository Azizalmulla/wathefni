import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

describe('Assistant page UX contract', () => {
  test('wires React Profiler and interaction marks', () => {
    const src = readFileSync(resolve(__dirname, 'AdminAIPage.tsx'), 'utf8')
    expect(src).toContain('ReactProfiler')
    expect(src).toContain('dashboardPerfMarkProfilerCommit')
    expect(src).toContain('assistant_open_history')
    expect(src).toContain('assistant_open_candidate')
    expect(src).toContain('assistant_confirm')
    expect(src).toContain('assistant_nav')
    const app = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(app).toContain('assistant_send')
    expect(app).toContain('assistant_stream_done')
    expect(app).toContain('assistant_cancel')
    expect(app).toContain('assistant_planning')
  })

  test('supports EN/AR RTL and overlay a11y', () => {
    const src = readFileSync(resolve(__dirname, 'AdminAIPage.tsx'), 'utf8')
    expect(src).toContain("dir={isAr ? 'rtl' : 'ltr'}")
    expect(src).toContain('useOverlayFocus')
    expect(src).toContain('useBodyScrollLock')
    expect(src).toContain('aria-modal')
    expect(src).toContain("role=\"dialog\"")
    expect(src).toContain('assistantCopy')
  })

  test('handles assistant_prompt navigation and cancel', () => {
    const app = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(app).toContain("item.type === 'assistant_prompt'")
    expect(app).toContain('AbortController')
    expect(app).toContain('cancelDashboardAssistant')
    expect(app).toContain('signal: controller.signal')
    const api = readFileSync(resolve(__dirname, '../lib/api.ts'), 'utf8')
    expect(api).toContain('signal?: AbortSignal')
  })

  test('renders workflow preview/result and stop control', () => {
    const src = readFileSync(resolve(__dirname, 'AdminAIPage.tsx'), 'utf8')
    expect(src).toContain('WorkflowCardView')
    expect(src).toContain('workflowCard')
    expect(src).toContain('onCancel')
    expect(src).toContain('onRetryWorkflow')
    expect(src).toContain('progressPhase')
  })

  test('empty-state is capability-catalog driven', () => {
    const src = readFileSync(resolve(__dirname, 'AdminAIPage.tsx'), 'utf8')
    expect(src).toContain('emptyState')
    expect(src).toContain('emptyStateStatus')
    expect(src).toContain('assistant-empty-modules')
    expect(src).toContain('assistant-empty-loading')
    expect(src).toContain('assistant-empty-error')
    expect(src).toContain('assistant-empty-none')
    expect(src).toContain('assistant-empty-chips')
    expect(src).not.toContain('function assistantPromptChips')
    expect(src).not.toContain('promptChips')
    const app = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(app).toContain('getAssistantCapabilities')
    expect(app).toContain('emptyState={assistantEmptyState}')
    expect(app).toContain('emptyStateStatus={assistantEmptyStatus}')
    expect(app).toContain('loadAssistantCapabilities')
    expect(app).toContain('onReloadCapabilities')
    const api = readFileSync(resolve(__dirname, '../lib/api.ts'), 'utf8')
    expect(api).toContain('/dashboard/prehire/assistant/capabilities')
  })

  test('suggestion chips stay neutral cream (no capability tint)', () => {
    const src = readFileSync(resolve(__dirname, 'AdminAIPage.tsx'), 'utf8')
    expect(src).toContain('bg-white/45')
    expect(src).toContain('text-subtle')
    expect(src).not.toMatch(/assistant-empty-chips[\s\S]{0,800}wf-accent-/)
  })

  test('backend removes wording-only nav chips and WhatsApp-centric identity', () => {
    const artifacts = readFileSync(
      resolve(__dirname, '../../../../wathefni-orchestrator/app.py'),
      'utf8',
    )
    expect(artifacts).toContain('Navigation must come from grounded tool/policy results only')
    expect(artifacts).not.toMatch(/if \"ranking\" in text or \"rank\" in text/)
    const orch = readFileSync(
      resolve(__dirname, '../../../../wathefni-orchestrator/tool_call_orchestrator.py'),
      'utf8',
    )
    expect(orch).toContain('grounded HR operating copilot')
    expect(orch).not.toContain('speaking to a company HR admin on WhatsApp')
    expect(orch).not.toContain('cv_text, ranking_score')
  })
})
