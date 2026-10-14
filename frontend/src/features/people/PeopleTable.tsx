import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { useMemo, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { Avatar } from '@/components/Avatar'
import { Table, TableWrap, Td, Th } from '@/components/ui/table'
import { money, usd } from '@/lib/format'
import { countryName } from '@/lib/meta'
import type { PeopleParams, SortKey } from '@/lib/peopleParams'
import type { EmployeeListItem, Meta } from '@/lib/types'

const features = tableFeatures({})
const helper = createColumnHelper<typeof features, EmployeeListItem>()

// Which server-side sort each column header uses, and how its cells are aligned/hidden.
const SORT_BY: Record<string, SortKey> = { employee: 'name', role: 'job_title', location: 'country', salary: 'salary' }
const COLUMN_CLASS: Record<string, string> = { role: 'max-sm:hidden', location: 'max-sm:hidden', salary: 'text-right' }

interface PeopleTableProps {
  rows: EmployeeListItem[]
  params: PeopleParams
  meta: Meta
  onSort: (sort: SortKey, order: 'asc' | 'desc') => void
}

export function PeopleTable({ rows, params, meta, onSort }: PeopleTableProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const q = params.q

  const columns = useMemo(
    () =>
      helper.columns([
        helper.display({
          id: 'employee',
          header: 'Employee',
          cell: ({ row: { original: p } }) => (
            <div className="flex items-center gap-3">
              <Avatar first={p.first_name} last={p.last_name} />
              <TwoLines
                top={<Highlight text={`${p.first_name} ${p.last_name}`} query={q} />}
                bottom={<Highlight text={p.employee_code} query={q} />}
              />
            </div>
          ),
        }),
        helper.display({
          id: 'role',
          header: 'Role',
          cell: ({ row: { original: p } }) => (
            <TwoLines top={p.job_title} bottom={`Level ${p.job_level}, ${p.department}`} />
          ),
        }),
        helper.display({
          id: 'location',
          header: 'Location',
          cell: ({ row: { original: p } }) => (
            <TwoLines top={countryName(meta, p.country_code)} bottom={p.city ?? ' '} />
          ),
        }),
        helper.display({
          id: 'salary',
          header: 'Yearly salary',
          cell: ({ row: { original: p } }) => (
            <TwoLines
              top={money(p.current_salary, p.current_currency)}
              bottom={p.current_currency === 'USD' ? ' ' : `≈ ${usd(p.current_salary_usd)}`}
            />
          ),
        }),
      ]),
    [q, meta],
  )

  const table = useTable({ features, columns, data: rows })

  const open = (id: number) => navigate(`/people/${id}`, { state: { from: location.search } })

  return (
    <TableWrap>
      <Table>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const sortKey = SORT_BY[header.id]
                const active = params.sort === sortKey
                return (
                  <Th
                    key={header.id}
                    className={COLUMN_CLASS[header.id]}
                    aria-sort={active ? (params.order === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    <button
                      className="cursor-pointer hover:text-foreground"
                      onClick={() =>
                        // Salary sorts highest first on the first click; text columns A–Z.
                        onSort(sortKey, active ? (params.order === 'asc' ? 'desc' : 'asc') : sortKey === 'salary' ? 'desc' : 'asc')
                      }
                    >
                      <table.FlexRender header={header} />
                      {active && (params.order === 'asc' ? ' ↑' : ' ↓')}
                    </button>
                  </Th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              tabIndex={0}
              className="cursor-pointer hover:bg-subtle focus:bg-subtle"
              onClick={() => open(row.original.id)}
              onKeyDown={(e) => {
                const tr = e.currentTarget
                if (e.key === 'Enter') open(row.original.id)
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  ;(tr.nextElementSibling as HTMLElement | null)?.focus()
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  ;(tr.previousElementSibling as HTMLElement | null)?.focus()
                }
              }}
            >
              {row.getAllCells().map((cell) => (
                <Td key={cell.id} className={COLUMN_CLASS[cell.column.id]}>
                  <table.FlexRender cell={cell} />
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </Table>
    </TableWrap>
  )
}

function TwoLines({ top, bottom }: { top: ReactNode; bottom: ReactNode }) {
  return (
    <div>
      <div>{top}</div>
      <div className="text-sm text-muted">{bottom}</div>
    </div>
  )
}

/** Marks the first match of the search text. */
export function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim()
  const at = q ? text.toLowerCase().indexOf(q.toLowerCase()) : -1
  if (at < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + q.length)}</mark>
      {text.slice(at + q.length)}
    </>
  )
}
