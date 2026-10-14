import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Field } from '@/components/Field'
import { Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Input, NativeSelect, Textarea } from '@/components/ui/input'
import { api, ApiError, newIdempotencyKey } from '@/lib/api'
import { label, money, signedPct, todayIso } from '@/lib/format'
import { refreshData } from '@/lib/queryClient'
import { amountError, changeHint, dateHint } from '@/lib/salary'
import type { Employee } from '@/lib/types'

const REASONS = ['merit', 'promotion', 'market_adjustment', 'correction', 'other'] as const

interface Props {
  employee: Employee
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ChangeSalaryDialog({ employee, open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* The form mounts per opening, so each opening gets fresh fields and a fresh idempotency key. */}
        <ChangeSalaryForm employee={employee} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}

function ChangeSalaryForm({ employee, onDone }: { employee: Employee; onDone: () => void }) {
  const client = useQueryClient()
  const currency = employee.current_currency
  const [idempotencyKey] = useState(newIdempotencyKey)
  const [amount, setAmount] = useState(employee.current_salary)
  const [effectiveDate, setEffectiveDate] = useState(todayIso)
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      api<Employee>(`/employees/${employee.id}/salaries`, {
        method: 'POST',
        idempotencyKey,
        body: {
          version: employee.version,
          amount: amount.trim(),
          currency,
          effective_date: effectiveDate,
          reason,
          note: note.trim() || null,
        },
      }),
    onSuccess: async () => {
      toast.success('Salary change saved')
      onDone()
      await refreshData(client)
    },
  })

  const serverFields = save.error instanceof ApiError ? save.error.fields : {}
  const errors = {
    amount: amountError(amount) ?? serverFields.amount,
    effective_date: (effectiveDate ? null : 'Choose the date the new salary starts.') ?? serverFields.effective_date,
    reason: (reason ? null : 'Choose a reason.') ?? serverFields.reason,
  }
  const hint = changeHint(employee.current_salary, amount)
  const when = dateHint(effectiveDate, todayIso())

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (errors.amount || errors.effective_date || errors.reason) return
    save.mutate()
  }

  return (
    <form onSubmit={submit} noValidate>
      <DialogTitle>Change salary</DialogTitle>
      <DialogDescription>
        {employee.first_name} {employee.last_name}, currently {money(employee.current_salary, currency)} a year
      </DialogDescription>

      <Field
        id="amount"
        label={`New yearly salary (${currency})`}
        error={submitted || save.isError ? (errors.amount ?? undefined) : undefined}
        hint={
          hint
            ? `${signedPct(hint.pct)}, ${money(Math.abs(hint.difference), currency)} ${hint.difference > 0 ? 'more' : 'less'} a year${hint.big ? ". That's a big change, so please double-check it." : ''}`
            : undefined
        }
        hintTone={hint?.big ? 'warn' : 'positive'}
      >
        <Input
          id="amount"
          inputMode="decimal"
          autoFocus
          onFocus={(e) => e.target.select()}
          value={amount}
          aria-invalid={submitted && !!errors.amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </Field>

      <Field
        id="effective_date"
        label="Starts on"
        error={submitted ? (errors.effective_date ?? undefined) : undefined}
        hint={when?.text}
        hintTone={when?.warn ? 'warn' : 'muted'}
      >
        <Input id="effective_date" type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
      </Field>

      <Field id="reason" label="Reason" error={submitted ? (errors.reason ?? undefined) : undefined}>
        <NativeSelect id="reason" value={reason} aria-invalid={submitted && !!errors.reason} onChange={(e) => setReason(e.target.value)}>
          <option value="">Choose a reason</option>
          {REASONS.map((r) => (
            <option key={r} value={r}>
              {label(r)}
            </option>
          ))}
        </NativeSelect>
      </Field>

      <Field id="note" label="Note (optional)">
        <Textarea id="note" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending && <Spinner />}
          Save salary change
        </Button>
      </DialogFooter>
    </form>
  )
}
