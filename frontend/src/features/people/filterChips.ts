import { label, usd } from '@/lib/format'
import { countryName } from '@/lib/meta'
import type { PeopleFilters } from '@/lib/peopleParams'
import type { Meta } from '@/lib/types'

interface Chip {
  key: string
  text: string
  remove: () => void
}

/** Active filters repeated above the table as removable chips, so they're never missed. */
export function filterChips(
  f: PeopleFilters,
  meta: Meta,
  update: (changes: Partial<PeopleFilters>) => void,
): Chip[] {
  const chips: Chip[] = []
  if (f.outliers_only) {
    chips.push({ key: 'outliers', text: 'Unusual salaries', remove: () => update({ outliers_only: false }) })
  }
  if (f.status !== 'active') {
    chips.push({
      key: 'status',
      text: f.status === 'left' ? 'People who left' : 'Everyone',
      remove: () => update({ status: 'active' }),
    })
  }
  const listChip = (key: 'country' | 'department_id' | 'level' | 'employment_type', text: (v: string) => string) =>
    f[key].forEach((value) =>
      chips.push({
        key: `${key}:${value}`,
        text: text(value),
        remove: () => update({ [key]: f[key].filter((v) => v !== value) }),
      }),
    )
  listChip('country', (v) => countryName(meta, v))
  listChip('department_id', (v) => meta.departments.find((d) => String(d.id) === v)?.name ?? v)
  listChip('level', (v) => `Level ${v}`)
  listChip('employment_type', label)
  if (f.min_salary_usd || f.max_salary_usd) {
    const min = f.min_salary_usd ? usd(f.min_salary_usd, true) : 'Any'
    const max = f.max_salary_usd ? usd(f.max_salary_usd, true) : 'any'
    chips.push({
      key: 'salary',
      text: `${min} to ${max} (USD)`,
      remove: () => update({ min_salary_usd: '', max_salary_usd: '' }),
    })
  }
  return chips
}
