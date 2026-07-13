type Tone = 'neutral' | 'success' | 'warning' | 'danger'
const KNOWN_STATUSES = new Set([
  'approved',
  'received',
  'present',
  'requested',
  'pending',
  'late',
  'scheduled',
  'rejected',
  'cancelled',
  'absent',
])

export function statusTone(status: string | null | undefined): Tone {
  switch ((status || '').toLowerCase()) {
    case 'approved':
    case 'received':
    case 'present':
      return 'success'
    case 'requested':
    case 'pending':
    case 'late':
    case 'scheduled':
      return 'warning'
    case 'rejected':
    case 'cancelled':
    case 'absent':
      return 'danger'
    default:
      return 'neutral'
  }
}

export function statusLabel(
  status: string | null | undefined,
  t: (key: string) => string,
): string {
  const normalized = (status || '').trim().toLowerCase()
  return t(KNOWN_STATUSES.has(normalized) ? `status.${normalized}` : 'status.unknown')
}

export function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar' : 'en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(d)
}

export function formatTimeRange(start: string | null, end: string | null): string {
  const fmt = (t: string | null) => (t ? String(t).slice(0, 5) : null)
  const s = fmt(start)
  const e = fmt(end)
  if (s && e) return `${s} – ${e}`
  return s || e || '—'
}
