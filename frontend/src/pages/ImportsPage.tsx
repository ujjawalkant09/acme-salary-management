import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type DragEvent } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Icon } from '@/components/icons'
import { importFileError, isOpen, isWorking, resultText, stepOf } from '@/features/imports/importState'
import { ErrorState, PageLoading, Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Table, TableWrap, Td, Th } from '@/components/ui/table'
import { api, API_BASE, newIdempotencyKey } from '@/lib/api'
import { useIsAdmin } from '@/lib/auth'
import { count, formatDate, plural } from '@/lib/format'
import { refreshData } from '@/lib/queryClient'
import type { ImportJob, ImportMode, ImportRow, Page } from '@/lib/types'
import { formData } from '@/lib/upload'
import { cn } from '@/lib/utils'

const STEPS = ['Upload', 'Check', 'Review', 'Apply', 'Done'] as const

export default function ImportsPage() {
  const isAdmin = useIsAdmin()
  const [historyPage, setHistoryPage] = useState(1)
  // The job this person is looking at. Falls back to any import still open, so leaving the
  // page and coming back picks up where it was.
  const [jobId, setJobId] = useState<string | null>(null)
  const history = useQuery({
    queryKey: ['imports', historyPage],
    queryFn: () => api<Page<ImportJob>>(`/imports?page=${historyPage}`),
    placeholderData: keepPreviousData,
  })
  const openJob = history.data?.items.find((job) => isOpen(job.status))
  const currentId = jobId ?? openJob?.id ?? null

  return (
    <div className="max-w-[64rem]">
      <p className="mb-5 text-muted">Add or update many people at once from a spreadsheet.</p>
      {isAdmin ? (
        // Until the history loads we don't know whether an import is already open.
        history.isPending ? (
          <PageLoading />
        ) : currentId ? (
          <CurrentImport jobId={currentId} onFinished={() => setJobId(null)} />
        ) : (
          <>
            <Steps step={1} />
            <UploadArea onStarted={setJobId} />
          </>
        )
      ) : (
        <div className="mb-5 rounded-lg bg-subtle px-4 py-3 text-muted">
          Only HR Admins can import files. You can see past imports below.
        </div>
      )}

      <h2 className="mt-7 mb-2.5 text-md font-semibold">Previous imports</h2>
      {history.isError ? (
        <ErrorState error={history.error} onRetry={history.refetch} />
      ) : !history.data ? (
        <PageLoading />
      ) : history.data.items.length === 0 ? (
        <p className="text-muted">No imports yet.</p>
      ) : (
        <>
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>File</Th>
                  <Th className="max-sm:hidden">Imported by</Th>
                  <Th>Date</Th>
                  <Th>Result</Th>
                </tr>
              </thead>
              <tbody>
                {history.data.items.map((job) => (
                  <tr key={job.id}>
                    <Td className="max-w-[15rem] truncate">{job.filename}</Td>
                    <Td className="max-sm:hidden">{job.created_by_name}</Td>
                    <Td className="text-muted">{formatDate(job.created_at)}</Td>
                    <Td className="whitespace-normal">{resultText(job)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
          {history.data.pages > 1 && (
            <div className="mt-3 flex items-center justify-end gap-2">
              <Button variant="outline" size="sm" disabled={historyPage <= 1} onClick={() => setHistoryPage(historyPage - 1)}>
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={historyPage >= history.data.pages}
                onClick={() => setHistoryPage(historyPage + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Steps({ step }: { step: number }) {
  return (
    <ol aria-label="Import steps" className="mb-6 flex list-none flex-wrap gap-1.5 p-0">
      {STEPS.map((name, i) => {
        const n = i + 1
        const done = n < step
        const current = n === step
        return (
          <li
            key={name}
            aria-current={current ? 'step' : undefined}
            className={cn(
              'flex items-center gap-2 text-sm font-medium text-muted',
              current && 'text-foreground',
              n < STEPS.length && 'after:mr-1 after:ml-1.5 after:h-px after:w-8 after:bg-border',
            )}
          >
            <span
              className={cn(
                'grid size-[1.375rem] place-items-center rounded-full border border-border text-xs',
                done && 'border-primary-soft bg-primary-soft text-primary',
                current && 'border-foreground bg-foreground text-white',
              )}
            >
              {done ? <Icon name="check" className="size-3" /> : n}
            </span>
            {name}
          </li>
        )
      })}
    </ol>
  )
}

function UploadArea({ onStarted }: { onStarted: (jobId: string) => void }) {
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const upload = useMutation({
    mutationFn: ({ file, idempotencyKey }: { file: File; idempotencyKey: string }) =>
      api<ImportJob>('/imports', { method: 'POST', body: formData(file), idempotencyKey }),
    onSuccess: (job) => {
      onStarted(job.id)
      return client.invalidateQueries({ queryKey: ['imports'] })
    },
  })

  function start(file: File | undefined) {
    if (!file) return
    const problem = importFileError(file)
    if (problem) toast.error(problem)
    else upload.mutate({ file, idempotencyKey: newIdempotencyKey() })
  }

  function drop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    start(event.dataTransfer.files[0])
  }

  return (
    <>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        className={cn(
          'rounded-xl border-[1.5px] border-dashed border-[#c9cbd3] px-6 py-11 text-center',
          dragging && 'border-primary bg-primary-soft',
        )}
      >
        <Icon name="upload" className="mx-auto size-6 text-muted" />
        <h2 className="mt-1.5 text-md font-semibold">Drop your Excel or CSV file here</h2>
        <p className="mt-1.5 mb-4 text-muted">.xlsx or .csv, up to 10 MB and 20,000 rows</p>
        <input
          ref={input}
          type="file"
          accept=".xlsx,.csv"
          className="hidden"
          aria-label="Choose a file to import"
          onChange={(e) => {
            start(e.target.files?.[0])
            e.target.value = ''
          }}
        />
        <div className="flex flex-wrap justify-center gap-2">
          <Button disabled={upload.isPending} onClick={() => input.current?.click()}>
            {upload.isPending && <Spinner />}
            Choose file
          </Button>
          <Button variant="ghost" asChild>
            <a href={`${API_BASE}/imports/template.xlsx`} download>
              Download template
            </a>
          </Button>
        </div>
      </div>
      <p className="mt-3 text-sm text-muted">
        People are matched by employee code: existing people are updated and new codes are added. No one is removed.
        If any row has a problem, nothing is saved unless you choose to save only the correct rows; the problem rows
        can be downloaded with the reason for each.
      </p>
    </>
  )
}

function CurrentImport({ jobId, onFinished }: { jobId: string; onFinished: () => void }) {
  const client = useQueryClient()
  const job = useQuery({
    queryKey: ['import', jobId],
    queryFn: () => api<ImportJob>(`/imports/${jobId}`),
    // Poll every second while the worker is busy with it.
    refetchInterval: (query) => (query.state.data && isWorking(query.state.data.status) ? 1000 : false),
  })
  const status = job.data?.status

  // When the job reaches a resting state, refresh the history (and, once applied, all employee data).
  const previous = useRef(status)
  useEffect(() => {
    const was = previous.current
    previous.current = status
    if (was === undefined || was === status || !status || isWorking(status)) return
    if (status === 'completed') {
      toast.success('Import saved')
      void refreshData(client)
    } else {
      void client.invalidateQueries({ queryKey: ['imports'] })
    }
  }, [status, client])

  if (job.isError) return <ErrorState error={job.error} onRetry={job.refetch} />
  if (!job.data) return <PageLoading />
  const j = job.data

  return (
    <>
      <Steps step={stepOf(j.status)} />
      <div className="rounded-xl border border-border p-5">
        {(j.status === 'queued' || j.status === 'validating') && (
          <Working title={`Checking ${j.filename}`} job={j} />
        )}
        {(j.status === 'commit_queued' || j.status === 'committing') && (
          <Working title={`Saving changes from ${j.filename}`} job={j} />
        )}
        {j.status === 'validated' && <Review job={j} onCancelled={onFinished} />}
        {j.status === 'completed' && (
          <>
            <h2 className="text-md font-semibold">Import finished</h2>
            <p className="my-3">
              {plural(j.created_count, 'person', 'people')} added and {plural(j.updated_count, 'person', 'people')}{' '}
              updated from {j.filename}.
              {j.mode === 'valid_rows_only' && j.error_count > 0 && ` ${plural(j.error_count, 'row', 'rows')} with problems were skipped.`}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <Link to="/people">Go to People</Link>
              </Button>
              <Button variant="outline" onClick={onFinished}>
                Import another file
              </Button>
            </div>
          </>
        )}
        {j.status === 'failed' && (
          <>
            <h2 className="text-md font-semibold">The import didn't finish</h2>
            <p className="my-3 text-error">{j.error_message ?? 'Something went wrong while reading the file.'}</p>
            <p className="mb-3 text-muted">Nothing was changed. Fix the file and upload it again.</p>
            <Button variant="outline" onClick={onFinished}>
              Import another file
            </Button>
          </>
        )}
        {j.status === 'cancelled' && (
          <>
            <h2 className="text-md font-semibold">Import cancelled</h2>
            <p className="my-3 text-muted">Nothing was changed.</p>
            <Button variant="outline" onClick={onFinished}>
              Import another file
            </Button>
          </>
        )}
      </div>
    </>
  )
}

function Working({ title, job }: { title: string; job: ImportJob }) {
  const pct = job.total_rows ? Math.round((job.processed_rows / job.total_rows) * 100) : 0
  return (
    <>
      <h2 className="text-md font-semibold">{title}</h2>
      <Progress value={pct} label={title} />
      <p className="text-sm text-muted">
        {job.total_rows
          ? `Row ${count(job.processed_rows)} of ${count(job.total_rows)}.`
          : 'Waiting to start.'}{' '}
        You can leave this page; the import keeps going.
      </p>
    </>
  )
}

function Review({ job, onCancelled }: { job: ImportJob; onCancelled: () => void }) {
  const client = useQueryClient()
  const [page, setPage] = useState(1)
  const [commitKey] = useState(newIdempotencyKey)
  const problems = useQuery({
    queryKey: ['import-rows', job.id, page],
    queryFn: () => api<Page<ImportRow>>(`/imports/${job.id}/rows?action=error&page=${page}`),
    enabled: job.error_count > 0,
    placeholderData: keepPreviousData,
  })
  const commit = useMutation({
    mutationFn: (mode: ImportMode) =>
      api<ImportJob>(`/imports/${job.id}/commit`, { method: 'POST', body: { mode }, idempotencyKey: commitKey }),
    onSuccess: (updated) => client.setQueryData(['import', job.id], updated),
  })
  const cancel = useMutation({
    mutationFn: () => api<ImportJob>(`/imports/${job.id}/cancel`, { method: 'POST' }),
    onSuccess: () => {
      toast.success('Import cancelled. Nothing was changed.')
      onCancelled()
      return client.invalidateQueries({ queryKey: ['imports'] })
    },
  })

  const changes = job.create_count + job.update_count
  const hasProblems = job.error_count > 0

  return (
    <>
      <h2 className="text-md font-semibold">Review {job.filename}</h2>
      {job.already_imported_at && (
        <p className="mt-2 rounded-md bg-amber-soft px-3 py-2 text-sm text-amber">
          This exact file was already imported on {formatDate(job.already_imported_at)}.
        </p>
      )}
      <div className="my-4 grid grid-cols-2 rounded-lg border border-border sm:grid-cols-4">
        <CountBox n={job.create_count} text="new people" />
        <CountBox n={job.update_count} text="changes" />
        <CountBox n={job.unchanged_count} text="no change" />
        <CountBox n={job.error_count} text="rows with problems" error />
      </div>

      {hasProblems ? (
        <>
          <p className="mb-3">Fix these rows in your file and upload it again, or save only the correct rows.</p>
          {problems.isError ? (
            <ErrorState error={problems.error} onRetry={problems.refetch} />
          ) : !problems.data ? (
            <PageLoading />
          ) : (
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Row</Th>
                    <Th>Employee code</Th>
                    <Th>Problem</Th>
                  </tr>
                </thead>
                <tbody>
                  {problems.data.items.map((row) => (
                    <tr key={row.row_number}>
                      <Td>{count(row.row_number)}</Td>
                      <Td>{row.employee_code ?? '–'}</Td>
                      <Td className="whitespace-normal text-error">
                        <ul className="space-y-0.5">
                          {row.errors.map((e, i) => (
                            <li key={i}>
                              {e.field}: {e.message}
                            </li>
                          ))}
                        </ul>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          )}
          {problems.data && problems.data.pages > 1 && (
            <div className="mt-3 flex items-center justify-end gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <span className="px-1.5 text-sm text-muted">
                Page {page} of {problems.data.pages}
              </span>
              <Button variant="outline" size="sm" disabled={page >= problems.data.pages} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </div>
          )}
        </>
      ) : (
        <p className="mb-3">{changes === 0 ? 'Nothing in this file changes anyone.' : 'Every row is correct.'}</p>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {hasProblems && (
          <Button variant="outline" asChild>
            <a href={`${API_BASE}/imports/${job.id}/errors.csv`} download>
              Download problem rows
            </a>
          </Button>
        )}
        <span className="flex-1" />
        <Button variant="ghost" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
          Cancel
        </Button>
        <Button
          disabled={commit.isPending || changes === 0}
          onClick={() => commit.mutate(hasProblems ? 'valid_rows_only' : 'all_or_nothing')}
        >
          {commit.isPending && <Spinner />}
          {hasProblems ? `Save ${plural(changes, 'correct row', 'correct rows')}` : `Save ${plural(changes, 'change', 'changes')}`}
        </Button>
      </div>
    </>
  )
}

function CountBox({ n, text, error = false }: { n: number; text: string; error?: boolean }) {
  return (
    <div className="border-border px-4 py-3.5 max-sm:nth-[-n+2]:border-b max-sm:odd:border-r sm:not-last:border-r">
      <b className={cn('block text-[1.375rem] font-semibold', error && n > 0 && 'text-error')}>{count(n)}</b>
      <span className="text-sm text-muted">{text}</span>
    </div>
  )
}
