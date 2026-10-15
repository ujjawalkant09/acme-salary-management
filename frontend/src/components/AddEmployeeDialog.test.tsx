import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EMPLOYEE } from '@/test/fixtures'
import { type ApiRoutes, mockApi, renderApp } from '@/test/utils'

import { AddEmployeeDialog } from './AddEmployeeDialog'

afterEach(() => vi.unstubAllGlobals())

async function open(routes: ApiRoutes = {}) {
  const fetchMock = mockApi(routes)
  renderApp(<AddEmployeeDialog />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Add employee' }))
  return { fetchMock, user }
}

async function fillIn(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('First name'), ' Asha ')
  await user.type(screen.getByLabelText('Last name'), 'Verma')
  await user.type(screen.getByLabelText('Work email'), 'asha.verma@acme.example')
  await user.type(screen.getByLabelText('Job title'), 'Software Engineer')
  await user.selectOptions(screen.getByLabelText('Level'), '3')
  await user.selectOptions(screen.getByLabelText('Department'), '1')
  await user.selectOptions(screen.getByLabelText('Country'), 'IN')
  await user.type(screen.getByLabelText('Joined on'), '2026-11-01')
  await user.type(screen.getByLabelText('Yearly salary (INR)'), '1840000')
}

describe('Add employee', () => {
  it('explains every missing field instead of sending', async () => {
    const { fetchMock, user } = await open()
    await user.click(screen.getAllByRole('button', { name: 'Add employee' }).at(-1)!)
    for (const message of ['Enter the first name.', 'Choose a country.', 'Choose the date they joined.', 'Enter the yearly salary.']) {
      expect(screen.getByText(message)).toBeInTheDocument()
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('asks for the share of full time only for part-time', async () => {
    const { user } = await open()
    expect(screen.queryByLabelText('Share of full time')).toBeNull()
    await user.selectOptions(screen.getByLabelText('Employment type'), 'part_time')
    expect(screen.getByLabelText('Share of full time')).toBeInTheDocument()
  })

  it("creates the employee in the country's currency with one idempotency key, then opens them", async () => {
    const { fetchMock, user } = await open({ 'POST /employees': () => ({ status: 201, body: { ...EMPLOYEE, id: 42 } }) })
    await fillIn(user)
    await user.click(screen.getAllByRole('button', { name: 'Add employee' }).at(-1)!)

    await vi.waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/people/42'))
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    expect((init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
    expect(JSON.parse(init!.body as string)).toMatchObject({
      first_name: 'Asha',
      email: 'asha.verma@acme.example',
      job_level: 3,
      department_id: 1,
      country_code: 'IN',
      fte: '1',
      salary: { amount: '1840000', currency: 'INR' },
    })
  })

  it("shows the server's field errors next to the fields", async () => {
    const { user } = await open({
      'POST /employees': () => ({
        status: 422,
        body: { error: { code: 'invalid', message: 'Some fields are not valid.', details: { fields: { email: 'Already used by another employee' } } } },
      }),
    })
    await fillIn(user)
    await user.click(screen.getAllByRole('button', { name: 'Add employee' }).at(-1)!)
    expect(await screen.findByText('Already used by another employee')).toBeInTheDocument()
  })
})
