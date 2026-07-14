import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { ProfileView } from '@/features/remaining/RemainingViews'

export default function ProfileScreen() {
  const { profile, signOut } = useAuth()
  const router = useRouter()
  return (
    <ProfileView
      profile={profile}
      onSettings={() => router.push('/settings')}
      onPrivacySupport={() => router.push('/privacy-support')}
      onSignOut={() => void signOut()}
    />
  )
}
