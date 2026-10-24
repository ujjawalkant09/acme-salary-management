import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { mockApi, renderApp } from '@tests/support/utils'

import ChangesPage from '@/pages/ChangesPage'

afterEach(() => vi.unstubAllGlobals())

const CHANGE = {
  id: 1, employee_id: 7, employee_name: 'Asha Rao', employee_code: 'ACM-000007', amount: '1200000.00',
  currency: 'INR', effective_date: '2026-10-01', reason: 'merit', created_by_name: 'Priya Sharma', created_at: '2026-10-01',
}

/** Answers with the page the request asked for, out of `total` changes. */
function mockChanges(total: number) {
  return mockApi({
    'GET /salary-changes': (url) => {
      const page = Number(url.searchParams.get('page'))
      const name = `Person ${page}`
      return { body: { items: total ? [{ ...CHANGE, id: page, employee_name: name }] : [], page, page_size: 50, total, pages: Math.max(1, Math.ceil(total / 50)) } }
    },
  })
}

it('lists salary changes with a link to each person', async () => {
  mockChanges(1)
  renderApp(<ChangesPage />, { route: '/changes' })
  expect(await screen.findByRole('link', { name: 'Person 1' })).toHaveAttribute('href', '/people/7')
  expect(screen.getByText('1–1 of 1')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
})

it('Next and Previous load the other pages', async () => {
  const fetchMock = mockChanges(120)
  const user = userEvent.setup()
  renderApp(<ChangesPage />, { route: '/changes' })
  await screen.findByRole('link', { name: 'Person 1' })

  await user.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByRole('link', { name: 'Person 2' })).toBeInTheDocument()
  expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
  expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain('/salary-changes?page=2&page_size=50')

  await user.click(screen.getByRole('button', { name: 'Previous' }))
  expect(await screen.findByRole('link', { name: 'Person 1' })).toBeInTheDocument()
})

it('opens the page in the URL, and treats a bad page number as page 1', async () => {
  mockChanges(120)
  renderApp(<ChangesPage />, { route: '/changes?page=3' })
  expect(await screen.findByRole('link', { name: 'Person 3' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  vi.unstubAllGlobals()

  mockChanges(120)
  renderApp(<ChangesPage />, { route: '/changes?page=abc' })
  expect(await screen.findByRole('link', { name: 'Person 1' })).toBeInTheDocument()
})

it('shows an empty state when there are no salary changes', async () => {
  mockChanges(0)
  renderApp(<ChangesPage />, { route: '/changes' })
  expect(await screen.findByText('No salary changes')).toBeInTheDocument()
})

it('a page past the end offers a way back to the first page', async () => {
  mockApi({ 'GET /salary-changes': { items: [], page: 999, page_size: 50, total: 120, pages: 3 } })
  renderApp(<ChangesPage />, { route: '/changes?page=999' })
  expect(await screen.findByText('This page is empty')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Go to the first page' })).toHaveAttribute('href', '/changes')
})

it('shows an error with a retry when loading fails', async () => {
  mockApi({ 'GET /salary-changes': () => ({ status: 500, body: { error: { code: 'server_error', message: 'Boom' } } }) })
  renderApp(<ChangesPage />, { route: '/changes' })
  expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument()
})
