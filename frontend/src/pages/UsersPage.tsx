import { useQuery } from '@tanstack/react-query'

import { ErrorState, PageLoading } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Table, TableWrap, Td, Th } from '@/components/ui/table'
import { AddUserDialog } from '@/features/users/AddUserDialog'
import { UserActions } from '@/features/users/UserActions'
import { api } from '@/lib/api'
import { useUser } from '@/lib/auth'
import { formatDate } from '@/lib/format'
import type { UserAccount } from '@/lib/types'

const ROLE_LABEL = { hr_admin: 'HR Admin', hr_viewer: 'HR Viewer' } as const

export default function UsersPage() {
  const me = useUser()
  const users = useQuery({
    queryKey: ['users'],
    queryFn: ({ signal }) => api<UserAccount[]>('/users', { signal }),
  })

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <p className="flex-1 text-muted">Everyone who can sign in to ACME Pay.</p>
        <AddUserDialog />
      </div>
      {users.isError ? (
        <ErrorState error={users.error} onRetry={users.refetch} />
      ) : users.isPending ? (
        <PageLoading />
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Email</Th>
                <Th>Role</Th>
                <Th className="max-sm:hidden">Last sign-in</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <Td>{u.name}{u.id === me.id && <span className="text-muted"> (you)</span>}</Td>
                  <Td className="break-all">{u.email}</Td>
                  <Td><Badge variant={u.role === 'hr_admin' ? 'blue' : 'default'}>{ROLE_LABEL[u.role]}</Badge></Td>
                  <Td className="text-muted max-sm:hidden">{u.last_login_at ? formatDate(u.last_login_at) : 'Never'}</Td>
                  <Td>{u.active ? 'Active' : <Badge variant="warn">Disabled</Badge>}</Td>
                  {/* Nobody changes their own account here, so another admin always remains. */}
                  <Td className="text-right">{u.id !== me.id && <UserActions user={u} />}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
    </>
  )
}
