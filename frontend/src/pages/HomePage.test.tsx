import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ImportJob, Summary } from '@/lib/types'
import { ADMIN, type ApiRoutes, mockApi, renderApp, VIEWER } from '@/test/utils'

import HomePage from './HomePage'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

const SUMMARY: Summary = {
  headcount: 9874,
  payroll_usd: '812400000',
  median_salary_usd: '64500',
  rates_date: '2026-10-13',
  outlier_count: 37,
  upcoming_changes_7d: 1,
  countries: 6,
}
const CHANGE = {
  id: 1, employee_id: 7, employee_name: 'Asha Verma', employee_code: 'ACM-004521', amount: '1840000.00',
  currency: 'INR', effective_date: '2026-04-01', reason: 'merit', created_by_name: 'Priya Sharma', created_at: '2026-04-01T09:00:00Z',
}
const WAITING = { id: 'j1', filename: 'october.xlsx', status: 'validated' } as ImportJob

function show(routes: ApiRoutes, user = ADMIN) {
  const fetchMock = mockApi({
    'GET /insights/summary': SUMMARY,
    'GET /salary-changes/recent': [CHANGE],
    'GET /imports': { items: [WAITING, { ...WAITING, id: 'j2', status: 'completed' }], page: 1, page_size: 10, total: 2, pages: 1 },
    ...routes,
  })
  renderApp(<HomePage />, { user })
  return fetchMock
}

describe('Home', () => {
  it('greets by first name and time of day, and shows the key numbers', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 14, 9, 30))
    show({})
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Good morning, Priya')
    expect(screen.getByText('Wednesday, 14 October 2026')).toBeInTheDocument()
    expect(await screen.findByText('9,874')).toBeInTheDocument()
    expect(screen.getByText('in 6 countries')).toBeInTheDocument()
    expect(screen.getByText('$812.4M')).toBeInTheDocument()
    expect(screen.getByText('in USD at ECB rates of 13 Oct 2026')).toBeInTheDocument()
    expect(screen.getByText('$64,500')).toBeInTheDocument()
  })

  it.each([
    [13, 'Good afternoon'],
    [19, 'Good evening'],
  ])('at %i:00 says %s', (hour, greeting) => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 14, hour))
    show({})
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(greeting)
  })

  it('lists what needs attention, with links where there is something to do', async () => {
    show({})
    const outliers = await screen.findByRole('link', { name: /37 people are paid outside the usual range/ })
    expect(outliers).toHaveAttribute('href', '/insights?tab=unusual')
    expect(screen.getByText('1 salary change starts in the next 7 days')).toBeInTheDocument()
    const review = await screen.findByRole('link', { name: /1 import is waiting for your review/ })
    expect(review).toHaveAttribute('href', '/imports')
    expect(within(review).getByText('october.xlsx')).toBeInTheDocument()
  })

  it('shows recent salary changes linking to the person', async () => {
    show({})
    const link = await screen.findByRole('link', { name: /Asha Verma/ })
    expect(link).toHaveAttribute('href', '/people/7')
    expect(link).toHaveTextContent('Merit, 1 Apr 2026, by Priya Sharma')
    expect(link).toHaveTextContent('₹18,40,000')
  })

  it('HR Viewers are not asked about imports', async () => {
    const fetchMock = show({}, VIEWER)
    await screen.findByText(/37 people are paid/)
    expect(screen.queryByText(/waiting for your review/)).toBeNull()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/imports'))).toBe(false)
  })

  it('says when everything is quiet', async () => {
    show({
      'GET /insights/summary': { ...SUMMARY, outlier_count: 0, upcoming_changes_7d: 0, rates_date: null },
      'GET /salary-changes/recent': [],
      'GET /imports': { items: [], page: 1, page_size: 10, total: 0, pages: 1 },
    })
    expect(await screen.findByText('Nothing needs your attention right now.')).toBeInTheDocument()
    expect(await screen.findByText('No salary changes yet.')).toBeInTheDocument()
    expect(screen.getByText('in USD')).toBeInTheDocument()
  })

  it('offers a retry when a part fails to load', async () => {
    let attempts = 0
    show({
      'GET /insights/summary': () => (++attempts === 1 ? { status: 500, body: { error: { message: 'Server error' } } } : { body: SUMMARY }),
      'GET /salary-changes/recent': () => ({ status: 500, body: { error: { message: 'History unavailable' } } }),
    })
    expect(await screen.findByText('Server error')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('9,874')).toBeInTheDocument()
    expect(await screen.findByText('History unavailable')).toBeInTheDocument() // the rest of the page still works
  })
})
