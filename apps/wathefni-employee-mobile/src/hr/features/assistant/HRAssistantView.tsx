import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Animated,
  Easing,
  FlatList,
  Image,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import {
  fetchAssistantCapabilities,
  streamAssistantChat,
  type AssistantChatResponse,
} from '@hr/api/assistant'
import { keyboardSafeBehavior, keyboardSafeOffset } from '@/components/keyboardSafe'
import { useAuth } from '@hr/auth/AuthProvider'
import { hasCapability } from '@hr/capabilities'
import {
  mapAssistantNavigation,
  mapCandidateCardLink,
  type AssistantDeepLink,
} from '@hr/features/assistant/assistantDeepLinks'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen } from '@/components/layout'
import { EditorialHeading, FadeIn, editorialFont } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { kuwaitDayPart } from '@/lib/format'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

const BRAND_BADGE = require('../../../../assets/brand/icon-composer/badge-black-alpha.png')

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  links?: AssistantDeepLink[]
  confirmation?: AssistantChatResponse['confirmation']
  /** thinking = quiet status row; streaming = progressive text; done = final */
  phase?: 'thinking' | 'streaming' | 'done'
}

const INPUT_LINE = 22
const INPUT_MIN = 44
const INPUT_MAX = 120

/**
 * Wathefni Assistant — thin mobile client of the platform spine.
 * Empty: logo mark → Kuwait-local greeting → composer. Conversation owns FlatList scroll.
 */
