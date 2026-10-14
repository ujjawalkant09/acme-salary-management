import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

export function TableWrap({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('overflow-x-auto rounded-xl border border-border', className)} {...props} />
}

export function Table({ className, ...props }: ComponentProps<'table'>) {
  return <table className={cn('w-full border-collapse', className)} {...props} />
}

export function Th({ className, ...props }: ComponentProps<'th'>) {
  return (
    <th
      className={cn(
        'border-b border-border bg-subtle px-4 py-3 text-left text-sm font-medium whitespace-nowrap text-muted',
        className,
      )}
      {...props}
    />
  )
}

export function Td({ className, ...props }: ComponentProps<'td'>) {
  return (
    <td
      className={cn('border-b border-border px-4 py-3 whitespace-nowrap [tr:last-child_&]:border-b-0', className)}
      {...props}
    />
  )
}
