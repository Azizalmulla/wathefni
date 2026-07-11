import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { ConfirmProvider } from '@/components/ConfirmDialog'
import '@/index.css'

import SetupConsoleApp from './SetupConsoleApp'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfirmProvider>
      <SetupConsoleApp />
    </ConfirmProvider>
  </StrictMode>,
)
