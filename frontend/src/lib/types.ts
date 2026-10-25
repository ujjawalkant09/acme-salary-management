// Shapes returned by the API (backend/app/schemas.py). Money and FTE are decimal strings.

export type Money = string
export type Role = 'hr_admin' | 'hr_viewer'
export type EmploymentType = 'full_time' | 'part_time' | 'contractor'
export type EmployeeStatus = 'active' | 'left'
export type Gender = 'female' | 'male' | 'non_binary' | 'undisclosed'
export type SalaryReason =
  | 'hire'
  | 'promotion'
  | 'merit'
  | 'market_adjustment'
  | 'correction'
  | 'other'

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

export interface User {
  id: number
  email: string
  name: string
  role: Role
}

export interface Country {
  code: string
  name: string
  currency: string
}

export interface Department {
  id: number
  name: string
}

export interface FxRates {
  rates_date: string | null
  source: string | null
  usd_per_unit: Record<string, string>
}

export interface Meta {
  countries: Country[]
  departments: Department[]
  job_titles: string[]
  levels: number[]
  employment_types: EmploymentType[]
  genders: Gender[]
  salary_reasons: SalaryReason[]
  fx: FxRates
  data_version: number
}

export interface EmployeeListItem {
  id: number
  employee_code: string
  first_name: string
  last_name: string
  email: string
  job_title: string
  job_level: number
  department_id: number
  department: string
  country_code: string
  city: string | null
  employment_type: EmploymentType
  fte: string
  status: EmployeeStatus
  current_salary: Money
  current_currency: string
  current_salary_usd: Money
}

export interface PeerStats {
  count: number
  currency: string
  min: Money
  p25: Money
  median: Money
  p75: Money
  max: Money
  employee_value: Money
  diff_from_median_pct: string
  is_outlier: boolean
}

export interface Employee extends EmployeeListItem {
  gender: Gender | null
  hire_date: string
  left_on: string | null
  salary_effective_date: string
  version: number
  photo_url: string | null
  created_at: string
  updated_at: string
  updated_by_name: string | null
  rates_date: string | null
  upcoming_salary: { amount: Money; currency: string; effective_date: string } | null
  peers: PeerStats | null
}

export interface Facets {
  status: Record<string, number>
  country: Record<string, number>
  department_id: Record<string, number>
  level: Record<string, number>
  employment_type: Record<string, number>
}

export interface SalaryRecord {
  id: number
  amount: Money
  currency: string
  effective_date: string
  reason: SalaryReason
  note: string | null
  change_pct: string | null
  created_by_name: string | null
  created_at: string
  from_import: boolean
  is_future: boolean
}

export interface RecentSalaryChange {
  id: number
  employee_id: number
  employee_name: string
  employee_code: string
  amount: Money
  currency: string
  effective_date: string
  reason: SalaryReason
  created_by_name: string | null
  created_at: string
}

export interface EmployeeDocument {
  id: number
  file_name: string
  content_type: string
  size_bytes: number
  uploaded_by_name: string
  uploaded_at: string
}

export interface Summary {
  headcount: number
  payroll_usd: Money
  median_salary_usd: Money
  rates_date: string | null
  outlier_count: number
  upcoming_changes_7d: number
  countries: number
}

export interface GroupStats {
  key: string
  label: string
  people: number
  currency: string
  cost: Money
  min: Money
  p25: Money
  median: Money
  p75: Money
  max: Money
  median_usd?: Money | null
  cost_usd?: Money | null
  job_level?: number | null
  outliers: number
}

export interface GroupStatsOut {
  rates_date: string | null
  groups: GroupStats[]
}

export interface Distribution {
  currency: string
  bins: { start: Money; end: Money; count: number }[]
}

export interface Outlier {
  employee_id: number
  employee_code: string
  name: string
  job_title: string
  job_level: number
  country_code: string
  department: string
  salary: Money
  currency: string
  peer_median: Money
  peer_count: number
  diff_from_median_pct: string
  direction: 'above' | 'below'
}

export type ImportStatus =
  | 'queued'
  | 'validating'
  | 'validated'
  | 'commit_queued'
  | 'committing'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type ImportMode = 'all_or_nothing' | 'valid_rows_only'

export interface ImportJob {
  id: string
  filename: string
  status: ImportStatus
  mode: ImportMode
  total_rows: number
  processed_rows: number
  create_count: number
  update_count: number
  unchanged_count: number
  error_count: number
  created_count: number
  updated_count: number
  error_message: string | null
  created_by_name: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  already_imported_at: string | null
}

export interface ImportRow {
  row_number: number
  employee_code: string | null
  action: 'create' | 'update' | 'unchanged' | 'error'
  payload: Record<string, unknown>
  errors: { field: string; message: string }[]
}

export interface UserAccount {
  id: number
  email: string
  name: string
  role: Role
  active: boolean
  last_login_at: string | null
  created_at: string | null
}
