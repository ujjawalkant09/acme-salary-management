import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LIST_ITEM } from '@tests/support/fixtures'
import { ADMIN, type ApiRoutes, META, mockApi, renderApp, VIEWER } from '@tests/support/utils'

import PeoplePage from '@/pages/PeoplePage'

afterEach(() => vi.unstubAllGlobals())

const facets = {
  status: { active: 120, left: 8 },
  country: { IN: 80, US: 40 },
  department_id: { '1': 90, '2': 30 },
  level: { '3': 50 },
  employment_type: { full_time: 110, part_time: 10 },
}

function setup(route = '/people', routes: ApiRoutes = {}, user = ADMIN) {
  const fetchMock = mockApi({
    'GET /employees': { items: [LIST_ITEM], page: 1, page_size: 20, total: 1, pages: 1 },
    'GET /employees/facets': facets,
    ...routes,
  })
  const { client } = renderApp(<PeoplePage />, { route, user })
  return { fetchMock, client, user: userEvent.setup() }
}

const location = () => screen.getByTestId('location').textContent
const calledWith = (fetchMock: ReturnType<typeof mockApi>, text: string) =>
  fetchMock.mock.calls.some(([url]) => String(url).includes(text))

describe('People', () => {
  it('offers Add employee to HR Admins', async () => {
    setup()
    expect(await screen.findByRole('button', { name: 'Add employee' })).toBeInTheDocument()
  })

  it('hides Add employee from HR Viewers', async () => {
    setup('/people', {}, VIEWER)
    await screen.findByText('Asha Verma')
    expect(screen.queryByRole('button', { name: 'Add employee' })).toBeNull()
  })

  it('lists people with counts on every filter option', async () => {
    setup()
    expect(await screen.findByText('Asha Verma')).toBeInTheDocument()
    expect(screen.getByText('1 person')).toBeInTheDocument()
    const panel = screen.getByRole('complementary', { name: 'Filters' })
    const india = within(panel).getByText('India').closest('label')!
    expect(india).toHaveTextContent('80')
  })

  it('applies a filter to the URL and the request, and shows it as a removable chip', async () => {
    const { fetchMock, user } = setup()
    await screen.findByText('Asha Verma')
    await user.click(screen.getByRole('checkbox', { name: /India/ }))
    expect(location()).toBe('/people?country=IN')
    await vi.waitFor(() => expect(calledWith(fetchMock, '/employees?country=IN')).toBe(true))
    expect(calledWith(fetchMock, '/employees/facets?country=IN')).toBe(true)

    await user.click(screen.getByRole('button', { name: 'Remove filter India' }))
    expect(location()).toBe('/people')
  })

  it('restores filters, sort and page from the URL (Back from an employee)', async () => {
    const { fetchMock } = setup('/people?department_id=2&level=3&sort=salary&order=desc&page=2')
    await screen.findByText('Asha Verma')
    expect(calledWith(fetchMock, '/employees?department_id=2&level=3&sort=salary&order=desc&page=2')).toBe(true)
    expect(screen.getByRole('button', { name: 'Remove filter Finance' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove filter Level 3' })).toBeInTheDocument()
  })

  it('searches after typing pauses and resets to page 1', async () => {
    const { user } = setup('/people?page=3')
    await screen.findByText('Asha Verma')
    await user.type(screen.getByLabelText('Search people'), 'asha')
    await vi.waitFor(() => expect(location()).toBe('/people?q=asha'))
  })

  it('sorts by salary, highest first, from the column header', async () => {
    const { user } = setup()
    await screen.findByText('Asha Verma')
    await user.click(screen.getByRole('button', { name: 'Yearly salary' }))
    expect(location()).toBe('/people?sort=salary&order=desc')
  })

  it('opens the employee page from a row', async () => {
    const { user } = setup('/people?country=IN')
    await user.click(await screen.findByText('Asha Verma'))
    expect(location()).toBe('/people/7')
  })
})

const ASHA_AND_RAVI = {
  items: [LIST_ITEM, { ...LIST_ITEM, id: 8, first_name: 'Ravi', last_name: 'Kumar', employee_code: 'ACM-004522' }],
  page: 1, page_size: 20, total: 45, pages: 3,
}

describe('People filters', () => {
  it('status, level, unusual salaries and clear all', async () => {
    const { user } = setup()
    await screen.findByText('Asha Verma')
    expect(screen.getByRole('radio', { name: /Everyone/ }).closest('label')).toHaveTextContent('128')
    await user.click(screen.getByRole('radio', { name: /People who left/ }))
    expect(location()).toBe('/people?status=left')
    await user.click(screen.getByRole('button', { name: 'Level 3, 50 people' }))
    expect(location()).toBe('/people?status=left&level=3')
    expect(screen.getByRole('button', { name: 'Level 3, 50 people' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('checkbox', { name: 'Only people paid outside the usual range' }))
    expect(location()).toBe('/people?status=left&level=3&outliers_only=true')
    await user.click(screen.getByRole('button', { name: 'Clear all' }))
    expect(location()).toBe('/people')
  })

  it('a salary range takes whole numbers only, after typing pauses', async () => {
    const { user } = setup()
    await screen.findByText('Asha Verma')
    const min = screen.getByLabelText('Minimum salary in USD')
    await user.type(min, '50k000')
    expect(min).toHaveValue('50000')
    await vi.waitFor(() => expect(location()).toBe('/people?min_salary_usd=50000'))
    await user.type(screen.getByLabelText('Maximum salary in USD'), '90000')
    await vi.waitFor(() => expect(location()).toBe('/people?min_salary_usd=50000&max_salary_usd=90000'))
  })

  it('shows the five biggest countries first, the rest on request', async () => {
    const { client, user } = setup()
    const countries = ['IN', 'US', 'CA', 'SG', 'BR', 'AU'].map((code) => ({ code, name: `Country ${code}`, currency: 'USD' }))
    act(() => client.setQueryData(['meta'], { ...META, countries }))
    await screen.findByText('Asha Verma')
    expect(screen.queryByText('Country AU')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Show 1 more' }))
    expect(screen.getByText('Country AU')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show fewer' }))
    expect(screen.queryByText('Country AU')).toBeNull()
  })

  it('the filter panel starts hidden, can be shown and hidden again, and opens as a drawer on phones', async () => {
    const { user } = setup('/people?country=IN&level=3')
    await screen.findByText('Asha Verma')
    const panel = screen.getByRole('complementary', { name: 'Filters' })
    expect(panel).toHaveClass('md:hidden')
    expect(screen.getByRole('button', { name: 'Show filters' })).toHaveAttribute('aria-pressed', 'false')
    await user.click(screen.getByRole('button', { name: 'Show filters' }))
    expect(panel).not.toHaveClass('md:hidden')
    await user.click(screen.getByRole('button', { name: 'Hide filters' }))
    expect(panel).toHaveClass('md:hidden')
    await user.click(screen.getByRole('button', { name: 'Filters (2)' }))
    expect(screen.getByRole('complementary', { name: 'Filters' })).not.toHaveClass('max-md:hidden')
    await user.click(screen.getByRole('button', { name: 'Close filters' }))
    expect(screen.getByRole('complementary', { name: 'Filters' })).toHaveClass('max-md:hidden')
  })
})

describe('People results', () => {
  it('says when no one matches and offers to clear the filters', async () => {
    const { user } = setup('/people?country=US', { 'GET /employees': { items: [], page: 1, page_size: 20, total: 0, pages: 0 } })
    expect(await screen.findByText('No one matches')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear all filters' }))
    expect(location()).toBe('/people')
  })

  it('shows a load error with a retry', async () => {
    setup('/people', { 'GET /employees': () => ({ status: 500, body: { error: { message: 'List is down' } } }) })
    expect(await screen.findByText('List is down')).toBeInTheDocument()
  })

  it('shows a reference-data load error with a retry', async () => {
    const { client } = setup('/people', { 'GET /meta': () => ({ status: 500, body: { error: { message: 'Meta is down' } } }) })
    await act(() => client.resetQueries({ queryKey: ['meta'] }))
    expect(await screen.findByText('Meta is down')).toBeInTheDocument()
  })

  it('pages through the results, keeping the filters', async () => {
    const { user } = setup('/people?country=IN', { 'GET /employees': ASHA_AND_RAVI })
    expect(await screen.findByText('1–20 of 45')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(location()).toBe('/people?country=IN&page=2')
  })

  it('rows can be moved through and opened with the keyboard', async () => {
    const { user } = setup('/people', { 'GET /employees': ASHA_AND_RAVI })
    const asha = (await screen.findByText('Asha Verma')).closest('tr')!
    const ravi = screen.getByText('Ravi Kumar').closest('tr')!
    asha.focus()
    await user.keyboard('{ArrowDown}')
    expect(ravi).toHaveFocus()
    await user.keyboard('{ArrowUp}')
    expect(asha).toHaveFocus()
    await user.keyboard('{ArrowDown}{Enter}')
    expect(location()).toBe('/people/8')
  })
})
