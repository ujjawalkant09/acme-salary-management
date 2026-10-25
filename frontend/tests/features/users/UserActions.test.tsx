import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { type ApiRoutes, mockApi, renderApp } from '@tests/support/utils'

import { UserActions } from '@/features/users/UserActions'
import type { UserAccount } from '@/lib/types'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const MEERA: UserAccount = {
  id: 5, email: 'meera.iyer@acme.example', name: 'Meera Iyer', role: 'hr_viewer', active: true,
  last_login_at: null, created_at: '2026-10-25T09:00:00Z',
}

async function choose(item: string, routes: ApiRoutes = {}, user: UserAccount = MEERA) {
  const fetchMock = mockApi(routes)
  const { client } = renderApp(<UserActions user={user} />)
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const success = vi.spyOn(toast, 'success')
  const events = userEvent.setup()
  await events.click(screen.getByRole('button', { name: 'Manage Meera Iyer' }))
  await events.click(await screen.findByRole('menuitem', { name: item }))
  return { fetchMock, invalidate, success, events }
}

const sent = (fetchMock: ReturnType<typeof mockApi>) => {
  const [url, init] = fetchMock.mock.calls.at(-1)!
  return { path: new URL(String(url), 'http://localhost').pathname, method: init!.method, body: init!.body && JSON.parse(init!.body as string) }
}

describe('Manage a user', () => {
  it('makes a viewer an HR Admin at once and reloads the list', async () => {
    const { fetchMock, invalidate, success } = await choose('Make HR Admin', { 'PUT /users/5/role': { ...MEERA, role: 'hr_admin' } })
    await vi.waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['users'] }))
    expect(sent(fetchMock)).toEqual({ path: '/api/v1/users/5/role', method: 'PUT', body: { role: 'hr_admin' } })
    expect(success).toHaveBeenCalledWith('Meera Iyer is now an HR Admin')
  })

  it('offers Make HR Viewer for an admin', async () => {
    const admin = { ...MEERA, role: 'hr_admin' as const }
    const { fetchMock } = await choose('Make HR Viewer', { 'PUT /users/5/role': MEERA }, admin)
    await vi.waitFor(() => expect(sent(fetchMock).body).toEqual({ role: 'hr_viewer' }))
  })

  it('asks before disabling, then disables', async () => {
    const { fetchMock, events } = await choose('Disable', { 'PUT /users/5/active': { ...MEERA, active: false } })
    expect(screen.getByText('Disable Meera Iyer?')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
    await events.click(screen.getByRole('button', { name: 'Disable' }))
    await vi.waitFor(() => expect(sent(fetchMock).body).toEqual({ active: false }))
    await vi.waitFor(() => expect(screen.queryByText('Disable Meera Iyer?')).toBeNull())
  })

  it('enables a disabled account without asking', async () => {
    const { fetchMock, success } = await choose('Enable', { 'PUT /users/5/active': MEERA }, { ...MEERA, active: false })
    await vi.waitFor(() => expect(sent(fetchMock).body).toEqual({ active: true }))
    await vi.waitFor(() => expect(success).toHaveBeenCalledWith('Meera Iyer can sign in again'))
  })

  it('asks before deleting, then deletes', async () => {
    const { fetchMock, events } = await choose('Delete', { 'DELETE /users/5': () => ({ status: 204 }) })
    expect(fetchMock).not.toHaveBeenCalled()
    await events.click(screen.getByRole('button', { name: 'Delete' }))
    await vi.waitFor(() => expect(sent(fetchMock)).toMatchObject({ path: '/api/v1/users/5', method: 'DELETE' }))
    await vi.waitFor(() => expect(screen.queryByText('Delete Meera Iyer?')).toBeNull())
  })

  it('cancelling a confirmation sends nothing', async () => {
    const { fetchMock, events } = await choose('Delete')
    await events.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByText('Delete Meera Iyer?')).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('opens the reset password form', async () => {
    await choose('Reset password')
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
  })
})
