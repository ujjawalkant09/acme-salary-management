import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { Meta } from '@/lib/types'

/** Countries, departments, titles and the rates in use. Changes rarely. */
export function useMeta() {
  return useQuery({ queryKey: ['meta'], queryFn: () => api<Meta>('/meta'), staleTime: 5 * 60_000 })
}

export function countryName(meta: Meta | undefined, code: string): string {
  return meta?.countries.find((c) => c.code === code)?.name ?? code
}

export function currencyOf(meta: Meta | undefined, code: string): string {
  return meta?.countries.find((c) => c.code === code)?.currency ?? 'USD'
}
