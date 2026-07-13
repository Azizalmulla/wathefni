type Tone = 'neutral' | 'success' | 'warning' | 'danger'
const KNOWN_STATUSES = new Set([
  'approved',
  'received',
  'present',
  'requested',
  'pending',
  'late',
  'scheduled',
  'reviewed',
  'completed',
  'rejected',
  'cancelled',
  'absent',
])

export function statusTone(status: string | null | undefined): Tone {
  switch ((status || '').toLowerCase()) {
    case 'approved':
    case 'received':
    case 'present':
    case 'reviewed':
    case 'completed':
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

export function localizeNumerals(value: string | number, locale: string): string {
  const text = String(value)
  if (locale !== 'ar') return text
  const arabicDigits = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩']
  return text.replace(/\d/g, (digit) => arabicDigits[Number(digit)])
}

export function formatNumber(value: number, locale: string, maximumFractionDigits = 1): string {
  return new Intl.NumberFormat(locale === 'ar' ? 'ar-KW-u-nu-arab' : 'en-GB', {
    maximumFractionDigits,
    useGrouping: false,
  }).format(value)
}

export function formatTimeRange(start: string | null, end: string | null, locale = 'en'): string {
  const fmt = (t: string | null) => (t ? String(t).slice(0, 5) : null)
  const s = fmt(start)
  const e = fmt(end)
  const range = s && e ? `${s} – ${e}` : s || e || '—'
  return localizeNumerals(range, locale)
}
