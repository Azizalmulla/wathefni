import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  FileJson,
  Languages,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { type ReactNode, useCallback, useEffect, useState } from 'react'

import {
  adaptProduct2Draft,
  createProduct2Blueprint,
  DashboardApiError,
  generateProduct2Drafts,
  getAssessmentAuthoringDrafts,
  getProduct2AuthoringStatus,
  getProduct2Blueprints,
  getProduct2DraftEvidence,
  getProduct2Run,
  humanReviewProduct2TranslationPair,
  reviewProduct2TranslationPair,
  rewriteProduct2Draft,
  runProduct2SecondaryReview,
  transitionAssessmentAuthoringDraft,
} from '@/lib/api'
import { formatDateTime } from '@/lib/utils'
import type {
  DashboardAccess,
  Product2AuthoringStatus,
  Product2Blueprint,
  Product2BlueprintInput,
  Product2Draft,
  Product2DraftContent,
  Product2DraftEvidenceResponse,
  Product2Locale,
  Product2Run,
} from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/field'

const DEFAULT_BLUEPRINT: Product2BlueprintInput = {
  battery_key: 'wathefni_ability_v1',
  source_locale: 'en',
  required_locales: ['en', 'ar'],
  section: 'workplace_judgment',
  constructs: ['judgment'],
  item_type: 'single_choice',
  difficulty_target: 'medium',
  reading_level: 'professional',
  role_context: [],
  allowed_context: ['workplace scenarios'],
  prohibited_content: ['protected traits', 'candidate data', 'live answers'],
  scoring_family: 'answer_key',
  choice_count: 4,
  originality_policy_version: 'product2_original_v1',
}

type AuthoringAccessState = 'loading' | 'ready' | 'off' | 'forbidden' | 'error'

