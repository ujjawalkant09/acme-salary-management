import type { ReactNode } from 'react'

import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface FieldProps {
  id: string
  label: string
  /** Shown under the input; replaced by `error` when there is one. */
  hint?: ReactNode
  hintTone?: 'muted' | 'positive' | 'warn'
  error?: string
  className?: string
  children: ReactNode
}

export function Field({ id, label, hint, hintTone = 'muted', error, className, children }: FieldProps) {
  return (
    <div className={cn('mt-4 flex flex-col gap-1.5', className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <span id={`${id}-error`} className="text-sm text-error" role="alert">
          {error}
        </span>
      ) : (
        hint && (
          <span
            className={cn(
              'text-sm',
              hintTone === 'muted' && 'text-muted',
              hintTone === 'positive' && 'text-green',
              hintTone === 'warn' && 'text-amber',
            )}
          >
            {hint}
          </span>
        )
      )}
    </div>
  )
}
