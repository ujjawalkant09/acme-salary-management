import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { parsePeopleParams, type PeopleParams } from '@/lib/peopleParams'
import { LIST_ITEM } from '@tests/support/fixtures'
import { META, renderApp } from '@tests/support/utils'

import { PeopleTable } from '@/features/people/PeopleTable'

function show(params: Partial<PeopleParams> = {}, rows = [LIST_ITEM]) {
  const onSort = vi.fn()
  const all = { ...parsePeopleParams(new URLSearchParams()), ...params }
  renderApp(<PeopleTable rows={rows} params={all} meta={META} onSort={onSort} />)
  return { onSort, user: userEvent.setup() }
}

const header = (name: string) => screen.getByRole('columnheader', { name: new RegExp(name) })

describe('PeopleTable cells', () => {
  it('shows a USD salary once, without a converted line', () => {
    show({}, [{ ...LIST_ITEM, current_currency: 'USD', current_salary: '64500.00', current_salary_usd: '64500.00' }])
    expect(screen.getByText('$64,500')).toBeInTheDocument()
    expect(screen.queryByText(/≈/)).toBeNull()
  })

  it('converts other currencies to USD and copes with no city', () => {
    show({}, [{ ...LIST_ITEM, city: null }])
    const row = screen.getAllByRole('row')[1]
    expect(within(row).getByText('≈ $22,080')).toBeInTheDocument()
    expect(within(row).getByText('India')).toBeInTheDocument()
    expect(within(row).queryByText('Pune')).toBeNull()
  })
})

describe('PeopleTable sorting', () => {
  it('sorts text columns A to Z and salary highest first on the first click', async () => {
    const { onSort, user } = show({ sort: 'name', order: 'asc' })
    await user.click(within(header('Role')).getByRole('button'))
    expect(onSort).toHaveBeenLastCalledWith('job_title', 'asc')
    await user.click(within(header('Yearly salary')).getByRole('button'))
    expect(onSort).toHaveBeenLastCalledWith('salary', 'desc')
  })

  it('flips the order of the column already sorted', async () => {
    const { onSort, user } = show({ sort: 'salary', order: 'desc' })
    expect(header('Yearly salary')).toHaveAttribute('aria-sort', 'descending')
    expect(header('Yearly salary')).toHaveTextContent('↓')
    expect(header('Employee')).toHaveAttribute('aria-sort', 'none')
    await user.click(within(header('Yearly salary')).getByRole('button'))
    expect(onSort).toHaveBeenLastCalledWith('salary', 'asc')
  })

  it('shows ascending order and flips it to descending', async () => {
    const { onSort, user } = show({ sort: 'country', order: 'asc' })
    expect(header('Location')).toHaveAttribute('aria-sort', 'ascending')
    expect(header('Location')).toHaveTextContent('↑')
    await user.click(within(header('Location')).getByRole('button'))
    expect(onSort).toHaveBeenLastCalledWith('country', 'desc')
  })
})
