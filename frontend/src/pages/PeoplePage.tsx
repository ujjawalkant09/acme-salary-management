import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { FilterPanel } from '@/features/people/FilterPanel'
import { filterChips } from '@/features/people/filterChips'
import { PeopleTable } from '@/features/people/PeopleTable'
import { Icon } from '@/components/icons'
import { EmptyState, ErrorState, PageLoading, Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api, API_BASE } from '@/lib/api'
import { count } from '@/lib/format'
import { useMeta } from '@/lib/meta'
import {
  activeFilterCount,
  EMPTY_FILTERS,
  filterParams,
  parsePeopleParams,
  toSearchParams,
  type PeopleParams,
} from '@/lib/peopleParams'
import type { EmployeeListItem, Facets, Page } from '@/lib/types'
import { useDebouncedInput } from '@/lib/useDebouncedValue'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 20

export default function PeoplePage() {
  const [search, setSearch] = useSearchParams()
  const params = useMemo(() => parsePeopleParams(search), [search])
  const [showFilters, setShowFilters] = useState(true)
  const [mobileFilters, setMobileFilters] = useState(false)
  const meta = useMeta()

  const listQuery = toSearchParams(params).toString()
  const filterQuery = filterParams(params).toString()
  const employees = useQuery({
    queryKey: ['employees', listQuery],
    queryFn: ({ signal }) =>
      api<Page<EmployeeListItem>>(`/employees?${listQuery}&page_size=${PAGE_SIZE}`, { signal }),
    placeholderData: keepPreviousData,
  })
  const facets = useQuery({
    queryKey: ['facets', filterQuery],
    queryFn: ({ signal }) => api<Facets>(`/employees/facets?${filterQuery}`, { signal }),
    placeholderData: keepPreviousData,
  })

  /** Any filter change goes back to page 1; typing replaces the history entry instead of adding one. */
  function update(changes: Partial<PeopleParams>, replace = false) {
    setSearch(toSearchParams({ ...params, page: 1, ...changes }), { replace })
  }

  const [q, setQ] = useDebouncedInput(params.q, (value) => update({ q: value }, true), 300)

  if (meta.isPending) return <PageLoading />
  if (meta.isError) return <ErrorState error={meta.error} onRetry={meta.refetch} />

  const chips = filterChips(params, meta.data, update)
  const filterCount = activeFilterCount(params)
  const clearAll = () => update({ ...EMPTY_FILTERS })
  const data = employees.data

  return (
    <div className={cn('grid items-start gap-6', showFilters && 'md:grid-cols-[15.5rem_1fr]')}>
      {mobileFilters && (
        <div className="fixed inset-0 z-40 bg-[rgba(20,22,30,.25)] md:hidden" onClick={() => setMobileFilters(false)} />
      )}
      <FilterPanel
        filters={params}
        facets={facets.data}
        meta={meta.data}
        onChange={(changes) => update(changes)}
        onClear={filterCount > 0 || params.q ? clearAll : null}
        onClose={() => setMobileFilters(false)}
        className={cn(
          // Desktop: a sticky panel next to the table. Phone: a bottom drawer.
          'max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:z-50 max-md:max-h-[80vh] max-md:rounded-b-none',
          'md:sticky md:top-[5.5rem] md:max-h-[calc(100vh-112px)]',
          !mobileFilters && 'max-md:hidden',
          !showFilters && 'md:hidden',
        )}
      />

      <section className="min-w-0">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Button variant="outline" className="max-md:hidden" aria-pressed={showFilters} onClick={() => setShowFilters(!showFilters)}>
            <Icon name="panel" />
            {showFilters ? 'Hide filters' : 'Show filters'}
          </Button>
          <Button variant="outline" className="md:hidden" onClick={() => setMobileFilters(true)}>
            <Icon name="filter" />
            Filters{filterCount > 0 && ` (${filterCount})`}
          </Button>
          <div className="relative max-w-[28rem] flex-[1_1_16rem]">
            <Icon name="search" className="absolute top-1/2 left-2.5 size-[1.125rem] -translate-y-1/2 text-muted" />
            <Input
              id="people-search"
              type="search"
              placeholder="Search name, email or employee code"
              aria-label="Search people"
              autoComplete="off"
              className="pl-9"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <span className="flex-1" />
          <Button variant="outline" asChild>
            <a href={`${API_BASE}/employees/export.csv?${filterQuery}`} download>
              Export CSV
            </a>
          </Button>
        </div>

        <div className="mb-3 flex min-h-[1.875rem] flex-wrap items-center gap-1.5">
          <span className="mr-1 text-sm text-muted" aria-live="polite">
            {data ? `${count(data.total)} ${data.total === 1 ? 'person' : 'people'}` : ' '}
          </span>
          {employees.isFetching && <Spinner className="size-3.5 text-muted" />}
          {chips.map((chip) => (
            <button
              key={chip.key}
              onClick={chip.remove}
              aria-label={`Remove filter ${chip.text}`}
              className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-full bg-primary-soft pr-1.5 pl-2.5 text-sm font-medium text-primary hover:bg-[#e2e9fc]"
            >
              {chip.text}
              <Icon name="x" className="size-3.5" />
            </button>
          ))}
        </div>

        {employees.isError ? (
          <ErrorState error={employees.error} onRetry={employees.refetch} />
        ) : !data ? (
          <PageLoading />
        ) : data.items.length === 0 ? (
          <div className="rounded-xl border border-border">
            <EmptyState title="No one matches">
              <p>Try another name, or remove some filters.</p>
              <Button variant="outline" className="mt-3" onClick={clearAll}>
                Clear all filters
              </Button>
            </EmptyState>
          </div>
        ) : (
          <>
            <PeopleTable
              rows={data.items}
              params={params}
              meta={meta.data}
              onSort={(sort, order) => setSearch(toSearchParams({ ...params, sort, order, page: 1 }))}
            />
            <Pager data={data} onPage={(page) => setSearch(toSearchParams({ ...params, page }))} />
          </>
        )}
      </section>
    </div>
  )
}

function Pager({ data, onPage }: { data: Page<unknown>; onPage: (page: number) => void }) {
  const first = (data.page - 1) * data.page_size + 1
  const last = Math.min(data.page * data.page_size, data.total)
  return (
    <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm text-muted">
        {count(first)}–{count(last)} of {count(data.total)}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>
          Previous
        </Button>
        <span className="px-1.5 text-sm text-muted">
          Page {count(data.page)} of {count(Math.max(1, data.pages))}
        </span>
        <Button variant="outline" size="sm" disabled={data.page >= data.pages} onClick={() => onPage(data.page + 1)}>
          Next
        </Button>
      </div>
    </div>
  )
}
