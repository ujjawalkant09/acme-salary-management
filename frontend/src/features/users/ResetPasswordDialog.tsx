import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Field } from '@/components/Field'
import { Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { passwordError } from '@/features/users/password'
import { api, ApiError } from '@/lib/api'
import type { UserAccount } from '@/lib/types'

interface Props {
  user: UserAccount
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ResetPasswordDialog({ user, open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <ResetPasswordForm user={user} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}

function ResetPasswordForm({ user, onDone }: { user: UserAccount; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const reset = useMutation({
    mutationFn: () => api<void>(`/users/${user.id}/password`, { method: 'PUT', body: { password } }),
    onSuccess: () => {
      toast.success(`${user.name}'s password was changed`)
      onDone()
    },
  })

  const local = passwordError(password)
  const server = reset.error instanceof ApiError ? reset.error.fields.password : undefined
  const error = (submitted && local) || server

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (!local) reset.mutate()
  }

  return (
    <form onSubmit={submit} noValidate>
      <DialogTitle>Reset {user.name}'s password?</DialogTitle>
      <DialogDescription>
        They are signed out everywhere and sign in with the new password. Share it with them privately.
      </DialogDescription>
      <Field id="new-password" label="New password" hint="At least 8 characters." error={error}>
        <Input
          id="new-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={reset.isPending}>
          {reset.isPending && <Spinner />} Reset password
        </Button>
      </DialogFooter>
    </form>
  )
}
