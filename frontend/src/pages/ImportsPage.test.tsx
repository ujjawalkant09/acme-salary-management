import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ImportJob } from '@/lib/types'
import { mockApi, renderApp, VIEWER } from '@/test/utils'

import ImportsPage from './ImportsPage'

afterEach(() => vi.unstubAllGlobals())

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
    expect(await screen.findByText('This email is already used.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save 12 correct rows' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download problem rows' })).toHaveAttribute('href', '/api/v1/imports/job-1/errors.csv')
  })

  it('tells HR Viewers that only Admins can import', async () => {
    mockApi({ 'GET /imports': page([{ ...job, status: 'completed', created_count: 2, updated_count: 10 }]) })
    renderApp(<ImportsPage />, { user: VIEWER })
    expect(await screen.findByText(/Only HR Admins can import files/)).toBeInTheDocument()
    expect(screen.queryByText('Drop your Excel or CSV file here')).toBeNull()
    expect(await screen.findByText('10 updated, 2 added')).toBeInTheDocument()
  })
})
