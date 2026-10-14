import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { ApiError, errorMessage } from '@/lib/api'

export const ME_KEY = ['me'] as const

export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Client errors (404, 403, 422…) won't change on retry; only retry network/server errors.
        retry: (failures, error) =>
          failures < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
      },
    },
    queryCache: new QueryCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) client.setQueryData(ME_KEY, null)
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) {
          client.setQueryData(ME_KEY, null)
          return
        }
        // Field errors (422) are shown next to the fields by the form itself.
        if (error instanceof ApiError && error.status === 422) return
        toast.error(errorMessage(error))
      },
    }),
  })
  return client
}

/** After any change to employee data, everything derived from it (lists, Insights, Home) is refetched. */
export function refreshData(client: QueryClient): Promise<void> {
  return client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] })
}
