import { QueryClientProvider } from '@tanstack/react-query'
import { Component, type ReactNode, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ConfirmProvider } from '@/components/ConfirmDialog'
import { dashboardQueryClient } from '@/lib/query/client'
import { installDashboardPerfGlobals } from '@/lib/perf/dashboardPerf'
import { reportClientError } from '@/lib/reportClientError'

installDashboardPerfGlobals()

// A single thrown render error must never blank the whole dashboard. This catches
// it and shows a calm recovery message instead of an empty page.
class AppErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    console.error('Dashboard render error:', error)
    reportClientError(error, 'hr_web')
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
            background: '#f4eee4',
          }}
        >
          <div style={{ maxWidth: 420, textAlign: 'center' }}>
            <h1 style={{ fontSize: 18, fontWeight: 600, margin: '0 0 8px' }}>Something interrupted the dashboard</h1>
            <p style={{ fontSize: 14, lineHeight: 1.6, color: '#5c564d', margin: '0 0 18px' }}>
              Please reload the page. If it keeps happening, contact your OctoHR administrator.
            </p>
            <button
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <QueryClientProvider client={dashboardQueryClient}>
        <ConfirmProvider>
          <App />
        </ConfirmProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  </StrictMode>,
)
