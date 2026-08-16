import { Component, StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'

import { ConfirmProvider } from '@/components/ConfirmDialog'
import '@/index.css'

import { reportClientError } from '@/lib/reportClientError'

import SetupConsoleApp from './SetupConsoleApp'

declare global {
  interface Window {
    __WATHEFNI_SETUP_CONSOLE_BOOT_FAIL__?: (message: string) => void
    __WATHEFNI_SETUP_CONSOLE_BOOT_TIMER__?: number
  }
}

function clearBootShell() {
  document.documentElement.dataset.setupConsoleMounted = '1'
  if (window.__WATHEFNI_SETUP_CONSOLE_BOOT_TIMER__) {
    window.clearTimeout(window.__WATHEFNI_SETUP_CONSOLE_BOOT_TIMER__)
  }
  const boot = document.getElementById('setup-console-boot')
  if (boot) boot.hidden = true
}

/** Mirrors dashboard AppErrorBoundary — Setup Console must never white-screen on a render throw. */
class SetupConsoleErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; message: string }
> {
  state = { hasError: false, message: '' }

  static getDerivedStateFromError(error: unknown) {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : 'Unexpected Setup Console render failure.',
    }
  }

  componentDidCatch(error: unknown) {
    console.error('Setup Console render error:', error)
    reportClientError(error, 'setup_console')
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            color: '#1f1c18',
            background: '#f8f2e6',
          }}
        >
          <div style={{ maxWidth: 420, textAlign: 'center' }}>
            <h1 style={{ fontSize: 18, fontWeight: 600, margin: '0 0 8px' }}>
              Something interrupted Setup Console
            </h1>
            <p style={{ fontSize: 14, lineHeight: 1.6, color: '#5c564d', margin: '0 0 18px' }}>
              {this.state.message || 'Please reload the page. If it keeps happening, contact Wathefni platform ops.'}
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                cursor: 'pointer',
                border: 'none',
                borderRadius: 999,
                padding: '10px 18px',
                fontSize: 14,
                fontWeight: 600,
                color: '#fff',
                background: '#11100e',
              }}
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

const rootEl = document.getElementById('root')
if (!rootEl) {
  window.__WATHEFNI_SETUP_CONSOLE_BOOT_FAIL__?.(
    'Setup Console root element is missing from the HTML shell.',
  )
} else {
  try {
    clearBootShell()
    createRoot(rootEl).render(
      <StrictMode>
        <SetupConsoleErrorBoundary>
          <ConfirmProvider>
            <SetupConsoleApp />
          </ConfirmProvider>
        </SetupConsoleErrorBoundary>
      </StrictMode>,
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to mount Setup Console.'
    console.error(message, error)
    reportClientError(error, 'setup_console')
    window.__WATHEFNI_SETUP_CONSOLE_BOOT_FAIL__?.(message)
  }
}
