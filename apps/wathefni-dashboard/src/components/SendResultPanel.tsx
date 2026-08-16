import { Badge } from '@/components/ui/badge'

export type OutboundSendChannel = {
  channel: string
  label?: string
  state: 'sent' | 'queued' | 'failed' | string
  ok?: boolean
  provider?: string
  message_id?: string | null
  sent_at?: string | null
  error?: string | null
}

export type OutboundSendResult = {
  version?: string
  kind?: string
  state: 'sent' | 'queued' | 'partially_sent' | 'failed' | string
  ok?: boolean
  message?: string
  human_error?: string | null
  suggested_next_action?: string | null
  recipient?: { name?: string | null; email?: string | null; phone?: string | null }
  channels?: OutboundSendChannel[]
  channels_attempted?: string[]
  timestamp?: string
}

export function SendResultPanel({ result, locale = 'en' }: { result: OutboundSendResult; locale?: 'en' | 'ar' }) {
  const isAr = locale === 'ar'
  const tone = result.state === 'sent' ? 'success' : result.state === 'partially_sent' || result.state === 'queued' ? 'warning' : 'danger'
  const stateLabel = {
    sent: isAr ? 'تم الإرسال' : 'Sent',
    queued: isAr ? 'قيد الإرسال' : 'Queued',
    partially_sent: isAr ? 'إرسال جزئي' : 'Partially sent',
    failed: isAr ? 'فشل الإرسال' : 'Failed',
  }[String(result.state)] || result.state
  return (
    <div className="rounded-[1.4rem] border border-line/60 bg-panel/85 p-4 ring-1 ring-white/50" dir={isAr ? 'rtl' : 'ltr'}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-text">{isAr ? 'نتيجة الإرسال' : 'Send result'}</div>
          {result.recipient?.name || result.recipient?.email || result.recipient?.phone ? (
            <div className="mt-0.5 text-xs text-subtle">
              {result.recipient?.name || ''}
              {result.recipient?.email ? ` · ${result.recipient.email}` : ''}
              {!result.recipient?.email && result.recipient?.phone ? ` · ${result.recipient.phone}` : ''}
            </div>
          ) : null}
        </div>
        <Badge tone={tone}>{stateLabel}</Badge>
      </div>
      {result.message ? <p className="mt-2 text-sm leading-6 text-subtle">{result.message}</p> : null}
      {result.channels?.length ? (
        <div className="mt-3 space-y-2">
          {result.channels.map((channel) => (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line/55 bg-white/40 px-3 py-2 text-sm" key={channel.channel}>
              <span className="font-medium text-text">{channel.label || channel.channel}</span>
              <span className="flex items-center gap-2 text-xs text-subtle">
                {channel.provider ? <span>{channel.provider}</span> : null}
                <Badge tone={channel.state === 'sent' ? 'success' : channel.state === 'queued' ? 'warning' : 'danger'}>
                  {channel.state === 'sent' ? (isAr ? 'تم الإرسال' : 'Sent') : channel.state === 'queued' ? (isAr ? 'قيد الإرسال' : 'Queued') : (isAr ? 'فشل' : 'Failed')}
                </Badge>
              </span>
              {channel.error ? <div className="w-full text-xs text-rose-700">{channel.error}</div> : null}
            </div>
          ))}
        </div>
      ) : null}
      {result.human_error ? <p className="mt-2 text-xs text-rose-700">{result.human_error}</p> : null}
      {result.suggested_next_action ? <p className="mt-2 text-xs text-subtle">{result.suggested_next_action}</p> : null}
      {result.timestamp ? <p className="mt-2 text-[11px] text-subtle/80">{result.timestamp}</p> : null}
    </div>
  )
}

export function extractSendResult(payload: unknown): OutboundSendResult | null {
  if (!payload || typeof payload !== 'object') return null
  const data = payload as Record<string, unknown>
  const result = (data.send_result || data.sendResult) as OutboundSendResult | undefined
  if (result && typeof result === 'object' && result.state) return result
  return null
}
