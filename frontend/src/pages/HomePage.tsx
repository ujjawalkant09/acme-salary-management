import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import { Avatar } from '@/components/Avatar'
import { Icon, type IconName } from '@/components/icons'
import { ErrorState, PageLoading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useIsAdmin, useUser } from '@/lib/auth'
import { count, formatDate, label, money, plural, usd } from '@/lib/format'
import type { ImportJob, Page, RecentSalaryChange, Summary } from '@/lib/types'

function greeting(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

const longDate = new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

export default function HomePage() {
  const user = useUser()
  const isAdmin = useIsAdmin()
  // All three load in parallel.
  const summary = useQuery({ queryKey: ['summary'], queryFn: () => api<Summary>('/insights/summary') })
  const recent = useQuery({
    queryKey: ['recent-changes'],
    queryFn: () => api<RecentSalaryChange[]>('/salary-changes/recent?limit=8'),
  })
  const imports = useQuery({
    queryKey: ['imports', 1],
    queryFn: () => api<Page<ImportJob>>('/imports?page=1'),
    enabled: isAdmin,
  })

  const [now] = useState(() => new Date())
  const waiting = imports.data?.items.filter((job) => job.status === 'validated') ?? []

  return (
    <>
      <h1 className="text-[1.375rem] font-semibold tracking-tight">
        {greeting(now.getHours())}, {user.name.split(' ')[0]}
      </h1>
      <p className="mt-1 mb-6 text-muted">{longDate.format(now)}</p>

      {summary.isError ? (
        <ErrorState error={summary.error} onRetry={summary.refetch} />
      ) : summary.isPending ? (
        <PageLoading />
      ) : (
        <>
          <div className="mb-7 grid rounded-xl border border-border sm:grid-cols-3">
            <Stat title="Current employees" value={count(summary.data.headcount)} note={`in ${plural(summary.data.countries, 'country', 'countries')}`} />
            <Stat
              title="Yearly salary cost"
              value={usd(summary.data.payroll_usd, true)}
              note={summary.data.rates_date ? `in USD at ECB rates of ${formatDate(summary.data.rates_date)}` : 'in USD'}
            />
            <Stat title="Median salary" value={usd(summary.data.median_salary_usd)} note="half earn more, half earn less" />
          </div>

          <div className="grid items-start gap-6 lg:grid-cols-2">
            <section className="rounded-xl border border-border">
              <div className="flex min-h-14 items-center border-b border-border px-5 py-3.5">
                <h2 className="text-md font-semibold">Needs your attention</h2>
              </div>
              <AttentionList summary={summary.data} waiting={waiting} />
            </section>

            <section className="rounded-xl border border-border">
              <div className="flex min-h-14 items-center gap-2 border-b border-border px-5 py-3.5">
                <h2 className="flex-1 text-md font-semibold">Recent salary changes</h2>
                <Button variant="ghost" size="sm" asChild>
                  <Link to="/people">View all people</Link>
                </Button>
              </div>
              {recent.isError ? (
                <div className="p-4">
                  <ErrorState error={recent.error} onRetry={recent.refetch} />
                </div>
              ) : recent.isPending ? (
                <p className="px-5 py-4 text-muted">Loading…</p>
              ) : recent.data.length === 0 ? (
                <p className="px-5 py-5 text-muted">No salary changes yet.</p>
              ) : (
                <ul>
                  {recent.data.map((change) => {
                    const [first = '', last = ''] = change.employee_name.split(' ')
                    return (
                      <li key={change.id} className="border-b border-border last:border-b-0">
                        <Link to={`/people/${change.employee_id}`} className="flex items-center gap-3 px-5 py-3.5 hover:bg-subtle">
                          <Avatar first={first} last={last} />
                          <span className="min-w-0 flex-1">
                            <span className="block font-medium">{change.employee_name}</span>
                            <span className="block text-sm text-muted">
                              {label(change.reason)}, {formatDate(change.effective_date)}
                              {change.created_by_name && `, by ${change.created_by_name}`}
                            </span>
                          </span>
                          <span className="text-right">{money(change.amount, change.currency)}</span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </>
  )
}

function Stat({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <div className="border-border px-6 py-5 not-last:border-b sm:not-last:border-r sm:not-last:border-b-0">
      <div className="text-muted">{title}</div>
      <div className="mt-0.5 text-[1.75rem] font-semibold tracking-tight">{value}</div>
      <div className="mt-0.5 text-sm text-muted">{note}</div>
    </div>
  )
}

interface Todo {
  icon: IconName
  tone: string
  title: string
  text: string
  /** Where to act on it; rows without a page to go to are plain text. */
  to?: string
}

function AttentionList({ summary, waiting }: { summary: Summary; waiting: ImportJob[] }) {
  const todos: Todo[] = []
  if (summary.outlier_count > 0) {
    todos.push({
      icon: 'alert',
      tone: 'bg-amber-soft text-amber',
      title: `${plural(summary.outlier_count, 'person is', 'people are')} paid outside the usual range`,
      text: 'Compared with others in the same role, level and country',
      to: '/insights?tab=unusual',
    })
  }
  if (summary.upcoming_changes_7d > 0) {
    todos.push({
      icon: 'calendar',
      tone: 'bg-primary-soft text-primary',
      title: `${plural(summary.upcoming_changes_7d, 'salary change starts', 'salary changes start')} in the next 7 days`,
      text: 'They take effect automatically on their start date',
    })
  }
  if (waiting.length > 0) {
    todos.push({
      icon: 'file',
      tone: 'bg-subtle text-foreground',
      title: `${plural(waiting.length, 'import is', 'imports are')} waiting for your review`,
      text: waiting[0].filename,
      to: '/imports',
    })
  }

  if (todos.length === 0) return <p className="m-0 p-5 text-muted">Nothing needs your attention right now.</p>
  return (
    <ul>
      {todos.map((todo) => (
        <li key={todo.title} className="border-b border-border last:border-b-0">
          {todo.to ? (
            <Link to={todo.to} className="flex items-center gap-3 px-5 py-3.5 hover:bg-subtle">
              <TodoBody todo={todo} />
              <Icon name="chevronRight" className="size-[1.125rem] text-faint" />
            </Link>
          ) : (
            <div className="flex items-center gap-3 px-5 py-3.5">
              <TodoBody todo={todo} />
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

function TodoBody({ todo }: { todo: Todo }) {
  return (
    <>
      <span className={`grid size-8 shrink-0 place-items-center rounded-md ${todo.tone}`}>
        <Icon name={todo.icon} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-medium">{todo.title}</span>
        <span className="block text-sm text-muted">{todo.text}</span>
      </span>
    </>
  )
}