export function HRAssistantView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const insets = useSafeAreaInsets()
  const { me, getAccessToken } = useAuth()
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const loc = locale === 'ar' ? 'ar' : 'en'
  const permitted = hasCapability(me, 'hr', 'assistant')

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [keyboardOpen, setKeyboardOpen] = useState(false)
  const [androidKeyboardPad, setAndroidKeyboardPad] = useState(0)
  const [inputHeight, setInputHeight] = useState(INPUT_MIN)
  const abortRef = useRef<AbortController | null>(null)
  const listRef = useRef<FlatList<ChatMessage>>(null)
  const sendingRef = useRef(false)
  const stickToBottomRef = useRef(true)

  const inConversation = messages.length > 0
  const firstName =
    (me?.principal.display_name || '').split(/\s+/).filter(Boolean)[0] || t('home.employee')
  const dayPart = kuwaitDayPart()
  const greetingKey =
    dayPart === 'morning'
      ? 'home.greetingMorning'
      : dayPart === 'afternoon'
        ? 'home.greetingAfternoon'
        : 'home.greetingEvening'

  const scrollToLatest = useCallback((animated = true) => {
    if (!stickToBottomRef.current) return
    requestAnimationFrame(() => {
      listRef.current?.scrollToEnd({ animated })
    })
  }, [])

  useEffect(() => {
    if (!permitted) return
    const controller = new AbortController()
    void fetchAssistantCapabilities(getAccessToken(), loc, controller.signal).catch(() => undefined)
    return () => {
      controller.abort()
      abortRef.current?.abort()
    }
  }, [getAccessToken, loc, permitted])

  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow'
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide'
    const onShow = Keyboard.addListener(showEvent, (event) => {
      setKeyboardOpen(true)
      if (Platform.OS === 'android') {
        setAndroidKeyboardPad(Math.max(0, event.endCoordinates?.height || 0))
      }
      scrollToLatest(true)
    })
    const onHide = Keyboard.addListener(hideEvent, () => {
      setKeyboardOpen(false)
      setAndroidKeyboardPad(0)
    })
    return () => {
      onShow.remove()
      onHide.remove()
    }
  }, [scrollToLatest])

  const onListScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent
    const distanceFromBottom = contentSize.height - layoutMeasurement.height - contentOffset.y
    stickToBottomRef.current = distanceFromBottom < 80
  }

  const send = async (raw: string, opts?: { confirm?: boolean }) => {
    const text = String(raw || '').trim()
    if ((!text && !opts?.confirm) || busy || sendingRef.current || !permitted) return
    sendingRef.current = true
    stickToBottomRef.current = true
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const userText = opts?.confirm
      ? loc === 'ar'
        ? 'تأكيد'
        : 'Confirm'
      : text
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      text: userText,
    }
    const assistantId = `a-${Date.now()}`
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: 'assistant', text: '', phase: 'thinking' },
    ])
    setDraft('')
    setInputHeight(INPUT_MIN)
    setBusy(true)
    scrollToLatest(true)
    try {
      const response = await streamAssistantChat(
        getAccessToken(),
        {
          message: opts?.confirm ? 'yes' : text,
          conversation_id: conversationId,
          locale: loc,
          confirm: opts?.confirm,
        },
        (event) => {
          if (event.type === 'delta' && event.text) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      text: (m.text || '') + String(event.text),
                      phase: 'streaming',
                    }
                  : m,
              ),
            )
            scrollToLatest(false)
          }
        },
        controller.signal,
      )
      if (response.conversation_id) setConversationId(response.conversation_id)
      const links = [
        ...mapAssistantNavigation(me, response.navigation, loc),
        ...((response.candidate_cards || [])
          .map((card) =>
            mapCandidateCardLink(
              me,
              card.app_key,
              card.name || (loc === 'ar' ? 'المرشح' : 'Candidate'),
            ),
          )
          .filter(Boolean) as ReturnType<typeof mapCandidateCardLink>[]),
      ].filter(Boolean) as AssistantDeepLink[]
      const reply = String(response.reply_text || '').trim()
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                // Prefer streamed text if already painted; fill if stream missed.
                text: (m.text || '').trim() || reply || t('hrAssistant.emptyReply'),
                links,
                confirmation: response.confirmation?.is_active ? response.confirmation : null,
                phase: 'done',
              }
            : m,
        ),
      )
    } catch (error) {
      if ((error as { name?: string })?.name === 'AbortError') return
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                text: error instanceof Error ? error.message : t('hrAssistant.sendError'),
                phase: 'done',
              }
            : m,
        ),
      )
    } finally {
      sendingRef.current = false
      setBusy(false)
      scrollToLatest(true)
    }
  }

  const canSend = Boolean(draft.trim()) && !busy
  const composerGrew = inputHeight > INPUT_MIN + 4
  const composerBottomPad =
    (keyboardOpen ? spacing.md : Math.max(insets.bottom, spacing.md)) + androidKeyboardPad

  const emptyLanding = useMemo(
    () => (
      <View style={styles.emptyLand}>
        <FadeIn style={styles.emptyInner}>
          <Image
            source={BRAND_BADGE}
            style={styles.brandBadge}
            accessibilityLabel="OctoHR"
            resizeMode="contain"
          />
          <Text
            maxFontSizeMultiplier={typeScaling.heading}
            style={[
              styles.greeting,
              align,
              { fontFamily: editorialFont(locale), textAlign: isRTL ? 'right' : 'center' },
            ]}
          >
            {t(greetingKey, { name: firstName })}
          </Text>
        </FadeIn>
      </View>
    ),
    [align, firstName, greetingKey, isRTL, locale, t],
  )

  if (!me) return null

  if (!permitted) {
    return (
      <PageScreen>
        <View style={styles.pad}>
          <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
          <EditorialHeading>{t('hrAssistant.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrAssistant.unavailable')}
          </Text>
        </View>
      </PageScreen>
    )
  }

  return (
    <PageScreen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={keyboardSafeBehavior()}
        keyboardVerticalOffset={keyboardSafeOffset(insets.top)}
      >
        <View style={styles.pad}>
          <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        </View>

        <FlatList
          ref={listRef}
          style={styles.flex}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={({ item: message }) => {
            if (message.role === 'assistant' && message.phase === 'thinking' && !message.text) {
              return (
                <View
                  style={[
                    styles.thinkingRow,
                    isRTL ? styles.assistantAlignRtl : styles.assistantAlignLtr,
                  ]}
                >
                  <ThinkingLabel label={t('hrAssistant.thinking')} align={align} />
                </View>
              )
            }
            return (
              <View
                style={[
                  styles.bubble,
                  message.role === 'user' ? styles.userBubble : styles.assistantBubble,
                  message.role === 'user'
                    ? isRTL
                      ? styles.userAlignRtl
                      : styles.userAlignLtr
                    : isRTL
                      ? styles.assistantAlignRtl
                      : styles.assistantAlignLtr,
                ]}
              >
                <Text
                  maxFontSizeMultiplier={typeScaling.body}
                  style={[
                    styles.bubbleText,
                    message.role === 'user' ? styles.userText : styles.assistantText,
                    align,
                  ]}
                >
                  {message.text}
                </Text>
                {message.links?.length ? (
                  <View style={[styles.links, isRTL ? styles.linksRtl : null]}>
                    {message.links.map((link) => (
                      <Pressable
                        key={`${link.kind}:${link.href}:${link.prompt || link.label}`}
                        onPress={() => {
                          if (link.kind === 'prompt' && link.prompt) void send(link.prompt)
                          else if (link.href) router.push(link.href as never)
                        }}
                        style={styles.linkChip}
                      >
                        <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.linkText}>
                          {link.label}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                ) : null}
                {message.confirmation?.is_active ? (
                  <Pressable
                    onPress={() => void send('yes', { confirm: true })}
                    style={styles.confirmBtn}
                    accessibilityRole="button"
                  >
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.confirmText}>
                      {message.confirmation.label || t('hrAssistant.confirm')}
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            )
          }}
          contentContainerStyle={[
            styles.thread,
            !inConversation ? styles.threadEmpty : null,
          ]}
          ListEmptyComponent={emptyLanding}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          onScroll={onListScroll}
          scrollEventThrottle={16}
          onContentSizeChange={() => scrollToLatest(inConversation)}
          showsVerticalScrollIndicator={false}
          maintainVisibleContentPosition={
            Platform.OS === 'ios' ? { minIndexForVisible: 0 } : undefined
          }
        />

        <View style={[styles.composerDock, { paddingBottom: composerBottomPad }]}>
          <View
            style={[
              styles.composerShell,
              isRTL ? styles.composerRtl : null,
              composerGrew ? styles.composerShellMultiline : styles.composerShellSingle,
            ]}
          >
            <TextInput
              value={draft}
              onChangeText={setDraft}
              placeholder={t('hrAssistant.placeholder')}
              placeholderTextColor={colors.navMuted}
              style={[
                styles.input,
                align,
                {
                  height: Math.max(INPUT_LINE, Math.min(INPUT_MAX - 20, inputHeight)),
                },
              ]}
              editable={!busy}
              multiline
              scrollEnabled={inputHeight >= INPUT_MAX - 24}
              textAlignVertical={composerGrew ? 'top' : 'center'}
              maxFontSizeMultiplier={typeScaling.body}
              blurOnSubmit={false}
              onContentSizeChange={(event) => {
                const next = Math.ceil(event.nativeEvent.contentSize.height)
                setInputHeight(Math.max(INPUT_LINE, Math.min(INPUT_MAX - 20, next)))
              }}
              onFocus={() => {
                stickToBottomRef.current = true
                scrollToLatest(true)
              }}
            />
            <Pressable
              onPress={() => void send(draft)}
              disabled={!canSend}
              style={[styles.sendBtn, canSend ? styles.sendActive : styles.sendQuiet]}
              accessibilityRole="button"
              accessibilityLabel={t('hrAssistant.send')}
              hitSlop={6}
            >
              <Ionicons
                name="arrow-up"
                size={18}
                color={canSend ? colors.ink : colors.navMuted}
              />
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </PageScreen>
  )
}

function ThinkingLabel({
  label,
  align,
}: {
  label: string
  align: object
}) {
  const opacity = useRef(new Animated.Value(0.35)).current
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 1,
          duration: 700,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.35,
          duration: 700,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    )
    loop.start()
    return () => loop.stop()
  }, [opacity])
  return (
    <Animated.Text
      maxFontSizeMultiplier={typeScaling.body}
      style={[styles.thinkingText, align, { opacity }]}
      accessibilityLiveRegion="polite"
    >
      {label}
    </Animated.Text>
  )
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  pad: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  subtitle: {
    marginTop: spacing.xs,
    color: colors.subtle,
    fontSize: font.small,
    lineHeight: 20,
  },
  thread: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.lg,
    gap: spacing.sm,
    flexGrow: 1,
  },
  threadEmpty: {
    justifyContent: 'center',
  },
  emptyLand: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    paddingBottom: '18%',
    minHeight: 280,
  },
  emptyInner: {
    alignItems: 'center',
    gap: spacing.lg,
  },
  brandBadge: {
    width: 56,
    height: 56,
  },
  greeting: {
    color: colors.ink,
    fontSize: font.h2,
    lineHeight: 30,
    fontWeight: '500',
    letterSpacing: -0.2,
    maxWidth: 320,
  },
  thinkingRow: {
    maxWidth: '86%',
    paddingVertical: 6,
    paddingHorizontal: 2,
  },
  thinkingText: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    fontWeight: '500',
    letterSpacing: -0.1,
  },
  bubble: {
    borderRadius: 18,
    paddingVertical: 10,
    paddingHorizontal: 14,
    maxWidth: '86%',
  },
  userBubble: {
    backgroundColor: colors.ink,
  },
  assistantBubble: {
    backgroundColor: 'transparent',
    paddingHorizontal: 2,
    paddingVertical: 4,
  },
  userAlignLtr: { alignSelf: 'flex-end' },
  userAlignRtl: { alignSelf: 'flex-start' },
  assistantAlignLtr: { alignSelf: 'flex-start' },
  assistantAlignRtl: { alignSelf: 'flex-end' },
  bubbleText: { fontSize: font.body, lineHeight: 21 },
  userText: { color: colors.bg },
  assistantText: { color: colors.ink },
  links: {
    marginTop: spacing.sm,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  linksRtl: { flexDirection: 'row-reverse' },
  linkChip: {
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  linkText: { color: colors.ink, fontSize: font.tiny, fontWeight: '600' },
  confirmBtn: {
    marginTop: spacing.sm,
    alignSelf: 'flex-start',
    backgroundColor: colors.ink,
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderRadius: radius.pill,
  },
  confirmText: { color: colors.bg, fontWeight: '700', fontSize: font.small },
  composerDock: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    backgroundColor: colors.bg,
  },
  composerShell: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: 26,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingLeft: spacing.md,
    paddingRight: 8,
    shadowColor: '#3D3428',
    shadowOpacity: 0.08,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  composerShellSingle: {
    alignItems: 'center',
    minHeight: INPUT_MIN + 8,
    paddingVertical: 6,
  },
  composerShellMultiline: {
    alignItems: 'flex-end',
    paddingVertical: 8,
  },
  composerRtl: {
    flexDirection: 'row-reverse',
    paddingLeft: 8,
    paddingRight: spacing.md,
  },
  input: {
    flex: 1,
    margin: 0,
    paddingHorizontal: 0,
    paddingTop: Platform.OS === 'ios' ? 0 : 2,
    paddingBottom: Platform.OS === 'ios' ? 0 : 2,
    color: colors.ink,
    fontSize: font.body,
    lineHeight: INPUT_LINE,
  },
  sendBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendQuiet: {
    backgroundColor: colors.surfaceMuted,
  },
  sendActive: {
    backgroundColor: colors.pink,
  },
})
