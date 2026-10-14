import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { useRef, useState, type ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { toast } from 'sonner'

import { Avatar } from '@/components/Avatar'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Icon } from '@/components/icons'
import { PayBand } from '@/components/PayBand'
import { ErrorState, PageLoading, Spinner } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, Td, Th } from '@/components/ui/table'
import { ChangeSalaryDialog } from '@/features/employee/ChangeSalaryDialog'
import { DocumentsSection } from '@/features/employee/DocumentsSection'
import { EditEmployeeDialog } from '@/features/employee/EditEmployeeDialog'
import { MarkLeftDialog } from '@/features/employee/MarkLeftDialog'
import { api, ApiError } from '@/lib/api'
import { useIsAdmin } from '@/lib/auth'
import { formatDate, label, money, signedPct, usd } from '@/lib/format'
import { countryName, useMeta } from '@/lib/meta'
import { refreshData } from '@/lib/queryClient'
import { peerSentence } from '@/lib/salary'
import type { Employee, PeerStats, SalaryRecord } from '@/lib/types'
import { fileError, formData, PHOTO_ACCEPT } from '@/lib/upload'
import { cn } from '@/lib/utils'

type DialogName = 'salary' | 'edit' | 'left' | null

export default function EmployeePage() {
  const { id } = useParams()
  const location = useLocation()
  const isAdmin = useIsAdmin()
  const meta = useMeta()
  const [dialog, setDialog] = useState<DialogName>(null)
  const employeeId = Number(id)

  // The profile and the history load in parallel.
  const employee = useQuery({
    queryKey: ['employee', employeeId],
    queryFn: () => api<Employee>(`/employees/${employeeId}`),
    enabled: Number.isInteger(employeeId),
  })
  const history = useQuery({
    queryKey: ['salaries', employeeId],
    queryFn: () => api<SalaryRecord[]>(`/employees/${employeeId}/salaries`),
    enabled: Number.isInteger(employeeId),
  })

  const from = (location.state as { from?: string } | null)?.from ?? ''
  const back = (
    <Link to={`/people${from}`} className="mb-4 inline-flex items-center gap-1.5 font-medium text-muted hover:text-foreground">
      <Icon name="chevronLeft" />
      Back to People
    </Link>
  )

  if (!Number.isInteger(employeeId) || (employee.error instanceof ApiError && employee.error.status === 404)) {
    return (
      <>
        {back}
        <ErrorState error={new ApiError(404, 'not_found', 'This employee was not found. They may have been removed from the link you used.')} />
      </>
    )
  }
  if (employee.isError) return <ErrorState error={employee.error} onRetry={employee.refetch} />
  if (employee.isPending || meta.isPending) return <PageLoading />
  if (meta.isError) return <ErrorState error={meta.error} onRetry={meta.refetch} />

  const e = employee.data
  const left = e.status === 'left'

  return (
    <>
      {back}
      <div className="mb-6 flex flex-wrap items-center gap-4">
        {e.photo_url ? (
          <img src={e.photo_url} alt="" className="size-12 rounded-full border border-border object-cover" />
        ) : (
          <Avatar first={e.first_name} last={e.last_name} className="size-12 text-base" />
        )}
        <div className="min-w-0">
          <h1 className="text-[1.375rem] font-semibold tracking-tight">
            {e.first_name} {e.last_name}
          </h1>
          <div className="text-muted">
            {e.job_title}, level {e.job_level}, {e.department} {left && <Badge className="ml-1">Left the company</Badge>}
          </div>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap gap-2 md:ml-auto">
            {!left && <Button onClick={() => setDialog('salary')}>Change salary</Button>}
            <Button variant="outline" onClick={() => setDialog('edit')}>
              Edit details
            </Button>
            {left ? <ReactivateButton employee={e} /> : (
              <Button variant="dangerOutline" onClick={() => setDialog('left')}>
                Mark as left
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <div className="flex min-w-0 flex-col gap-6">
          <SalaryCard employee={e} />
          <HistorySection query={history} />
          <DocumentsSection employeeId={e.id} isAdmin={isAdmin} />
        </div>
        <DetailsCard employee={e} countryLabel={countryName(meta.data, e.country_code)} isAdmin={isAdmin} />
      </div>

      {isAdmin && (
        <>
          <ChangeSalaryDialog employee={e} open={dialog === 'salary'} onOpenChange={(o) => setDialog(o ? 'salary' : null)} />
          <EditEmployeeDialog employee={e} meta={meta.data} open={dialog === 'edit'} onOpenChange={(o) => setDialog(o ? 'edit' : null)} />
          {!left && <MarkLeftDialog employee={e} open={dialog === 'left'} onOpenChange={(o) => setDialog(o ? 'left' : null)} />}
        </>
      )}
    </>
  )
}

function Section({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn('rounded-xl border border-border', className)}>
      <div className="flex min-h-[3.375rem] items-center border-b border-border px-5 py-3.5">
        <h2 className="text-md font-semibold">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function SalaryCard({ employee: e }: { employee: Employee }) {
  const local = e.current_currency
  return (
    <Section title="Yearly salary">
      <div className="px-5 py-4.5">
        <div className="text-3xl leading-tight font-semibold tracking-tight">
          <span data-testid="current-salary">{money(e.current_salary, local)}</span>
          {local !== 'USD' && <small className="ml-2 text-base font-normal tracking-normal text-muted">≈ {usd(e.current_salary_usd)}</small>}
        </div>
        <p className="mt-1.5 text-sm text-muted">
          Since {formatDate(e.salary_effective_date)}
          {local !== 'USD' && e.rates_date && `. USD at European Central Bank rates of ${formatDate(e.rates_date)}`}.
        </p>
        {e.upcoming_salary && (
          <p className="mt-2.5 text-sm">
            <Badge variant="blue">Upcoming</Badge> {money(e.upcoming_salary.amount, e.upcoming_salary.currency)} from{' '}
            {formatDate(e.upcoming_salary.effective_date)}
          </p>
        )}
        {e.peers ? <PeerComparison peers={e.peers} /> : (
          <p className="mt-5 text-sm text-muted">Not enough people in the same role, level and country to compare with.</p>
        )}
      </div>
    </Section>
  )
}

function PeerComparison({ peers }: { peers: PeerStats }) {
  const c = peers.currency
  return (
    <div className="mt-5.5">
      <p className="mb-1.5 text-sm text-muted">
        Compared with {peers.count} people in the same role, level and country (full-time pay)
      </p>
      <PayBand
        stats={peers}
        value={peers.employee_value}
        outlier={peers.is_outlier}
        width={520}
        label={`Pay range ${money(peers.min, c)} to ${money(peers.max, c)}, median ${money(peers.median, c)}, this person ${money(peers.employee_value, c)}`}
      />
      <div className="mt-1 flex max-w-[32.5rem] justify-between text-xs text-muted">
        <span>{money(peers.min, c)}</span>
        <span>median {money(peers.median, c)}</span>
        <span>{money(peers.max, c)}</span>
      </div>
      <p className={cn('mt-2.5 font-medium', peers.is_outlier && 'text-amber')}>{peerSentence(peers)}</p>
    </div>
  )
}

function HistorySection({ query }: { query: UseQueryResult<SalaryRecord[]> }) {
  return (
    <Section title="Salary history">
      {query.isError ? (
        <div className="p-4">
          <ErrorState error={query.error} onRetry={query.refetch} />
        </div>
      ) : query.isPending ? (
        <p className="px-5 py-4.5 text-muted">Loading history…</p>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <thead>
              <tr>
                <Th>Starts on</Th>
                <Th className="text-right">Yearly salary</Th>
                <Th className="text-right">Change</Th>
                <Th>Reason</Th>
                <Th className="max-sm:hidden">Changed by</Th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((r) => (
                <tr key={r.id}>
                  <Td>{formatDate(r.effective_date)}</Td>
                  <Td className="text-right">{money(r.amount, r.currency)}</Td>
                  <Td className="text-right">
                    {r.change_pct === null ? (
                      <span className="text-muted">–</span>
                    ) : (
                      <span className={Number(r.change_pct) >= 0 ? 'text-sm font-medium text-green' : 'text-muted'}>
                        {signedPct(r.change_pct)}
                      </span>
                    )}
                  </Td>
                  <Td>
                    <Badge variant={r.is_future ? 'blue' : 'default'} title={r.note ?? undefined}>
                      {r.is_future ? 'Upcoming' : label(r.reason)}
                    </Badge>
                  </Td>
                  <Td className="text-muted max-sm:hidden">
                    {r.created_by_name ?? (r.from_import ? 'Import' : '')}
                    {r.created_by_name && r.from_import && ' (import)'}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </Section>
  )
}

function DetailsCard({ employee: e, countryLabel, isAdmin }: { employee: Employee; countryLabel: string; isAdmin: boolean }) {
  const rows: [string, ReactNode][] = [
    ['Employee code', e.employee_code],
    ['Email', <span key="email" className="break-all">{e.email}</span>],
    ['Department', e.department],
    ['Location', e.city ? `${e.city}, ${countryLabel}` : countryLabel],
    ['Type', e.employment_type === 'part_time' ? `${label(e.employment_type)}, ${Math.round(Number(e.fte) * 100)}%` : label(e.employment_type)],
    ['Joined', formatDate(e.hire_date)],
    ...(e.left_on ? ([['Left', formatDate(e.left_on)]] as [string, ReactNode][]) : []),
    ['Gender', e.gender ? label(e.gender) : <span key="gender" className="text-muted">Not recorded</span>],
    ['Currency', e.current_currency],
  ]
  return (
    <Section title="Details">
      <div className="px-5 py-4.5">
        <dl className="m-0 grid grid-cols-[6.875rem_1fr] gap-x-3 gap-y-1.5">
          {rows.map(([term, value]) => (
            <div key={term} className="contents">
              <dt className="text-muted">{term}</dt>
              <dd className="m-0">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3.5 text-sm text-muted">Gender is shown only here. It is not used in lists, exports or Insights.</p>
        {e.updated_by_name && (
          <p className="mt-2 text-sm text-muted">
            Last changed by {e.updated_by_name} on {formatDate(e.updated_at)}.
          </p>
        )}
        {isAdmin && <PhotoControls employee={e} />}
      </div>
    </Section>
  )
}

function PhotoControls({ employee: e }: { employee: Employee }) {
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const upload = useMutation({
    mutationFn: (file: File) => api<{ photo_url: string }>(`/employees/${e.id}/photo`, { method: 'PUT', body: formData(file) }),
    onSuccess: () => {
      toast.success('Photo updated')
      return refreshData(client)
    },
  })
  const remove = useMutation({
    mutationFn: () => api<void>(`/employees/${e.id}/photo`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Photo removed')
      setConfirmRemove(false)
      return refreshData(client)
    },
  })

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4">
      <input
        ref={input}
        type="file"
        accept={PHOTO_ACCEPT}
        className="hidden"
        aria-label="Choose a photo"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (!file) return
          const problem = fileError(file, 'photo')
          if (problem) toast.error(problem)
          else upload.mutate(file)
        }}
      />
      <Button variant="outline" size="sm" disabled={upload.isPending} onClick={() => input.current?.click()}>
        {upload.isPending && <Spinner />}
        {e.photo_url ? 'Change photo' : 'Upload photo'}
      </Button>
      {e.photo_url && (
        <Button variant="ghost" size="sm" className="text-error hover:text-error" onClick={() => setConfirmRemove(true)}>
          Remove photo
        </Button>
      )}
      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title="Remove this photo?"
        description="Their initials are shown instead."
        action="Remove photo"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  )
}

function ReactivateButton({ employee: e }: { employee: Employee }) {
  const client = useQueryClient()
  const reactivate = useMutation({
    mutationFn: () => api<Employee>(`/employees/${e.id}/reactivate`, { method: 'POST', body: { version: e.version } }),
    onSuccess: () => {
      toast.success(`${e.first_name} ${e.last_name} is a current employee again`)
      return refreshData(client)
    },
  })
  return (
    <Button variant="outline" disabled={reactivate.isPending} onClick={() => reactivate.mutate()}>
      {reactivate.isPending && <Spinner />}
      Mark as current employee
    </Button>
  )
}
