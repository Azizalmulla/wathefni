import { useEffect, useRef } from 'react'
import { AppState, Platform } from 'react-native'
import * as Notifications from 'expo-notifications'
import { useRouter, type Href } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { PUSH_REGISTRATION_ENABLED, ensureDefaultPushChannel, registerForPushToken } from './registerForPush'
import { isPushOptedOut } from './preferences'
import { pushFollowThroughHref } from './resolvePushDestination'
import { syncInboxBadge } from './syncInboxBadge'

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
})

export function PushLifecycle() {
  const { status, can, me, request } = useAuth()
  const { locale } = useI18n()
  const router = useRouter()
  const signedIn = status === 'signedIn'
  const registrationEnabled =
    signedIn && can('settings', 'manage_push') && PUSH_REGISTRATION_ENABLED

  // AuthProvider recreates `request` often — never put it in effect deps or
  // push registration remounts into a token/register storm.
  const requestRef = useRef(request)
  requestRef.current = request

  // Ensure the Android channel exists on sign-in so the first remote notification
  // can use wathefni_default sound even before permission is granted.
  useEffect(() => {
    if (!signedIn) return
    void ensureDefaultPushChannel().catch(() => undefined)
  }, [signedIn])

  // Auto-register after OS permission (or request once when undetermined).
  // Opt-out in Settings is the only in-app gate — not a second consent wall.
  useEffect(() => {
    if (!registrationEnabled) return
    let active = true
    let inFlight: Promise<void> | null = null
    // Claimed as soon as we know the Expo token string — even if server POST fails —
    // so addPushTokenListener cannot re-enter getExpoPushTokenAsync forever.
    let lastHandledToken: string | null = null
    let askedPermission = false

    const registerOnce = async (opts: { requestPermission: boolean; knownToken?: string | null }) => {
      if (await isPushOptedOut()) return
      if (opts.knownToken && opts.knownToken === lastHandledToken) return
      if (inFlight) {
        await inFlight
        return
      }
      inFlight = (async () => {
        try {
          let tokenValue = typeof opts.knownToken === 'string' && opts.knownToken ? opts.knownToken : null
          let platform: 'ios' | 'android' | 'windows' | 'macos' | 'web' = Platform.OS
          if (!tokenValue) {
            const shouldAsk = opts.requestPermission && !askedPermission
            if (shouldAsk) askedPermission = true
            const token = await registerForPushToken({ requestPermission: shouldAsk })
            if (!active || !token) return
            tokenValue = token.token
            platform = token.platform as typeof platform
          }
          if (!tokenValue || tokenValue === lastHandledToken) return
          // Claim before network — server blips must not reopen the listener loop.
          lastHandledToken = tokenValue
          try {
            await requestRef.current('/app/push/register', {
              method: 'POST',
              json: { push_token: tokenValue, platform },
            })
          } catch {
            // Best-effort. Token already active from a prior successful register is enough
            // for delivery; do not clear lastHandledToken (that restarts the storm).
          }
        } finally {
          inFlight = null
        }
      })()
      await inFlight
    }

    void registerOnce({ requestPermission: true }).catch(() => undefined)

    // Token refresh only — never re-ask OS permission; never call getExpoPushTokenAsync
    // when the listener already provided the token string.
    const tokenSubscription = Notifications.addPushTokenListener((event) => {
      const next = typeof event?.data === 'string' ? event.data : null
      if (!next || next === lastHandledToken) return
      void registerOnce({ requestPermission: false, knownToken: next }).catch(() => undefined)
    })

    return () => {
      active = false
      tokenSubscription.remove()
    }
  }, [registrationEnabled])

  // Soft-refresh badge when returning to foreground (Inbox unread is authoritative).
  useEffect(() => {
    if (!signedIn) return
    let active = true
    const refreshBadge = async () => {
      try {
        const res = await requestRef.current<{ unread?: number }>(
          `/app/notifications?locale=${encodeURIComponent(locale)}`,
        )
        if (!active) return
        await syncInboxBadge(Number(res.unread || 0))
      } catch {
        // Ignore — Home / Inbox screens also sync.
      }
    }
    void refreshBadge()
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'active') void refreshBadge()
    })
    return () => {
      active = false
      sub.remove()
    }
  }, [signedIn, locale])

  // Tap follow-through is independent of registration: a cold-start push tap must
  // still resolve through the Phase 1 registry when the employee is signed in.
  useEffect(() => {
    if (!signedIn) return
    let active = true

    const followThrough = (response: Notifications.NotificationResponse | null | undefined) => {
      if (!active || !response) return
      const data = response.notification.request.content.data
      const href = pushFollowThroughHref(me, data)
      router.push(href as Href)
    }

    void Notifications.getLastNotificationResponseAsync()
      .then(async (response) => {
        if (!active || !response) return
        await Notifications.clearLastNotificationResponseAsync()
        if (active) followThrough(response)
      })
      .catch(() => undefined)

    const responseSubscription = Notifications.addNotificationResponseReceivedListener((response) => {
      void Notifications.clearLastNotificationResponseAsync().catch(() => undefined)
      followThrough(response)
    })

    return () => {
      active = false
      responseSubscription.remove()
    }
  }, [signedIn, me, router])

  return null
}
