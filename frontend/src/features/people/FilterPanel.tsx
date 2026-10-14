import { useState, type ReactNode } from 'react'

import { Icon } from '@/components/icons'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { count, label } from '@/lib/format'
import { toggle, type ListFilterKey, type PeopleFilters, type StatusFilter } from '@/lib/peopleParams'
import type { Facets, Meta } from '@/lib/types'
import { useDebouncedInput } from '@/lib/useDebouncedValue'
import { cn } from '@/lib/utils'

interface FilterPanelProps {
  filters: PeopleFilters
  facets: Facets | undefined
  meta: Meta
  onChange: (changes: Partial<PeopleFilters>) => void
  onClear: (() => void) | null
  onClose: () => void
  className?: string
}

const STATUS_OPTIONS: { value: StatusFilter; text: string }[] = [
  { value: 'active', text: 'Current employees' },
  { value: 'left', text: 'People who left' },
  { value: 'all', text: 'Everyone' },
]
const TOP_COUNTRIES = 5

export function FilterPanel({ filters, facets, meta, onChange, onClear, onClose, className }: FilterPanelProps) {
  const [showAllCountries, setShowAllCountries] = useState(false)
  const n = (group: keyof Facets, key: string | number) => facets?.[group][String(key)] ?? 0

  const countries = meta.countries.toSorted((a, b) => n('country', b.code) - n('country', a.code))
  const shownCountries = showAllCountries ? countries : countries.slice(0, TOP_COUNTRIES)
  const statusTotal = (facets?.status.active ?? 0) + (facets?.status.left ?? 0)

  const checkboxes = (key: ListFilterKey, options: { value: string; text: string; n: number }[]) =>
    options.map((o) => (
      <label key={o.value} className={cn('flex cursor-pointer items-center gap-2.5 py-1', o.n === 0 && 'text-faint')}>
        <input
          type="checkbox"
          className="size-4 accent-primary"
          checked={filters[key].includes(o.value)}
          onChange={() => onChange({ [key]: toggle(filters[key], o.value) })}
        />
        <span>{o.text}</span>
        <span className="ml-auto text-xs text-faint">{count(o.n)}</span>
      </label>
    ))

  return (
    <aside aria-label="Filters" className={cn('overflow-y-auto rounded-xl border border-border bg-background', className)}>
      <div className="sticky top-0 z-10 flex min-h-[3.25rem] items-center gap-1 border-b border-border bg-background py-2.5 pr-2.5 pl-4">
        <h2 className="flex-1 text-md font-semibold">Filters</h2>
        {onClear && (
          <Button variant="ghost" size="sm" onClick={onClear}>
            Clear all
          </Button>
        )}
        <Button variant="ghost" size="sm" className="w-[1.875rem] px-0 md:hidden" aria-label="Close filters" onClick={onClose}>
          <Icon name="x" />
        </Button>
      </div>

      <Group title="Status">
        {STATUS_OPTIONS.map((o) => (
          <label key={o.value} className="flex cursor-pointer items-center gap-2.5 py-1">
            <input
              type="radio"
              name="status"
              className="size-4 accent-primary"
              checked={filters.status === o.value}
              onChange={() => onChange({ status: o.value })}
            />
            <span>{o.text}</span>
            <span className="ml-auto text-xs text-faint">
              {count(o.value === 'all' ? statusTotal : n('status', o.value))}
            </span>
          </label>
        ))}
      </Group>

      <Group title="Country">
        {checkboxes(
          'country',
          shownCountries.map((c) => ({ value: c.code, text: c.name, n: n('country', c.code) })),
        )}
        {countries.length > TOP_COUNTRIES && (
          <button
            className="cursor-pointer py-1 text-sm font-medium text-primary"
            onClick={() => setShowAllCountries(!showAllCountries)}
          >
            {showAllCountries ? 'Show fewer' : `Show ${countries.length - TOP_COUNTRIES} more`}
          </button>
        )}
      </Group>

      <Group title="Department">
        {checkboxes(
          'department_id',
          meta.departments.map((d) => ({ value: String(d.id), text: d.name, n: n('department_id', d.id) })),
        )}
      </Group>

      <Group title="Level">
        <div className="grid grid-cols-6 gap-1">
          {meta.levels.map((level) => {
            const value = String(level)
            const on = filters.level.includes(value)
            return (
              <button
                key={level}
                aria-pressed={on}
                aria-label={`Level ${level}, ${count(n('level', level))} people`}
                onClick={() => onChange({ level: toggle(filters.level, value) })}
                className={cn(
                  'h-8 cursor-pointer rounded-[0.375rem] border border-border font-medium',
                  on ? 'border-foreground bg-foreground text-white' : 'bg-background hover:bg-subtle',
                )}
              >
                {level}
              </button>
            )
          })}
        </div>
      </Group>

      <Group title="Employment type">
        {checkboxes(
          'employment_type',
          meta.employment_types.map((t) => ({ value: t, text: label(t), n: n('employment_type', t) })),
        )}
      </Group>

      <Group title="Yearly salary (USD)">
        <div className="flex items-center gap-2">
          <SalaryInput text="Min" value={filters.min_salary_usd} onCommit={(v) => onChange({ min_salary_usd: v })} />
          <span className="text-muted">to</span>
          <SalaryInput text="Max" value={filters.max_salary_usd} onCommit={(v) => onChange({ max_salary_usd: v })} />
        </div>
      </Group>

      <Group title="Unusual salaries">
        <label className="flex cursor-pointer items-center gap-2.5 py-1">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={filters.outliers_only}
            onChange={() => onChange({ outliers_only: !filters.outliers_only })}
          />
          <span>Only people paid outside the usual range</span>
        </label>
      </Group>
    </aside>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-b border-border px-4 py-3.5 last:border-b-0">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      {children}
    </div>
  )
}

const WHOLE_NUMBER = /^\d*$/

function SalaryInput({ text, value, onCommit }: { text: string; value: string; onCommit: (value: string) => void }) {
  const [draft, setDraft] = useDebouncedInput(value, onCommit, 500)
  return (
    <Input
      inputMode="numeric"
      placeholder={text}
      aria-label={`${text}imum salary in USD`}
      className="h-8 px-2"
      value={draft}
      onChange={(e) => WHOLE_NUMBER.test(e.target.value) && setDraft(e.target.value)}
    />
  )
}
