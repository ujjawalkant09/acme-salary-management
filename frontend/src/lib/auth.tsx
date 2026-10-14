import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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

/** The signed-in user, `null` when signed out, `undefined` while loading. */
export function useMe() {
  return useQuery({ queryKey: ME_KEY, queryFn: fetchMe, staleTime: Infinity })
}

/** For components inside the signed-in app shell, where the user is always known. */
export function useUser(): User {
  const { data } = useMe()
  if (!data) throw new Error('useUser must be used inside the signed-in app')
  return data
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
      client.clear()
      client.setQueryData(ME_KEY, null)
    },
  })
}
