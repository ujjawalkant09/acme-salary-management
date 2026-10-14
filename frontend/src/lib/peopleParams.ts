// People list state lives in the URL, so the employee page's Back link and the browser's
// Back button return to exactly the same filters, sort and page.

export type StatusFilter = 'active' | 'left' | 'all'
export type SortKey = 'name' | 'salary' | 'hire_date' | 'country' | 'job_title' | 'code'

export interface PeopleFilters {
  q: string
  status: StatusFilter
  country: string[]
  department_id: string[]
  level: string[]
  employment_type: string[]
  min_salary_usd: string
  max_salary_usd: string
  outliers_only: boolean
}

export interface PeopleParams extends PeopleFilters {
  sort: SortKey
  order: 'asc' | 'desc'
  page: number
}

export type ListFilterKey = 'country' | 'department_id' | 'level' | 'employment_type'

const SORT_KEYS: SortKey[] = ['name', 'salary', 'hire_date', 'country', 'job_title', 'code']
const MONEY = /^\d+(\.\d{1,2})?$/

export function parsePeopleParams(search: URLSearchParams): PeopleParams {
  const status = search.get('status')
  const sort = search.get('sort') as SortKey | null
  const page = Number(search.get('page'))
  const money = (key: string) => {
    const value = search.get(key) ?? ''
    return MONEY.test(value) ? value : ''
  }
  return {
    q: search.get('q') ?? '',
    status: status === 'left' || status === 'all' ? status : 'active',
    country: search.getAll('country'),
    department_id: search.getAll('department_id'),
    level: search.getAll('level'),
    employment_type: search.getAll('employment_type'),
    min_salary_usd: money('min_salary_usd'),
    max_salary_usd: money('max_salary_usd'),
    outliers_only: search.get('outliers_only') === 'true',
    sort: sort && SORT_KEYS.includes(sort) ? sort : 'name',
    order: search.get('order') === 'desc' ? 'desc' : 'asc',
    page: Number.isInteger(page) && page > 0 ? page : 1,
  }
}

/** URL search params for the given state; defaults are left out to keep links short. */
export function toSearchParams(params: PeopleParams): URLSearchParams {
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.status !== 'active') search.set('status', params.status)
  for (const key of ['country', 'department_id', 'level', 'employment_type'] as const) {
    for (const value of params[key]) search.append(key, value)
  }
  if (params.min_salary_usd) search.set('min_salary_usd', params.min_salary_usd)
  if (params.max_salary_usd) search.set('max_salary_usd', params.max_salary_usd)
  if (params.outliers_only) search.set('outliers_only', 'true')
  if (params.sort !== 'name') search.set('sort', params.sort)
  if (params.order !== 'asc') search.set('order', params.order)
  if (params.page > 1) search.set('page', String(params.page))
  return search
}

/** The filter part only, for the facet counts and the CSV export. */
export function filterParams(params: PeopleParams): URLSearchParams {
  return toSearchParams({ ...params, sort: 'name', order: 'asc', page: 1 })
}

export const EMPTY_FILTERS: PeopleFilters = {
  q: '',
  status: 'active',
  country: [],
  department_id: [],
  level: [],
  employment_type: [],
  min_salary_usd: '',
  max_salary_usd: '',
  outliers_only: false,
}

/** How many filters are active (shown on the mobile "Filters (n)" button). */
export function activeFilterCount(f: PeopleFilters): number {
  return (
    (f.status !== 'active' ? 1 : 0) +
    f.country.length +
    f.department_id.length +
    f.level.length +
    f.employment_type.length +
    (f.min_salary_usd || f.max_salary_usd ? 1 : 0) +
    (f.outliers_only ? 1 : 0)
  )
}

export function toggle(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value]
}
