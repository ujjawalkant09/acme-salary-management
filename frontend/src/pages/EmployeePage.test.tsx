import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EMPLOYEE } from '@/test/fixtures'
import { ADMIN, mockApi, renderApp, VIEWER } from '@/test/utils'

import EmployeePage from './EmployeePage'

afterEach(() => vi.unstubAllGlobals())

const routes = {
  'GET /employees/7': EMPLOYEE,
  'GET /employees/7/salaries': [
    {
      id: 2, amount: '1840000.00', currency: 'INR', effective_date: '2026-04-01', reason: 'merit', note: null,
      change_pct: '8.24', created_by_name: 'Priya Sharma', created_at: '2026-04-01T09:00:00Z', from_import: false, is_future: false,
    },
    {
      id: 1, amount: '1700000.00', currency: 'INR', effective_date: '2022-04-01', reason: 'hire', note: null,
      change_pct: null, created_by_name: null, created_at: '2022-04-01T09:00:00Z', from_import: true, is_future: false,
    },
  ],
  'GET /employees/7/documents': [],
}

function show(user = ADMIN) {
  mockApi(routes)
  return renderApp(<EmployeePage />, { user, route: '/people/7', path: '/people/:id' })
}

describe('Employee page', () => {
  it('shows salary in local currency and USD, position among peers and history', async () => {
    show()
    expect(await screen.findByRole('heading', { name: 'Asha Verma' })).toBeInTheDocument()
    expect(screen.getAllByText('₹18,40,000').length).toBeGreaterThan(0)
    expect(screen.getByText('≈ $22,080')).toBeInTheDocument()
    expect(screen.getByText('Paid 8% more than the middle of this group.')).toBeInTheDocument()
    expect(await screen.findByText('+8.2%')).toBeInTheDocument()
    expect(screen.getByText('Import')).toBeInTheDocument()
  })

  it('gives HR Admins the actions', async () => {
    show(ADMIN)
    await screen.findByRole('heading', { name: 'Asha Verma' })
    for (const name of ['Change salary', 'Edit details', 'Mark as left', 'Upload', 'Upload photo']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('hides every change for HR Viewers', async () => {
    show(VIEWER)
    await screen.findByRole('heading', { name: 'Asha Verma' })
    for (const name of ['Change salary', 'Edit details', 'Mark as left', 'Upload', 'Upload photo']) {
      expect(screen.queryByRole('button', { name })).toBeNull()
    }
    expect(await screen.findByText(/Only HR Admins can upload or remove documents/)).toBeInTheDocument()
  })

  it('says so when the employee does not exist', async () => {
    mockApi({})
    renderApp(<EmployeePage />, { route: '/people/999', path: '/people/:id' })
    expect(await screen.findByText(/This employee was not found/)).toBeInTheDocument()
  })
})
