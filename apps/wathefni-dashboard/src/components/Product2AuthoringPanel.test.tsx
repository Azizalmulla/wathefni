import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { Product2AuthoringPanel } from './Product2AuthoringPanel'
import type { DashboardAccess } from '@/types'

const access: DashboardAccess = {
  token: 'dashboard-token',
  companyCode: 'WATHEFNI',
  hrPhone: '',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Product2AuthoringPanel', () => {
  test('does not call authoring APIs without assessment.manage permission', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<Product2AuthoringPanel access={access} canManageAssessments={false} />)

    expect(screen.getByText('Assessment authoring access required')).toBeInTheDocument()
    expect(screen.getByText('Production authoring is off.')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  test('shows backend kill-switch handling for a 403 response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse({
        detail: {
          error: 'assessment_authoring_disabled',
          message: 'Assessment authoring is not enabled in this environment.',
        },
      }, 403),
    ))

    render(<Product2AuthoringPanel access={access} canManageAssessments />)

    expect(await screen.findByText('Authoring unavailable')).toBeInTheDocument()
    expect(screen.getByText('AI cannot publish, score, or decide.')).toBeInTheDocument()
    expect(screen.getByText('Publish unavailable. No publish control exists.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate draft items/i })).not.toBeInTheDocument()
  })

  test('loads evidence and queues the exact Product-2 secondary-review route', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path.endsWith('/status')) {
        return jsonResponse({
          product_version: 'assessment_product2_v1',
          global_flag: true,
          environment: 'staging',
          production_hard_off: true,
          publish_available: false,
          live_scoring_ai_calls: false,
          draft_counts: { ai_draft: 1, automated_review: 0 },
          model_roles: [{
            role_key: 'assessment.author_primary',
            version: 2,
            provider: 'openai',
            requested_model: 'gpt-author',
            api_kind: 'openai-responses',
            enabled: true,
            output_schema_name: 'GeneratedItemPackageV1',
            output_schema_version: 'assessment_product2_v1',
          }],
        })
      }
      if (path.endsWith('/product2/blueprints')) {
        return jsonResponse({ ok: true, blueprints: [], publish_available: false })
      }
      if (path.endsWith('/authoring/drafts?limit=100')) {
        return jsonResponse({ ok: true, drafts: [draft()], publish_available: false })
      }
      if (path.endsWith(`/drafts/${draft().draft_id}/evidence`)) {
        return jsonResponse({
          ok: true,
          draft: { ...draft(), content_json: content(), content_sha256: 'a'.repeat(64), compiled_scoring_sha256: 'b'.repeat(64), revision: 1 },
          revisions: [],
          reviews: [],
          events: [],
          publish_available: false,
        })
      }
      if (path.endsWith(`/drafts/${draft().draft_id}/secondary-review`) && init?.method === 'POST') {
        return jsonResponse({
          ok: true,
          publish_available: false,
          run: {
            run_id: 'run-1',
            company_code: 'WATHEFNI',
            role_key: 'assessment.review_secondary',
            run_kind: 'review_secondary',
            status: 'queued',
            registry_version_id: 'registry-1',
            prompt_version_id: 'prompt-1',
            requested_model: 'gpt-reviewer',
            schema_name: 'AssessmentReviewResultV1',
            schema_version: 'assessment_product2_v1',
            schema_sha256: 'c'.repeat(64),
          },
        })
      }
      return jsonResponse({ detail: `Unexpected path ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<Product2AuthoringPanel access={access} canManageAssessments />)

    expect(await screen.findByText('How should the employee respond?')).toBeInTheDocument()
    expect(screen.getByText('Author primary')).toBeInTheDocument()
    expect(screen.getByText('openai · gpt-author')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /run automated review/i }))

    expect(await screen.findByText(/independent automated review was queued/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/dashboard/prehire/assessments/authoring/product2/drafts/${draft().draft_id}/secondary-review`,
        expect.objectContaining({ method: 'POST' }),
      )
    })
    expect(screen.getByText('Prompt, schema, and run evidence')).toBeInTheDocument()
  })
})

function draft() {
  return {
    draft_id: '11111111-1111-4111-8111-111111111111',
    company_code: 'WATHEFNI',
    battery_key: 'wathefni_ability_v1',
    lifecycle_status: 'ai_draft',
    section: 'workplace_judgment',
    difficulty: 'medium',
    locale: 'en',
    prompt_text: 'How should the employee respond?',
    choices: [
      { key: 'A', text: 'Escalate the issue.' },
      { key: 'B', text: 'Ignore the issue.' },
    ],
  }
}

function content() {
  return {
    draft_local_id: 'item-1',
    locale: 'en',
    prompt_text: 'How should the employee respond?',
    choices: [
      { key: 'A', text: 'Escalate the issue.' },
      { key: 'B', text: 'Ignore the issue.' },
    ],
    proposed_answer_key: 'A',
    proposed_scoring: { family: 'answer_key', correct_points: 1, incorrect_points: 0, max_points: 1, choice_points: [] },
    rationale: 'Tests judgment.',
    explanation: 'Escalation follows policy.',
    distractor_rationales: [],
    competency_tags: ['judgment'],
    skill_tags: [],
    role_tags: [],
    difficulty_rationale: 'Medium complexity.',
    assumptions: [],
    original_content_attested: true,
    safety_flags: [],
  }
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
