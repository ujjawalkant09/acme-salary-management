import { describe, expect, it } from 'vitest'

import { activeFilterCount, EMPTY_FILTERS, filterParams, parsePeopleParams, toSearchParams, toggle } from '@/lib/peopleParams'

describe('people URL state', () => {
  it('uses sensible defaults for an empty URL', () => {
    expect(parsePeopleParams(new URLSearchParams())).toEqual({
      ...EMPTY_FILTERS,
      sort: 'name',
      order: 'asc',
      page: 1,
    })
  })

  it('round-trips every filter, sort and page through the URL', () => {
    const url = 'q=asha&status=all&country=IN&country=US&department_id=3&level=2&employment_type=part_time' +
      '&min_salary_usd=50000&max_salary_usd=90000.50&outliers_only=true&sort=salary&order=desc&page=3'
    const params = parsePeopleParams(new URLSearchParams(url))
    expect(params.country).toEqual(['IN', 'US'])
    expect(params.page).toBe(3)
    expect(toSearchParams(params).toString()).toBe(url)
  })

  it('ignores invalid values instead of sending them to the API', () => {
    const params = parsePeopleParams(new URLSearchParams('status=gone&sort=drop&page=-2&min_salary_usd=abc&order=sideways'))
    expect(params.status).toBe('active')
    expect(params.sort).toBe('name')
    expect(params.order).toBe('asc')
    expect(params.page).toBe(1)
    expect(params.min_salary_usd).toBe('')
  })

  it('leaves defaults out of the URL and keeps sort and page out of the filter query', () => {
    const params = parsePeopleParams(new URLSearchParams('country=IN&sort=salary&page=4'))
    expect(toSearchParams({ ...params, country: [] }).toString()).toBe('sort=salary&page=4')
    expect(filterParams(params).toString()).toBe('country=IN')
  })

  it('counts active filters and toggles values', () => {
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0)
    expect(activeFilterCount({ ...EMPTY_FILTERS, country: ['IN', 'US'], min_salary_usd: '1', max_salary_usd: '2', status: 'left' })).toBe(4)
    expect(toggle(['IN'], 'US')).toEqual(['IN', 'US'])
    expect(toggle(['IN', 'US'], 'IN')).toEqual(['US'])
  })
})
