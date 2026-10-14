// Shared loading, empty and error states.
import type { ReactNode } from 'react'

import { Icon } from '@/components/icons'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/api'

export function Spinner({ className = 'size-4' }: { className?: string }) {
  return <Icon name="spinner" className={`${className} animate-spin`} />
}

export function PageLoading() {
  return (
    <div className="flex min-h-40 items-center justify-center gap-2 p-10 text-muted" role="status">
      <Spinner /> Loading…
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-border px-5 py-10 text-center" role="alert">
      <p className="mb-3">{errorMessage(error)}</p>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-14 text-center">
      <h2 className="text-md font-semibold">{title}</h2>
      {children && <div className="mt-1 text-muted">{children}</div>}
    </div>
  )
}
