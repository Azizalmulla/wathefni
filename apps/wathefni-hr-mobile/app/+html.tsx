import type { PropsWithChildren } from 'react'
import { ScrollViewStyleReset } from 'expo-router/html'

/**
 * Custom HTML shell for static/web exports.
 * viewport-fit=cover is required so env(safe-area-inset-*) works on iPhone Safari.
 * ScrollViewStyleReset keeps body overflow locked so one root ScrollView owns page scroll.
 */
export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover"
        />
        <ScrollViewStyleReset />
      </head>
      <body>{children}</body>
    </html>
  )
}
