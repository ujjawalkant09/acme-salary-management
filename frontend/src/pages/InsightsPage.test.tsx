import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { GroupStats, Outlier } from '@/lib/types'
import { type ApiRoutes, mockApi, renderApp } from '@/test/utils'

import InsightsPage from './InsightsPage'

beforeEach(() => {
  // Recharts measures its container; jsdom has no layout.
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
})
afterEach(() => vi.unstubAllGlobals())

function group(key: string, label: string, people: number, extra: Partial<GroupStats> = {}): GroupStats {
  return {
    key, label, people, currency: 'USD', cost: '1000000', min: '50000', p25: '60000', median: '70000', p75: '80000',
    max: '90000', median_usd: '70000', cost_usd: '1000000', job_level: null, outliers: 0, ...extra,
  }
}

const BY_COUNTRY = {
  rates_date: '2026-10-13',
  groups: [
    group('US', 'United States', 120),
    group('IN', 'India', 4210, { currency: 'INR', median: '1700000', min: '900000', p25: '1400000', p75: '2000000', max: '3000000' }),
  ],
}
const BY_DEPARTMENT = { rates_date: '2026-10-13', groups: [group('Finance', 'Finance', 50), group('Gone', 'Gone', 2)] }
const BY_ROLE = {
  rates_date: '2026-10-13',
  groups: [group('Software Engineer|3', 'Software Engineer', 14, { currency: 'INR', job_level: 3, outliers: 2 })],
}
const DISTRIBUTION = {
  currency: 'INR',
  bins: [
    { start: '1000000', end: '1500000', count: 3 },
    { start: '1500000', end: '2000000', count: 9 },
    { start: '2000000', end: '2500000', count: 2 },
  ],
}
const OUTLIER: Outlier = {
  employee_id: 7, employee_code: 'ACM-004521', name: 'Asha Verma', job_title: 'Software Engineer', job_level: 3,
  country_code: 'IN', department: 'Engineering', salary: '3000000', currency: 'INR', peer_median: '1700000',
  peer_count: 14, diff_from_median_pct: '76.5', direction: 'above',
}

function show(route = '/insights', routes: ApiRoutes = {}) {
  const fetchMock = mockApi({
    'GET /insights/by-country': BY_COUNTRY,
    'GET /insights/by-department': BY_DEPARTMENT,
    'GET /insights/by-role': BY_ROLE,
    'GET /insights/distribution': DISTRIBUTION,
    'GET /insights/outliers': { items: [OUTLIER], page: 1, page_size: 20, total: 1, pages: 1 },
    ...routes,
  })
  renderApp(<InsightsPage />, { route })
  return { fetchMock, user: userEvent.setup() }
}

const requested = (fetchMock: ReturnType<typeof mockApi>) => fetchMock.mock.calls.map(([url]) => String(url))

describe('Insights overview', () => {
  it('compares countries, largest first, with links to the people', async () => {
    show()
    expect(screen.getByText(/European Central Bank rates of 13 Oct 2026/)).toBeInTheDocument()
    const rows = (await screen.findAllByRole('row')).slice(1)
    expect(rows.map((r) => within(r).getAllByRole('cell')[0].textContent)).toEqual(['India', 'United States'])
    expect(within(rows[0]).getByRole('link', { name: '4,210' })).toHaveAttribute('href', '/people?country=IN')
    expect(within(rows[0]).getByText('₹17,00,000')).toBeInTheDocument() // median in local currency
  })

  it('switches to departments', async () => {
    const { fetchMock, user } = show()
    await screen.findByText('India')
    await user.click(screen.getByRole('radio', { name: 'Department' }))
    expect(await screen.findByRole('link', { name: '50' })).toHaveAttribute('href', '/people?department_id=2')
    expect(screen.getByRole('link', { name: '2' })).toHaveAttribute('href', '/people') // not a known department
    expect(screen.queryByText('Median (local)')).toBeNull()
    expect(requested(fetchMock)).toContain('/api/v1/insights/by-department')
  })

  it('says when there is nobody to compare', async () => {
    show('/insights', { 'GET /insights/by-country': { rates_date: null, groups: [] } })
    expect(await screen.findByText('No current employees yet.')).toBeInTheDocument()
  })

  it('shows a load error with a retry', async () => {
    show('/insights', { 'GET /insights/by-country': () => ({ status: 500, body: { error: { message: 'Stats are down' } } }) })
    expect(await screen.findByText('Stats are down')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('an unknown tab in the link opens the overview, and tabs update the link', async () => {
    const { user } = show('/insights?tab=nonsense')
    expect(await screen.findByText('India')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'By role' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/insights?tab=role')
  })
})

describe('Insights by role', () => {
  it('shows each role with its range, unusual count and the salary spread', async () => {
    show('/insights?tab=role')
    expect(await screen.findByText('2 unusual')).toBeInTheDocument()
    expect(screen.getByText('L3')).toBeInTheDocument()
    expect(screen.getByText('Amounts in INR')).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: '14 salaries from ₹10,00,000 to ₹25,00,000' })).toBeInTheDocument()
  })

  it('reloads for another country', async () => {
    const { fetchMock, user } = show('/insights?tab=role')
    await screen.findByText('2 unusual')
    await user.selectOptions(screen.getByLabelText('Country'), 'US')
    await vi.waitFor(() => expect(requested(fetchMock)).toContain('/api/v1/insights/by-role?country=US'))
    expect(requested(fetchMock)).toContain('/api/v1/insights/distribution?country=US&bins=20')
  })

  it('says when a country has nobody or no salaries', async () => {
    show('/insights?tab=role', {
      'GET /insights/by-role': { rates_date: null, groups: [] },
      'GET /insights/distribution': { currency: 'INR', bins: [{ start: '0', end: '1', count: 0 }] },
    })
    expect(await screen.findByText('No current employees in this country.')).toBeInTheDocument()
    expect(await screen.findByText('No salaries to show.')).toBeInTheDocument()
  })
})

describe('Unusual salaries', () => {
  it('lists people paid outside the usual range and opens them', async () => {
    const { user } = show('/insights?tab=unusual')
    expect(await screen.findByText('1 person is paid outside the usual range')).toBeInTheDocument()
    expect(screen.getByText('+77%')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open in People' })).toHaveAttribute('href', '/people?outliers_only=true')
    await user.click(screen.getByText('Asha Verma'))
    expect(screen.getByTestId('location')).toHaveTextContent('/people/7')
  })

  it('opens a person with the keyboard too', async () => {
    const { user } = show('/insights?tab=unusual')
    const row = (await screen.findByText('Asha Verma')).closest('tr')!
    row.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByTestId('location')).toHaveTextContent('/people/7')
  })

  it('filters by country and pages through the list', async () => {
    const { fetchMock, user } = show('/insights?tab=unusual', {
      'GET /insights/outliers': (url: URL) => ({
        body: { items: [OUTLIER], page: Number(url.searchParams.get('page')), page_size: 20, total: 45, pages: 3 },
      }),
    })
    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Country'), 'IN')
    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument() // a new filter starts on page 1
    expect(requested(fetchMock)).toContain('/api/v1/insights/outliers?page=1&page_size=20&country=IN')
    expect(screen.getByRole('link', { name: 'Open in People' })).toHaveAttribute('href', '/people?outliers_only=true&country=IN')
  })

  it('says when nobody stands out', async () => {
    show('/insights?tab=unusual', { 'GET /insights/outliers': { items: [], page: 1, page_size: 20, total: 0, pages: 1 } })
    expect(await screen.findByText('No one is paid outside the usual range.')).toBeInTheDocument()
  })
})
