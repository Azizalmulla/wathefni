import { useRouter } from 'expo-router'

import { NotFoundView } from '@/features/remaining/RemainingViews'

export default function NotFoundScreen() {
  const router = useRouter()
  return <NotFoundView onHome={() => router.replace('/(tabs)')} />
}
