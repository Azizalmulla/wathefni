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
  'in_progress',
  'submitted',
  'processing',
  'accepted',
  'replacement_required',
  'waived',
  'blocked',
])

export function statusTone(status: string | null | undefined): Tone {
  switch ((status || '').toLowerCase()) {
    case 'approved':
    case 'accepted':
    case 'waived':
    case 'present':
    case 'reviewed':
    case 'completed':
      return 'success'
    case 'received':
    case 'submitted':
    case 'processing':
    case 'in_progress':
    case 'requested':
    case 'pending':
    case 'late':
    case 'scheduled':
      return 'warning'
    case 'rejected':
    case 'replacement_required':
    case 'cancelled':
    case 'blocked':
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

/**
 * A leave request for one day is one date.
 *
 * Leave history printed `12 Mar 2026 – 12 Mar 2026` for every single-day request,
 * which is most of them, and made the list twice as wide as it needed to be for
 * no added information.
 */
export function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: string,
): string {
  const from = String(start || '').trim()
  const to = String(end || '').trim()
  if (!from && !to) return '—'
  if (!to || from === to) return formatDate(from || to, locale)
  if (!from) return formatDate(to, locale)
  return `${formatDate(from, locale)} – ${formatDate(to, locale)}`
}

/** Calendar year of a stored date, for grouping long history. Null when unparseable. */
export function yearOf(value: string | null | undefined): number | null {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) {
    const match = /^(\d{4})/.exec(String(value).trim())
    return match ? Number(match[1]) : null
  }
  return d.getFullYear()
}

/**
 * "2h ago" rather than a date stamp, for inbox messages.
 *
 * An employee scanning their inbox wants to know whether something is new, and
 * `8 Aug 2026` does not answer that at a glance. Anything older than a week falls
 * back to the absolute date, where the exact day is what matters again.
 */
export function formatRelativeTime(
  value: string | null | undefined,
  locale: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
  now: number = Date.now(),
): string {
  if (!value) return '—'
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return '—'
  const seconds = Math.round((now - then) / 1000)
  // A clock skew between device and server must not read as "in the future".
  if (seconds < 60) return t('time.justNow')
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return t('time.minutesAgo', { count: formatNumber(minutes, locale, 0) })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return t('time.hoursAgo', { count: formatNumber(hours, locale, 0) })
  const days = Math.floor(hours / 24)
  if (days === 1) return t('time.yesterday')
  if (days < 7) return t('time.daysAgo', { count: formatNumber(days, locale, 0) })
  return formatDate(value, locale)
}

/** Today's calendar date in Kuwait as `YYYY-MM-DD`, independent of device zone. */
export function kuwaitToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Kuwait',
  }).format(now)
}

/**
 * Whole days from today until a stored expiry date, counted in Kuwait days.
 *
 * Both sides are calendar dates, so this compares date strings rather than
 * instants — a document does not expire at a different hour depending on where
 * the employee is holding their phone. Negative means already past; null means
 * the date was missing or unparseable, and the caller must then say nothing
 * about timing rather than fall back to "today".
 */
export function daysUntil(value: string | null | undefined, today: string = kuwaitToday()): number | null {
  const target = String(value || '').trim().slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(target) || !/^\d{4}-\d{2}-\d{2}$/.test(today)) return null
  const to = Date.parse(`${target}T00:00:00Z`)
  const from = Date.parse(`${today}T00:00:00Z`)
  if (Number.isNaN(to) || Number.isNaN(from)) return null
  return Math.round((to - from) / 86_400_000)
}

/**
 * Exact date and time in Kuwait, for the places relative time is only a summary.
 *
 * Empty string rather than an em dash: the caller composes this into a longer
 * sentence, where a dash would read as a missing word.
 */
export function formatDateTime(value: string | null | undefined, locale = 'en'): string {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar-KW-u-nu-arab' : 'en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kuwait',
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

/**
 * Format an absolute timestamp as a Kuwait wall-clock time. Attendance check-in/out are
 * stored as instants, but the employee's workday is a Kuwait day, so the device time
 * zone must not shift what they see.
 */
export function formatClockTime(value: string | null | undefined, locale = 'en'): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar-KW-u-nu-arab' : 'en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kuwait',
  }).format(d)
}

export function formatTimeRange(start: string | null, end: string | null, locale = 'en'): string {
  const fmt = (t: string | null) => (t ? String(t).slice(0, 5) : null)
  const s = fmt(start)
  const e = fmt(end)
  const range = s && e ? `${s} – ${e}` : s || e || '—'
  return localizeNumerals(range, locale)
}
