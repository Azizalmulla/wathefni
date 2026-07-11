import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function compactNumber(value: number | string | null | undefined) {
  if (typeof value === 'string' && value.trim() && Number.isNaN(Number(value))) return value
  const numeric = Number(value ?? 0)
  if (Number.isNaN(numeric)) return '—'
  return new Intl.NumberFormat('en', { notation: 'compact' }).format(numeric)
}

/**
 * Run an async task over a list with bounded concurrency, preserving input order
 * in the results. Bulk actions (e.g. "remind everyone in view") can fan out a few
 * requests at a time instead of one strictly-sequential await per item — much
 * faster at scale, without hammering the server with N simultaneous calls.
 */
export async function mapWithConcurrency<T, R>(
  items: readonly T[],
  limit: number,
  task: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length)
  let cursor = 0
  const workerCount = Math.max(1, Math.min(Math.floor(limit) || 1, items.length))
  const worker = async () => {
    for (let index = cursor++; index < items.length; index = cursor++) {
      results[index] = await task(items[index], index)
    }
  }
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
  return results
}

export function statusTone(status: string | null | undefined): 'default' | 'success' | 'warning' | 'danger' | 'muted' {
  const normalized = String(status || '').toLowerCase()
  if (['sent', 'completed', 'hired', 'shortlisted', 'screening_complete', 'strong', 'qualified'].includes(normalized)) return 'success'
  if (['failed', 'rejected', 'blocked_closed_conversation', 'blocked_by_closed_conversation', 'no_usable_conversation', 'no_show', 'cancelled'].includes(normalized)) return 'danger'
  if (['stale', 'stale_conversation', 'pending', 'in_progress', 'awaiting_cv', 'review_pending', 'interview', 'needs_review', 'scheduled', 'rescheduled', 'notes_pending'].includes(normalized)) return 'warning'
  return 'muted'
}
