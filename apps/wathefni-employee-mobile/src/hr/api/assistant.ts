/** Mobile Assistant API + stream client (spine thin client). */

import { fetch as expoFetch } from 'expo/fetch'

import { ApiError } from './client'

const configuredBase = (process.env.EXPO_PUBLIC_API_BASE_URL || '').replace(/\/$/, '')

export type AssistantCapabilityPayload = {
  ok?: boolean
  surface?: string
  empty_state?: {
    headline?: string
    chips?: string[]
    modules?: Array<{ id?: string; label?: string }>
    has_capabilities?: boolean
    offerable?: string[]
  }
  catalog?: {
    offerable?: string[]
    enabled_modules?: string[]
    providers?: Record<string, boolean>
    unsupported_messaging?: string[]
  }
  unsupported_messaging?: string[]
}

export type AssistantChatResponse = {
  ok?: boolean
  reply_text?: string
  conversation_id?: string
  turn_id?: string
  candidate_cards?: Array<{
    app_key?: string
    name?: string
    position?: string
    phone?: string
  }>
  navigation?: Array<{
    type?: string
    page?: string
    label?: string
    prompt?: string
    app_key?: string
  }>
  confirmation?: {
    label?: string
    summary?: string
    is_active?: boolean
    status?: string
    pending_action_id?: string
  } | null
  workflow_card?: Record<string, unknown> | null
  audit?: { capability_offerable?: string[] }
}

export type StreamEvent = {
  type: 'typing' | 'delta' | 'done' | 'error' | 'progress'
  text?: string
  phase?: string
  message?: AssistantChatResponse | string
}

type ChatBody = {
  message: string
  conversation_id?: string | null
  locale?: 'en' | 'ar'
  confirm?: boolean
}

export async function fetchAssistantCapabilities(
  token: string | null | undefined,
  locale: 'en' | 'ar',
  signal?: AbortSignal,
): Promise<AssistantCapabilityPayload> {
  if (!configuredBase) throw new ApiError(0, 'api_not_configured', 'API not configured')
  const response = await expoFetch(
    `${configuredBase}/dashboard/mobile/assistant/capabilities?locale=${locale}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal,
    },
  )
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = (payload as { detail?: { error?: string; message?: string } })?.detail
    throw new ApiError(
      response.status,
      detail?.error || 'assistant_capabilities_failed',
      detail?.message || 'Could not load Assistant capabilities.',
    )
  }
  return payload as AssistantCapabilityPayload
}

export async function postAssistantChat(
  token: string | null | undefined,
  body: ChatBody,
  signal?: AbortSignal,
): Promise<AssistantChatResponse> {
  if (!configuredBase) throw new ApiError(0, 'api_not_configured', 'API not configured')
  const response = await expoFetch(`${configuredBase}/dashboard/mobile/assistant/chat`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = (payload as { detail?: { error?: string; message?: string } })?.detail
    throw new ApiError(
      response.status,
      detail?.error || 'assistant_chat_failed',
      detail?.message || 'Assistant could not complete this turn.',
    )
  }
  return payload as AssistantChatResponse
}

function parseSseBuffer(
  buffer: string,
  onEvent: (event: StreamEvent) => void,
): { rest: string; final: AssistantChatResponse | null } {
  const chunks = buffer.split('\n\n')
  const rest = chunks.pop() || ''
  let final: AssistantChatResponse | null = null
  for (const chunk of chunks) {
    const line = chunk.split('\n').find((item) => item.startsWith('data: '))
    if (!line) continue
    try {
      const event = JSON.parse(line.slice(6)) as StreamEvent
      onEvent(event)
      if (event.type === 'done' && event.message && typeof event.message === 'object') {
        final = event.message
      }
    } catch {
      // ignore malformed frames
    }
  }
  return { rest, final }
}

/**
 * Prefer SSE stream via expo/fetch (RN-native streaming). Fall back to JSON + caller reveal.
 */
export async function streamAssistantChat(
  token: string | null | undefined,
  body: ChatBody,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<AssistantChatResponse> {
  if (!configuredBase) throw new ApiError(0, 'api_not_configured', 'API not configured')
  onEvent({ type: 'typing', phase: 'thinking' })
  try {
    const response = await expoFetch(`${configuredBase}/dashboard/mobile/assistant/chat/stream`, {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    })
    if (!response.ok) {
      return postAssistantChat(token, body, signal)
    }
    const bodyStream = response.body
    if (!bodyStream || typeof bodyStream.getReader !== 'function') {
      const fallback = await postAssistantChat(token, body, signal)
      await revealTextAsDeltas(String(fallback.reply_text || ''), onEvent, signal)
      onEvent({ type: 'done', message: fallback })
      return fallback
    }
    const reader = bodyStream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalPayload: AssistantChatResponse | null = null
    while (true) {
      if (signal?.aborted) {
        await reader.cancel().catch(() => undefined)
        throw new DOMException('Aborted', 'AbortError')
      }
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parsed = parseSseBuffer(buffer, onEvent)
      buffer = parsed.rest
      if (parsed.final) finalPayload = parsed.final
    }
    if (buffer.trim()) {
      const parsed = parseSseBuffer(`${buffer}\n\n`, onEvent)
      if (parsed.final) finalPayload = parsed.final
    }
    if (finalPayload) return finalPayload
    return postAssistantChat(token, body, signal)
  } catch (error) {
    if (signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) {
      throw error
    }
    const fallback = await postAssistantChat(token, body, signal)
    await revealTextAsDeltas(String(fallback.reply_text || ''), onEvent, signal)
    onEvent({ type: 'done', message: fallback })
    return fallback
  }
}

/** Client-side progressive reveal when the transport cannot stream frames live. */
async function revealTextAsDeltas(
  text: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const raw = String(text || '')
  if (!raw) return
  const parts = raw.split(/(\s+)/)
  let buf = ''
  for (let i = 0; i < parts.length; i += 1) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    buf += parts[i]
    if (buf.length >= 12 || i === parts.length - 1) {
      onEvent({ type: 'delta', text: buf })
      buf = ''
      await sleep(28)
    }
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
