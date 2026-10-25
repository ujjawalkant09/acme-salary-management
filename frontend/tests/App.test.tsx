import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LocationProbe } from '@tests/support/LocationProbe'
import { ADMIN, META, mockApi, VIEWER } from '@tests/support/utils'

import App from '@/App'

afterEach(() => vi.unstubAllGlobals())

const HOME_ROUTES = {
  'GET /auth/me': ADMIN,
  'GET /meta': META,
  'GET /insights/summary': {
    headcount: 0, payroll_usd: '0', median_salary_usd: '0', rates_date: null, outlier_count: 0, upcoming_changes_7d: 0, countries: 0,
  },
  'GET /salary-changes/recent': [],
  'GET /imports': { items: [], page: 1, page_size: 10, total: 0, pages: 1 },
  'POST /auth/logout': () => ({ status: 204 }),
}

function show(route = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return client
}

describe('App', () => {
  it('shows sign-in when nobody is signed in', async () => {
    mockApi({ 'GET /auth/me': () => ({ status: 401, body: {} }) })
    show()
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('offers a retry when the server cannot be reached', async () => {
    let up = false
    mockApi({ 'GET /auth/me': () => (up ? { body: ADMIN } : { status: 503, body: {} }) })
    show()
    expect(await screen.findByText("Can't reach the server.")).toBeInTheDocument()
    up = true
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })

  it('sends unknown addresses to Home', async () => {
    mockApi(HOME_ROUTES)
    show('/no-such-page')
    expect(await screen.findByRole('heading', { name: /^Good (morning|afternoon|evening), Priya$/ })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/)
  })

  it('opens the Users page for HR Admins', async () => {
    mockApi({ ...HOME_ROUTES, 'GET /users': [] })
    show('/users')
    expect(await screen.findByText('Everyone who can sign in to ACME Pay.')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/users$/)
  })

  it('sends HR Viewers who open /users to Home', async () => {
    mockApi({ ...HOME_ROUTES, 'GET /auth/me': VIEWER })
    show('/users')
    expect(await screen.findByRole('heading', { name: /^Good (morning|afternoon|evening), Arjun$/ })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/)
  })

  it('signing out shows the sign-in page and forgets the data', async () => {
    mockApi(HOME_ROUTES)
    const client = show()
    const user = userEvent.setup()
    await user.click(await screen.findByText('Priya Sharma'))
    await user.click(await screen.findByRole('menuitem', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(client.getQueryData(['summary'])).toBeUndefined()
  })
})
