// Form state, checks and API body for "Add employee" and "Edit details".
import type { Employee } from '@/lib/types'

export interface EmployeeForm {
  first_name: string
  last_name: string
  email: string
  job_title: string
  job_level: string
  department_id: string
  country_code: string
  city: string
  gender: string
  employment_type: string
  fte: string
  hire_date: string
}

export type FormErrors = Partial<Record<string, string>>

export const EMPTY_EMPLOYEE_FORM: EmployeeForm = {
  first_name: '',
  last_name: '',
  email: '',
  job_title: '',
  job_level: '',
  department_id: '',
  country_code: '',
  city: '',
  gender: '',
  employment_type: 'full_time',
  fte: '1',
  hire_date: '',
}

export function formFromEmployee(e: Employee): EmployeeForm {
  return {
    first_name: e.first_name,
    last_name: e.last_name,
    email: e.email,
    job_title: e.job_title,
    job_level: String(e.job_level),
    department_id: String(e.department_id),
    country_code: e.country_code,
    city: e.city ?? '',
    gender: e.gender ?? '',
    employment_type: e.employment_type,
    fte: String(Number(e.fte)),
    hire_date: e.hire_date,
  }
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const FTE = /^(0(\.\d{1,3})?|1(\.0{1,3})?)$/

export function validateEmployee(form: EmployeeForm): FormErrors {
  const errors: FormErrors = {}
  if (!form.first_name.trim()) errors.first_name = 'Enter the first name.'
  if (!form.last_name.trim()) errors.last_name = 'Enter the last name.'
  if (!EMAIL.test(form.email.trim())) errors.email = 'Enter a work email like name@acme.example.'
  if (!form.job_title.trim()) errors.job_title = 'Enter the job title.'
  if (!form.job_level) errors.job_level = 'Choose a level.'
  if (!form.department_id) errors.department_id = 'Choose a department.'
  if (!form.country_code) errors.country_code = 'Choose a country.'
  if (!form.hire_date) errors.hire_date = 'Choose the date they joined.'
  if (form.employment_type === 'part_time' && (!FTE.test(form.fte) || Number(form.fte) <= 0 || Number(form.fte) >= 1)) {
    errors.fte = 'For part-time, enter a share of full time between 0 and 1, like 0.5.'
  }
  return errors
}

/** The API body for the employee fields (money-free, so plain values). */
export function employeeBody(form: EmployeeForm) {
  return {
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    email: form.email.trim(),
    job_title: form.job_title.trim(),
    job_level: Number(form.job_level),
    department_id: Number(form.department_id),
    country_code: form.country_code,
    city: form.city.trim() || null,
    gender: form.gender || null,
    employment_type: form.employment_type,
    fte: form.employment_type === 'part_time' ? form.fte : '1',
    hire_date: form.hire_date,
  }
}