export function Product2AuthoringPanel({
  access,
  canManageAssessments,
}: {
  access: DashboardAccess
  canManageAssessments: boolean
}) {
  const [accessState, setAccessState] = useState<AuthoringAccessState>('loading')
  const [status, setStatus] = useState<Product2AuthoringStatus | null>(null)
  const [blueprints, setBlueprints] = useState<Product2Blueprint[]>([])
  const [drafts, setDrafts] = useState<Product2Draft[]>([])
  const [selectedBlueprintId, setSelectedBlueprintId] = useState('')
  const [selectedDraftId, setSelectedDraftId] = useState('')
  const [evidence, setEvidence] = useState<Product2DraftEvidenceResponse | null>(null)
  const [latestRun, setLatestRun] = useState<Product2Run | null>(null)
  const [operation, setOperation] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [blueprintKey, setBlueprintKey] = useState('workplace-judgment')
  const [blueprintJson, setBlueprintJson] = useState(() => JSON.stringify(DEFAULT_BLUEPRINT, null, 2))
  const [approveBlueprint, setApproveBlueprint] = useState(false)
  const [requestedItemCount, setRequestedItemCount] = useState(1)
  const [transitionNotes, setTransitionNotes] = useState('')
  const [translationPairId, setTranslationPairId] = useState('')
  const [rewriteJson, setRewriteJson] = useState('')
  const [originalityAttested, setOriginalityAttested] = useState(false)

  const handleRequestError = useCallback((requestError: unknown, fallback: string) => {
    if (requestError instanceof DashboardApiError && requestError.status === 403) {
      if (requestError.code === 'assessment_authoring_disabled') {
        setAccessState('off')
        setError('Assessment authoring is disabled in this environment.')
      } else {
        setAccessState('forbidden')
        setError('The backend did not grant assessment authoring access.')
      }
      return
    }
    setError(requestError instanceof Error ? requestError.message : fallback)
  }, [])

  const loadDrafts = useCallback(async () => {
    const response = await getAssessmentAuthoringDrafts(access)
    setDrafts(response.drafts)
    setSelectedDraftId((current) => {
      if (current && response.drafts.some((draft) => draft.draft_id === current)) return current
      return response.drafts[0]?.draft_id || ''
    })
  }, [access])

  const loadPanel = useCallback(async () => {
    if (!canManageAssessments) {
      setAccessState('forbidden')
      return
    }
    setAccessState('loading')
    setError('')
    try {
      const statusResponse = await getProduct2AuthoringStatus(access)
      setStatus(statusResponse)
      const [blueprintResponse] = await Promise.all([
        getProduct2Blueprints(access),
        loadDrafts(),
      ])
      setBlueprints(blueprintResponse.blueprints)
      setSelectedBlueprintId((current) => {
        if (current && blueprintResponse.blueprints.some((blueprint) => blueprint.blueprint_version_id === current)) return current
        return blueprintResponse.blueprints.find((blueprint) => blueprint.status === 'approved')?.blueprint_version_id || ''
      })
      setAccessState('ready')
    } catch (requestError) {
      handleRequestError(requestError, 'Could not load Product-2 authoring.')
      setAccessState((current) => current === 'loading' ? 'error' : current)
    }
  }, [access, canManageAssessments, handleRequestError, loadDrafts])

  useEffect(() => {
    void loadPanel()
  }, [loadPanel])

  useEffect(() => {
    if (!selectedDraftId || accessState !== 'ready') {
      setEvidence(null)
      return
    }
    let cancelled = false
    getProduct2DraftEvidence(access, selectedDraftId)
      .then((response) => {
        if (cancelled) return
        setEvidence(response)
        const content = response.draft.content_json || response.revisions[0]?.content_json
        setRewriteJson(content ? JSON.stringify(content, null, 2) : '')
      })
      .catch((requestError) => {
        if (!cancelled) handleRequestError(requestError, 'Could not load draft evidence.')
      })
    return () => {
      cancelled = true
    }
  }, [access, accessState, handleRequestError, selectedDraftId])

  async function runAction(label: string, action: () => Promise<void>) {
    setOperation(label)
    setError('')
    setMessage('')
    try {
      await action()
    } catch (requestError) {
      handleRequestError(requestError, `Could not ${label.toLowerCase()}.`)
    } finally {
      setOperation('')
    }
  }

  function captureRun(run: Product2Run, successMessage: string) {
    setLatestRun(run)
    setMessage(successMessage)
  }

  async function createBlueprint() {
    await runAction('Saving blueprint', async () => {
      const parsed = JSON.parse(blueprintJson) as Product2BlueprintInput
      const response = await createProduct2Blueprint(access, {
        blueprint_key: blueprintKey.trim(),
        blueprint: parsed,
        approve: approveBlueprint,
      })
      const next = await getProduct2Blueprints(access)
      setBlueprints(next.blueprints)
      if (response.blueprint.status === 'approved') setSelectedBlueprintId(response.blueprint.blueprint_version_id)
      setMessage(`Blueprint v${response.blueprint.version} saved as ${response.blueprint.status}.`)
    })
  }

  async function generateDrafts() {
    if (!selectedBlueprintId) return
    await runAction('Queueing generation', async () => {
      const response = await generateProduct2Drafts(access, {
        blueprint_version_id: selectedBlueprintId,
        requested_item_count: requestedItemCount,
      })
      captureRun(response.run, 'Draft generation queued. Refresh the run to follow its evidence.')
    })
  }

  async function secondaryReview() {
    if (!selectedDraftId) return
    await runAction('Queueing automated review', async () => {
      const response = await runProduct2SecondaryReview(access, selectedDraftId)
      captureRun(response.run, 'Deterministic checks passed and independent automated review was queued.')
    })
  }

  async function adaptDraft(targetLocale: Product2Locale) {
    if (!selectedDraftId) return
    await runAction(`Queueing ${targetLocale.toUpperCase()} adaptation`, async () => {
      const response = await adaptProduct2Draft(access, selectedDraftId, targetLocale)
      captureRun(response.run, `${targetLocale.toUpperCase()} adaptation queued with answer and scoring invariants.`)
    })
  }

  async function reviewTranslation() {
    if (!translationPairId.trim()) return
    await runAction('Queueing bilingual review', async () => {
      const response = await reviewProduct2TranslationPair(access, translationPairId.trim())
      captureRun(response.run, 'Independent bilingual review queued.')
    })
  }

  async function approveTranslationAsHuman() {
    if (!translationPairId.trim()) return
    await runAction('Approving bilingual pair', async () => {
      await humanReviewProduct2TranslationPair(access, translationPairId.trim(), {
        decision: 'approve',
        notes: transitionNotes.trim() || undefined,
      })
      setMessage('Bilingual pair approved by a human reviewer. It remains outside the live bank.')
    })
  }

  async function refreshRun() {
    if (!latestRun) return
    await runAction('Refreshing run', async () => {
      const response = await getProduct2Run(access, latestRun.run_id)
      setLatestRun(response.run)
      setMessage(`Run is ${humanize(response.run.status)}.`)
      const pairId = stringField(response.run.output_json, 'translation_pair_id')
      if (pairId) setTranslationPairId(pairId)
      if (response.run.status === 'completed') {
        await loadDrafts()
        const createdDraftId = firstCreatedDraftId(response.run)
        if (createdDraftId) setSelectedDraftId(createdDraftId)
      }
    })
  }

  async function rewriteDraft() {
    if (!selectedDraftId) return
    await runAction('Saving human rewrite', async () => {
      const content = JSON.parse(rewriteJson) as Product2DraftContent
      await rewriteProduct2Draft(access, selectedDraftId, content)
      await loadDrafts()
      const refreshedEvidence = await getProduct2DraftEvidence(access, selectedDraftId)
      setEvidence(refreshedEvidence)
      setMessage('Human rewrite saved. Prior automated reviews were invalidated.')
    })
  }

  async function transitionDraft(toStatus: 'human_review' | 'pilot' | 'approved') {
    if (!selectedDraftId) return
    if (toStatus === 'human_review' && !originalityAttested) {
      setError('Confirm the human originality attestation before accepting this revision for human review.')
      return
    }
    await runAction(`Moving to ${humanize(toStatus)}`, async () => {
      await transitionAssessmentAuthoringDraft(access, selectedDraftId, {
        to_status: toStatus,
        notes: transitionNotes.trim() || undefined,
        original_content_attested: toStatus === 'human_review' ? originalityAttested : undefined,
      })
      await loadDrafts()
      const refreshedEvidence = await getProduct2DraftEvidence(access, selectedDraftId)
      setEvidence(refreshedEvidence)
      if (toStatus === 'human_review') setOriginalityAttested(false)
      setMessage(toStatus === 'approved'
        ? 'Draft approved by a human. It was not published.'
        : `Draft moved to ${humanize(toStatus)} by a human.`)
    })
  }

  const selectedDraft = drafts.find((draft) => draft.draft_id === selectedDraftId) || evidence?.draft || null
  const currentContent = evidence?.draft.content_json || evidence?.revisions[0]?.content_json
  const nextTransition = humanTransitionFor(selectedDraft?.lifecycle_status)
  const busy = Boolean(operation)

  return (
    <Card className="border-[#d5ad68]/45 bg-[linear-gradient(145deg,rgba(255,252,245,0.96),rgba(250,244,232,0.88))]">
      <CardHeader>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge tone="warning">Product-2 · non-production</Badge>
              <Badge tone="muted">Human controlled</Badge>
            </div>
            <CardTitle>Assessment authoring workbench</CardTitle>
            <CardDescription>
              Create blueprint-bound drafts, inspect immutable evidence, and move content through human review. This workspace is separate from candidate attempts.
            </CardDescription>
          </div>
          <Button disabled={busy || !canManageAssessments} onClick={() => void loadPanel()} size="sm" variant="secondary">
            {accessState === 'loading' ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
            Refresh authoring
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <AuthoringGuardrails />

        {!canManageAssessments ? (
          <AccessMessage
            description="You need assessment.manage permission to view evidence or run authoring actions."
            title="Assessment authoring access required"
          />
        ) : null}
        {canManageAssessments && accessState === 'off' ? (
          <AccessMessage
            description="The backend kill switch is authoritative. No authoring request can run in this environment."
            title="Authoring unavailable"
          />
        ) : null}
        {canManageAssessments && accessState === 'forbidden' ? (
          <AccessMessage
            description="Your dashboard session does not have backend permission for Product-2 authoring."
            title="Backend access denied"
          />
        ) : null}
        {canManageAssessments && accessState === 'error' ? (
          <AccessMessage description={error || 'The authoring service could not be loaded.'} title="Authoring status unavailable" />
        ) : null}
        {accessState === 'loading' && canManageAssessments ? (
          <div className="flex items-center gap-2 rounded-2xl border border-line bg-white/55 p-4 text-sm text-subtle">
            <Loader2 className="animate-spin" size={16} /> Loading authoring controls and evidence…
          </div>
        ) : null}

        {accessState === 'ready' ? (
          <>
            {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
            {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
            {operation ? <InlineNotice><Loader2 className="animate-spin" size={14} /> {operation}…</InlineNotice> : null}

            <div className="grid gap-3 xl:grid-cols-[1.15fr_1fr]">
              <LifecycleSummary status={status} />
              <ModelRegistry status={status} />
            </div>

            <details className="rounded-2xl border border-line/65 bg-white/50 p-4">
              <summary className="cursor-pointer font-semibold text-text">Create a versioned blueprint</summary>
              <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(180px,0.45fr)_1fr]">
                <label className="grid gap-1.5 text-xs font-medium text-subtle">
                  Blueprint key
                  <Input onChange={(event) => setBlueprintKey(event.target.value)} value={blueprintKey} />
                </label>
                <label className="grid gap-1.5 text-xs font-medium text-subtle">
                  Blueprint JSON
                  <Textarea
                    className="min-h-52 font-mono text-xs"
                    onChange={(event) => setBlueprintJson(event.target.value)}
                    spellCheck={false}
                    value={blueprintJson}
                  />
                </label>
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm text-subtle">
                  <input
                    checked={approveBlueprint}
                    onChange={(event) => setApproveBlueprint(event.target.checked)}
                    type="checkbox"
                  />
                  Approve this version as a human author
                </label>
                <Button disabled={busy || !blueprintKey.trim()} onClick={() => void createBlueprint()} size="sm">
                  <FileJson size={14} /> Save blueprint
                </Button>
              </div>
            </details>

            <div className="grid gap-4 xl:grid-cols-[0.78fr_1.22fr]">
              <section className="space-y-4 rounded-2xl border border-line/65 bg-white/50 p-4">
                <div>
                  <h3 className="font-semibold text-text">Generate drafts</h3>
                  <p className="mt-1 text-xs leading-5 text-subtle">Only a human-approved, tenant-scoped blueprint can be queued.</p>
                </div>
                <label className="grid gap-1.5 text-xs font-medium text-subtle">
                  Approved blueprint
                  <Select onChange={(event) => setSelectedBlueprintId(event.target.value)} value={selectedBlueprintId}>
                    <option value="">Select an approved blueprint</option>
                    {blueprints.filter((blueprint) => blueprint.status === 'approved').map((blueprint) => (
                      <option key={blueprint.blueprint_version_id} value={blueprint.blueprint_version_id}>
                        {blueprint.blueprint_key} · v{blueprint.version}
                      </option>
                    ))}
                  </Select>
                </label>
                <label className="grid gap-1.5 text-xs font-medium text-subtle">
                  Draft count
                  <Input
                    max={20}
                    min={1}
                    onChange={(event) => setRequestedItemCount(Math.max(1, Math.min(20, Number(event.target.value) || 1)))}
                    type="number"
                    value={requestedItemCount}
                  />
                </label>
                <Button disabled={busy || !selectedBlueprintId} onClick={() => void generateDrafts()} size="sm">
                  <Sparkles size={14} /> Generate draft items
                </Button>

                <div className="border-t border-line/60 pt-4">
                  <label className="grid gap-1.5 text-xs font-medium text-subtle">
                    Draft workspace
                    <Select onChange={(event) => setSelectedDraftId(event.target.value)} value={selectedDraftId}>
                      <option value="">Select a draft</option>
                      {drafts.map((draft) => (
                        <option key={draft.draft_id} value={draft.draft_id}>
                          {humanize(draft.locale)} · {humanize(draft.lifecycle_status)} · {shortId(draft.draft_id)}
                        </option>
                      ))}
                    </Select>
                  </label>
                </div>
              </section>

              <DraftWorkspace
                busy={busy}
                content={currentContent}
                draft={selectedDraft}
                evidence={evidence}
                nextTransition={nextTransition}
                onAdapt={(locale) => void adaptDraft(locale)}
                onReview={() => void secondaryReview()}
                onTransition={(toStatus) => void transitionDraft(toStatus)}
                originalityAttested={originalityAttested}
                setOriginalityAttested={setOriginalityAttested}
                transitionNotes={transitionNotes}
                setTransitionNotes={setTransitionNotes}
              />
            </div>

            {selectedDraft ? (
              <details className="rounded-2xl border border-line/65 bg-white/50 p-4">
                <summary className="cursor-pointer font-semibold text-text">Human rewrite and bilingual review</summary>
                <div className="mt-4 grid gap-5 xl:grid-cols-2">
                  <div>
                    <label className="grid gap-1.5 text-xs font-medium text-subtle">
                      Human rewrite JSON
                      <Textarea
                        className="min-h-64 font-mono text-xs"
                        onChange={(event) => setRewriteJson(event.target.value)}
                        spellCheck={false}
                        value={rewriteJson}
                      />
                    </label>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <p className="text-xs leading-5 text-subtle">A rewrite creates a new revision and invalidates prior automated reviews.</p>
                      <Button disabled={busy || !rewriteJson.trim()} onClick={() => void rewriteDraft()} size="sm" variant="secondary">
                        Save human rewrite
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <label className="grid gap-1.5 text-xs font-medium text-subtle">
                      Translation pair ID
                      <Input
                        onChange={(event) => setTranslationPairId(event.target.value)}
                        placeholder="Available after an adaptation run completes"
                        value={translationPairId}
                      />
                    </label>
                    <Button disabled={busy || !translationPairId.trim()} onClick={() => void reviewTranslation()} size="sm" variant="secondary">
                      <Languages size={14} /> Run bilingual review
                    </Button>
                    <Button disabled={busy || !translationPairId.trim()} onClick={() => void approveTranslationAsHuman()} size="sm">
                      <ShieldCheck size={14} /> Human approve bilingual pair
                    </Button>
                    <p className="text-xs leading-5 text-subtle">
                      Bilingual review checks semantic equivalence, answer-key invariance, naturalness, RTL punctuation, cultural fairness, and difficulty drift.
                    </p>
                  </div>
                </div>
              </details>
            ) : null}

            {latestRun ? <RunEvidence busy={busy} onRefresh={() => void refreshRun()} run={latestRun} /> : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

function AuthoringGuardrails() {
  return (
    <div className="grid gap-2 lg:grid-cols-3">
      <InlineNotice tone="warning"><AlertTriangle size={15} /> Production authoring is off.</InlineNotice>
      <InlineNotice><ShieldCheck size={15} /> AI cannot publish, score, or decide.</InlineNotice>
      <InlineNotice tone="warning"><CheckCircle2 size={15} /> Publish unavailable. No publish control exists.</InlineNotice>
    </div>
  )
}

function AccessMessage({ description, title }: { description: string; title: string }) {
  return (
    <div className="rounded-2xl border border-amber-200/75 bg-amber-50/65 p-4">
      <div className="font-semibold text-amber-950">{title}</div>
      <div className="mt-1 text-sm leading-6 text-amber-900/75">{description}</div>
    </div>
  )
}

function InlineNotice({
  children,
  tone = 'default',
}: {
  children: ReactNode
  tone?: 'default' | 'success' | 'warning' | 'danger'
}) {
  return (
    <div className={[
      'flex items-center gap-2 rounded-2xl border px-3 py-2 text-xs font-medium',
      tone === 'success' ? 'border-emerald-200/70 bg-emerald-50/70 text-emerald-900' : '',
      tone === 'warning' ? 'border-amber-200/75 bg-amber-50/70 text-amber-900' : '',
      tone === 'danger' ? 'border-rose-200/75 bg-rose-50/70 text-rose-900' : '',
      tone === 'default' ? 'border-line/70 bg-white/60 text-subtle' : '',
    ].join(' ')}>
      {children}
    </div>
  )
}

function LifecycleSummary({ status }: { status: Product2AuthoringStatus | null }) {
  const lifecycle = ['ai_draft', 'automated_review', 'human_review', 'pilot', 'approved', 'retired']
  return (
    <section className="rounded-2xl border border-line/65 bg-white/50 p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold text-text">Authoring lifecycle</h3>
        <Badge tone={status?.global_flag ? 'success' : 'warning'}>{status?.global_flag ? 'Authoring enabled here' : 'Kill switch off'}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
        {lifecycle.map((state) => (
          <div className="rounded-xl border border-line/55 bg-panel/60 p-2 text-center" key={state}>
            <div className="text-lg font-semibold text-text">{status?.draft_counts[state] || 0}</div>
            <div className="mt-1 text-[10px] leading-4 text-subtle">{humanize(state)}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function ModelRegistry({ status }: { status: Product2AuthoringStatus | null }) {
  return (
    <details className="rounded-2xl border border-line/65 bg-white/50 p-4">
      <summary className="cursor-pointer font-semibold text-text">Model roles and schemas</summary>
      <div className="mt-3 space-y-2">
        {status?.model_roles.map((role) => (
          <div className="rounded-xl border border-line/55 bg-panel/60 p-3 text-xs" key={`${role.role_key}-${role.version}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-text">{humanize(role.role_key.replace('assessment.', ''))}</span>
              <div className="flex items-center gap-2">
                <Badge tone={role.enabled ? 'success' : 'muted'}>{role.enabled ? 'Qualified' : 'Inactive'}</Badge>
                <Badge tone="muted">role v{role.version}</Badge>
              </div>
            </div>
            <div className="mt-1 text-subtle">{role.provider} · {role.requested_model}</div>
            <div className="mt-1 break-all text-subtle">Schema: {role.output_schema_name} · {role.output_schema_version}</div>
          </div>
        ))}
        {!status?.model_roles.length ? <div className="text-xs text-subtle">No model registry roles reported.</div> : null}
      </div>
    </details>
  )
}

function DraftWorkspace({
  busy,
  content,
  draft,
  evidence,
  nextTransition,
  onAdapt,
  onReview,
  onTransition,
  originalityAttested,
  setOriginalityAttested,
  setTransitionNotes,
  transitionNotes,
}: {
  busy: boolean
  content?: Product2DraftContent
  draft: Product2Draft | null
  evidence: Product2DraftEvidenceResponse | null
  nextTransition: 'human_review' | 'pilot' | 'approved' | null
  onAdapt: (locale: Product2Locale) => void
  onReview: () => void
  onTransition: (status: 'human_review' | 'pilot' | 'approved') => void
  originalityAttested: boolean
  setOriginalityAttested: (value: boolean) => void
  setTransitionNotes: (value: string) => void
  transitionNotes: string
}) {
  if (!draft) {
    return (
      <section className="flex min-h-72 items-center justify-center rounded-2xl border border-dashed border-line bg-white/35 p-6 text-center text-sm text-subtle">
        Generate or select a draft to inspect its evidence and human transitions.
      </section>
    )
  }
  const locale = content?.locale || draft.locale
  const choices = content?.choices || draft.choices || []
  const canAdapt = ['automated_review', 'human_review'].includes(draft.lifecycle_status)
  return (
    <section className="space-y-4 rounded-2xl border border-line/65 bg-white/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-text">Draft evidence</h3>
            <Badge tone={lifecycleTone(draft.lifecycle_status)}>{humanize(draft.lifecycle_status)}</Badge>
            <Badge tone="muted">{locale.toUpperCase()}</Badge>
          </div>
          <div className="mt-1 text-xs text-subtle">{draft.section ? humanize(draft.section) : 'Assessment item'} · {shortId(draft.draft_id)}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy || draft.lifecycle_status !== 'ai_draft'} onClick={onReview} size="sm" variant="secondary">
            <Bot size={14} /> Run automated review
          </Button>
          <Button disabled={busy || !canAdapt || locale === 'en'} onClick={() => onAdapt('en')} size="sm" variant="secondary">
            Adapt to EN
          </Button>
          <Button disabled={busy || !canAdapt || locale === 'ar'} onClick={() => onAdapt('ar')} size="sm" variant="secondary">
            Adapt to AR
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-line/55 bg-panel/65 p-4" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
        <div className="text-sm font-semibold leading-6 text-text">{content?.prompt_text || draft.prompt_text}</div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {choices.map((choice) => (
            <div className="rounded-lg border border-line/55 bg-white/55 px-3 py-2 text-xs text-subtle" key={choice.key}>
              <span className="font-semibold text-text">{choice.key}.</span> {choice.text}
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-2 text-xs sm:grid-cols-2 xl:grid-cols-4">
        <EvidenceValue label="Revision" value={evidence?.draft.revision ? `v${evidence.draft.revision}` : '—'} />
        <EvidenceValue label="Content digest" value={shortDigest(evidence?.draft.content_sha256)} />
        <EvidenceValue label="Scoring digest" value={shortDigest(evidence?.draft.compiled_scoring_sha256)} />
        <EvidenceValue label="Evidence trail" value={`${evidence?.reviews.length || 0} reviews · ${evidence?.events.length || 0} events`} />
      </div>

      {evidence?.reviews.length ? (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-subtle">Latest review evidence</div>
          {evidence.reviews.slice(0, 3).map((review) => (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/55 bg-white/50 p-3 text-xs" key={review.review_id}>
              <span className="font-medium text-text">{humanize(review.review_type)}</span>
              <span className="text-subtle">{review.to_status ? humanize(review.to_status) : review.created_at ? formatDateTime(review.created_at) : 'Recorded'}</span>
            </div>
          ))}
        </div>
      ) : null}

      {nextTransition ? (
        <div className="border-t border-line/60 pt-4">
          {nextTransition === 'human_review' ? (
            <label className="mb-3 flex items-start gap-2 text-xs leading-5 text-subtle">
              <input
                checked={originalityAttested}
                className="mt-1"
                onChange={(event) => setOriginalityAttested(event.target.checked)}
                type="checkbox"
              />
              I attest that I reviewed this exact revision for originality and did not identify copied proprietary test content.
            </label>
          ) : null}
          <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
            <Input
              onChange={(event) => setTransitionNotes(event.target.value)}
              placeholder="Human review notes (optional)"
              value={transitionNotes}
            />
            <Button
              disabled={busy || (nextTransition === 'human_review' && !originalityAttested)}
              onClick={() => onTransition(nextTransition)}
              size="sm"
            >
              {transitionLabel(nextTransition)}
            </Button>
          </div>
          <p className="mt-2 text-xs text-subtle">This records a human lifecycle transition only. The live item bank remains unchanged.</p>
        </div>
      ) : null}
    </section>
  )
}

function RunEvidence({ busy, onRefresh, run }: { busy: boolean; onRefresh: () => void; run: Product2Run }) {
  return (
    <details className="rounded-2xl border border-line/65 bg-white/50 p-4" open>
      <summary className="cursor-pointer font-semibold text-text">Prompt, schema, and run evidence</summary>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <EvidenceValue label="Role" value={run.role_key} />
        <EvidenceValue label="Model" value={run.provider_response_model || run.requested_model} />
        <EvidenceValue label="Prompt version ID" value={shortId(run.prompt_version_id)} />
        <EvidenceValue label="Schema" value={`${run.schema_name} · ${run.schema_version}`} />
        <EvidenceValue label="Schema digest" value={shortDigest(run.schema_sha256)} />
        <EvidenceValue label="Input digest" value={shortDigest(run.input_sha256)} />
        <EvidenceValue label="Output digest" value={shortDigest(run.output_sha256)} />
        <EvidenceValue label="Tokens" value={`${run.input_tokens ?? '—'} in · ${run.output_tokens ?? '—'} out`} />
        <EvidenceValue label="Estimated cost" value={run.estimated_cost_usd == null ? '—' : `$${Number(run.estimated_cost_usd).toFixed(6)}`} />
        <EvidenceValue label="Latency" value={run.latency_ms == null ? '—' : `${run.latency_ms} ms`} />
        <EvidenceValue label="Status" value={humanize(run.status)} />
      </div>
      {run.error_message || run.refusal_reason ? (
        <div className="mt-3 rounded-xl border border-rose-200/70 bg-rose-50/65 p-3 text-xs text-rose-900">
          {run.error_message || run.refusal_reason}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-subtle">
        <span>Run {shortId(run.run_id)} · {run.completed_at ? formatDateTime(run.completed_at) : 'queued evidence retained'}</span>
        <Button disabled={busy} onClick={onRefresh} size="sm" variant="secondary">
          <RefreshCw size={14} /> Refresh run
        </Button>
      </div>
    </details>
  )
}

function EvidenceValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line/55 bg-panel/60 p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-subtle">{label}</div>
      <div className="mt-1 break-all text-xs font-medium text-text">{value}</div>
    </div>
  )
}

function firstCreatedDraftId(run: Product2Run) {
  const created = run.output_json?.created_drafts
  if (!Array.isArray(created)) return ''
  const first = created[0]
  if (!first || typeof first !== 'object') return ''
  const id = (first as Record<string, unknown>).draft_id
  return typeof id === 'string' ? id : ''
}

function stringField(value: Record<string, unknown> | null | undefined, key: string) {
  const field = value?.[key]
  return typeof field === 'string' ? field : ''
}

function humanTransitionFor(status: string | undefined) {
  if (status === 'automated_review') return 'human_review' as const
  if (status === 'human_review') return 'pilot' as const
  if (status === 'pilot') return 'approved' as const
  return null
}

function transitionLabel(status: 'human_review' | 'pilot' | 'approved') {
  if (status === 'human_review') return 'Accept for human review'
  if (status === 'pilot') return 'Move to pilot'
  return 'Approve draft (not publish)'
}

function lifecycleTone(status: string | undefined): 'default' | 'success' | 'warning' | 'danger' | 'muted' {
  if (status === 'approved') return 'success'
  if (status === 'automated_review' || status === 'human_review' || status === 'pilot') return 'warning'
  if (status === 'retired') return 'muted'
  return 'default'
}

function humanize(value: string | null | undefined) {
  const text = String(value || 'unknown').replaceAll('_', ' ').replaceAll('.', ' · ').trim()
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text
}

function shortId(value: string | null | undefined) {
  if (!value) return '—'
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value
}

function shortDigest(value: string | null | undefined) {
  if (!value) return '—'
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value
}
