import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return (
    <input
      className={cn(
        'h-9 w-full rounded-md border border-border bg-background px-3 placeholder:text-faint aria-invalid:border-error disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      className={cn(
        'min-h-16 w-full rounded-md border border-border bg-background px-3 py-2 placeholder:text-faint',
        className,
      )}
      {...props}
    />
  )
}

/** A native select styled like the inputs; enough for short option lists. */
export function NativeSelect({ className, ...props }: ComponentProps<'select'>) {
  return (
    <select
      className={cn(
        'h-9 w-full cursor-pointer appearance-none rounded-md border border-border bg-background bg-[url("data:image/svg+xml,%3Csvg%20xmlns=%27http://www.w3.org/2000/svg%27%20width=%2710%27%20height=%276%27%3E%3Cpath%20d=%27M1%201l4%204%204-4%27%20fill=%27none%27%20stroke=%27%236B6E7A%27%20stroke-width=%271.4%27/%3E%3C/svg%3E")] bg-[position:right_11px_center] bg-no-repeat pr-8 pl-3 aria-invalid:border-error',
        className,
      )}
      {...props}
    />
  )
}
