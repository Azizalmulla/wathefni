import { useEffect } from 'react'
import * as Notifications from 'expo-notifications'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { PUSH_REGISTRATION_ENABLED, registerForPushToken } from './registerForPush'
import { loadPushPreference } from './preferences'

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: true,
  }),
})

export function PushLifecycle() {
  const { status, can, request } = useAuth()
  const router = useRouter()
  const enabled = status === 'signedIn' && can('settings', 'manage_push') && PUSH_REGISTRATION_ENABLED

  useEffect(() => {
    if (!enabled) return
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
    const responseSubscription = Notifications.addNotificationResponseReceivedListener(() => {
      router.push('/notifications')
    })

    return () => {
      active = false
      tokenSubscription.remove()
      responseSubscription.remove()
    }
  }, [enabled, request, router])

  return null
}
