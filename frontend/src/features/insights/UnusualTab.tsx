import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { Avatar } from '@/components/Avatar'
import { ErrorState, PageLoading } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { NativeSelect } from '@/components/ui/input'
import { Table, TableWrap, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { count, money, plural, signedPct } from '@/lib/format'
import { countryName, useMeta } from '@/lib/meta'
import type { Outlier, Page } from '@/lib/types'

export function UnusualTab() {
  const navigate = useNavigate()
  const meta = useMeta()
  const [country, setCountry] = useState('')
  const [page, setPage] = useState(1)
  const outliers = useQuery({
    queryKey: ['insights', 'outliers', country, page],
    queryFn: () => api<Page<Outlier>>(`/insights/outliers?page=${page}&page_size=20${country ? `&country=${country}` : ''}`),
    placeholderData: keepPreviousData,
  })
  const data = outliers.data
  const peopleLink = `/people?outliers_only=true${country ? `&country=${country}` : ''}`

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-md font-semibold">
            {data ? `${plural(data.total, 'person is', 'people are')} paid outside the usual range` : 'Unusual salaries'}
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            Compared with others in the same role, level and country. Not necessarily wrong, but worth a look.
          </p>
        </div>
        <span className="flex-1" />
        <NativeSelect
          className="w-auto min-w-44"
          aria-label="Country"
          value={country}
          onChange={(e) => {
            setCountry(e.target.value)
            setPage(1)
          }}
        >
          <option value="">All countries</option>
          {meta.data?.countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
        <Button variant="outline" asChild>
          <Link to={peopleLink}>Open in People</Link>
        </Button>
      </div>

      {outliers.isError ? (
        <ErrorState error={outliers.error} onRetry={outliers.refetch} />
      ) : !data ? (
        <PageLoading />
      ) : data.items.length === 0 ? (
        <p className="rounded-xl border border-border p-5 text-muted">No one is paid outside the usual range.</p>
      ) : (
        <>
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Employee</Th>
                  <Th className="max-sm:hidden">Role</Th>
                  <Th className="max-sm:hidden">Country</Th>
                  <Th className="text-right">Salary</Th>
                  <Th className="text-right max-sm:hidden">Group median</Th>
                  <Th className="text-right">vs. median</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((o) => {
                  const [first = '', last = ''] = o.name.split(' ')
                  const open = () => navigate(`/people/${o.employee_id}`)
                  return (
                    <tr
                      key={o.employee_id}
                      tabIndex={0}
                      className="cursor-pointer hover:bg-subtle focus:bg-subtle"
                      onClick={open}
                      onKeyDown={(e) => e.key === 'Enter' && open()}
                    >
                      <Td>
                        <div className="flex items-center gap-3">
                          <Avatar first={first} last={last} />
                          {o.name}
                        </div>
                      </Td>
                      <Td className="max-sm:hidden">
                        {o.job_title} <span className="text-muted">L{o.job_level}</span>
                      </Td>
                      <Td className="max-sm:hidden">{countryName(meta.data, o.country_code)}</Td>
                      <Td className="text-right">{money(o.salary, o.currency)}</Td>
                      <Td className="text-right text-muted max-sm:hidden">
                        {money(o.peer_median, o.currency)} <span className="text-xs">({o.peer_count})</span>
                      </Td>
                      <Td className="text-right">
                        <Badge variant={o.direction === 'above' ? 'warn' : 'default'}>{signedPct(o.diff_from_median_pct, 0)}</Badge>
                      </Td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>
          </TableWrap>
          {data.pages > 1 && (
            <div className="mt-3.5 flex items-center justify-end gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <span className="px-1.5 text-sm text-muted">
                Page {count(data.page)} of {count(data.pages)}
              </span>
              <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </>
  )
}
