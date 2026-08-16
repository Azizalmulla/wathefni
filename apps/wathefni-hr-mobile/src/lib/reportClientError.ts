import { rawRequest } from '@/api/client'

const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi
const PHONE_RE = /\+?\d[\d\s-]{7,16}\d/g

export function redactClientText(value: string, limit = 400): string {
  return String(value || '')
    .replace(EMAIL_RE, '[redacted-email]')
    .replace(PHONE_RE, '[redacted-phone]')
    .slice(0, limit)
}

export function reportClientError(error: unknown): void {
  const name = error instanceof Error ? error.name : 'Error'
  const message = redactClientText(error instanceof Error ? error.message : 'unspecified_client_error')
  void rawRequest('/dashboard/mobile/telemetry/error', {
    method: 'POST',
    json: { surface: 'hr_mobile', name, message },
  }).catch(() => undefined)
}
