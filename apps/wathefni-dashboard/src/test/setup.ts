import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Full-app integration tests boot the whole shell and settle several queries,
// which exceeds the 1s default once files run in parallel on a loaded machine.
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
})
