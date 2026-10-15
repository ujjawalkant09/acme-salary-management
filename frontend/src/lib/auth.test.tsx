import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from '@/App'
import { ADMIN, mockApi, renderApp } from '@/test/utils'

import { useLogout, useMe, UserContext, useUser } from './auth'
import { ME_KEY } from './queryClient'

afterEach(() => vi.unstubAllGlobals())

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { client, wrapper }
}

describe('the signed-in user', () => {
  it('is the user from /auth/me', async () => {
    mockApi({ 'GET /auth/me': ADMIN })
    const { result } = renderHook(useMe, setup())
    await waitFor(() => expect(result.current.data).toEqual(ADMIN))
  })

  it('is null when signed out', async () => {
    mockApi({ 'GET /auth/me': () => ({ status: 401, body: { error: { code: 'unauthorized', message: 'Please sign in.' } } }) })
    const { result } = renderHook(useMe, setup())
    await waitFor(() => expect(result.current.data).toBeNull())
  })

  it('is an error when the server is down, so the app can offer a retry', async () => {
    mockApi({ 'GET /auth/me': () => ({ status: 503, body: {} }) })
    const { result } = renderHook(useMe, setup())
    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it('useUser refuses to run outside the signed-in app', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { wrapper, client } = setup()
    client.setQueryData(ME_KEY, ADMIN) // even when signed in, only App provides the user
    expect(() => renderHook(useUser, { wrapper })).toThrow('useUser must be used inside the signed-in app')
  })

  it('useUser gives the user that App provides', () => {
    const wrapper = ({ children }: { children: ReactNode }) => <UserContext value={ADMIN}>{children}</UserContext>
    expect(renderHook(useUser, { wrapper }).result.current).toEqual(ADMIN)
  })

  it('signing out forgets all data, even if the request fails', async () => {
    mockApi({ 'POST /auth/logout': () => ({ status: 503, body: {} }) })
    const { client, wrapper } = setup()
    client.setQueryData(ME_KEY, ADMIN)
    client.setQueryData(['employee', 7], { secret: true })
    const { result } = renderHook(useLogout, { wrapper })
    result.current.mutate()
    await waitFor(() => expect(client.getQueryData(ME_KEY)).toBeNull())
    expect(client.getQueryData(['employee', 7])).toBeUndefined()
  })
})

describe('signing out', () => {
  it('shows the sign-in page and forgets the cached data', async () => {
    mockApi({ 'POST /auth/logout': { status: 204 } })
    const user = userEvent.setup()
    const { client } = renderApp(<App />)
    client.setQueryData(['employees', ''], { items: [] })

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Sign out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(client.getQueryData(ME_KEY)).toBeNull()
    expect(client.getQueryData(['employees', ''])).toBeUndefined()
  })
})
