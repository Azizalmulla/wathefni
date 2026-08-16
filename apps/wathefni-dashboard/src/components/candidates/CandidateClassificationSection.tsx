import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'

import type { DashboardAccess } from '@/types'
import {
  getApplicationClassification,
  getTalentPoolClassificationTaxonomy,
  reviewApplicationClassification,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { useConfirm } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import type { TaxonomyNodeOption } from '@/components/candidates/ClassificationFilters'

type ClassificationSection = {
  status?: string
  refusal_reason?: string | null
  taxonomy_version?: string
  classifier_version?: string
  currency?: string
  current_run?: Record<string, unknown> | null
  confirmed?: Array<Record<string, unknown>>
  ai_suggested?: Array<Record<string, unknown>>
  rejected_node_ids?: string[]
  history?: Array<Record<string, unknown>>
  runs?: Array<Record<string, unknown>>
  runs_total?: number
  runs_offset?: number
  runs_limit?: number
  chip?: string | null
  actions?: string[]
  hiring_score?: null
  role_profile_score?: null
  job_assignment?: null
}

function displayBand(value: unknown) {
  const band = String(value || '').trim()
  if (!band) return '—'
  if (band.toLowerCase() === 'unclassified') return 'Unclassified'
  return band
}

function suggestionLabel(item: Record<string, unknown>, locale: 'en' | 'ar') {
  if (locale === 'ar') return String(item.label_ar || item.label_en || item.node_id || '—')
  return String(item.label_en || item.label_ar || item.node_id || '—')
}

export function CandidateClassificationSection({
  access,
  appKey,
  enabled,
  locale = 'en',
  onAccessIssue,
}: {
  access: DashboardAccess
  appKey: string
  enabled: boolean
  locale?: 'en' | 'ar'
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const confirm = useConfirm()
  const [section, setSection] = useState<ClassificationSection | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [addNodeId, setAddNodeId] = useState('')
  const [correctFrom, setCorrectFrom] = useState('')
  const [correctTo, setCorrectTo] = useState('')
  const [taxonomyNodes, setTaxonomyNodes] = useState<TaxonomyNodeOption[]>([])

  const refresh = async (runsOffset = 0) => {
    if (!enabled) return
    setLoading(true)
    try {
      const payload = await getApplicationClassification(access, appKey, {
        runs_offset: runsOffset,
        runs_limit: 20,
      })
      setSection(payload.classification as ClassificationSection)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setMessage('Classification unavailable for this tenant or flag.')
      setSection(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [access, appKey, enabled])

  useEffect(() => {
    if (!enabled) return
    void getTalentPoolClassificationTaxonomy(access)
      .then((payload) => {
        const nodes = (payload.dimensions || []).flatMap((dimension) => dimension.nodes || [])
        setTaxonomyNodes(nodes)
      })
      .catch(() => setTaxonomyNodes([]))
  }, [access, enabled])

  const nodeOptions = useMemo(() => {
    const q = ''
    return taxonomyNodes
      .filter((node) => !q || `${node.label_en} ${node.label_ar} ${node.node_id}`.toLowerCase().includes(q))
      .slice(0, 200)
  }, [taxonomyNodes])

  if (!enabled) return null

  const runReview = async (
    action: 'confirm' | 'reject' | 'add' | 'correct',
    body: Record<string, unknown>,
    prompt: string,
  ) => {
    const ok = await confirm({
      title: `Confirm classification ${action}`,
      body: prompt,
      confirmLabel: action === 'reject' ? 'Reject' : 'Confirm',
      destructive: action === 'reject',
    })
    if (!ok) return
    setBusy(true)
    setMessage('')
    try {
      await reviewApplicationClassification(access, appKey, {
        ...body,
        action,
        confirm: true,
      })
      setMessage(`Classification ${action} recorded (append-only).`)
      await refresh(section?.runs_offset || 0)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setMessage('Could not save classification review.')
    } finally {
      setBusy(false)
    }
  }

  const statusLabel = displayBand(section?.status)
  const currency = String(section?.currency || (section?.current_run ? 'current' : 'unclassified'))

  return (
    <section className="mt-5 rounded-[1.45rem] border border-white/70 bg-white/58 p-4" data-testid="candidate-classification-section">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">Classification</div>
          <p className="mt-1 text-xs text-subtle">
            Advisory organization only — not a hiring score, Job assignment, or Role Profile match.
          </p>
        </div>
        <Button disabled={busy} onClick={() => void refresh()} size="sm" type="button" variant="secondary">
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="mt-3 flex items-center gap-2 text-sm text-subtle">
          <Loader2 className="animate-spin" size={16} /> Loading classification…
        </div>
      ) : null}

      {section ? (
        <div className="mt-3 space-y-4">
          <div className="flex flex-wrap gap-2">
            <Badge tone="muted">{statusLabel}</Badge>
            <Badge tone="muted">{currency === 'current' ? 'Current' : currency === 'stale' ? 'Stale' : 'Unclassified'}</Badge>
            {section.chip ? <Badge tone="success">Chip: {section.chip}</Badge> : <Badge tone="muted">No compact chip</Badge>}
            <Badge tone="muted">Taxonomy {section.taxonomy_version || '—'}</Badge>
            <Badge tone="muted">Classifier {section.classifier_version || '—'}</Badge>
          </div>
          {section.refusal_reason ? (
            <p className="text-sm text-subtle">Insufficient evidence: {section.refusal_reason}</p>
          ) : null}

          <div data-testid="classification-confirmed">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-subtle">HR confirmed</div>
            <ul className="mt-2 space-y-1 text-sm">
              {(section.confirmed || []).map((item) => (
                <li key={String(item.node_id)}>
                  • {suggestionLabel(item, locale)}
                  {item.node_type ? <span className="text-subtle"> · {String(item.node_type)}</span> : null}
                </li>
              ))}
              {!section.confirmed?.length ? <li className="text-subtle">None confirmed yet.</li> : null}
            </ul>
          </div>

          <div data-testid="classification-ai-suggested">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-subtle">AI suggested (advisory)</div>
            <ul className="mt-2 space-y-2 text-sm">
              {(section.ai_suggested || []).map((item) => (
                <li className="rounded-xl border border-line/50 bg-white/50 p-2" key={String(item.node_id)}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{suggestionLabel(item, locale)}</span>
                    <Badge tone="muted">{displayBand(item.confidence_band)}</Badge>
                  </div>
                  <div className="mt-1 text-xs text-subtle">
                    Evidence:{' '}
                    {Array.isArray(item.evidence) && item.evidence.length
                      ? JSON.stringify(item.evidence[0])
                      : 'No supporting evidence snippet'}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button
                      disabled={busy}
                      onClick={() =>
                        void runReview(
                          'confirm',
                          { node_id: String(item.node_id), suggestion_id: item.suggestion_id, label_en: item.label_en },
                          `Confirm “${suggestionLabel(item, locale)}” as an HR-confirmed classification? This does not assign a Job or change lifecycle.`,
                        )
                      }
                      size="sm"
                      type="button"
                    >
                      Confirm
                    </Button>
                    <Button
                      disabled={busy}
                      onClick={() =>
                        void runReview(
                          'reject',
                          { node_id: String(item.node_id), suggestion_id: item.suggestion_id },
                          `Reject “${suggestionLabel(item, locale)}”? The AI suggestion remains in history; it will not appear as current.`,
                        )
                      }
                      size="sm"
                      type="button"
                      variant="secondary"
                    >
                      Reject
                    </Button>
                  </div>
                </li>
              ))}
              {!section.ai_suggested?.length ? <li className="text-subtle">No active AI suggestions.</li> : null}
            </ul>
          </div>

          <div className="rounded-xl border border-line/40 bg-white/40 p-3" data-testid="classification-add-correct">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-subtle">HR add / correct</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <select
                className="h-10 min-w-[14rem] rounded-full border border-line/60 bg-white/80 px-3 text-sm"
                onChange={(event) => setAddNodeId(event.target.value)}
                value={addNodeId}
              >
                <option value="">Add taxonomy node…</option>
                {nodeOptions.map((node) => (
                  <option key={node.node_id} value={node.node_id}>
                    {locale === 'ar' ? node.label_ar || node.label_en : node.label_en || node.label_ar} ({node.node_id})
                  </option>
                ))}
              </select>
              <Button
                disabled={busy || !addNodeId}
                onClick={() =>
                  void runReview(
                    'add',
                    { node_id: addNodeId },
                    'Add this taxonomy node as HR-confirmed? It will not be attributed to the classifier.',
                  ).then(() => setAddNodeId(''))
                }
                size="sm"
                type="button"
              >
                Add
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Input
                className="h-10 w-48"
                onChange={(event) => setCorrectFrom(event.target.value)}
                placeholder="Previous node id"
                value={correctFrom}
              />
              <Input
                className="h-10 w-48"
                onChange={(event) => setCorrectTo(event.target.value)}
                placeholder="Corrected node id"
                value={correctTo}
              />
              <Button
                disabled={busy || !correctFrom || !correctTo}
                onClick={() =>
                  void runReview(
                    'correct',
                    { node_id: correctTo, previous_node_id: correctFrom },
                    `Correct ${correctFrom} → ${correctTo}? This creates a superseding review event; prior history is preserved.`,
                  ).then(() => {
                    setCorrectFrom('')
                    setCorrectTo('')
                  })
                }
                size="sm"
                type="button"
                variant="secondary"
              >
                Correct
              </Button>
            </div>
          </div>

          {section.rejected_node_ids?.length ? (
            <p className="text-xs text-subtle">Rejected (audit retained): {section.rejected_node_ids.length} node(s)</p>
          ) : null}

          <div>
            <Button onClick={() => setShowHistory((value) => !value)} size="sm" type="button" variant="ghost">
              {showHistory ? 'Hide' : 'Show'} classification history
            </Button>
            {showHistory ? (
              <div className="mt-3 space-y-3" data-testid="classification-history">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-subtle">
                    Immutable classifier runs
                  </div>
                  <ul className="mt-2 space-y-2 text-sm">
                    {(section.runs || []).map((run) => (
                      <li className="rounded-xl border border-line/40 bg-white/40 p-2" key={String(run.run_id)}>
                        <div className="flex flex-wrap gap-2">
                          <Badge tone={run.currency === 'current' ? 'success' : 'muted'}>
                            {String(run.currency || 'stale')}
                          </Badge>
                          <Badge tone="muted">{displayBand(run.status)}</Badge>
                          <Badge tone="muted">{String(run.taxonomy_version || '—')}</Badge>
                          <Badge tone="muted">{String(run.classifier_version || '—')}</Badge>
                        </div>
                        <div className="mt-1 text-xs text-subtle">
                          Doc {String(run.document_version_id || '—')} · Extraction{' '}
                          {String(run.extraction_version_id || '—')} · {String(run.created_at || '')}
                        </div>
                        {run.invalidated && Array.isArray(run.invalidations) ? (
                          <div className="mt-2 rounded-lg border border-amber-300/60 bg-amber-50/70 p-2 text-xs text-amber-950">
                            {run.invalidations.map((value, index) => {
                              const invalidation = value as Record<string, unknown>
                              return (
                                <div key={String(invalidation.invalidation_id || index)}>
                                  Invalidated: {String(invalidation.reason_code || 'unspecified')} · by{' '}
                                  {String(invalidation.invalidated_by || 'unknown')} ·{' '}
                                  {String(invalidation.created_at || '')}
                                </div>
                              )
                            })}
                          </div>
                        ) : null}
                      </li>
                    ))}
                    {!section.runs?.length ? <li className="text-subtle">No classifier runs yet.</li> : null}
                  </ul>
                  {(section.runs_total || 0) > (section.runs || []).length ? (
                    <Button
                      className="mt-2"
                      onClick={() => void refresh((section.runs_offset || 0) + (section.runs_limit || 20))}
                      size="sm"
                      type="button"
                      variant="secondary"
                    >
                      Load older runs
                    </Button>
                  ) : null}
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-subtle">
                    HR review history (append-only)
                  </div>
                  <ul className="mt-2 space-y-1 text-sm">
                    {(section.history || []).map((event) => (
                      <li key={String(event.event_id)}>
                        • {String(event.action)} · {suggestionLabel(event, locale)}
                        {event.previous_node_id ? ` (from ${String(event.previous_node_id)})` : ''}
                      </li>
                    ))}
                    {!section.history?.length ? <li className="text-subtle">No HR review events yet.</li> : null}
                  </ul>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-subtle">Unclassified or not yet run.</p>
      )}

      {message ? <p className="mt-3 text-xs text-subtle">{message}</p> : null}
    </section>
  )
}
