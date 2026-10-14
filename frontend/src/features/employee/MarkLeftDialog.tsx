import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Field } from '@/components/Field'
import { Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { todayIso } from '@/lib/format'
import { refreshData } from '@/lib/queryClient'
import type { Employee } from '@/lib/types'

interface Props {
  employee: Employee
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function MarkLeftDialog({ employee, open, onOpenChange }: Props) {
  const client = useQueryClient()
  const [leftOn, setLeftOn] = useState(todayIso)
  const name = `${employee.first_name} ${employee.last_name}`

  const markLeft = useMutation({
    mutationFn: () =>
      api<Employee>(`/employees/${employee.id}/mark-left`, {
        method: 'POST',
        body: { version: employee.version, left_on: leftOn },
      }),
    onSuccess: async () => {
      toast.success(`${name} marked as left`)
      onOpenChange(false)
      await refreshData(client)
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    if (leftOn) markLeft.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} noValidate>
          <DialogTitle>Mark {name} as left?</DialogTitle>
          <DialogDescription>
            Their record, salary history and documents are kept. You can undo this later.
          </DialogDescription>
          <Field id="left_on" label="Last day" error={leftOn ? undefined : 'Choose their last day.'}>
            <Input id="left_on" type="date" value={leftOn} onChange={(e) => setLeftOn(e.target.value)} />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" disabled={markLeft.isPending || !leftOn}>
              {markLeft.isPending && <Spinner />}
              Mark as left
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
