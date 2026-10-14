import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { api, ApiError } from '@/lib/api'
import { refreshData } from '@/lib/queryClient'
import type { Employee, Meta } from '@/lib/types'

import { EmployeeFields } from './EmployeeFields'
import { employeeBody, formFromEmployee, validateEmployee, type EmployeeForm } from './employeeForm'

interface Props {
  employee: Employee
  meta: Meta
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditEmployeeDialog({ employee, meta, open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[35rem]">
        <EditForm employee={employee} meta={meta} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}

function EditForm({ employee, meta, onDone }: { employee: Employee; meta: Meta; onDone: () => void }) {
  const client = useQueryClient()
  const [form, setForm] = useState<EmployeeForm>(() => formFromEmployee(employee))
  const [submitted, setSubmitted] = useState(false)

  // PATCH sends only what changed, plus the version that was read.
  const before = employeeBody(formFromEmployee(employee))
  const after = employeeBody(form)
  const changes = Object.fromEntries(
    Object.entries(after).filter(([key, value]) => before[key as keyof typeof before] !== value),
  )

  const save = useMutation({
    mutationFn: () =>
      api<Employee>(`/employees/${employee.id}`, { method: 'PATCH', body: { version: employee.version, ...changes } }),
    onSuccess: async () => {
      toast.success('Details saved')
      onDone()
      await refreshData(client)
    },
  })

  const local = validateEmployee(form)
  const server = save.error instanceof ApiError ? save.error.fields : {}
  const errors = submitted ? { ...server, ...local } : server

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (Object.keys(local).length > 0) return
    if (Object.keys(changes).length === 0) {
      onDone()
      return
    }
    save.mutate()
  }

  return (
    <form onSubmit={submit} noValidate>
      <DialogTitle>Edit details</DialogTitle>
      <EmployeeFields form={form} onChange={(c) => setForm({ ...form, ...c })} meta={meta} errors={errors} />
      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending && <Spinner />}
          Save details
        </Button>
      </DialogFooter>
    </form>
  )
}
