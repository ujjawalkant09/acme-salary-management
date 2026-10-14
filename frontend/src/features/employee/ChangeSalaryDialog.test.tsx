import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EMPLOYEE } from '@/test/fixtures'
import { mockApi, renderApp } from '@/test/utils'

import { ChangeSalaryDialog } from './ChangeSalaryDialog'

afterEach(() => vi.unstubAllGlobals())

function setup() {
  const onOpenChange = vi.fn()
  renderApp(<ChangeSalaryDialog employee={EMPLOYEE} open onOpenChange={onOpenChange} />)
  return { user: userEvent.setup(), onOpenChange }
}

describe('Change salary', () => {
  it('shows the change live as you type', async () => {
    mockApi({})
    const { user } = setup()
    const amount = screen.getByLabelText('New yearly salary (INR)')
    await user.clear(amount)
    await user.type(amount, '2000000')
    expect(screen.getByText('+8.7%, ₹1,60,000 more a year')).toBeInTheDocument()

    await user.clear(amount)
    await user.type(amount, '3000000')
    expect(screen.getByText(/\+63\.0%.*That's a big change, so please double-check it\./)).toBeInTheDocument()
  })

  it('explains what is missing instead of sending', async () => {
    const fetchMock = mockApi({})
    const { user } = setup()
    await user.clear(screen.getByLabelText('New yearly salary (INR)'))
    await user.click(screen.getByRole('button', { name: 'Save salary change' }))
    expect(screen.getByText('Enter the yearly salary.')).toBeInTheDocument()
    expect(screen.getByText('Choose a reason.')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends money as a string with the version and one idempotency key, reused on retry', async () => {
    let calls = 0
    const fetchMock = mockApi({
      'POST /employees/7/salaries': () => (++calls === 1 ? { status: 503, body: {} } : { status: 201, body: EMPLOYEE }),
    })
    const { user, onOpenChange } = setup()
    const amount = screen.getByLabelText('New yearly salary (INR)')
    await user.clear(amount)
    await user.type(amount, '2000000.50')
    await user.selectOptions(screen.getByLabelText('Reason'), 'promotion')

    await user.click(screen.getByRole('button', { name: 'Save salary change' }))
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await user.click(screen.getByRole('button', { name: 'Save salary change' }))
    await vi.waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))

    const [first, second] = fetchMock.mock.calls.map(([, init]) => init!)
    const key = (init: RequestInit) => (init.headers as Record<string, string>)['Idempotency-Key']
    expect(key(first)).toBeTruthy()
    expect(key(second)).toBe(key(first))
    expect(JSON.parse(second.body as string)).toMatchObject({
      version: 4,
      amount: '2000000.50',
      currency: 'INR',
      reason: 'promotion',
      note: null,
    })
  })

  it('shows server field errors next to the field', async () => {
    mockApi({
      'POST /employees/7/salaries': () => ({
        status: 422,
        body: { error: { code: 'invalid', message: 'Some fields are not valid.', details: { fields: { effective_date: 'Too far in the future.' } } } },
      }),
    })
    const { user } = setup()
    await user.selectOptions(screen.getByLabelText('Reason'), 'merit')
    await user.click(screen.getByRole('button', { name: 'Save salary change' }))
    expect(await screen.findByText('Too far in the future.')).toBeInTheDocument()
  })
})
