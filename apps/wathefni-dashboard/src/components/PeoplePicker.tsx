import { useEffect, useMemo, useState } from 'react'
import type { DashboardAccess } from '@/types'
import { getTeamPeople, type TeamPerson } from '@/lib/api'

export type PeoplePickerPurpose =
  | 'recruiter'
  | 'hiring_manager'
  | 'interviewer'
  | 'task_owner'
  | 'approver'
  | 'directory'

type PeoplePickerProps = {
  access: DashboardAccess
  purpose: PeoplePickerPurpose
  value: string
  onChange: (userId: string, person: TeamPerson | null) => void
  allowUnassigned?: boolean
  disabled?: boolean
  locale?: 'en' | 'ar'
  className?: string
  placeholder?: string
}

export function PeoplePicker({
  access,
  purpose,
  value,
  onChange,
  allowUnassigned = true,
  disabled = false,
  locale = 'en',
  className,
  placeholder,
}: PeoplePickerProps) {
  const isAr = locale === 'ar'
  const [query, setQuery] = useState('')
  const [people, setPeople] = useState<TeamPerson[]>([])
  const [selected, setSelected] = useState<TeamPerson | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    const handle = window.setTimeout(() => {
      setBusy(true)
      void getTeamPeople(access, { purpose, q: query || undefined, limit: 40 })
        .then((payload) => {
          if (cancelled) return
          setPeople(Array.isArray(payload.people) ? payload.people : [])
        })
        .catch(() => {
          if (!cancelled) setPeople([])
        })
        .finally(() => {
          if (!cancelled) setBusy(false)
        })
    }, 180)
    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [access, purpose, query])

  useEffect(() => {
    if (!value) {
      setSelected(null)
      return
    }
    const match = people.find((person) => person.user_id === value)
    if (match) setSelected(match)
  }, [value, people])

  const display = useMemo(() => {
    if (!value) return isAr ? 'غير مسند' : 'Unassigned'
    if (selected?.label) return selected.label
    if (selected?.name) return `${selected.name} · ${selected.role_label || selected.role}`
    return isAr ? 'عضو الفريق' : 'Team member'
  }, [value, selected, isAr])

  return (
    <div className={className || 'relative'}>
      <button
        className="flex w-full items-center justify-between rounded-xl border border-line bg-white px-3 py-2 text-left text-sm text-text disabled:opacity-50"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span className="truncate">{display}</span>
        <span className="text-xs text-subtle">{open ? (isAr ? 'إغلاق' : 'Close') : (isAr ? 'اختيار' : 'Choose')}</span>
      </button>
      {open ? (
        <div className="absolute z-20 mt-2 w-full rounded-xl border border-line bg-panel p-2 shadow-soft">
          <input
            autoFocus
            className="mb-2 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"
            onChange={(event) => setQuery(event.target.value)}
            placeholder={placeholder || (isAr ? 'ابحث بالاسم أو الدور' : 'Search by name or role')}
            value={query}
          />
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {allowUnassigned ? (
              <button
                className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-panel-muted"
                onClick={() => {
                  onChange('', null)
                  setSelected(null)
                  setOpen(false)
                }}
                type="button"
              >
                {isAr ? 'غير مسند' : 'Unassigned'}
              </button>
            ) : null}
            {people.map((person) => (
              <button
                className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-panel-muted"
                key={person.user_id}
                onClick={() => {
                  onChange(person.user_id, person)
                  setSelected(person)
                  setOpen(false)
                }}
                type="button"
              >
                <div className="font-medium text-text">{person.name}</div>
                <div className="text-xs text-subtle">{person.role_label || person.role}</div>
              </button>
            ))}
            {!busy && people.length === 0 ? (
              <div className="px-3 py-2 text-xs text-subtle">{isAr ? 'لا يوجد أعضاء مؤهلون' : 'No eligible people'}</div>
            ) : null}
            {busy ? <div className="px-3 py-2 text-xs text-subtle">{isAr ? 'جارٍ التحميل…' : 'Loading…'}</div> : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
