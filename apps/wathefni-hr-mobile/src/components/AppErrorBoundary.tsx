import { Component, type ErrorInfo, type ReactNode } from 'react'

import { LocaleProvider } from '@/i18n'
import { reportClientError } from '@/lib/reportClientError'
import { Screen, StatePanel } from './primitives'

type Props = { children: ReactNode }
type State = { failed: boolean }

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, _info: ErrorInfo) {
    reportClientError(error)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <LocaleProvider initialLocale="en" persist={false}>
        <Screen>
          <StatePanel
            title="Wathefni HR needs a fresh start"
            body="No decision was submitted. Close and reopen the app, then try again."
            icon="shield-checkmark-outline"
          />
        </Screen>
      </LocaleProvider>
    )
  }
}
