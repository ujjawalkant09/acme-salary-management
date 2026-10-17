import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ImportJob } from '@/lib/types'
import { type ApiRoutes, mockApi, renderApp, VIEWER } from '@tests/support/utils'

import ImportsPage from '@/pages/ImportsPage'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const job: ImportJob = {
  id: 'job-1', filename: 'salary-review.xlsx', status: 'validated', mode: 'all_or_nothing',
  total_rows: 100, processed_rows: 100, create_count: 2, update_count: 10, unchanged_count: 85, error_count: 3,
  created_count: 0, updated_count: 0, error_message: null, created_by_name: 'Priya Sharma',
  created_at: '2026-10-14T09:00:00Z', started_at: null, finished_at: null, already_imported_at: null,
}
const page = (items: ImportJob[]) => ({ items, page: 1, page_size: 20, total: items.length, pages: 1 })

describe('Imports', () => {
  it('starts with the upload step and a template link when nothing is open', async () => {
    mockApi({ 'GET /imports': page([]) })
    renderApp(<ImportsPage />)
    expect(await screen.findByText('Drop your Excel or CSV file here')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download template' })).toHaveAttribute('href', '/api/v1/imports/template.xlsx')
    expect(screen.getByText('No imports yet.')).toBeInTheDocument()
  })

  it('picks up an import waiting for review, with its problem rows', async () => {
    mockApi({
      'GET /imports': page([job]),
      'GET /imports/job-1': job,
      'GET /imports/job-1/rows': {
        ...page([]),
        items: [{ row_number: 18, employee_code: 'ACM-004211', action: 'error', payload: {}, errors: [{ field: 'email', message: 'This email is already used.' }] }],
      },
    })
    renderApp(<ImportsPage />)
    expect(await screen.findByText('Review salary-review.xlsx')).toBeInTheDocument()
    expect(await screen.findByText('email: This email is already used.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save 12 correct rows' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download problem rows' })).toHaveAttribute('href', '/api/v1/imports/job-1/errors.csv')
  })

  it('lists each problem in a row on its own line with its column', async () => {
    mockApi({
      'GET /imports': page([job]),
      'GET /imports/job-1': job,
      'GET /imports/job-1/rows': {
        ...page([]),
        items: [{
          row_number: 31,
          employee_code: 'ACM-020210',
          action: 'error',
          payload: {},
          errors: [
            { field: 'salary_effective_date', message: 'Before the hire date' },
            { field: 'hire_date', message: 'More than a year ahead' },
          ],
        }],
      },
    })
    renderApp(<ImportsPage />)
    const first = await screen.findByText('salary_effective_date: Before the hire date')
    const problems = within(first.closest('ul')!).getAllByRole('listitem')
    expect(problems.map((li) => li.textContent)).toEqual([
      'salary_effective_date: Before the hire date',
      'hire_date: More than a year ahead',
    ])
  })

  it('tells HR Viewers that only Admins can import', async () => {
    mockApi({ 'GET /imports': page([{ ...job, status: 'completed', created_count: 2, updated_count: 10 }]) })
    renderApp(<ImportsPage />, { user: VIEWER })
    expect(await screen.findByText(/Only HR Admins can import files/)).toBeInTheDocument()
    expect(screen.queryByText('Drop your Excel or CSV file here')).toBeNull()
    expect(await screen.findByText('10 updated, 2 added')).toBeInTheDocument()
  })
})

const at = (status: ImportJob['status'], extra: Partial<ImportJob> = {}): ImportJob => ({ ...job, status, ...extra })
const csv = () => new File(['employee_code\nACM-1'], 'people.csv', { type: 'text/csv' })
const sent = (fetchMock: ReturnType<typeof mockApi>, path: string) =>
  fetchMock.mock.calls.filter(([url, init]) => init?.method === 'POST' && String(url).endsWith(path))
const POLL = { timeout: 3000 } // the page polls every second while the worker is busy

function show(routes: ApiRoutes) {
  const fetchMock = mockApi(routes)
  renderApp(<ImportsPage />)
  return { fetchMock, user: userEvent.setup({ applyAccept: false }) }
}

describe('Starting an import', () => {
  it('uploads a chosen file with an idempotency key and shows the check starting', async () => {
    const { fetchMock, user } = show({
      'GET /imports': page([]),
      'POST /imports': () => ({ status: 202, body: at('queued', { filename: 'people.csv', total_rows: 0 }) }),
      'GET /imports/job-1': at('queued', { filename: 'people.csv', total_rows: 0 }),
    })
    await user.upload(await screen.findByLabelText('Choose a file to import'), csv())
    expect(await screen.findByRole('heading', { name: 'Checking people.csv' })).toBeInTheDocument()
    expect(screen.getByText(/Waiting to start\./)).toBeInTheDocument()
    const [, init] = sent(fetchMock, '/imports')[0]
    expect((init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
  })

  it('takes a dropped file too', async () => {
    const { fetchMock } = show({
      'GET /imports': page([]),
      'POST /imports': () => ({ status: 202, body: at('queued') }),
      'GET /imports/job-1': at('queued'),
    })
    const area = (await screen.findByText('Drop your Excel or CSV file here')).parentElement!
    fireEvent.dragOver(area)
    fireEvent.drop(area, { dataTransfer: { files: [csv()] } })
    await vi.waitFor(() => expect(sent(fetchMock, '/imports')).toHaveLength(1))
  })

  it('refuses files that are not .xlsx or .csv before uploading', async () => {
    const error = vi.spyOn(toast, 'error')
    const { fetchMock, user } = show({ 'GET /imports': page([]) })
    await user.upload(await screen.findByLabelText('Choose a file to import'), new File(['x'], 'macros.xlsm'))
    expect(error).toHaveBeenCalledWith('Choose an Excel (.xlsx) or CSV file.')
    expect(sent(fetchMock, '/imports')).toHaveLength(0)
  })
})

describe('An open import', () => {
  it('shows progress while checking, then the review when done', async () => {
    let polls = 0
    show({
      'GET /imports': page([at('validating')]),
      'GET /imports/job-1': () => ({ body: ++polls === 1 ? at('validating', { processed_rows: 40 }) : at('validated', { error_count: 0 }) }),
    })
    expect(await screen.findByText(/Row 40 of 100\./)).toBeInTheDocument()
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Check')
    expect(await screen.findByText('Every row is correct.', {}, POLL)).toBeInTheDocument()
  })

  it('saves every change when there are no problems, then reports the result', async () => {
    let applied = false
    const { fetchMock, user } = show({
      'GET /imports': page([at('validated', { error_count: 0 })]),
      'GET /imports/job-1': () => ({ body: applied ? at('completed', { created_count: 2, updated_count: 10 }) : at('validated', { error_count: 0 }) }),
      'POST /imports/job-1/commit': () => {
        applied = true
        return { body: at('commit_queued', { error_count: 0 }) }
      },
    })
    await user.click(await screen.findByRole('button', { name: 'Save 12 changes' }))
    expect(await screen.findByRole('heading', { name: 'Saving changes from salary-review.xlsx' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Import finished' }, POLL)).toBeInTheDocument()
    expect(screen.getByText(/2 people added and 10 people updated from salary-review.xlsx\./)).toBeInTheDocument()

    const [, init] = sent(fetchMock, '/commit')[0]
    expect(JSON.parse(init!.body as string)).toEqual({ mode: 'all_or_nothing' })
    expect((init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
  })

  it('with problems, saves only the correct rows and says how many were skipped', async () => {
    let applied = false
    const { fetchMock, user } = show({
      'GET /imports': page([job]),
      'GET /imports/job-1': () => ({ body: applied ? at('completed', { mode: 'valid_rows_only', created_count: 2, updated_count: 10 }) : job }),
      'GET /imports/job-1/rows': page([]),
      'POST /imports/job-1/commit': () => {
        applied = true
        return { body: at('commit_queued') }
      },
    })
    await user.click(await screen.findByRole('button', { name: 'Save 12 correct rows' }))
    expect(await screen.findByText(/3 rows with problems were skipped\./, {}, POLL)).toBeInTheDocument()
    expect(JSON.parse(sent(fetchMock, '/commit')[0][1]!.body as string)).toEqual({ mode: 'valid_rows_only' })
  })

  it('cannot be saved when nothing changes, and warns about a repeated file', async () => {
    const quiet = at('validated', { create_count: 0, update_count: 0, error_count: 0, already_imported_at: '2026-10-01T09:00:00Z' })
    show({ 'GET /imports': page([quiet]), 'GET /imports/job-1': quiet })
    expect(await screen.findByText('Nothing in this file changes anyone.')).toBeInTheDocument()
    expect(screen.getByText('This exact file was already imported on 1 Oct 2026.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save 0 changes' })).toBeDisabled()
  })

  it('can be cancelled, which goes back to the upload step', async () => {
    let cancelled = false
    const { fetchMock, user } = show({
      'GET /imports': () => ({ body: page([cancelled ? at('cancelled') : job]) }),
      'GET /imports/job-1': job,
      'GET /imports/job-1/rows': page([]),
      'POST /imports/job-1/cancel': () => {
        cancelled = true
        return { body: at('cancelled') }
      },
    })
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(await screen.findByText('Drop your Excel or CSV file here')).toBeInTheDocument()
    expect(sent(fetchMock, '/cancel')).toHaveLength(1)
    expect(await screen.findByText('Cancelled, nothing changed')).toBeInTheDocument()
  })

  it.each([
    ['failed', { error_message: 'Missing columns: salary.' }, "The import didn't finish", 'Missing columns: salary.'],
    ['failed', { error_message: null }, "The import didn't finish", 'Something went wrong while reading the file.'],
    ['cancelled', {}, 'Import cancelled', 'Nothing was changed.'],
  ] as const)('ending as %s explains what happened', async (status, extra, heading, text) => {
    let polls = 0
    show({
      'GET /imports': page([at('validating')]),
      'GET /imports/job-1': () => ({ body: ++polls === 1 ? at('validating') : at(status, extra) }),
    })
    expect(await screen.findByRole('heading', { name: heading }, POLL)).toBeInTheDocument()
    expect(screen.getByText(text)).toBeInTheDocument()
  })

  it('pages through the problem rows', async () => {
    show({
      'GET /imports': page([job]),
      'GET /imports/job-1': job,
      'GET /imports/job-1/rows': (url: URL) => ({
        body: {
          items: [{ row_number: Number(url.searchParams.get('page')) * 100, employee_code: null, action: 'error', payload: {}, errors: [{ field: 'salary', message: 'Must be a number' }] }],
          page: Number(url.searchParams.get('page')), page_size: 20, total: 30, pages: 2,
        },
      }),
    })
    expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument()
    expect(screen.getByText('–')).toBeInTheDocument() // no employee code
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('200')).toBeInTheDocument()
  })

  it('shows load errors with a retry', async () => {
    show({
      'GET /imports': page([job]),
      'GET /imports/job-1': () => ({ status: 500, body: { error: { message: 'Import is unavailable' } } }),
    })
    expect(await screen.findByText('Import is unavailable')).toBeInTheDocument()
  })
})

describe('Previous imports', () => {
  it('pages through the history', async () => {
    const { fetchMock, user } = show({
      'GET /imports': (url: URL) => ({
        body: { items: [at('completed', { id: `j${url.searchParams.get('page')}` })], page: 1, page_size: 10, total: 15, pages: 2 },
      }),
    })
    const next = await screen.findByRole('button', { name: 'Next' })
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(next)
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/imports?page=2'))).toBe(true))
  })

  it('shows a load error with a retry', async () => {
    show({ 'GET /imports': () => ({ status: 500, body: { error: { message: 'History is down' } } }) })
    expect(await screen.findByText('History is down')).toBeInTheDocument()
  })
})
