import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'

import { ConfirmProvider } from '@/components/ConfirmDialog'

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 60_000,
      },
      mutations: { retry: false },
    },
  })
}

export function renderWithProviders(ui: ReactElement, client = createTestQueryClient()) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <ConfirmProvider>{children}</ConfirmProvider>
      </QueryClientProvider>
    )
  }
  return {
    client,
    ...render(ui, { wrapper: Wrapper }),
  }
}
