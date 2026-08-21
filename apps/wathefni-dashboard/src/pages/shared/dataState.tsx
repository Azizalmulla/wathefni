import { Button } from '@/components/ui/button'

export type DataStateKind = 'loading' | 'empty' | 'error' | 'unavailable' | 'forbidden' | 'ready'

export type DataStateLocale = 'en' | 'ar'

const COPY: Record<DataStateLocale, Record<Exclude<DataStateKind, 'ready'>, { title: string; detail: string; retry: string; retrying: string }>> = {
  en: {
    loading: { title: 'Loading…', detail: '', retry: 'Retry', retrying: 'Retrying…' },
    empty: { title: 'Nothing to show', detail: '', retry: 'Retry', retrying: 'Retrying…' },
    error: {
      title: 'Could not load this data',
      detail: 'The request failed. This is not an empty result — try again.',
      retry: 'Retry',
      retrying: 'Retrying…',
    },
    unavailable: {
      title: 'This capability is not available',
      detail: 'It is turned off or not included for this company.',
      retry: 'Retry',
      retrying: 'Retrying…',
    },
    forbidden: {
      title: 'You do not have access',
      detail: 'This page is hidden because your role cannot use it.',
      retry: 'Retry',
      retrying: 'Retrying…',
    },
  },
  ar: {
    loading: { title: 'جاري التحميل…', detail: '', retry: 'إعادة المحاولة', retrying: 'جاري إعادة المحاولة…' },
    empty: { title: 'لا يوجد ما يُعرض', detail: '', retry: 'إعادة المحاولة', retrying: 'جاري إعادة المحاولة…' },
    error: {
      title: 'تعذّر تحميل هذه البيانات',
      detail: 'فشل الطلب. هذه ليست نتيجة فارغة — حاول مرة أخرى.',
      retry: 'إعادة المحاولة',
      retrying: 'جاري إعادة المحاولة…',
    },
    unavailable: {
      title: 'هذه القدرة غير متاحة',
      detail: 'هي متوقفة أو غير مشمولة لهذه الشركة.',
      retry: 'إعادة المحاولة',
      retrying: 'جاري إعادة المحاولة…',
    },
    forbidden: {
      title: 'ليست لديك صلاحية الوصول',
      detail: 'هذه الصفحة مخفية لأن صلاحيتك لا تسمح باستخدامها.',
      retry: 'إعادة المحاولة',
      retrying: 'جاري إعادة المحاولة…',
    },
  },
}

/** Resolve a list/read into a UI kind. Failure never collapses to empty. */
export function resolveListDataState(args: {
  forbidden?: boolean
  unavailable?: boolean
  loading?: boolean
  error?: boolean
  itemCount?: number
}): DataStateKind {
  if (args.forbidden) return 'forbidden'
  if (args.unavailable) return 'unavailable'
  if (args.loading) return 'loading'
  if (args.error) return 'error'
  if (!args.itemCount) return 'empty'
  return 'ready'
}

export function ResourceState({
  kind,
  locale = 'en',
  title,
  detail,
  onRetry,
  retrying = false,
  testId,
}: {
  kind: Exclude<DataStateKind, 'ready'>
  locale?: DataStateLocale
  title?: string
  detail?: string
  onRetry?: () => void
  retrying?: boolean
  testId?: string
}) {
  const copy = COPY[locale][kind]
  const heading = title ?? copy.title
  const body = detail ?? copy.detail
  const isError = kind === 'error'
  const showRetry = Boolean(onRetry) && (kind === 'error' || kind === 'unavailable')

  if (kind === 'loading') {
    return (
      <div className="space-y-3" data-testid={testId || 'resource-state-loading'} aria-busy="true">
        <div className="h-12 animate-pulse rounded-2xl bg-white/55" />
        <div className="h-12 animate-pulse rounded-2xl bg-white/55" />
        <div className="h-24 animate-pulse rounded-2xl bg-white/55" />
        <p className="sr-only">{heading}</p>
      </div>
    )
  }

  if (kind === 'empty') {
    return (
      <div
        className="rounded-[1.5rem] border border-dashed border-line/75 bg-white/28 p-5 text-sm leading-6 text-subtle"
        data-testid={testId || 'resource-state-empty'}
      >
        <div className="flex items-center gap-2 font-medium text-text">
          <span className="h-1.5 w-1.5 rounded-full bg-semantic-accent" />
          <span className="max-w-2xl">{heading}</span>
        </div>
        {body ? <p className="mt-2 max-w-2xl text-subtle">{body}</p> : null}
      </div>
    )
  }

  return (
    <div
      className={
        isError
          ? 'rounded-[1.5rem] border border-rose-200/80 bg-rose-50/70 p-5 text-sm leading-6 text-rose-900'
          : 'rounded-[1.5rem] border border-line/75 bg-white/40 p-5 text-sm leading-6 text-text'
      }
      data-testid={testId || `resource-state-${kind}`}
      role={isError || kind === 'forbidden' ? 'alert' : undefined}
    >
      <div className="font-semibold">{heading}</div>
      {body ? <p className={`mt-1 ${isError ? 'text-rose-800/90' : 'text-subtle'}`}>{body}</p> : null}
      {showRetry ? (
        <div className="mt-4">
          <Button disabled={retrying} onClick={() => onRetry?.()} size="sm" type="button">
            {retrying ? copy.retrying : copy.retry}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
