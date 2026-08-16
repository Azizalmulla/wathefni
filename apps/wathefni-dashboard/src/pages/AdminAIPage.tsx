import { ArrowUp, Loader2, MessageCircle, Square } from 'lucide-react'
import { Profiler as ReactProfiler, useCallback, useEffect, useRef } from 'react'

import {
  dashboardPerfMarkInteractionStart,
  dashboardPerfMarkNetworkComplete,
  dashboardPerfMarkProfilerCommit,
} from '@/lib/perf/dashboardPerf'
import { type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { useBodyScrollLock, useOverlayFocus } from '@/hooks/useOverlayA11y'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/field'
import { EmptyState } from '@/pages/shared/primitives'
import { stageLabel } from '@/pages/shared/format'
import type {
  AssistantEmptyState,
  ChatMessage,
  DashboardChatNavigation,
  DashboardChatSession,
  DashboardChatWorkflowCard,
} from '@/types'

function AssistantProfiler({ id, children }: { id: string; children: React.ReactNode }) {
  const onRender = useCallback(
    (
      profilerId: string,
      phase: 'mount' | 'update' | 'nested-update',
      actualDuration: number,
      baseDuration: number,
    ) => {
      dashboardPerfMarkProfilerCommit(`assistant:${profilerId}`, {
        phase,
        actualDurationMs: Math.round(actualDuration),
        baseDurationMs: Math.round(baseDuration),
      })
    },
    [],
  )
  return (
    <ReactProfiler id={id} onRender={onRender}>
      {children}
    </ReactProfiler>
  )
}

function assistantCopy(locale: RecruitingLocale, key: string) {
  const ar = locale === 'ar'
  const copy: Record<string, [string, string]> = {
    title: ['OctoHR Assistant', 'مساعد OctoHR'],
    history: ['History', 'السجل'],
    new_chat: ['New chat', 'محادثة جديدة'],
    close: ['Close', 'إغلاق'],
    cancel: ['Cancel', 'إلغاء'],
    stop: ['Stop', 'إيقاف'],
    message: ['Message', 'رسالة'],
    confirm_required: ['Confirmation required', 'مطلوب تأكيد'],
    confirm_inactive: ['Confirmation inactive', 'التأكيد غير نشط'],
    confirm_default: ['Confirm action', 'تأكيد الإجراء'],
    expired: ['Expired', 'منتهي'],
    inactive: ['Inactive', 'غير نشط'],
    empty_fallback: ['What can you help me with?', 'بماذا يمكنني المساعدة؟'],
    empty_loading: ['Loading what you can do…', 'جارٍ تحميل ما يمكنك فعله…'],
    empty_error: [
      'Couldn’t load Assistant capabilities. Try again.',
      'تعذر تحميل إمكانيات المساعد. حاول مرة أخرى.',
    ],
    empty_none: [
      'No Assistant actions are available for your access yet.',
      'لا تتوفر إجراءات للمساعد حسب صلاحياتك حالياً.',
    ],
    empty_retry: ['Retry', 'إعادة المحاولة'],
    history_title: ['History', 'السجل'],
    history_empty: [
      'No OctoHR Assistant sessions yet. Your recent dashboard chats will appear here.',
      'لا توجد محادثات بعد. ستظهر محادثات لوحة التحكم هنا.',
    ],
    new_chat_title: ['Start a new chat?', 'بدء محادثة جديدة؟'],
    new_chat_body: [
      'This clears the current conversation view, but saved actions and hiring records will remain.',
      'هذا يمسح عرض المحادثة الحالية، لكن الإجراءات والسجلات المحفوظة تبقى.',
    ],
    today: ['Today', 'اليوم'],
    yesterday: ['Yesterday', 'أمس'],
    earlier: ['Earlier', 'أقدم'],
    session_fallback: ['OctoHR Assistant chat', 'محادثة مساعد OctoHR'],
    workflow_preview: ['Workflow preview', 'معاينة سير العمل'],
    workflow_result: ['Workflow result', 'نتيجة سير العمل'],
    workflow_partial: ['Partial success', 'نجاح جزئي'],
    retry_failed: ['Retry failed step', 'إعادة محاولة الخطوة الفاشلة'],
    planning: ['Planning…', 'جارٍ التخطيط…'],
    running_tool: ['Working…', 'جارٍ العمل…'],
    creating_meeting: ['Creating meeting…', 'جارٍ إنشاء الاجتماع…'],
    sending_communications: ['Sending communications…', 'جارٍ إرسال الرسائل…'],
    awaiting_confirmation: ['Waiting for confirmation…', 'بانتظار التأكيد…'],
    workflow_completed: ['Workflow finished', 'اكتمل سير العمل'],
  }
  const pair = copy[key]
  if (!pair) return key
  return ar ? pair[1] : pair[0]
}

function progressLabel(locale: RecruitingLocale, phase?: string | null) {
  if (!phase) return null
  const map: Record<string, string> = {
    planning: 'planning',
    running_tool: 'running_tool',
    creating_meeting: 'creating_meeting',
    sending_communications: 'sending_communications',
    awaiting_confirmation: 'awaiting_confirmation',
    workflow_completed: 'workflow_completed',
    workflow_partial: 'workflow_partial',
  }
  const key = map[phase]
  return key ? assistantCopy(locale, key) : null
}

export function AdminAIPage({
  assessmentEnabled: _assessmentEnabled,
  enabledModules: _enabledModules,
  busy,
  emptyState,
  emptyStateStatus = 'ready',
  historyOpen,
  input,
  locale = 'en',
  messages,
  newChatConfirmOpen,
  onApplyNavigation,
  onAsk,
  onCancel,
  onCloseHistory,
  onCloseNewChatConfirm,
  onConfirm,
  onInputChange,
  onNewChat,
  onOpenCandidate,
  onOpenHistory,
  onOpenSession,
  onPrompt,
  onReloadCapabilities,
  onRequestNewChat,
  onRetryWorkflow,
  sessions,
}: {
  assessmentEnabled: boolean
  enabledModules?: string[]
  busy: boolean
  emptyState?: AssistantEmptyState | null
  emptyStateStatus?: 'loading' | 'ready' | 'error'
  historyOpen: boolean
  input: string
  locale?: RecruitingLocale
  messages: ChatMessage[]
  newChatConfirmOpen: boolean
  onApplyNavigation: (item: DashboardChatNavigation) => void
  onAsk: () => void
  onCancel?: () => void
  onCloseHistory: () => void
  onCloseNewChatConfirm: () => void
  onConfirm: () => void
  onInputChange: (value: string) => void
  onNewChat: () => void
  onOpenCandidate: (appKey?: string) => void
  onOpenHistory: () => void
  onOpenSession: (session: DashboardChatSession) => void
  onPrompt: (prompt: string) => void
  onReloadCapabilities?: () => void
  onRequestNewChat: () => void
  onRetryWorkflow?: (prompt: string) => void
  sessions: DashboardChatSession[]
}) {
  const chatEndRef = useRef<HTMLDivElement | null>(null)
  const historyRef = useRef<HTMLElement | null>(null)
  const newChatRef = useRef<HTMLDivElement | null>(null)
  const isAr = locale === 'ar'

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  useBodyScrollLock(historyOpen || newChatConfirmOpen)
  useOverlayFocus(historyOpen, onCloseHistory, historyRef)
  useOverlayFocus(newChatConfirmOpen, onCloseNewChatConfirm, newChatRef)

  const groupedSessions = groupDashboardChatSessions(sessions, locale)
  const catalogChips = Array.isArray(emptyState?.chips) ? emptyState!.chips.filter((c) => Boolean(c?.trim())) : []
  const hasCapabilities = Boolean(emptyState?.has_capabilities && catalogChips.length)
  const emptyPrompt =
    (emptyState?.headline && emptyState.headline.trim()) || assistantCopy(locale, 'empty_fallback')
  const moduleList = Array.isArray(emptyState?.modules) ? emptyState!.modules : []

  return (
    <section className="flex min-h-0 flex-1 flex-col" data-testid="assistant-page" dir={isAr ? 'rtl' : 'ltr'}>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[1.75rem] border border-[#e8dfd0]/80 bg-wf-surface shadow-[0_12px_32px_rgba(35,33,29,0.06)]">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line/55 px-5 py-3 lg:px-8">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-subtle">{assistantCopy(locale, 'title')}</div>
          <div className="flex items-center gap-1 text-sm">
            <button
              className="rounded-full px-3 py-1.5 text-subtle transition hover:bg-white/55 hover:text-text"
              onClick={() => {
                dashboardPerfMarkInteractionStart('assistant_open_history')
                onOpenHistory()
                dashboardPerfMarkNetworkComplete('assistant_open_history')
              }}
              type="button"
            >
              {assistantCopy(locale, 'history')}
            </button>
            <span className="text-line">|</span>
            <button
              className="rounded-full px-3 py-1.5 text-subtle transition hover:bg-white/55 hover:text-text"
              onClick={onRequestNewChat}
              type="button"
            >
              {assistantCopy(locale, 'new_chat')}
            </button>
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          <AssistantProfiler id="transcript">
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-6 lg:px-10">
              {messages.length === 0 ? (
                <div
                  className="flex min-h-[220px] flex-col items-center justify-center px-2 text-center"
                  data-testid="assistant-empty-state"
                  data-status={emptyStateStatus}
                >
                  {emptyStateStatus === 'loading' && !emptyState ? (
                    <>
                      <Loader2 className="mb-3 h-5 w-5 animate-spin text-mist" />
                      <div className="max-w-xl text-base font-medium text-subtle" data-testid="assistant-empty-loading">
                        {assistantCopy(locale, 'empty_loading')}
                      </div>
                    </>
                  ) : null}
                  {emptyStateStatus === 'error' ? (
                    <>
                      <div className="max-w-xl text-lg font-semibold tracking-[-0.02em] text-text" data-testid="assistant-empty-error">
                        {assistantCopy(locale, 'empty_error')}
                      </div>
                      {onReloadCapabilities ? (
                        <button
                          className="mt-4 rounded-full border border-line bg-white/70 px-4 py-2 text-sm font-medium text-text transition hover:bg-panel"
                          onClick={onReloadCapabilities}
                          type="button"
                        >
                          {assistantCopy(locale, 'empty_retry')}
                        </button>
                      ) : null}
                    </>
                  ) : null}
                  {(emptyStateStatus === 'ready' || (emptyStateStatus === 'loading' && emptyState)) && !hasCapabilities ? (
                    <div className="max-w-xl text-lg font-semibold tracking-[-0.02em] text-text" data-testid="assistant-empty-none">
                      {assistantCopy(locale, 'empty_none')}
                    </div>
                  ) : null}
                  {(emptyStateStatus === 'ready' || Boolean(emptyState)) && hasCapabilities ? (
                    <>
                      <div className="max-w-xl text-lg font-semibold tracking-[-0.02em] text-text">{emptyPrompt}</div>
                      {moduleList.length > 0 ? (
                        <div className="mt-2 max-w-xl text-sm text-subtle" data-testid="assistant-empty-modules">
                          {moduleList.slice(0, 8).join(' · ')}
                          {moduleList.length > 8 ? (isAr ? ` · +${moduleList.length - 8}` : ` · +${moduleList.length - 8}`) : ''}
                        </div>
                      ) : null}
                      <div className="mt-5 flex max-w-2xl flex-wrap justify-center gap-2" data-testid="assistant-empty-chips">
                        {catalogChips.map((prompt) => (
                          <button
                            className="rounded-full border border-white/70 bg-white/45 px-4 py-2 text-sm font-medium text-subtle shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_8px_20px_rgba(24,20,15,0.035)] transition duration-200 hover:-translate-y-0.5 hover:bg-panel hover:text-text hover:shadow-soft"
                            key={prompt}
                            onClick={() => onPrompt(prompt)}
                            type="button"
                          >
                            {prompt}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : null}
                </div>
              ) : null}
              {messages.map((message) => (
                <div
                  className={
                    message.role === 'user'
                      ? 'ml-auto w-fit max-w-[60%] rounded-[1.35rem] bg-[linear-gradient(180deg,#24211d_0%,#11100e_100%)] px-[18px] py-3 text-white shadow-[0_14px_34px_rgba(24,20,15,0.18)]'
                      : 'flex max-w-5xl items-start gap-3'
                  }
                  key={message.id}
                >
                  {message.role === 'assistant' ? (
                    <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full border border-white/70 bg-white/55 text-slate shadow-soft">
                      <MessageCircle size={15} />
                    </div>
                  ) : null}
                  <div className={message.role === 'assistant' ? 'min-w-0 flex-1' : ''}>
                    <div
                      className={`whitespace-pre-wrap text-base ${message.role === 'assistant' ? 'leading-7 text-text' : 'leading-6 text-white'}`}
                    >
                      {message.text ||
                        (message.isStreaming ? (
                          <span className="text-sm text-subtle">
                            {progressLabel(locale, message.progressPhase) || (
                              <span className="inline-flex gap-1 text-mist">
                                <span className="h-2 w-2 animate-pulse rounded-full bg-mist" />
                                <span className="h-2 w-2 animate-pulse rounded-full bg-mist [animation-delay:120ms]" />
                                <span className="h-2 w-2 animate-pulse rounded-full bg-mist [animation-delay:240ms]" />
                              </span>
                            )}
                          </span>
                        ) : null)}
                    </div>
                    {message.candidateCards?.length ? (
                      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                        {message.candidateCards.map((card) => (
                          <button
                            className="group rounded-3xl border border-white/70 bg-white/55 p-5 text-left shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_14px_34px_rgba(24,20,15,0.055)] backdrop-blur transition duration-200 hover:-translate-y-1 hover:bg-panel/90 hover:shadow-[0_18px_46px_rgba(24,20,15,0.09)]"
                            key={card.app_key || card.phone || card.name}
                            onClick={() => {
                              dashboardPerfMarkInteractionStart('assistant_open_candidate', {
                                appKey: card.app_key || '',
                              })
                              onOpenCandidate(card.app_key)
                              dashboardPerfMarkNetworkComplete('assistant_open_candidate', {
                                appKey: card.app_key || '',
                              })
                            }}
                            type="button"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="font-semibold">{card.name || card.phone || 'Candidate'}</div>
                                <div className="mt-1 text-sm text-subtle">
                                  {card.position || (card.status ? stageLabel(card.status) : '') || card.phone}
                                </div>
                              </div>
                              {card.score != null ? (
                                <div className="rounded-full border border-white/70 bg-white/60 px-2.5 py-1 text-xs font-semibold text-text shadow-[0_1px_0_rgba(255,255,255,0.8)_inset]">
                                  {Math.round(Number(card.score))}/100
                                </div>
                              ) : null}
                            </div>
                            {card.reasons?.length ? (
                              <div className="mt-3 text-xs leading-5 text-subtle">{card.reasons[0]}</div>
                            ) : null}
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {message.workflowCard ? (
                      <WorkflowCardView
                        card={message.workflowCard}
                        locale={locale}
                        onRetry={onRetryWorkflow}
                      />
                    ) : null}
                    {message.confirmation ? (
                      <div className="mt-4 max-w-2xl rounded-3xl border border-amber-200/70 bg-[linear-gradient(180deg,rgba(255,251,235,0.92),rgba(254,243,199,0.62))] p-5 shadow-[0_1px_0_rgba(255,255,255,0.85)_inset,0_16px_42px_rgba(146,64,14,0.10)] backdrop-blur">
                        <div className="text-sm font-semibold text-amber-900">
                          {message.confirmation.is_active === false
                            ? assistantCopy(locale, 'confirm_inactive')
                            : assistantCopy(locale, 'confirm_required')}
                        </div>
                        <div className="mt-1 text-sm leading-6 text-amber-800">
                          {message.confirmation.summary ||
                            'This action will only run after explicit approval.'}
                        </div>
                        {message.confirmation.workflow_card ? (
                          <WorkflowCardView
                            card={message.confirmation.workflow_card}
                            locale={locale}
                            nested
                          />
                        ) : Array.isArray(message.confirmation.steps) &&
                          message.confirmation.steps.length ? (
                          <ul className="mt-3 list-disc space-y-1 ps-5 text-sm text-amber-900">
                            {message.confirmation.steps.map((step, index) => (
                              <li key={`${typeof step === 'string' ? step : JSON.stringify(step)}-${index}`}>
                                {typeof step === 'string'
                                  ? humanStep(step)
                                  : humanStep(String((step as { step?: string }).step || ''))}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        {message.confirmation.is_active === false ? (
                          <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-amber-700">
                            {message.confirmation.status === 'expired'
                              ? assistantCopy(locale, 'expired')
                              : assistantCopy(locale, 'inactive')}
                          </div>
                        ) : (
                          <Button
                            className="mt-3"
                            onClick={() => {
                              dashboardPerfMarkInteractionStart('assistant_confirm')
                              onConfirm()
                              dashboardPerfMarkNetworkComplete('assistant_confirm')
                            }}
                            size="sm"
                          >
                            {message.confirmation.label || assistantCopy(locale, 'confirm_default')}
                          </Button>
                        )}
                      </div>
                    ) : null}
                    {message.navigation?.length ? (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {message.navigation.map((item) => (
                          <Button
                            key={`${item.type || 'page'}-${item.page || ''}-${item.prompt || ''}-${item.label || ''}-${item.position_code || ''}`}
                            onClick={() => {
                              dashboardPerfMarkInteractionStart('assistant_nav', {
                                page: item.page || '',
                                type: item.type || '',
                              })
                              onApplyNavigation(item)
                              dashboardPerfMarkNetworkComplete('assistant_nav', {
                                page: item.page || '',
                                type: item.type || '',
                              })
                            }}
                            size="sm"
                            variant="secondary"
                          >
                            {item.label || (item.page ? `Open ${item.page}` : 'Continue')}
                          </Button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          </AssistantProfiler>

          <AssistantProfiler id="composer">
            <form
              className="shrink-0 border-t border-line/55 bg-panel/72 px-5 py-4 backdrop-blur-xl lg:px-8"
              onSubmit={(event) => {
                event.preventDefault()
                onAsk()
              }}
            >
              <div className="flex min-h-[68px] items-center gap-3 rounded-[1.6rem] border border-white/70 bg-white/55 py-2 pl-4 pr-2 shadow-[0_1px_0_rgba(255,255,255,0.85)_inset,0_18px_46px_rgba(24,20,15,0.075)] backdrop-blur">
                <Textarea
                  className="max-h-28 min-h-10 flex-1 resize-none border-0 bg-transparent py-2 text-base shadow-none focus:ring-0"
                  onChange={(event) => onInputChange(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      onAsk()
                    }
                  }}
                  placeholder={assistantCopy(locale, 'message')}
                  value={input}
                />
                {busy && onCancel ? (
                  <button
                    aria-label={assistantCopy(locale, 'stop')}
                    className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-ink/20 bg-white text-ink transition hover:-translate-y-0.5 hover:shadow-soft"
                    onClick={onCancel}
                    type="button"
                  >
                    <Square size={14} fill="currentColor" />
                  </button>
                ) : (
                  <button
                    aria-label="Send message"
                    className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-ink bg-ink text-white transition hover:-translate-y-0.5 hover:shadow-soft disabled:border-line disabled:bg-panel disabled:text-mist"
                    disabled={busy || !input.trim()}
                    type="submit"
                  >
                    {busy ? <Loader2 className="animate-spin" size={17} /> : <ArrowUp size={19} />}
                  </button>
                )}
              </div>
            </form>
          </AssistantProfiler>
        </div>
      </div>
      {historyOpen ? (
        <div className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-[2px]" onClick={onCloseHistory}>
          <aside
            aria-modal="true"
            className="ml-auto flex h-full w-full max-w-md flex-col border-l border-white/70 bg-panel/95 p-6 shadow-[0_24px_80px_rgba(24,20,15,0.18)] backdrop-blur-2xl"
            dir={isAr ? 'rtl' : 'ltr'}
            onClick={(event) => event.stopPropagation()}
            ref={historyRef}
            role="dialog"
          >
            <div className="flex items-start justify-between gap-3 border-b border-line/55 pb-4">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-subtle">
                  {assistantCopy(locale, 'title')}
                </div>
                <h3 className="mt-1 text-xl font-semibold tracking-tight">{assistantCopy(locale, 'history_title')}</h3>
              </div>
              <Button onClick={onCloseHistory} size="sm" variant="secondary">
                {assistantCopy(locale, 'close')}
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto py-4">
              {groupedSessions.some((group) => group.sessions.length) ? (
                groupedSessions.map((group) =>
                  group.sessions.length ? (
                    <section className="mb-5" key={group.label}>
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-mist">
                        {group.label}
                      </div>
                      <div className="space-y-2">
                        {group.sessions.map((session) => (
                          <button
                            className="w-full rounded-2xl border border-line/60 bg-white/36 p-3 text-left transition hover:border-[#c89445]/35 hover:bg-panel/75"
                            key={session.conversation_id}
                            onClick={() => onOpenSession(session)}
                            type="button"
                          >
                            <div className="font-semibold text-text">
                              {session.title || assistantCopy(locale, 'session_fallback')}
                            </div>
                            <div className="mt-1 text-xs text-subtle">{chatSessionTimeLabel(session, locale)}</div>
                          </button>
                        ))}
                      </div>
                    </section>
                  ) : null,
                )
              ) : (
                <EmptyState text={assistantCopy(locale, 'history_empty')} />
              )}
            </div>
          </aside>
        </div>
      ) : null}
      {newChatConfirmOpen ? (
        <div
          className="fixed inset-0 z-40 grid place-items-center bg-ink/20 p-4 backdrop-blur-[2px]"
          onClick={onCloseNewChatConfirm}
        >
          <div
            aria-modal="true"
            className="w-full max-w-md rounded-[1.75rem] border border-white/70 bg-panel/95 p-6 shadow-[0_24px_80px_rgba(24,20,15,0.18)] backdrop-blur-2xl"
            dir={isAr ? 'rtl' : 'ltr'}
            onClick={(event) => event.stopPropagation()}
            ref={newChatRef}
            role="dialog"
          >
            <div className="text-lg font-semibold tracking-tight">{assistantCopy(locale, 'new_chat_title')}</div>
            <p className="mt-2 text-sm leading-6 text-subtle">{assistantCopy(locale, 'new_chat_body')}</p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Button onClick={onCloseNewChatConfirm} variant="secondary">
                {assistantCopy(locale, 'cancel')}
              </Button>
              <Button disabled={busy} onClick={onNewChat}>
                {assistantCopy(locale, 'new_chat')}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

function WorkflowCardView({
  card,
  locale,
  nested,
  onRetry,
}: {
  card: DashboardChatWorkflowCard
  locale: RecruitingLocale
  nested?: boolean
  onRetry?: (prompt: string) => void
}) {
  const partial = card.status === 'partial'
  return (
    <div
      className={`${nested ? 'mt-3' : 'mt-4'} max-w-2xl rounded-3xl border border-line/60 bg-white/55 p-5 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset,0_12px_28px_rgba(24,20,15,0.05)]`}
    >
      <div className="text-sm font-semibold text-text">
        {card.title ||
          (card.kind === 'workflow_result'
            ? assistantCopy(locale, partial ? 'workflow_partial' : 'workflow_result')
            : assistantCopy(locale, 'workflow_preview'))}
      </div>
      {Array.isArray(card.steps) && card.steps.length ? (
        <ul className="mt-3 space-y-2 text-sm text-subtle">
          {card.steps.map((step, index) => (
            <li className="flex items-start justify-between gap-3" key={`${step.step || 'step'}-${index}`}>
              <span>{humanStep(String(step.step || ''))}</span>
              <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-mist">
                {step.status || (step.success === false ? 'failed' : 'planned')}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {partial && card.retry_prompt && onRetry ? (
        <Button className="mt-3" onClick={() => onRetry(card.retry_prompt || '')} size="sm" variant="secondary">
          {assistantCopy(locale, 'retry_failed')}
        </Button>
      ) : null}
      {partial && card.compensation_state?.note ? (
        <p className="mt-2 text-xs leading-5 text-subtle">{card.compensation_state.note}</p>
      ) : null}
    </div>
  )
}

function humanStep(step: string) {
  return step
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase())
}

function chatSessionDate(session: DashboardChatSession) {
  const raw = session.last_message_at || session.updated_at || session.created_at
  const date = raw ? new Date(raw) : new Date()
  return Number.isNaN(date.getTime()) ? new Date() : date
}

function groupDashboardChatSessions(sessions: DashboardChatSession[], locale: RecruitingLocale) {
  const now = new Date()
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startYesterday = startToday - 24 * 60 * 60 * 1000
  const groups = [
    { label: assistantCopy(locale, 'today'), sessions: [] as DashboardChatSession[] },
    { label: assistantCopy(locale, 'yesterday'), sessions: [] as DashboardChatSession[] },
    { label: assistantCopy(locale, 'earlier'), sessions: [] as DashboardChatSession[] },
  ]
  sessions.forEach((session) => {
    const time = chatSessionDate(session).getTime()
    if (time >= startToday) groups[0].sessions.push(session)
    else if (time >= startYesterday) groups[1].sessions.push(session)
    else groups[2].sessions.push(session)
  })
  return groups
}

function chatSessionTimeLabel(session: DashboardChatSession, locale: RecruitingLocale) {
  const date = chatSessionDate(session)
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar' : 'en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}
