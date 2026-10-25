import { screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ADMIN, mockApi, renderApp } from '@tests/support/utils'

import UsersPage from '@/pages/UsersPage'
import type { UserAccount } from '@/lib/types'

afterEach(() => vi.unstubAllGlobals())

const USERS: UserAccount[] = [
  { ...ADMIN, active: true, last_login_at: '2026-10-20T09:00:00Z', created_at: null },
  {
    id: 5, email: 'meera.iyer@acme.example', name: 'Meera Iyer', role: 'hr_viewer', active: true,
    last_login_at: null, created_at: '2026-10-25T09:00:00Z',
  },
]

it('lists everyone who can sign in, marking you and who never signed in', async () => {
  mockApi({ 'GET /users': USERS })
  renderApp(<UsersPage />, { route: '/users' })
  const meera = (await screen.findByText('Meera Iyer')).closest('tr')!
  expect(within(meera).getByText('HR Viewer')).toBeInTheDocument()
  expect(within(meera).getByText('Never')).toBeInTheDocument()
  const me = screen.getByText('Priya Sharma').closest('tr')!
  expect(within(me).getByText('(you)')).toBeInTheDocument()
  expect(within(me).getByText('HR Admin')).toBeInTheDocument()
  expect(within(me).queryByText('Never')).toBeNull()
})

it('shows who is disabled, and offers Manage on everyone but you', async () => {
  mockApi({ 'GET /users': [USERS[0], { ...USERS[1], active: false }] })
  renderApp(<UsersPage />, { route: '/users' })
  const meera = (await screen.findByText('Meera Iyer')).closest('tr')!
  expect(screen.getByRole('columnheader', { name: 'Actions' }).querySelector('.sr-only')).toBeNull() // shown, not only read out
  expect(within(meera).getByText('Disabled')).toBeInTheDocument()
  expect(within(meera).getByRole('button', { name: 'Manage Meera Iyer' })).toBeInTheDocument()
  const me = screen.getByText('Priya Sharma').closest('tr')!
  expect(within(me).getByText('Active')).toBeInTheDocument()
  expect(within(me).queryByRole('button', { name: /Manage/ })).toBeNull()
})

it('shows an error with a retry when loading fails', async () => {
  mockApi({ 'GET /users': () => ({ status: 500, body: { error: { code: 'server_error', message: 'Boom' } } }) })
  renderApp(<UsersPage />, { route: '/users' })
  expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument()
})
