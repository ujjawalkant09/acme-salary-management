import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EMPLOYEE } from '@/test/fixtures'
import { type ApiRoutes, META, mockApi, renderApp } from '@/test/utils'

import { EditEmployeeDialog } from './EditEmployeeDialog'

afterEach(() => vi.unstubAllGlobals())

function setup(routes: ApiRoutes = {}) {
  const fetchMock = mockApi(routes)
  const onOpenChange = vi.fn()
  renderApp(<EditEmployeeDialog employee={EMPLOYEE} meta={META} open onOpenChange={onOpenChange} />)
  return { fetchMock, onOpenChange, user: userEvent.setup() }
}

const save = () => screen.getByRole('button', { name: 'Save details' })

describe('Edit details', () => {
  it('starts from the current details', () => {
    setup()
    expect(screen.getByLabelText('First name')).toHaveValue('Asha')
    expect(screen.getByLabelText('Department')).toHaveValue('1')
    expect(screen.getByLabelText('City (optional)')).toHaveValue('Pune')
  })

  it('sends only what changed, with the version that was read', async () => {
    const { fetchMock, onOpenChange, user } = setup({ 'PATCH /employees/7': { ...EMPLOYEE, version: 5 } })
    await user.selectOptions(screen.getByLabelText('Level'), '4')
    await user.clear(screen.getByLabelText('City (optional)'))
    await user.click(save())
    await vi.waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({ version: 4, job_level: 4, city: null })
  })

  it('closes without a request when nothing changed', async () => {
    const { fetchMock, onOpenChange, user } = setup()
    await user.click(save())
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('checks the fields before sending', async () => {
    const { fetchMock, user } = setup()
    await user.clear(screen.getByLabelText('First name'))
    await user.selectOptions(screen.getByLabelText('Employment type'), 'part_time')
    await user.clear(screen.getByLabelText('Share of full time'))
    await user.type(screen.getByLabelText('Share of full time'), '2')
    await user.click(save())
    expect(screen.getByText('Enter the first name.')).toBeInTheDocument()
    expect(screen.getByText(/enter a share of full time between 0 and 1/)).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("shows the server's field errors", async () => {
    const { user } = setup({
      'PATCH /employees/7': () => ({
        status: 422,
        body: { error: { code: 'invalid', message: 'x', details: { fields: { hire_date: 'After the first salary entry' } } } },
      }),
    })
    await user.clear(screen.getByLabelText('Joined on'))
    await user.type(screen.getByLabelText('Joined on'), '2026-12-01')
    await user.click(save())
    expect(await screen.findByText('After the first salary entry')).toBeInTheDocument()
  })
})
