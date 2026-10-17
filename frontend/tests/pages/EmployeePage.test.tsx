import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Employee } from '@/lib/types'

import { EMPLOYEE } from '@tests/support/fixtures'
import { ADMIN, type ApiRoutes, mockApi, renderApp, VIEWER } from '@tests/support/utils'

import EmployeePage from '@/pages/EmployeePage'

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

function show(user = ADMIN, extra: ApiRoutes = {}) {
  const fetchMock = mockApi({ ...routes, ...extra })
  renderApp(<EmployeePage />, { user, route: '/people/7', path: '/people/:id' })
  return { fetchMock, user: userEvent.setup() }
}

function showEmployee(changes: Partial<Employee>, extra: ApiRoutes = {}) {
  return show(ADMIN, { 'GET /employees/7': { ...EMPLOYEE, ...changes }, ...extra })
}

const sent = (fetchMock: ReturnType<typeof mockApi>, method: string) => fetchMock.mock.calls.filter(([, init]) => init?.method === method)

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

describe('Employee page details', () => {
  it('shows an upcoming salary, part-time share and the leaving date', async () => {
    showEmployee({
      upcoming_salary: { amount: '2000000.00', currency: 'INR', effective_date: '2026-12-01' },
      employment_type: 'part_time',
      fte: '0.500',
      status: 'left',
      left_on: '2026-09-30',
      gender: 'female',
      city: null,
    })
    expect(await screen.findByText(/₹20,00,000 from 1 Dec 2026/)).toBeInTheDocument()
    expect(screen.getByText('Part-time, 50%')).toBeInTheDocument()
    expect(screen.getByText('30 Sept 2026')).toBeInTheDocument()
    expect(screen.getByText('Female')).toBeInTheDocument()
    expect(screen.getByText('India')).toBeInTheDocument() // no city
  })

  it('says when there are too few peers to compare with', async () => {
    showEmployee({ peers: null })
    expect(await screen.findByText(/Not enough people in the same role, level and country/)).toBeInTheDocument()
  })

  it('USD salaries are not converted again', async () => {
    showEmployee({ current_currency: 'USD', current_salary: '64500.00', current_salary_usd: '64500.00', peers: null })
    expect(await screen.findByTestId('current-salary')).toHaveTextContent('$64,500')
    expect(screen.queryByText(/≈/)).toBeNull()
  })

  it('shows a history load error with a retry', async () => {
    show(ADMIN, { 'GET /employees/7/salaries': () => ({ status: 500, body: { error: { message: 'History is down' } } }) })
    expect(await screen.findByText('History is down')).toBeInTheDocument()
  })

  it('a non-numeric id is a not-found, without asking the server', async () => {
    const fetchMock = mockApi(routes)
    renderApp(<EmployeePage />, { route: '/people/abc', path: '/people/:id' })
    expect(screen.getByText(/This employee was not found/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/employees/'))).toBe(false)
  })
})

describe('Employee page actions', () => {
  it.each([
    ['Change salary', 'Change salary'],
    ['Edit details', 'Edit details'],
    ['Mark as left', 'Mark Asha Verma as left?'],
  ])('%s opens its dialog and Cancel closes it', async (button, title) => {
    const { user } = show()
    await user.click(await screen.findByRole('button', { name: button }))
    expect(screen.getByRole('dialog')).toHaveAccessibleName(title)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('someone who left can be made a current employee again', async () => {
    const { fetchMock, user } = showEmployee(
      { status: 'left', left_on: '2026-09-30' },
      { 'POST /employees/7/reactivate': EMPLOYEE },
    )
    expect(await screen.findByText('Left the company')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change salary' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Mark as current employee' }))
    await vi.waitFor(() => expect(sent(fetchMock, 'POST')).toHaveLength(1))
    expect(JSON.parse(sent(fetchMock, 'POST')[0][1]!.body as string)).toEqual({ version: 4 })
  })

  it('uploads a photo', async () => {
    const { fetchMock, user } = show(ADMIN, { 'PUT /employees/7/photo': { photo_url: '/api/v1/files/t' } })
    await screen.findByRole('button', { name: 'Upload photo' })
    await user.upload(screen.getByLabelText('Choose a photo'), new File(['png'], 'me.png', { type: 'image/png' }))
    await vi.waitFor(() => expect(sent(fetchMock, 'PUT')).toHaveLength(1))
  })

  it('the photo button opens the file picker', async () => {
    const { user } = show()
    const button = await screen.findByRole('button', { name: 'Upload photo' })
    const picker = vi.spyOn(screen.getByLabelText('Choose a photo'), 'click')
    await user.click(button)
    expect(picker).toHaveBeenCalledOnce()
  })

  it('refuses a photo that is not an image', async () => {
    const { fetchMock } = show()
    await screen.findByRole('button', { name: 'Upload photo' })
    const noAccept = userEvent.setup({ applyAccept: false })
    await noAccept.upload(screen.getByLabelText('Choose a photo'), new File(['%PDF'], 'me.pdf', { type: 'application/pdf' }))
    expect(sent(fetchMock, 'PUT')).toHaveLength(0)
  })

  it('removes a photo after confirming', async () => {
    const { fetchMock, user } = showEmployee({ photo_url: '/api/v1/files/t' }, { 'DELETE /employees/7/photo': () => ({ status: 204 }) })
    expect(await screen.findByRole('button', { name: 'Change photo' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove photo' }))
    await user.click(screen.getAllByRole('button', { name: 'Remove photo' }).at(-1)!)
    await vi.waitFor(() => expect(sent(fetchMock, 'DELETE')).toHaveLength(1))
  })
})
