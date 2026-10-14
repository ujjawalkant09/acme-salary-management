import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { EmployeeFields } from '@/features/employee/EmployeeFields'
import {
  EMPTY_EMPLOYEE_FORM,
  employeeBody,
  validateEmployee,
  type EmployeeForm,
  type FormErrors,
} from '@/features/employee/employeeForm'
import { Field } from '@/components/Field'
import { Icon } from '@/components/icons'
import { PageLoading, Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { api, ApiError, newIdempotencyKey } from '@/lib/api'
import { currencyOf, useMeta } from '@/lib/meta'
import { refreshData } from '@/lib/queryClient'
import { amountError } from '@/lib/salary'
import type { Employee, Meta } from '@/lib/types'

export function AddEmployeeDialog() {
  const [open, setOpen] = useState(false)
  const meta = useMeta()
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button aria-label="Add employee">
          <Icon name="plus" />
          <span className="max-sm:hidden">Add employee</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[35rem]">
        {meta.data ? <AddEmployeeForm meta={meta.data} onDone={() => setOpen(false)} /> : <PageLoading />}
      </DialogContent>
    </Dialog>
  )
}

function AddEmployeeForm({ meta, onDone }: { meta: Meta; onDone: () => void }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [idempotencyKey] = useState(newIdempotencyKey)
  const [form, setForm] = useState<EmployeeForm>(EMPTY_EMPLOYEE_FORM)
  const [salary, setSalary] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const currency = currencyOf(meta, form.country_code)

  const create = useMutation({
    mutationFn: () =>
      api<Employee>('/employees', {
        method: 'POST',
        idempotencyKey,
        body: { ...employeeBody(form), salary: { amount: salary.trim(), currency } },
      }),
    onSuccess: async (employee) => {
      toast.success(`${employee.first_name} ${employee.last_name} added`)
      onDone()
      navigate(`/people/${employee.id}`)
      await refreshData(client)
    },
  })

  const local: FormErrors = { ...validateEmployee(form) }
  const salaryError = amountError(salary)
  if (salaryError) local['salary.amount'] = salaryError
  const server = create.error instanceof ApiError ? create.error.fields : {}
  const errors: FormErrors = submitted ? { ...server, ...local } : server

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (Object.keys(local).length === 0) create.mutate()
  }

  return (
    <form onSubmit={submit} noValidate>
      <DialogTitle>Add employee</DialogTitle>
      <DialogDescription>Their first salary entry is saved with the reason "Hire".</DialogDescription>
      <EmployeeFields form={form} onChange={(changes) => setForm({ ...form, ...changes })} meta={meta} errors={errors} />
      <Field
        id="salary"
        label={form.country_code ? `Yearly salary (${currency})` : 'Yearly salary'}
        hint="Starts on the joining date."
        error={errors['salary.amount']}
      >
        <Input id="salary" inputMode="decimal" value={salary} aria-invalid={!!errors['salary.amount']} onChange={(e) => setSalary(e.target.value)} />
      </Field>
      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending && <Spinner />}
          Add employee
        </Button>
      </DialogFooter>
    </form>
  )
}
