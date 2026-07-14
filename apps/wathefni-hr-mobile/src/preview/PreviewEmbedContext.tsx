import { createContext, useContext, type ReactNode } from 'react'

const PreviewEmbedContext = createContext(false)

/** When true, Screen renders content without a nested ScrollView so the page can scroll. */
export function PreviewEmbedProvider({ children, value = true }: { children: ReactNode; value?: boolean }) {
  return <PreviewEmbedContext.Provider value={value}>{children}</PreviewEmbedContext.Provider>
}

export function usePreviewEmbed() {
  return useContext(PreviewEmbedContext)
}
