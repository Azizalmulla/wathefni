import { Stack } from 'expo-router'

import { colors } from '@/theme'

/** Auth stack must never show Expo Router default titles (e.g. "(auth)/activate"). */
export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        title: '',
        headerTitle: '',
        contentStyle: { backgroundColor: colors.bg },
        animation: 'fade',
      }}
    >
      <Stack.Screen
        name="activate"
        options={{
          headerShown: false,
          title: '',
          headerTitle: '',
          headerBackVisible: false,
          headerTransparent: true,
        }}
      />
    </Stack>
  )
}
