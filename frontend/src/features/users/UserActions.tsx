import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Icon } from '@/components/icons'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ResetPasswordDialog } from '@/features/users/ResetPasswordDialog'
import { api } from '@/lib/api'
import type { UserAccount } from '@/lib/types'

type DialogName = 'password' | 'disable' | 'delete' | null

interface Change {
  path: 'role' | 'active'
  body: object
  done: string
}

/** The menu of changes an HR Admin can make to another user's account. */
export function UserActions({ user }: { user: UserAccount }) {
  const client = useQueryClient()
  const [dialog, setDialog] = useState<DialogName>(null)
  const refresh = () => client.invalidateQueries({ queryKey: ['users'] })

  const change = useMutation({
    mutationFn: ({ path, body }: Change) => api<UserAccount>(`/users/${user.id}/${path}`, { method: 'PUT', body }),
    onSuccess: async (_, { done }) => {
      toast.success(done)
      setDialog(null)
      await refresh()
    },
  })
  const remove = useMutation({
    mutationFn: () => api<void>(`/users/${user.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      toast.success(`${user.name} was deleted`)
      setDialog(null)
      await refresh()
    },
  })

  const toAdmin = user.role === 'hr_viewer'
  const setOpen = (name: DialogName) => (open: boolean) => setDialog(open ? name : null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" aria-label={`Manage ${user.name}`}>
            Manage
            <Icon name="chevronDown" className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onSelect={() =>
              change.mutate({
                path: 'role',
                body: { role: toAdmin ? 'hr_admin' : 'hr_viewer' },
                done: `${user.name} is now an ${toAdmin ? 'HR Admin' : 'HR Viewer'}`,
              })
            }
          >
            {toAdmin ? 'Make HR Admin' : 'Make HR Viewer'}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setDialog('password')}>Reset password</DropdownMenuItem>
          {user.active ? (
            <DropdownMenuItem onSelect={() => setDialog('disable')}>Disable</DropdownMenuItem>
          ) : (
            <DropdownMenuItem
              onSelect={() => change.mutate({ path: 'active', body: { active: true }, done: `${user.name} can sign in again` })}
            >
              Enable
            </DropdownMenuItem>
          )}
          <DropdownMenuItem className="text-error" onSelect={() => setDialog('delete')}>
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ResetPasswordDialog user={user} open={dialog === 'password'} onOpenChange={setOpen('password')} />
      <ConfirmDialog
        open={dialog === 'disable'}
        onOpenChange={setOpen('disable')}
        title={`Disable ${user.name}?`}
        description="They are signed out at once and can't sign in until you enable the account again."
        action="Disable"
        pending={change.isPending}
        onConfirm={() => change.mutate({ path: 'active', body: { active: false }, done: `${user.name} was disabled` })}
      />
      <ConfirmDialog
        open={dialog === 'delete'}
        onOpenChange={setOpen('delete')}
        title={`Delete ${user.name}?`}
        description="Only an account that never changed any data can be deleted. Otherwise, disable it: the record of who changed what stays."
        action="Delete"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  )
}
