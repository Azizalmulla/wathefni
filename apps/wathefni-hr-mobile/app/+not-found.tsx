import { useRouter } from 'expo-router'

import { Screen, StatePanel } from '@/components/primitives'

export default function NotFound() {
  const router = useRouter()
  return (
    <Screen>
      <StatePanel
        title="This screen is unavailable"
        body="The route may have been removed after a permission or module change."
        action="Back to priorities"
        onAction={() => router.replace('/')}
        icon="compass-outline"
      />
    </Screen>
  )
}
