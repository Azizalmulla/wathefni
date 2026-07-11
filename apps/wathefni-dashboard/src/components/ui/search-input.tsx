import { useEffect, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * Debounce a fast-changing value (e.g. a search box) so consumers can drive
 * server requests off the settled value without firing on every keystroke.
 */
export function useDebouncedValue<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

/**
 * Shared search field for module directory pages. Controlled: the parent owns
 * the raw text and typically pairs it with `useDebouncedValue` to hit the API.
 */
export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  className,
  ariaLabel,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  ariaLabel?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div className={cn('relative w-full max-w-xs', className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle/70" />
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel || placeholder}
        className="h-10 w-full rounded-full border border-line/60 bg-white/70 pl-9 pr-9 text-[13px] text-text outline-none transition focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15"
      />
      {value ? (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => {
            onChange('')
            inputRef.current?.focus()
          }}
          className="absolute right-2.5 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-subtle/70 transition hover:bg-black/5 hover:text-text"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  )
}
