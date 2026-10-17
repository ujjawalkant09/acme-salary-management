import { describe, expect, it, vi } from 'vitest'

import { parsePeopleParams, type PeopleFilters } from '@/lib/peopleParams'
import { META } from '@tests/support/utils'

import { filterChips } from '@/features/people/filterChips'

function chipsFor(query: string) {
  const update = vi.fn<(changes: Partial<PeopleFilters>) => void>()
  const chips = filterChips(parsePeopleParams(new URLSearchParams(query)), META, update)
  return { chips, update, texts: chips.map((c) => c.text) }
}

describe('filter chips', () => {
  it('shows nothing for the default view', () => {
    expect(chipsFor('').chips).toEqual([])
  })

  it('names every active filter in plain words', () => {
    const { texts } = chipsFor(
      'outliers_only=true&status=left&country=IN&department_id=2&department_id=9&level=3&employment_type=part_time',
    )
    expect(texts).toEqual(['Unusual salaries', 'People who left', 'India', 'Finance', '9', 'Level 3', 'Part-time'])
    expect(chipsFor('status=all').texts).toEqual(['Everyone'])
  })

  it('shows a salary range with an open end', () => {
    expect(chipsFor('min_salary_usd=50000&max_salary_usd=120000').texts).toEqual(['$50K to $120K (USD)'])
    expect(chipsFor('min_salary_usd=50000').texts).toEqual(['$50K to any (USD)'])
    expect(chipsFor('max_salary_usd=120000').texts).toEqual(['Any to $120K (USD)'])
  })

  it('removing a chip clears only that filter', () => {
    const { chips, update } = chipsFor('outliers_only=true&status=left&country=IN&country=US&min_salary_usd=1')
    for (const chip of chips) chip.remove()
    expect(update.mock.calls.map(([changes]) => changes)).toEqual([
      { outliers_only: false },
      { status: 'active' },
      { country: ['US'] },
      { country: ['IN'] },
      { min_salary_usd: '', max_salary_usd: '' },
    ])
  })
})
