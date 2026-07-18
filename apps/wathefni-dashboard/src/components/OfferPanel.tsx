import { useEffect, useState } from 'react'
import type { DashboardAccess } from '@/types'
import {
  approveOffer,
  createOfferDraft,
  listApplicationOffers,
  recordOfferResponse,
  returnOffer,
  sendOffer,
  submitOfferApproval,
  updateOfferDraft,
  withdrawOffer,
  type EmploymentOffer,
} from '@/lib/offers-api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

type Props = {
  access: DashboardAccess
  appKey: string
  enabled: boolean
  busy: boolean
  onMessage: (value: string) => void
  onRefresh?: () => void
}

export function OfferPanel({ access, appKey, enabled, busy, onMessage, onRefresh }: Props) {
  const [offers, setOffers] = useState<EmploymentOffer[]>([])
  const [loading, setLoading] = useState(false)
  const [salary, setSalary] = useState('')
  const [title, setTitle] = useState('')
  const [wordingEn, setWordingEn] = useState('')
  const [acting, setActing] = useState(false)

  const current = offers.find((o) => ['draft', 'pending_approval', 'approved', 'sent', 'accepted'].includes(o.status)) || offers[0]
  const actions = new Set(current?.allowed_actions || [])

  const reload = async () => {
    if (!enabled) return
    setLoading(true)
    try {
      const result = await listApplicationOffers(access, appKey)
      setOffers(result.items || [])
    } catch (error) {
      onMessage(error instanceof Error ? error.message : 'Could not load offers.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [access.token, access.companyCode, appKey, enabled])

  if (!enabled) return null

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setActing(true)
    try {
      await fn()
      onMessage(label)
      await reload()
      onRefresh?.()
    } catch (error) {
      onMessage(error instanceof Error ? error.message : label)
    } finally {
      setActing(false)
    }
  }

  return (
    <section className="mt-6 rounded-2xl border border-line/70 bg-white/50 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-ink">Employment offer</h3>
          <p className="text-xs text-subtle">Formal offer lifecycle — separate from application stage.</p>
        </div>
        {current ? <Badge>{current.status_label || current.status}</Badge> : null}
      </div>

      {loading && !current ? <p className="mt-3 text-xs text-subtle">Loading offer…</p> : null}

      {!current ? (
        <div className="mt-4 space-y-3">
          <input
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"
            placeholder="Position title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"
            placeholder="Base salary (KWD)"
            value={salary}
            onChange={(e) => setSalary(e.target.value)}
          />
          <textarea
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"
            placeholder="Offer wording (English)"
            rows={3}
            value={wordingEn}
            onChange={(e) => setWordingEn(e.target.value)}
          />
          <Button
            disabled={busy || acting}
            size="sm"
            onClick={() =>
              void run('Offer draft created', () =>
                createOfferDraft(access, appKey, {
                  position_title: title || undefined,
                  base_salary: salary ? Number(salary) : undefined,
                  wording_en: wordingEn || undefined,
                  currency: 'KWD',
                }),
              )
            }
          >
            Create draft offer
          </Button>
        </div>
      ) : (
        <div className="mt-4 space-y-3 text-sm">
          <div className="grid gap-1 text-xs text-subtle">
            <div>Version {current.current_version}</div>
            <div>
              {current.position_title || current.position_code || 'Role'} · {current.base_salary || '—'} {current.currency}
            </div>
            {current.candidate_name_snapshot ? <div>Snapshot name: {current.candidate_name_snapshot}</div> : null}
            {current.delivery?.status ? (
              <div>
                Delivery (v{current.delivery.offer_version}): {current.delivery.status}
                {current.delivery.channel ? ` · ${current.delivery.channel}` : ''}
              </div>
            ) : null}
            {current.respond_url ? (
              <div className="break-all">Respond link: {current.respond_url}</div>
            ) : null}
          </div>

          {current.status === 'draft' ? (
            <div className="space-y-2">
              <input
                className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"
                placeholder="Update base salary"
                value={salary}
                onChange={(e) => setSalary(e.target.value)}
              />
              {actions.has('edit') ? (
                <Button
                  disabled={busy || acting}
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    void run('Offer updated', () =>
                      updateOfferDraft(access, current.offer_id, {
                        expected_version: current.current_version,
                        base_salary: salary ? Number(salary) : undefined,
                      }),
                    )
                  }
                >
                  Save draft version
                </Button>
              ) : null}
              {actions.has('submit_approval') ? (
                <Button
                  disabled={busy || acting}
                  size="sm"
                  onClick={() => void run('Submitted for approval', () => submitOfferApproval(access, current.offer_id))}
                >
                  Submit for approval
                </Button>
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {actions.has('approve') ? (
              <Button disabled={busy || acting} size="sm" onClick={() => void run('Offer approved', () => approveOffer(access, current.offer_id))}>
                Approve
              </Button>
            ) : null}
            {actions.has('return_draft') ? (
              <Button
                disabled={busy || acting}
                size="sm"
                variant="secondary"
                onClick={() => void run('Returned to draft', () => returnOffer(access, current.offer_id, 'Needs revision'))}
              >
                Return
              </Button>
            ) : null}
            {actions.has('send') ? (
              <Button disabled={busy || acting} size="sm" onClick={() => void run('Offer sent', () => sendOffer(access, current.offer_id))}>
                Send offer
              </Button>
            ) : null}
            {actions.has('record_accept') ? (
              <Button
                disabled={busy || acting}
                size="sm"
                onClick={() => void run('Marked accepted', () => recordOfferResponse(access, current.offer_id, 'accepted'))}
              >
                Record accept
              </Button>
            ) : null}
            {actions.has('record_decline') ? (
              <Button
                disabled={busy || acting}
                size="sm"
                variant="secondary"
                onClick={() => void run('Marked declined', () => recordOfferResponse(access, current.offer_id, 'declined'))}
              >
                Record decline
              </Button>
            ) : null}
            {actions.has('withdraw') ? (
              <Button
                disabled={busy || acting}
                size="sm"
                variant="secondary"
                onClick={() => void run('Offer withdrawn', () => withdrawOffer(access, current.offer_id, 'Withdrawn by HR'))}
              >
                Withdraw
              </Button>
            ) : null}
          </div>
        </div>
      )}
    </section>
  )
}
