import { useEffect } from 'react'
import * as Notifications from 'expo-notifications'
import { useRouter, type Href } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { PUSH_REGISTRATION_ENABLED, registerForPushToken } from './registerForPush'
import { loadPushPreference } from './preferences'
import { pushFollowThroughHref } from './resolvePushDestination'

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: true,
  }),
})

export function PushLifecycle() {
  const { status, can, me, request } = useAuth()
  const router = useRouter()
  const signedIn = status === 'signedIn'
  const registrationEnabled =
    signedIn && can('settings', 'manage_push') && PUSH_REGISTRATION_ENABLED

  // Token registration stays behind the push preference + entitlement gate.
  useEffect(() => {
    if (!registrationEnabled) return
    let active = true

    const registerExistingPermission = async () => {
      if (!(await loadPushPreference())) return
      const token = await registerForPushToken()
      if (!active || !token) return
      await request('/app/push/register', {
        method: 'POST',
        json: { push_token: token.token, platform: token.platform },
      })
    }

    void registerExistingPermission().catch(() => undefined)
    const tokenSubscription = Notifications.addPushTokenListener(() => {
      void registerExistingPermission().catch(() => undefined)
    })

    return () => {
      active = false
      tokenSubscription.remove()
    }
  }, [registrationEnabled, request])

  // Tap follow-through is independent of registration: a cold-start push tap must
  // still resolve through the Phase 1 registry when the employee is signed in.
  // LocalUnlockShell continues to cover the UI — this never bypasses unlock/auth.
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
