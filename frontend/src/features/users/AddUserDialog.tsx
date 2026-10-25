import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { Field } from '@/components/Field'
import { Icon } from '@/components/icons'
import { Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input, NativeSelect } from '@/components/ui/input'
import { passwordError } from '@/features/users/password'
import { api, ApiError, newIdempotencyKey } from '@/lib/api'
import type { Role, UserAccount } from '@/lib/types'

const ROLES: { value: Role; label: string }[] = [
  { value: 'hr_viewer', label: 'HR Viewer: can view everything, change nothing' },
  { value: 'hr_admin', label: 'HR Admin: can view and change everything' },
]

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function AddUserDialog() {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Icon name="plus" />
          Add user
        </Button>
      </DialogTrigger>
      <DialogContent>
        <AddUserForm onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  )
}

function AddUserForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient()
  const [idempotencyKey] = useState(newIdempotencyKey)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('hr_viewer')
  const [password, setPassword] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const create = useMutation({
    mutationFn: () =>
      api<UserAccount>('/users', {
        method: 'POST',
        idempotencyKey,
        body: { name: name.trim(), email: email.trim(), role, password },
      }),
    onSuccess: async (user) => {
      toast.success(`${user.name} can now sign in`)
      onDone()
      await client.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const local: Record<string, string> = {}
  if (!name.trim()) local.name = 'Enter their name.'
  if (!EMAIL.test(email.trim())) local.email = 'Enter a work email like name@acme.example.'
  const badPassword = passwordError(password)
  if (badPassword) local.password = badPassword
  const server = create.error instanceof ApiError ? create.error.fields : {}
  const errors = submitted ? { ...server, ...local } : server

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (Object.keys(local).length === 0) create.mutate()
  }

  return (
    <form onSubmit={submit} noValidate>
      <DialogTitle>Add user</DialogTitle>
      <DialogDescription>They sign in with this email and password. Share the password with them privately.</DialogDescription>
      <Field id="user-name" label="Name" error={errors.name}>
        <Input id="user-name" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field id="user-email" label="Work email" error={errors.email}>
        <Input id="user-email" type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field id="user-role" label="Role">
        <NativeSelect id="user-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field id="user-password" label="First password" hint="At least 8 characters." error={errors.password}>
        <Input
          id="user-password"
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
        <Button type="submit" disabled={create.isPending}>
          {create.isPending && <Spinner />} Add user
        </Button>
      </DialogFooter>
    </form>
  )
}
