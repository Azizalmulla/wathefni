import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import { colors, font, radius, spacing } from '@/theme'

type Props = {
  children: ReactNode
  label?: string
}

type State = {
  error: Error | null
  info: string | null
}

// Preview-only diagnostic boundary. Production app screens do not use this;
// it exists so a design-preview runtime failure never collapses to a blank white page.
export class PreviewErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({
      error,
      info: info.componentStack?.trim() || null,
    })
  }

  render() {
    const { error, info } = this.state
    if (!error) return this.props.children

    return (
      <View style={styles.root} accessibilityLabel="preview-error-boundary">
        <Text style={styles.eyebrow}>{this.props.label ?? 'Design preview crashed'}</Text>
        <Text style={styles.title}>Runtime error</Text>
        <Text style={styles.message}>{error.message || String(error)}</Text>
        {info ? <Text style={styles.stack}>{info.slice(0, 1200)}</Text> : null}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Try again"
          onPress={() => this.setState({ error: null, info: null })}
          style={styles.button}
        >
          <Text style={styles.buttonText}>Try again</Text>
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
  eyebrow: {
    color: colors.danger,
    fontSize: font.tiny,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  title: {
    color: colors.ink,
    fontSize: font.h2,
    fontWeight: '700',
  },
  message: {
    color: colors.ink,
    fontSize: font.body,
    lineHeight: 22,
  },
  stack: {
    color: colors.subtle,
    fontSize: font.tiny,
    lineHeight: 18,
    fontFamily: 'monospace',
  },
  button: {
    alignSelf: 'flex-start',
    marginTop: spacing.sm,
    backgroundColor: colors.ink,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  buttonText: {
    color: colors.surface,
    fontSize: font.small,
    fontWeight: '700',
  },
})
