import type { Locale } from '@hr/api/types'

function parsed(value: string | null | undefined): Date | null {
  if (!value) return null
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value)
  const date = new Date(dateOnly ? `${value}T12:00:00` : value)
  return Number.isNaN(date.getTime()) ? null : date
}

function language(locale: Locale): string {
  return locale === 'ar' ? 'ar-KW-u-nu-arab' : 'en-GB'
}

export function formatDate(value: string | null | undefined, locale: Locale): string {
  const date = parsed(value)
  if (!date) return '—'
  return new Intl.DateTimeFormat(language(locale), {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(date)
}

export function formatTime(value: string | null | undefined, locale: Locale): string {
  const date = parsed(value)
  if (!date) return '—'
  return new Intl.DateTimeFormat(language(locale), {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}

export function formatDateTime(value: string | null | undefined, locale: Locale): string {
  const date = parsed(value)
  if (!date) return '—'
  return new Intl.DateTimeFormat(language(locale), {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}

export function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: Locale,
): string {
  const from = parsed(start)
  const to = parsed(end)
  if (!from && !to) return '—'
  if (!from) return formatDate(end, locale)
  if (!to) return formatDate(start, locale)
  const formatter = new Intl.DateTimeFormat(language(locale), {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  if (typeof formatter.formatRange === 'function') return formatter.formatRange(from, to)
  return `${formatter.format(from)} – ${formatter.format(to)}`
}

export function formatTimeRange(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: Locale,
): string {
  if (!parsed(start) && !parsed(end)) return '—'
  const separator = locale === 'ar' ? ' إلى ' : '–'
  return `${formatTime(start, locale)} ${separator} ${formatTime(end, locale)}`
}
