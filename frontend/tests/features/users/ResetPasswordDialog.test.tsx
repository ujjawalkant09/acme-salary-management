import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { afterEach, expect, it, vi } from 'vitest'

import { type ApiRoutes, mockApi, renderApp } from '@tests/support/utils'

import { ResetPasswordDialog } from '@/features/users/ResetPasswordDialog'
import type { UserAccount } from '@/lib/types'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const MEERA: UserAccount = {
  id: 5, email: 'meera.iyer@acme.example', name: 'Meera Iyer', role: 'hr_viewer', active: true,
  last_login_at: null, created_at: null,
}

function open(routes: ApiRoutes = {}) {
  const fetchMock = mockApi(routes)
  const onOpenChange = vi.fn()
  renderApp(<ResetPasswordDialog user={MEERA} open onOpenChange={onOpenChange} />)
  return { fetchMock, onOpenChange, user: userEvent.setup() }
}

it('refuses a short password without sending', async () => {
  const { fetchMock, user } = open()
  await user.type(screen.getByLabelText('New password'), '1234567')
  await user.click(screen.getByRole('button', { name: 'Reset password' }))
  expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('sends the new password and closes', async () => {
  const success = vi.spyOn(toast, 'success')
  const { fetchMock, onOpenChange, user } = open({ 'PUT /users/5/password': () => ({ status: 204 }) })
  await user.type(screen.getByLabelText('New password'), 'a-new-password')
  await user.click(screen.getByRole('button', { name: 'Reset password' }))
  await vi.waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  const [, init] = fetchMock.mock.calls[0]
  expect(init!.method).toBe('PUT')
  expect(JSON.parse(init!.body as string)).toEqual({ password: 'a-new-password' })
  expect(success).toHaveBeenCalledWith("Meera Iyer's password was changed")
})

it("shows the server's password error next to the field", async () => {
  const { user } = open({
    'PUT /users/5/password': () => ({
      status: 422,
      body: { error: { code: 'invalid', message: 'Some fields are not valid.', details: { fields: { password: 'Too weak' } } } },
    }),
  })
  await user.type(screen.getByLabelText('New password'), 'a-new-password')
  await user.click(screen.getByRole('button', { name: 'Reset password' }))
  expect(await screen.findByText('Too weak')).toBeInTheDocument()
})
