import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'

import { Pager } from '@/components/Pager'
import { EmptyState, ErrorState, PageLoading } from '@/components/states'
import { Table, TableWrap, Td, Th } from '@/components/ui/table'
import { api } from '@/lib/api'
import { formatDate, label, money } from '@/lib/format'
import type { Page, RecentSalaryChange } from '@/lib/types'

const PAGE_SIZE = 50

export default function ChangesPage() {
  // The page lives in the URL (?page=2), so refresh, Back and shared links keep it.
  const [search, setSearch] = useSearchParams()
  const page = Math.max(1, Number.parseInt(search.get('page') ?? '', 10) || 1)
  const changes = useQuery({
    queryKey: ['salary-changes', page],
    queryFn: ({ signal }) =>
      api<Page<RecentSalaryChange>>(`/salary-changes?page=${page}&page_size=${PAGE_SIZE}`, { signal }),
    // Keep showing the current page while the next one loads, instead of a spinner.
    placeholderData: keepPreviousData,
  })

  if (changes.isError) return <ErrorState error={changes.error} onRetry={changes.refetch} />
  if (changes.isPending) return <PageLoading />
  if (changes.data.total === 0) return <EmptyState title="No salary changes" />
  // A page number past the end (an old link, or ?page=999 typed in) has no rows to show.
  if (changes.data.items.length === 0) {
    return (
      <EmptyState title="This page is empty">
        <Link to="/changes" className="text-primary hover:underline">
          Go to the first page
        </Link>
      </EmptyState>
    )
  }

  return (
    <>
      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Employee</Th>
              <Th>Starts on</Th>
              <Th className="text-right">Yearly salary</Th>
              <Th>Reason</Th>
              <Th className="max-sm:hidden">Changed by</Th>
            </tr>
          </thead>
          <tbody>
            {changes.data.items.map((c) => (
              <tr key={c.id}>
                <Td>
                  <Link to={`/people/${c.employee_id}`} className="font-medium text-primary hover:underline">
                    {c.employee_name}
                  </Link>
                  <div className="text-sm text-muted">{c.employee_code}</div>
                </Td>
                <Td>{formatDate(c.effective_date)}</Td>
                <Td className="text-right">{money(c.amount, c.currency)}</Td>
                <Td>{label(c.reason)}</Td>
                <Td className="text-muted max-sm:hidden">{c.created_by_name ?? 'Import'}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
      <Pager data={changes.data} onPage={(next) => setSearch({ page: String(next) })} />
    </>
  )
}
