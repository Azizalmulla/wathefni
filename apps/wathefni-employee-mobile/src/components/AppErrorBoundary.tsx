import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import { reportClientError } from '@/lib/reportClientError'
import { colors, font, radius, spacing } from '@/theme'

type Props = {
  children: ReactNode
  title: string
  message: string
  retryLabel: string
}

type State = { failed: boolean }

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Always emit — production OTA crashes must be visible in device logs.
    console.error(
      '[AppErrorBoundary] Uncaught app render error',
      error?.message || String(error),
      error?.stack || '',
      info?.componentStack || '',
    )
    reportClientError(error)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <View style={styles.root} accessibilityRole="alert" accessibilityLiveRegion="assertive">
        <Text style={styles.title}>{this.props.title}</Text>
        <Text style={styles.message}>{this.props.message}</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => this.setState({ failed: false })}
          style={styles.button}
        >
          <Text style={styles.buttonText}>{this.props.retryLabel}</Text>
        </Pressable>
      </View>
    )
  }
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
    padding: spacing.xl,
    justifyContent: 'center',
    gap: spacing.md,
  },
  title: { color: colors.ink, fontSize: font.h2, fontWeight: '700' },
  message: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  button: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
    backgroundColor: colors.ink,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
  },
  buttonText: { color: colors.surface, fontSize: font.small, fontWeight: '700' },
})
