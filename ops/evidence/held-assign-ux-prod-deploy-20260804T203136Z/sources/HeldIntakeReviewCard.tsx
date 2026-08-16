/** Wave D Phase 4 — lightweight held-CV review inside Candidates (not Intake Operations). */

import { AlertTriangle, Check, CheckCheck, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { useConfirm } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select } from '@/components/ui/field'
import {
  bulkImportAction,
  getImportIntake,
  previewCandidateCv,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  groupAllowsSafeBulkAdmit,
  heldGroupKindLabel,
  intakeStatePresentation,
} from '@/lib/inboundIntakePresentation'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import { friendlyDashboardError } from '@/pages/shared/format'
import type {
  ApplicationSummary,
  DashboardAccess,
  ImportIntakeGroup,
  PositionSummary,
} from '@/types'

function openJobs(positions: PositionSummary[]) {
  return positions.filter((job) => String(job.status || '').toLowerCase() === 'open')
}

export function HeldIntakeReviewCard({
  access,
  positions,
  applications,
  locale,
  reloadKey = 0,
  onChanged,
  onOpenCandidate,
  onAccessIssue,
}: {
  access: DashboardAccess
  positions: PositionSummary[]
  applications: ApplicationSummary[]
  locale: RecruitingLocale
  reloadKey?: number
  onChanged: () => void
  onOpenCandidate?: (appKey: string) => void
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const isAr = locale === 'ar'
  const confirm = useConfirm()
  const [groups, setGroups] = useState<ImportIntakeGroup[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  /** Per-candidate assign drafts (app_key → position_code). */
  const [rowAssignDraft, setRowAssignDraft] = useState<Record<string, string>>({})
  /** Which row currently shows the assign-job selector. */
  const [assigningAppKey, setAssigningAppKey] = useState<string | null>(null)
  /** Explicit bulk job draft — only used when checkboxes are selected. */
  const [bulkAssignDraft, setBulkAssignDraft] = useState<Record<string, string>>({})
  const [busyKey, setBusyKey] = useState('')
  const jobs = useMemo(() => openJobs(positions), [positions])

  const identityWarned = useMemo(() => {
    const map = new Map<string, boolean>()
    for (const app of applications) {
      const key = String(app.app_key || '')
      if (!key) continue
      const flagged = Boolean(
        (app as { identity_review_warning?: boolean }).identity_review_warning
          || String(app.status || '').toLowerCase() === 'identity_review',
      )
      map.set(key, flagged)
    }
    return map
  }, [applications])

  const refresh = useCallback(async () => {
    try {
      const response = await getImportIntake(access, 500)
      setGroups(response.groups || [])
      setTotal(response.total || 0)
      setSelected((current) => {
        const live = new Set((response.groups || []).flatMap((g) => g.app_keys))
        return new Set([...current].filter((key) => live.has(key)))
      })
      setAssigningAppKey(null)
      setError('')
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(
        friendlyDashboardError(
          err,
          isAr ? 'تعذر تحميل السير المعلّقة.' : 'Could not load held CVs.',
          locale,
        ),
      )
    } finally {
      setLoading(false)
    }
  }, [access, isAr, locale, onAccessIssue])

  useEffect(() => {
    void refresh()
  }, [refresh, reloadKey])

  /** Explicit selection only — never fall back to the whole group. */
  const selectedKeysInGroup = (group: ImportIntakeGroup) =>
    group.app_keys.filter((key) => selected.has(key))

  const toggleItem = (appKey: string) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(appKey)) next.delete(appKey)
      else next.add(appKey)
      return next
    })
  }

  const runAction = async (
    action: 'confirm' | 'assign',
    appKeys: string[],
    opts?: { positionCode?: string; roleLabel?: string; busyToken: string },
  ) => {
    if (!appKeys.length) return
    const body: {
      action: 'confirm' | 'assign'
      app_keys: string[]
      position_code?: string
      position_title?: string
    } = { action, app_keys: appKeys }
    if (action === 'assign') {
      const code = String(opts?.positionCode || '').trim()
      if (!code) {
        setError(isAr ? 'اختر وظيفة قبل الإضافة.' : 'Pick a job before admitting.')
        return
      }
      body.position_code = code
      body.position_title = jobs.find((j) => j.position_code === code)?.position_title || code
    }

    const warned = appKeys.filter((key) => identityWarned.get(key))
    const n = appKeys.length
    const title =
      action === 'confirm'
        ? isAr
          ? `إضافة ${n} مرشح؟`
          : `Admit ${n} candidate${n === 1 ? '' : 's'}?`
        : isAr
          ? `تعيين وإضافة ${n}؟`
          : `Assign and admit ${n}?`
    const roleLabel = opts?.roleLabel || body.position_title || ''
    const bodyText = [
      action === 'confirm'
        ? isAr
          ? n === 1
            ? `سيُضاف هذا المرشح إلى «${roleLabel}» ويظهر في المرشحين.`
            : `سيُضاف ${n} مرشحين محددين إلى «${roleLabel}» ويظهرون في المرشحين.`
          : n === 1
            ? `This candidate will join “${roleLabel}” and appear in Candidates.`
            : `${n} selected candidates will join “${roleLabel}” and appear in Candidates.`
        : isAr
          ? n === 1
            ? `سيُعيَّن هذا المرشح إلى «${body.position_title}» ثم يُضاف.`
            : `سيُعيَّن ${n} مرشحين محددين إلى نفس الوظيفة «${body.position_title}» ثم يُضافون.`
          : n === 1
            ? `This candidate will be assigned to “${body.position_title}” then admitted.`
            : `${n} selected candidates will all receive the same job “${body.position_title}” then be admitted.`,
      warned.length
        ? isAr
          ? `${warned.length} لديهم تحذير هوية — راجعهم قبل المتابعة إن لزم.`
          : `${warned.length} have an identity warning — review before continuing if needed.`
        : '',
    ]
      .filter(Boolean)
      .join(' ')

    if (
      !(await confirm({
        title,
        body: bodyText,
        confirmLabel: isAr ? 'إضافة' : 'Admit',
      }))
    ) {
      return
    }

    setBusyKey(opts?.busyToken || `${action}:${appKeys.join(',')}`)
    setError('')
    setSuccess('')
    try {
      const res = await bulkImportAction(access, body)
      await refresh()
      onChanged()
      const parts: string[] = []
      if (res.promoted) parts.push(isAr ? `${res.promoted} أُضيفوا` : `${res.promoted} admitted`)
      if (res.skipped) parts.push(isAr ? `${res.skipped} تُخطّوا` : `${res.skipped} skipped`)
      setSuccess(parts.length ? parts.join(' · ') : isAr ? 'تم.' : 'Done.')
      setAssigningAppKey(null)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(
        friendlyDashboardError(
          err,
          isAr ? 'تعذر تحديث هؤلاء المرشحين.' : 'Could not update these candidates.',
          locale,
        ),
      )
    } finally {
      setBusyKey('')
    }
  }

  if (loading && !groups.length && !error) {
    return (
      <Card data-testid="held-intake-review">
        <CardContent className="flex items-center gap-2 py-4 text-sm text-subtle">
          <Loader2 className="animate-spin" size={16} />
          {isAr ? 'جاري تحميل السير المعلّقة…' : 'Loading held CVs…'}
        </CardContent>
      </Card>
    )
  }

  if (!groups.length && !error) return null

  const needsRole = intakeStatePresentation('needs_role', locale)
  const identity = intakeStatePresentation('identity_review', locale)
  const quarantined = intakeStatePresentation('quarantined', locale)

  return (
    <Card data-testid="held-intake-review" data-held-assign-scope="explicit">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              {isAr ? 'سير معلّقة بانتظار وظيفة' : 'Held CVs waiting for a job'}
              {total ? <Badge tone="warning">{total}</Badge> : null}
            </CardTitle>
            <CardDescription>
              {isAr
                ? 'الفعل الافتراضي لكل مرشح: تعيين وظيفة ثم إضافة صريحة. التحديد المتعدد للتعيين الجماعي فقط.'
                : 'Default action is per candidate: Assign job, then admit explicitly. Checkboxes are for bulk assignment only.'}
            </CardDescription>
          </div>
          {groups.length ? (
            <Button onClick={() => setCollapsed((v) => !v)} size="sm" type="button" variant="ghost">
              {collapsed ? (isAr ? 'إظهار' : 'Show') : isAr ? 'إخفاء' : 'Hide'}
            </Button>
          ) : null}
        </div>
      </CardHeader>
      {!collapsed ? (
        <CardContent className="space-y-3" dir={isAr ? 'rtl' : 'ltr'}>
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge tone={needsRole.tone}>{needsRole.label}</Badge>
            <Badge tone={identity.tone}>{identity.label}</Badge>
            <Badge tone={quarantined.tone}>{quarantined.label}</Badge>
            <Badge tone="success">{intakeStatePresentation('ready', locale).label}</Badge>
          </div>
          <p className="text-xs leading-5 text-subtle">
            {quarantined.hint} {quarantined.recovery}
          </p>

          {error ? (
            <div className="flex items-start gap-2 rounded-2xl border border-rose-200/70 bg-rose-50/70 px-4 py-2.5 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 shrink-0" size={16} />
              <span>{error}</span>
            </div>
          ) : null}
          {success ? <p className="text-sm text-emerald-800">{success}</p> : null}

          {groups.map((group) => {
            const safeBulk = groupAllowsSafeBulkAdmit(group)
            const selectedKeys = selectedKeysInGroup(group)
            const selectedCount = selectedKeys.length
            const showBulkToolbar = selectedCount > 0
            const bulkJob = bulkAssignDraft[group.key] ?? ''
            const groupWarned = group.app_keys.some((key) => identityWarned.get(key))
            return (
              <div key={group.key} className="rounded-2xl border border-line bg-panel-muted/40" data-testid={`held-group-${group.kind}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/60 px-3 py-2.5">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-text">
                      <span>{heldGroupKindLabel(group.kind, locale)}</span>
                      {group.role_title || group.role_code ? (
                        <span className="font-normal text-subtle">· {group.role_title || group.role_code}</span>
                      ) : null}
                      <Badge tone="muted">{group.count}</Badge>
                      {groupWarned ? <Badge tone="warning">{identity.label}</Badge> : null}
                    </div>
                    <p className="text-xs text-subtle">{needsRole.hint}</p>
                  </div>
                </div>

                {showBulkToolbar ? (
                  <div
                    className="flex flex-wrap items-center gap-2 border-b border-line/60 bg-panel px-3 py-2.5"
                    data-testid="held-bulk-toolbar"
                    data-held-bulk-count={selectedCount}
                  >
                    <p className="w-full text-xs font-medium text-text" data-testid="held-bulk-copy">
                      {isAr
                        ? `${selectedCount} محددون — سيحصل جميع المحددين على نفس الوظيفة.`
                        : `${selectedCount} selected — all selected candidates will receive the same job.`}
                    </p>
                    <Select
                      aria-label={isAr ? 'وظيفة للتعيين الجماعي' : 'Job for bulk assignment'}
                      className="w-52"
                      data-testid="held-bulk-job-select"
                      onChange={(event) =>
                        setBulkAssignDraft((current) => ({ ...current, [group.key]: event.target.value }))
                      }
                      value={bulkJob}
                    >
                      <option value="">{isAr ? 'اختر وظيفة…' : 'Choose a job…'}</option>
                      {jobs.map((job) => (
                        <option key={job.position_code} value={job.position_code}>
                          {job.position_title || job.position_code}
                        </option>
                      ))}
                    </Select>
                    <Button
                      data-testid="held-bulk-assign-admit"
                      disabled={!bulkJob || busyKey.startsWith(`bulk:${group.key}:`)}
                      onClick={() =>
                        void runAction('assign', selectedKeys, {
                          positionCode: bulkJob,
                          busyToken: `bulk:${group.key}:assign`,
                        })
                      }
                      size="sm"
                      type="button"
                      variant="secondary"
                    >
                      {busyKey === `bulk:${group.key}:assign` ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
                      {isAr ? `تعيين وإضافة ${selectedCount}` : `Assign and admit ${selectedCount}`}
                    </Button>
                    {safeBulk ? (
                      <Button
                        data-testid="held-bulk-admit"
                        disabled={busyKey.startsWith(`bulk:${group.key}:`)}
                        onClick={() =>
                          void runAction('confirm', selectedKeys, {
                            roleLabel: group.role_title || group.role_code || '',
                            busyToken: `bulk:${group.key}:confirm`,
                          })
                        }
                        size="sm"
                        type="button"
                      >
                        {busyKey === `bulk:${group.key}:confirm` ? (
                          <Loader2 className="animate-spin" size={14} />
                        ) : (
                          <CheckCheck size={14} />
                        )}
                        {isAr ? `إضافة ${selectedCount}` : `Admit ${selectedCount}`}
                      </Button>
                    ) : null}
                  </div>
                ) : null}

                <ul className="divide-y divide-line/50">
                  {group.items.map((item) => {
                    const warned = identityWarned.get(item.app_key)
                    const state = intakeStatePresentation(warned ? 'identity_review' : item.status || 'needs_role', locale)
                    const rowOpen = assigningAppKey === item.app_key
                    const rowJob = rowAssignDraft[item.app_key] ?? ''
                    const suggestionLabel =
                      group.kind === 'suggested' && (group.role_title || group.role_code)
                        ? isAr
                          ? `اقتراح: ${group.role_title || group.role_code}`
                          : `Suggestion: ${group.role_title || group.role_code}`
                        : null
                    return (
                      <li key={item.app_key} className="space-y-2 px-3 py-2 text-sm" data-testid={`held-row-${item.app_key}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <input
                            aria-label={
                              isAr
                                ? `تحديد ${item.candidate_name || item.app_key} للتعيين الجماعي`
                                : `Select ${item.candidate_name || item.app_key} for bulk assignment`
                            }
                            checked={selected.has(item.app_key)}
                            className="h-4 w-4 rounded border-subtle/40 accent-ink"
                            data-testid={`held-select-${item.app_key}`}
                            onChange={() => toggleItem(item.app_key)}
                            type="checkbox"
                          />
                          <button
                            className="min-w-0 flex-1 truncate text-start font-medium text-text hover:underline"
                            onClick={() => onOpenCandidate?.(item.app_key)}
                            type="button"
                          >
                            {item.candidate_name || item.original_filename || item.app_key}
                          </button>
                          <Badge tone={state.tone}>{state.label}</Badge>
                          {suggestionLabel ? (
                            <Badge data-testid={`held-suggestion-${item.app_key}`} tone="muted">
                              {suggestionLabel}
                            </Badge>
                          ) : null}
                          {warned ? (
                            <span className="text-xs text-amber-800" title={state.hint}>
                              {state.recovery}
                            </span>
                          ) : null}
                          <Button
                            onClick={() =>
                              void previewCandidateCv(access, item.app_key).catch((err) => {
                                setError(
                                  friendlyDashboardError(err, isAr ? 'تعذر فتح السيرة.' : 'Could not open CV.', locale),
                                )
                              })
                            }
                            size="sm"
                            type="button"
                            variant="ghost"
                          >
                            {isAr ? 'معاينة' : 'Preview'}
                          </Button>
                          {safeBulk ? (
                            <Button
                              data-testid={`held-admit-${item.app_key}`}
                              disabled={busyKey === `row:${item.app_key}:confirm`}
                              onClick={() =>
                                void runAction('confirm', [item.app_key], {
                                  roleLabel: group.role_title || group.role_code || '',
                                  busyToken: `row:${item.app_key}:confirm`,
                                })
                              }
                              size="sm"
                              type="button"
                              variant="ghost"
                            >
                              {busyKey === `row:${item.app_key}:confirm` ? (
                                <Loader2 className="animate-spin" size={14} />
                              ) : (
                                <CheckCheck size={14} />
                              )}
                              {isAr ? 'إضافة' : 'Admit'}
                            </Button>
                          ) : null}
                          <Button
                            data-testid={`held-assign-job-${item.app_key}`}
                            onClick={() => {
                              setAssigningAppKey((current) => (current === item.app_key ? null : item.app_key))
                              if (group.role_code && !rowAssignDraft[item.app_key]) {
                                setRowAssignDraft((current) => ({
                                  ...current,
                                  [item.app_key]: group.role_code || '',
                                }))
                              }
                            }}
                            size="sm"
                            type="button"
                            variant="secondary"
                          >
                            {isAr ? 'تعيين وظيفة' : 'Assign job'}
                          </Button>
                        </div>
                        {rowOpen ? (
                          <div
                            className="ms-6 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2"
                            data-testid={`held-row-assign-${item.app_key}`}
                          >
                            <Select
                              aria-label={isAr ? 'اختر وظيفة' : 'Choose a job'}
                              className="w-52"
                              data-testid={`held-row-job-select-${item.app_key}`}
                              onChange={(event) =>
                                setRowAssignDraft((current) => ({ ...current, [item.app_key]: event.target.value }))
                              }
                              value={rowJob}
                            >
                              <option value="">{isAr ? 'اختر وظيفة…' : 'Choose a job…'}</option>
                              {jobs.map((job) => (
                                <option key={job.position_code} value={job.position_code}>
                                  {job.position_title || job.position_code}
                                </option>
                              ))}
                            </Select>
                            <Button
                              data-testid={`held-row-assign-admit-${item.app_key}`}
                              disabled={!rowJob || busyKey === `row:${item.app_key}:assign`}
                              onClick={() =>
                                void runAction('assign', [item.app_key], {
                                  positionCode: rowJob,
                                  busyToken: `row:${item.app_key}:assign`,
                                })
                              }
                              size="sm"
                              type="button"
                            >
                              {busyKey === `row:${item.app_key}:assign` ? (
                                <Loader2 className="animate-spin" size={14} />
                              ) : (
                                <Check size={14} />
                              )}
                              {isAr ? 'تعيين وإضافة' : 'Assign and admit'}
                            </Button>
                          </div>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )
          })}
        </CardContent>
      ) : null}
    </Card>
  )
}
