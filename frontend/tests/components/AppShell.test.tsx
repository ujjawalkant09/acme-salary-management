import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ME_KEY } from '@/lib/queryClient'
import { ADMIN, mockApi, renderApp, VIEWER } from '@tests/support/utils'

import { AppShell } from '@/components/AppShell'

afterEach(() => vi.unstubAllGlobals())

describe('App shell', () => {
  it('shows who is signed in, with no Add employee in the shared header', () => {
    mockApi({})
    renderApp(<AppShell>page</AppShell>, { user: ADMIN })
    expect(screen.getByText('Priya Sharma')).toBeInTheDocument()
    expect(screen.getByText('HR Admin')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add employee' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/users')
  })

  it('hides Users from HR Viewers', () => {
    mockApi({})
    renderApp(<AppShell>page</AppShell>, { user: VIEWER })
    expect(screen.getByText('HR Viewer')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Users' })).toBeNull()
  })

  it('sends a header search to People and focuses search with /', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderApp(<AppShell>page</AppShell>)
    await user.keyboard('/')
    expect(screen.getByLabelText('Search people')).toHaveFocus()
    await user.keyboard('asha{Enter}')
    expect(screen.getByTestId('location')).toHaveTextContent('/people?q=asha')
  })
})

describe('App shell navigation', () => {
  it('names the page in the header', () => {
    mockApi({})
    renderApp(<AppShell>page</AppShell>, { route: '/people/7' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Employee')
  })

  it('names the Users page in the header', () => {
    mockApi({})
    renderApp(<AppShell>page</AppShell>, { route: '/users' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Users')
  })

  it('the phone menu opens, and closes on a link or a tap outside', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderApp(<AppShell>page</AppShell>)
    const menu = () => screen.getByRole('navigation', { name: 'Main' }).closest('aside')!
    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    expect(menu()).toHaveClass('translate-x-0')
    await user.click(screen.getByRole('link', { name: 'Insights' }))
    expect(menu()).toHaveClass('-translate-x-full')
    expect(screen.getByTestId('location')).toHaveTextContent('/insights')

    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    await user.click(menu().previousElementSibling as HTMLElement) // the dimmed backdrop
    expect(menu()).toHaveClass('-translate-x-full')
  })

  it('typing / inside a field types it instead of jumping to search', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderApp(<AppShell><input aria-label="Note" /></AppShell>)
    await user.type(screen.getByLabelText('Note'), 'a/b')
    expect(screen.getByLabelText('Note')).toHaveValue('a/b')
  })

  it('an empty header search opens People', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderApp(<AppShell>page</AppShell>)
    await user.type(screen.getByLabelText('Search people'), '   {Enter}')
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/people$/)
  })

  it('signs out from the user menu', async () => {
    const fetchMock = mockApi({ 'POST /auth/logout': () => ({ status: 204 }) })
    const user = userEvent.setup()
    const { client } = renderApp(<AppShell>page</AppShell>)
    await user.click(screen.getByText('Priya Sharma'))
    await user.click(await screen.findByRole('menuitem', { name: 'Sign out' }))
    await vi.waitFor(() => expect(client.getQueryData(ME_KEY)).toBeNull())
    expect(fetchMock.mock.calls[0][1]!.method).toBe('POST')
  })
})
