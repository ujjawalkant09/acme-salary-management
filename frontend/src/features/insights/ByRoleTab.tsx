import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, useState } from 'react'

import { PayBand } from '@/components/PayBand'
import { ErrorState, PageLoading } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { NativeSelect } from '@/components/ui/input'
import { Table, TableWrap, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { money } from '@/lib/format'
import { useMeta } from '@/lib/meta'
import type { Distribution, GroupStatsOut } from '@/lib/types'

// Recharts is the heaviest dependency; it loads only when this tab is opened.
const Histogram = lazy(() => import('./Histogram'))

export function ByRoleTab() {
  const meta = useMeta()
  const [country, setCountry] = useState('IN')
  // The role table and the histogram load in parallel.
  const roles = useQuery({
    queryKey: ['insights', 'by-role', country],
    queryFn: () => api<GroupStatsOut>(`/insights/by-role?country=${country}`),
  })
  const spread = useQuery({
    queryKey: ['insights', 'distribution', country],
    queryFn: () => api<Distribution>(`/insights/distribution?country=${country}&bins=20`),
  })
  const countryInfo = meta.data?.countries.find((c) => c.code === country)

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-md font-semibold">Pay by role in</h2>
        <NativeSelect className="w-auto min-w-44" aria-label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
          {meta.data?.countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
        {countryInfo && <span className="text-sm text-muted">Amounts in {countryInfo.currency}</span>}
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[3fr_2fr]">
        {roles.isError ? (
          <ErrorState error={roles.error} onRetry={roles.refetch} />
        ) : roles.isPending ? (
          <PageLoading />
        ) : roles.data.groups.length === 0 ? (
          <p className="text-muted">No current employees in this country.</p>
        ) : (
          <TableWrap className="max-h-[35rem] overflow-auto">
            <Table>
              <thead className="sticky top-0">
                <tr>
                  <Th>Role</Th>
                  <Th className="text-right">People</Th>
                  <Th className="max-sm:hidden">Pay range</Th>
                  <Th className="text-right">Median</Th>
                </tr>
              </thead>
              <tbody>
                {roles.data.groups.map((g) => (
                  <tr key={g.key}>
                    <Td>
                      {g.label} <span className="text-muted">L{g.job_level}</span>
                      {g.outliers > 0 && (
                        <Badge variant="warn" className="ml-1.5">
                          {g.outliers} unusual
                        </Badge>
                      )}
                    </Td>
                    <Td className="text-right">{g.people}</Td>
                    <Td className="max-sm:hidden">
                      <PayBand
                        stats={g}
                        width={240}
                        label={`${g.label} level ${g.job_level}: ${money(g.min, g.currency)} to ${money(g.max, g.currency)}, median ${money(g.median, g.currency)}`}
                      />
                    </Td>
                    <Td className="text-right">{money(g.median, g.currency)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        )}

        <div className="rounded-xl border border-border p-5">
          <h2 className="mb-1 text-md font-semibold">How salaries are spread{countryInfo && ` in ${countryInfo.name}`}</h2>
          <p className="mb-3 text-sm text-muted">Number of people in each salary bracket (full-time pay).</p>
          {spread.isError ? (
            <ErrorState error={spread.error} onRetry={spread.refetch} />
          ) : spread.isPending ? (
            <PageLoading />
          ) : (
            <Suspense fallback={<PageLoading />}>
              <Histogram data={spread.data} />
            </Suspense>
          )}
        </div>
      </div>
    </>
  )
}
