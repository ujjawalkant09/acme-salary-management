import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { todayIso } from '@/lib/format'
import { EMPLOYEE } from '@tests/support/fixtures'
import { type ApiRoutes, mockApi, renderApp } from '@tests/support/utils'

import { MarkLeftDialog } from '@/features/employee/MarkLeftDialog'

afterEach(() => vi.unstubAllGlobals())

function setup(routes: ApiRoutes = {}) {
  const fetchMock = mockApi(routes)
  const onOpenChange = vi.fn()
  renderApp(<MarkLeftDialog employee={EMPLOYEE} open onOpenChange={onOpenChange} />)
  return { fetchMock, onOpenChange, user: userEvent.setup() }
}

describe('Mark as left', () => {
  it('defaults to today and sends the chosen day with the version', async () => {
    const { fetchMock, onOpenChange, user } = setup({ 'POST /employees/7/mark-left': { ...EMPLOYEE, status: 'left' } })
    expect(screen.getByRole('heading', { name: 'Mark Asha Verma as left?' })).toBeInTheDocument()
    const lastDay = screen.getByLabelText('Last day')
    expect(lastDay).toHaveValue(todayIso())
    await user.clear(lastDay)
    await user.type(lastDay, '2026-10-31')
    await user.click(screen.getByRole('button', { name: 'Mark as left' }))
    await vi.waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({ version: 4, left_on: '2026-10-31' })
  })

  it('needs a last day', async () => {
    const { fetchMock, user } = setup()
    await user.clear(screen.getByLabelText('Last day'))
    expect(screen.getByText('Choose their last day.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark as left' })).toBeDisabled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('Cancel closes without a change', async () => {
    const { fetchMock, onOpenChange, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
