import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LIST_ITEM } from '@/test/fixtures'
import { mockApi, renderApp } from '@/test/utils'

import PeoplePage from './PeoplePage'

afterEach(() => vi.unstubAllGlobals())

const facets = {
  status: { active: 120, left: 8 },
  country: { IN: 80, US: 40 },
  department_id: { '1': 90, '2': 30 },
  level: { '3': 50 },
  employment_type: { full_time: 110, part_time: 10 },
}

function setup(route = '/people') {
  const fetchMock = mockApi({
    'GET /employees': { items: [LIST_ITEM], page: 1, page_size: 20, total: 1, pages: 1 },
    'GET /employees/facets': facets,
  })
  renderApp(<PeoplePage />, { route })
  return { fetchMock, user: userEvent.setup() }
}

const location = () => screen.getByTestId('location').textContent
const calledWith = (fetchMock: ReturnType<typeof mockApi>, text: string) =>
  fetchMock.mock.calls.some(([url]) => String(url).includes(text))

describe('People', () => {
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
