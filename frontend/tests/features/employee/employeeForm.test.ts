import { describe, expect, it } from 'vitest'

import { EMPLOYEE } from '@tests/support/fixtures'

import { EMPTY_EMPLOYEE_FORM, employeeBody, formFromEmployee, validateEmployee, type EmployeeForm } from '@/features/employee/employeeForm'

const FILLED: EmployeeForm = { ...formFromEmployee(EMPLOYEE), gender: 'female' }

describe('employee form', () => {
  it('fills the form from an employee, with blanks for missing optional values', () => {
    expect(formFromEmployee({ ...EMPLOYEE, city: null, fte: '0.500' })).toMatchObject({
      job_level: '3',
      department_id: '1',
      city: '',
      gender: '',
      fte: '0.5',
      hire_date: '2022-04-01',
    })
  })

  it('names every missing required field', () => {
    expect(Object.keys(validateEmployee(EMPTY_EMPLOYEE_FORM)).sort()).toEqual([
      'country_code', 'department_id', 'email', 'first_name', 'hire_date', 'job_level', 'job_title', 'last_name',
    ])
    expect(validateEmployee(FILLED)).toEqual({})
  })

  it.each(['asha', 'asha@acme', 'a sha@acme.example'])('rejects the email %s', (email) => {
    expect(validateEmployee({ ...FILLED, email }).email).toBeTruthy()
  })

  it.each([
    ['0.5', false],
    ['0.125', false],
    ['0', true],
    ['1', true],
    ['1.5', true],
    ['0.1234', true],
    ['half', true],
  ])('part-time share %s is invalid: %s', (fte, invalid) => {
    expect(!!validateEmployee({ ...FILLED, employment_type: 'part_time', fte }).fte).toBe(invalid)
  })

  it('ignores the share for full-time and contractors', () => {
    expect(validateEmployee({ ...FILLED, employment_type: 'contractor', fte: 'half' })).toEqual({})
  })

  it('builds the API body: trimmed text, numbers, nulls for blanks, full time unless part-time', () => {
    const body = employeeBody({ ...FILLED, first_name: '  Asha ', city: '  ', gender: '', fte: '0.5' })
    expect(body).toMatchObject({ first_name: 'Asha', job_level: 3, department_id: 1, city: null, gender: null, fte: '1' })
    expect(employeeBody({ ...FILLED, employment_type: 'part_time', fte: '0.5' }).fte).toBe('0.5')
  })
})
