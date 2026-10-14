import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import { PayBand, type BandStats } from '@/components/PayBand'
import { ErrorState, PageLoading } from '@/components/states'
import { Table, TableWrap, Td, Th } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api } from '@/lib/api'
import { count, money, usd } from '@/lib/format'
import { useMeta } from '@/lib/meta'
import type { GroupStats, GroupStatsOut } from '@/lib/types'

type GroupBy = 'country' | 'department'

/** Country stats come in local currency; for the shared USD scale they're converted for drawing only. */
function inUsd(group: GroupStats, usdPerUnit: string | undefined): BandStats {
  const rate = Number(usdPerUnit ?? 1)
  const convert = (value: string) => String(Number(value) * rate)
  return {
    min: convert(group.min),
    p25: convert(group.p25),
    median: convert(group.median),
    p75: convert(group.p75),
    max: convert(group.max),
  }
}

export function OverviewTab() {
  const [groupBy, setGroupBy] = useState<GroupBy>('country')
  const meta = useMeta()
  const stats = useQuery({
    queryKey: ['insights', groupBy],
    queryFn: () => api<GroupStatsOut>(`/insights/by-${groupBy}`),
  })
  const isCountry = groupBy === 'country'

  const rows = (stats.data?.groups ?? []).toSorted((a, b) => b.people - a.people)
  const bands = rows.map((g) => (isCountry ? inUsd(g, meta.data?.fx.usd_per_unit[g.currency]) : g))
  // One scale for every row, so the bands can be compared with each other.
  const hi = Math.max(0, ...bands.map((b) => Number(b.max)))

  function peopleLink(group: GroupStats): string {
    if (isCountry) return `/people?country=${group.key}`
    const department = meta.data?.departments.find((d) => d.name === group.key)
    return department ? `/people?department_id=${department.id}` : '/people'
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-md font-semibold">How pay compares by {groupBy}</h2>
        <span className="flex-1" />
        <ToggleGroup type="single" value={groupBy} onValueChange={(v) => v && setGroupBy(v as GroupBy)} aria-label="Group by">
          <ToggleGroupItem value="country">Country</ToggleGroupItem>
          <ToggleGroupItem value="department">Department</ToggleGroupItem>
        </ToggleGroup>
      </div>

      {stats.isError ? (
        <ErrorState error={stats.error} onRetry={stats.refetch} />
      ) : stats.isPending ? (
        <PageLoading />
      ) : rows.length === 0 ? (
        <p className="text-muted">No current employees yet.</p>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>{isCountry ? 'Country' : 'Department'}</Th>
                <Th className="text-right">People</Th>
                {isCountry && <Th className="text-right max-sm:hidden">Median (local)</Th>}
                <Th className="text-right">Median (USD)</Th>
                <Th className="text-right max-sm:hidden">Yearly cost (USD)</Th>
                <Th className="max-sm:hidden">Pay range (USD)</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((g, i) => (
                <tr key={g.key}>
                  <Td>{g.label}</Td>
                  <Td className="text-right">
                    <Link to={peopleLink(g)} className="font-medium text-primary hover:underline">
                      {count(g.people)}
                    </Link>
                  </Td>
                  {isCountry && <Td className="text-right max-sm:hidden">{money(g.median, g.currency)}</Td>}
                  <Td className="text-right">{usd(g.median_usd ?? g.median)}</Td>
                  <Td className="text-right max-sm:hidden">{usd(g.cost_usd ?? g.cost, true)}</Td>
                  <Td className="max-sm:hidden">
                    <PayBand
                      stats={bands[i]}
                      width={420}
                      scale={{ lo: 0, hi }}
                      label={`${g.label}: middle half of salaries ${usd(bands[i].p25)} to ${usd(bands[i].p75)}`}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
      <p className="mt-2.5 text-sm text-muted">
        Pay range: the shaded bar holds the middle half of salaries; the blue line is the median. Click a number of
        people to see them.
      </p>
    </>
  )
}
