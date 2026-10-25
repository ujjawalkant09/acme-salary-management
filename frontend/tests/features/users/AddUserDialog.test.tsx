import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { type ApiRoutes, mockApi, renderApp } from '@tests/support/utils'

import { AddUserDialog } from '@/features/users/AddUserDialog'

afterEach(() => vi.unstubAllGlobals())

const MEERA = {
  id: 5, email: 'meera.iyer@acme.example', name: 'Meera Iyer', role: 'hr_admin', active: true,
  last_login_at: null, created_at: '2026-10-25T09:00:00Z',
}

async function open(routes: ApiRoutes = {}) {
  const fetchMock = mockApi(routes)
  renderApp(<AddUserDialog />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Add user' }))
  return { fetchMock, user }
}

async function fillIn(user: ReturnType<typeof userEvent.setup>, password = 'a-long-password') {
  await user.type(screen.getByLabelText('Name'), ' Meera Iyer ')
  await user.type(screen.getByLabelText('Work email'), ' meera.iyer@acme.example ')
  await user.selectOptions(screen.getByLabelText('Role'), 'hr_admin')
  await user.type(screen.getByLabelText('First password'), password)
}

const submit = () => screen.getAllByRole('button', { name: 'Add user' }).at(-1)!

describe('Add user', () => {
  it('explains every missing field instead of sending', async () => {
    const { fetchMock, user } = await open()
    await user.click(submit())
    for (const message of ['Enter their name.', 'Enter a work email like name@acme.example.', 'Use at least 8 characters.']) {
      expect(screen.getByText(message)).toBeInTheDocument()
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refuses a 7-character password and accepts 8', async () => {
    const { fetchMock, user } = await open({ 'POST /users': () => ({ status: 201, body: MEERA }) })
    await fillIn(user, '1234567')
    await user.click(submit())
    expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText('First password'), '8')
    await user.click(submit())
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
  })

  it('sends the trimmed user with one idempotency key, then closes', async () => {
    const { fetchMock, user } = await open({ 'POST /users': () => ({ status: 201, body: MEERA }) })
    await fillIn(user)
    await user.click(submit())

    await vi.waitFor(() => expect(screen.queryByLabelText('Name')).toBeNull())
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    expect((init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
    expect(JSON.parse(init!.body as string)).toEqual({
      name: 'Meera Iyer',
      email: 'meera.iyer@acme.example',
      role: 'hr_admin',
      password: 'a-long-password',
    })
  })

  it("shows the server's field errors next to the fields", async () => {
    const { user } = await open({
      'POST /users': () => ({
        status: 409,
        body: { error: { code: 'conflict', message: 'Someone already signs in with this email.', details: { fields: { email: 'Already used by another user' } } } },
      }),
    })
    await fillIn(user)
    await user.click(submit())
    expect(await screen.findByText('Already used by another user')).toBeInTheDocument()
  })

  it('Cancel closes without sending', async () => {
    const { fetchMock, user } = await open()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Name')).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
