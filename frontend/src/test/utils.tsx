// Test helpers: a fake API (no network) and a renderer with the app's providers.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { vi } from 'vitest'

import { UserContext } from '@/lib/auth'
import { ME_KEY } from '@/lib/queryClient'
import { LocationProbe } from '@/test/LocationProbe'
import type { Meta, User } from '@/lib/types'

export const ADMIN: User = { id: 1, email: 'priya.sharma@acme.example', name: 'Priya Sharma', role: 'hr_admin' }
export const VIEWER: User = { id: 2, email: 'arjun.mehta@acme.example', name: 'Arjun Mehta', role: 'hr_viewer' }

export const META: Meta = {
  countries: [
    { code: 'IN', name: 'India', currency: 'INR' },
    { code: 'US', name: 'United States', currency: 'USD' },
  ],
  departments: [
    { id: 1, name: 'Engineering' },
    { id: 2, name: 'Finance' },
  ],
  job_titles: ['Software Engineer'],
  levels: [1, 2, 3, 4, 5, 6],
  employment_types: ['full_time', 'part_time', 'contractor'],
  genders: ['female', 'male', 'non_binary', 'undisclosed'],
  salary_reasons: ['hire', 'promotion', 'merit', 'market_adjustment', 'correction', 'other'],
  fx: { rates_date: '2026-10-13', source: 'ECB', usd_per_unit: { INR: '0.012', USD: '1' } },
  data_version: 1,
}

type Handler = (url: URL, init: RequestInit) => { status?: number; body?: unknown }

/** Replaces fetch. `routes` maps "METHOD /path" (no query string) to a response. */
export function mockApi(routes: Record<string, Handler | object>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), 'http://localhost')
    const key = `${init.method ?? 'GET'} ${url.pathname.replace('/api/v1', '')}`
    const route = routes[key]
    if (!route) return new Response(JSON.stringify({ error: { code: 'not_found', message: `No mock for ${key}` } }), { status: 404 })
    const { status = 200, body } = typeof route === 'function' ? (route as Handler)(url, init) : { body: route }
    return new Response(status === 204 ? null : JSON.stringify(body), { status })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function renderApp(ui: ReactElement, { user = ADMIN, route = '/', path = '*' } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  client.setQueryData(ME_KEY, user)
  client.setQueryData(['meta'], META)
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <UserContext value={user}>
          <MemoryRouter initialEntries={[route]}>
            <Routes>
              <Route path={path} element={ui} />
            </Routes>
            <LocationProbe />
          </MemoryRouter>
        </UserContext>
      </QueryClientProvider>,
    ),
  }
}
