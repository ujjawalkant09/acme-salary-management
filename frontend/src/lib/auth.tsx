import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext } from 'react'

import { api, ApiError } from '@/lib/api'
import { ME_KEY } from '@/lib/queryClient'
import type { User } from '@/lib/types'

async function fetchMe(): Promise<User | null> {
  try {
    return await api<User>('/auth/me')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

/** The signed-in user, `null` when signed out, `undefined` while loading. Only App reads it. */
export function useMe() {
  return useQuery({ queryKey: ME_KEY, queryFn: fetchMe, staleTime: Infinity })
}

// App hands the user to the signed-in app through context instead of every component reading
// `useMe`: on sign-out, App switches to the sign-in page before anything inside sees no user.
export const UserContext = createContext<User | null>(null)

/** For components inside the signed-in app shell, where the user is always known. */
export function useUser(): User {
  const user = useContext(UserContext)
  if (!user) throw new Error('useUser must be used inside the signed-in app')
  return user
}

export function useIsAdmin(): boolean {
  return useUser().role === 'hr_admin'
}

export function useLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<User>('/auth/login', { method: 'POST', body }),
    onSuccess: (user) => client.setQueryData(ME_KEY, user),
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api<void>('/auth/logout', { method: 'POST' }),
    onSettled: () => {
      // Set on the query App is watching (clearing the cache first would detach App from it),
      // then forget everything else this session loaded.
      client.setQueryData(ME_KEY, null)
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] })
      client.getMutationCache().clear()
    },
  })
}
